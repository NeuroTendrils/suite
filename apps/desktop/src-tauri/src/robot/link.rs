//! Transports to the RoArm-M2-S: USB serial (115200 baud, newline-terminated JSON)
//! and Wi-Fi HTTP (`GET http://<ip>/js?json=<cmd>`), both as documented by Waveshare.

use serde::Serialize;
use serde_json::Value;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::time::{Duration, Instant};

#[derive(Debug, Clone, PartialEq)]
pub enum LinkError {
    /// The connection itself failed (unplugged, Wi-Fi dropped, timeout).
    Io(String),
    /// The device answered, but not the way RoArm-M2-S firmware does.
    Protocol(String),
}

impl std::fmt::Display for LinkError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LinkError::Io(m) => write!(f, "connection error: {m}"),
            LinkError::Protocol(m) => write!(f, "unexpected reply: {m}"),
        }
    }
}

/// How sure we are that the firmware received a command.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Delivery {
    /// Serial: the firmware echoed the command line. HTTP: the firmware answered 200.
    Confirmed,
    /// Bytes were written but no acknowledgement arrived in time.
    Unconfirmed,
}

pub trait Link: Send {
    fn describe(&self) -> String;
    fn send(&mut self, cmd: &Value) -> Result<Delivery, LinkError>;
    /// Send `{"T":105}` and return the `T:1051` reply.
    fn feedback(&mut self) -> Result<Value, LinkError>;
    /// True once if the firmware's boot banner was seen since the last call
    /// (the board rebooted, which also runs its power-on move to the init pose).
    fn take_boot_notice(&mut self) -> bool {
        false
    }
    /// An independent handle used only for emergency stop, so it never waits on
    /// a feedback read in progress on this link.
    fn estop_handle(&self) -> Option<Box<dyn EStopSender>>;
    /// After an E-stop went out on the dedicated handle: did the firmware acknowledge it?
    /// `None` when this transport cannot tell.
    fn confirm_estop(&mut self) -> Option<bool> {
        None
    }
}

pub trait EStopSender: Send {
    fn send_estop(&mut self) -> Result<(), String>;
}

/// Lines the official firmware prints while booting (RoArm-M2_example.ino `setup()`).
const BOOT_MARKERS: [&str; 3] = ["RoArm-M2 started", "Moving BASE_JOINT to initPos", "ServoCtrl init"];

fn same_json(line: &str, cmd: &Value) -> bool {
    serde_json::from_str::<Value>(line).map(|v| &v == cmd).unwrap_or(false)
}

// ── USB serial ────────────────────────────────────────────────────────────────

pub struct SerialLink {
    path: String,
    reader: BufReader<Box<dyn serialport::SerialPort>>,
    writer: Box<dyn serialport::SerialPort>,
    estop_writer: Option<Box<dyn serialport::SerialPort>>,
    boot_seen: bool,
}

const SERIAL_READ_TIMEOUT: Duration = Duration::from_millis(40);
const ECHO_TIMEOUT: Duration = Duration::from_millis(300);
const FEEDBACK_TIMEOUT: Duration = Duration::from_millis(450);

impl SerialLink {
    pub fn open(path: &str) -> Result<Self, LinkError> {
        let mut port = serialport::new(path, 115_200).timeout(SERIAL_READ_TIMEOUT).open().map_err(|e| {
            let busy = matches!(e.kind(), serialport::ErrorKind::NoDevice)
                || e.to_string().to_lowercase().contains("busy");
            LinkError::Io(if busy {
                format!("cannot open {path}: it is in use by another program (close any serial monitor) or was unplugged ({e})")
            } else {
                format!("cannot open {path}: {e}")
            })
        })?;
        // macOS asserts DTR and RTS while opening the port. The ESP32's auto-reset circuit
        // resets the board when RTS is asserted while DTR is not, so release RTS first, then
        // DTR (same order as Waveshare's serial demo). This lowers, but cannot rule out, the
        // chance that opening the port reboots the arm — and every boot runs its start-pose move.
        let _ = port.write_request_to_send(false);
        let _ = port.write_data_terminal_ready(false);
        Self::from_port(path, port)
    }

    /// Wrap an already-open port (also used by tests with a pseudo-terminal).
    pub fn from_port(path: &str, port: Box<dyn serialport::SerialPort>) -> Result<Self, LinkError> {
        let writer = port.try_clone().map_err(|e| LinkError::Io(e.to_string()))?;
        let estop_writer = port.try_clone().ok();
        Ok(Self {
            path: path.to_string(),
            reader: BufReader::new(port),
            writer,
            estop_writer,
            boot_seen: false,
        })
    }

    /// Discard replies left over from an earlier request (e.g. a feedback line that arrived
    /// after its timeout) so they cannot be mistaken for the answer to the next one.
    /// Boot banners in the discarded text are still noticed.
    fn drain(&mut self) -> Result<(), LinkError> {
        let mut stale = String::from_utf8_lossy(self.reader.buffer()).into_owned();
        let n = self.reader.buffer().len();
        self.reader.consume(n);
        let pending = self.reader.get_ref().bytes_to_read().unwrap_or(0) as usize;
        if pending > 0 {
            let mut buf = vec![0u8; pending];
            let got = self.reader.get_mut().read(&mut buf).unwrap_or(0);
            stale.push_str(&String::from_utf8_lossy(&buf[..got]));
        }
        if BOOT_MARKERS.iter().any(|m| stale.contains(m)) {
            self.boot_seen = true;
        }
        Ok(())
    }

    fn write_line(&mut self, cmd: &Value) -> Result<(), LinkError> {
        let line = format!("{cmd}\n");
        self.writer
            .write_all(line.as_bytes())
            .and_then(|_| self.writer.flush())
            .map_err(|e| LinkError::Io(format!("write to {}: {e}", self.path)))
    }

    /// Read lines until `want` accepts one or `timeout` passes.
    fn read_until(
        &mut self,
        timeout: Duration,
        mut want: impl FnMut(&str) -> bool,
    ) -> Result<Option<String>, LinkError> {
        let deadline = Instant::now() + timeout;
        let mut line = String::new();
        while Instant::now() < deadline {
            match self.reader.read_line(&mut line) {
                Ok(0) => return Err(LinkError::Io(format!("{} closed", self.path))),
                Ok(_) if line.ends_with('\n') => {
                    let text = line.trim().to_string();
                    line.clear();
                    if BOOT_MARKERS.iter().any(|m| text.contains(m)) {
                        self.boot_seen = true;
                    }
                    if want(&text) {
                        return Ok(Some(text));
                    }
                }
                Ok(_) => {}
                Err(e) if e.kind() == std::io::ErrorKind::TimedOut => {}
                Err(e) => return Err(LinkError::Io(format!("read from {}: {e}", self.path))),
            }
        }
        Ok(None)
    }
}

impl Link for SerialLink {
    fn describe(&self) -> String {
        format!("USB serial {}", self.path)
    }

    fn send(&mut self, cmd: &Value) -> Result<Delivery, LinkError> {
        self.drain()?;
        self.write_line(cmd)?;
        // The stock firmware (InfoPrint = 1) echoes each JSON line it parses.
        let echoed = self.read_until(ECHO_TIMEOUT, |l| same_json(l, cmd))?;
        Ok(if echoed.is_some() { Delivery::Confirmed } else { Delivery::Unconfirmed })
    }

    fn feedback(&mut self) -> Result<Value, LinkError> {
        self.drain()?;
        self.write_line(&super::protocol::feedback_cmd())?;
        let reply = self.read_until(FEEDBACK_TIMEOUT, |l| {
            serde_json::from_str::<Value>(l)
                .ok()
                .and_then(|v| v.get("T").and_then(Value::as_i64))
                == Some(super::protocol::FEEDBACK_REPLY_T)
        })?;
        match reply {
            Some(l) => serde_json::from_str(&l).map_err(|e| LinkError::Protocol(e.to_string())),
            None => Err(LinkError::Io("no feedback reply within 450 ms".into())),
        }
    }

    fn take_boot_notice(&mut self) -> bool {
        std::mem::take(&mut self.boot_seen)
    }

    fn estop_handle(&self) -> Option<Box<dyn EStopSender>> {
        self.estop_writer
            .as_ref()
            .and_then(|p| p.try_clone().ok())
            .map(|port| Box::new(SerialEStop { port }) as Box<dyn EStopSender>)
    }

    fn confirm_estop(&mut self) -> Option<bool> {
        // The firmware echoes the line before running the stop (which then blocks it ~10 s).
        let cmd = super::protocol::estop_cmd();
        Some(matches!(self.read_until(ECHO_TIMEOUT, |l| same_json(l, &cmd)), Ok(Some(_))))
    }
}

struct SerialEStop {
    port: Box<dyn serialport::SerialPort>,
}

impl EStopSender for SerialEStop {
    fn send_estop(&mut self) -> Result<(), String> {
        // Lead with a newline: if a heartbeat line was being written on the other handle,
        // this terminates it so the stop still arrives as a complete line of its own.
        let line = format!("\n{}\n", super::protocol::estop_cmd());
        self.port
            .write_all(line.as_bytes())
            .and_then(|_| self.port.flush())
            .map_err(|e| e.to_string())
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct PortInfo {
    pub path: String,
    pub description: String,
    /// USB bridge chip commonly used on Waveshare ESP32 boards (CP210x or CH34x).
    pub likely_roarm: bool,
}

pub fn list_serial_ports() -> Result<Vec<PortInfo>, String> {
    let ports = serialport::available_ports().map_err(|e| e.to_string())?;
    let mut out: Vec<PortInfo> = ports
        .into_iter()
        // macOS lists each device twice; the call-out (cu.*) node is the one to open.
        .filter(|p| !p.port_name.starts_with("/dev/tty."))
        .map(|p| {
            let (description, likely) = match &p.port_type {
                serialport::SerialPortType::UsbPort(u) => {
                    let name = u.product.clone().unwrap_or_else(|| "USB serial".into());
                    let likely = matches!(u.vid, 0x10C4 | 0x1A86);
                    (format!("{name} (USB {:04x}:{:04x})", u.vid, u.pid), likely)
                }
                serialport::SerialPortType::BluetoothPort => ("Bluetooth".into(), false),
                serialport::SerialPortType::PciPort => ("PCI".into(), false),
                serialport::SerialPortType::Unknown => ("Unknown".into(), false),
            };
            PortInfo { path: p.port_name, description, likely_roarm: likely }
        })
        .collect();
    out.sort_by_key(|p| !p.likely_roarm);
    Ok(out)
}

// ── Wi-Fi HTTP ────────────────────────────────────────────────────────────────

pub struct HttpLink {
    host: String,
    addr: SocketAddr,
}

const HTTP_CONNECT_TIMEOUT: Duration = Duration::from_millis(800);
const HTTP_READ_TIMEOUT: Duration = Duration::from_millis(1200);

/// Accept `192.168.4.1`, `192.168.4.1:80` or a plain hostname. No scheme, path, or credentials.
pub fn parse_host(input: &str) -> Result<(String, u16), String> {
    let s = input.trim();
    let s = s.strip_prefix("http://").unwrap_or(s).trim_end_matches('/');
    if s.is_empty() || s.contains(['/', '@', '?', '#', ' ']) {
        return Err(format!("\"{input}\" is not an IP address or host name"));
    }
    match s.rsplit_once(':') {
        Some((h, p)) => {
            let port = p.parse::<u16>().map_err(|_| format!("bad port in \"{input}\""))?;
            Ok((h.to_string(), port))
        }
        None => Ok((s.to_string(), 80)),
    }
}

pub fn url_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 3);
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => out.push(b as char),
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

impl HttpLink {
    pub fn open(input: &str) -> Result<Self, LinkError> {
        let (host, port) = parse_host(input).map_err(LinkError::Io)?;
        let addr = (host.as_str(), port)
            .to_socket_addrs()
            .map_err(|e| LinkError::Io(format!("cannot resolve {host}: {e}")))?
            .next()
            .ok_or_else(|| LinkError::Io(format!("cannot resolve {host}")))?;
        Ok(Self { host: format!("{host}:{port}"), addr })
    }

    fn get(addr: SocketAddr, host: &str, cmd: &Value, read_timeout: Duration) -> Result<String, LinkError> {
        let mut stream = TcpStream::connect_timeout(&addr, HTTP_CONNECT_TIMEOUT)
            .map_err(|e| LinkError::Io(format!("connect {host}: {e}")))?;
        stream.set_read_timeout(Some(read_timeout)).ok();
        stream.set_write_timeout(Some(HTTP_CONNECT_TIMEOUT)).ok();
        let request = format!(
            "GET /js?json={} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n",
            url_encode(&cmd.to_string())
        );
        stream
            .write_all(request.as_bytes())
            .map_err(|e| LinkError::Io(format!("send to {host}: {e}")))?;
        let mut raw = Vec::new();
        stream
            .read_to_end(&mut raw)
            .map_err(|e| LinkError::Io(format!("read from {host}: {e}")))?;
        let text = String::from_utf8_lossy(&raw);
        let (head, body) = text.split_once("\r\n\r\n").unwrap_or((&text, ""));
        let status = head.lines().next().unwrap_or("");
        if !status.split_whitespace().nth(1).is_some_and(|c| c == "200") {
            return Err(LinkError::Protocol(format!(
                "{host} answered \"{status}\", which is not how the arm replies. It is probably a different \
                 device — many home routers also use 192.168.4.1. Join the arm's \"RoArm-M2\" Wi-Fi network first"
            )));
        }
        Ok(body.trim().to_string())
    }
}

impl Link for HttpLink {
    fn describe(&self) -> String {
        format!("Wi-Fi http://{}", self.host)
    }

    fn send(&mut self, cmd: &Value) -> Result<Delivery, LinkError> {
        // The firmware runs the command before it answers, so a 200 confirms receipt.
        Self::get(self.addr, &self.host, cmd, HTTP_READ_TIMEOUT).map(|_| Delivery::Confirmed)
    }

    fn feedback(&mut self) -> Result<Value, LinkError> {
        let body = Self::get(self.addr, &self.host, &super::protocol::feedback_cmd(), HTTP_READ_TIMEOUT)?;
        serde_json::from_str(&body).map_err(|_| {
            LinkError::Protocol(format!(
                "the reply was not RoArm JSON feedback (\"{body:.60}\"). Check you are on the arm's \"RoArm-M2\" Wi-Fi network"
            ))
        })
    }

    fn estop_handle(&self) -> Option<Box<dyn EStopSender>> {
        Some(Box::new(HttpEStop { addr: self.addr, host: self.host.clone() }))
    }
}

struct HttpEStop {
    addr: SocketAddr,
    host: String,
}

impl EStopSender for HttpEStop {
    fn send_estop(&mut self) -> Result<(), String> {
        // The firmware pauses ~10 s inside the E-stop handler before replying, so a read
        // timeout after the request was written still means the stop was delivered.
        match HttpLink::get(self.addr, &self.host, &super::protocol::estop_cmd(), Duration::from_millis(300)) {
            Ok(_) => Ok(()),
            Err(LinkError::Io(m)) if m.starts_with("read from") => Ok(()),
            Err(e) => Err(e.to_string()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::sync::mpsc;

    /// Scripted stand-in for the firmware's serial loop on the far end of a pseudo-terminal:
    /// echoes every JSON line (stock `InfoPrint = 1`) and answers `{"T":105}` with feedback.
    /// This exercises the real `SerialLink` code path — not the real arm.
    fn fake_firmware(prelude: &'static str, answer_feedback: bool) -> (SerialLink, std::sync::mpsc::Receiver<String>) {
        let (mut master, slave) = serialport::TTYPort::pair().expect("pty pair");
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader, Write};
            master.write_all(prelude.as_bytes()).unwrap();
            let mut writer = master.try_clone_native().unwrap();
            let mut lines = BufReader::new(master);
            let mut line = String::new();
            loop {
                line.clear();
                match lines.read_line(&mut line) {
                    Ok(0) | Err(_) if line.is_empty() => {
                        std::thread::sleep(Duration::from_millis(5));
                        continue;
                    }
                    _ => {}
                }
                let text = line.trim().to_string();
                if text.is_empty() {
                    continue;
                }
                if tx.send(text.clone()).is_err() {
                    return;
                }
                let Ok(v) = serde_json::from_str::<Value>(&text) else { continue };
                let _ = writeln!(writer, "{text}");
                if v["T"] == 105 && answer_feedback {
                    let _ = writeln!(writer, r#"{{"T":1051,"x":235,"y":0,"z":234,"b":0.0,"s":0.0,"e":1.57,"t":3.14}}"#);
                }
            }
        });
        let mut slave: Box<dyn serialport::SerialPort> = Box::new(slave);
        slave.set_timeout(SERIAL_READ_TIMEOUT).unwrap();
        (SerialLink::from_port("pty", slave).unwrap(), rx)
    }

    #[test]
    fn serial_feedback_and_echo_acknowledgement_over_pty() {
        let (mut link, rx) = fake_firmware("", true);
        let fb = link.feedback().unwrap();
        assert_eq!(fb["T"], 1051);
        assert_eq!(rx.recv().unwrap(), r#"{"T":105}"#);
        let cmd = serde_json::json!({"T":102,"base":0.1,"shoulder":0.0,"elbow":1.57,"hand":3.14,"spd":60,"acc":5});
        assert_eq!(link.send(&cmd).unwrap(), Delivery::Confirmed);
        assert_eq!(serde_json::from_str::<Value>(&rx.recv().unwrap()).unwrap(), cmd);
    }

    #[test]
    fn serial_stale_reply_is_not_taken_as_fresh_feedback() {
        // A late reply from an earlier request is already waiting when we ask again.
        let (mut link, _rx) = fake_firmware(
            "{\"T\":1051,\"x\":0,\"y\":0,\"z\":0,\"b\":9.9,\"s\":0,\"e\":0,\"t\":0}\n",
            true,
        );
        std::thread::sleep(Duration::from_millis(100));
        let fb = link.feedback().unwrap();
        assert_eq!(fb["b"], 0.0, "stale b=9.9 line must be discarded");
    }

    #[test]
    fn serial_boot_banner_in_discarded_output_is_still_reported() {
        let (mut link, _rx) = fake_firmware("Moving BASE_JOINT to initPos.\r\nRoArm-M2 started.\r\n", true);
        std::thread::sleep(Duration::from_millis(100));
        link.feedback().unwrap();
        assert!(link.take_boot_notice());
        assert!(!link.take_boot_notice(), "reported once");
    }

    #[test]
    fn serial_estop_arrives_as_its_own_line_and_is_confirmed_by_echo() {
        let (mut link, rx) = fake_firmware("", true);
        let mut estop = link.estop_handle().expect("estop handle");
        estop.send_estop().unwrap();
        assert_eq!(rx.recv().unwrap(), r#"{"T":0}"#);
        assert_eq!(link.confirm_estop(), Some(true));
    }

    #[test]
    fn serial_silent_device_is_a_connection_error() {
        let (mut link, _rx) = fake_firmware("", false);
        assert!(matches!(link.feedback(), Err(LinkError::Io(_))));
        assert_eq!(link.send(&serde_json::json!({"T":999})).ok(), Some(Delivery::Confirmed));
    }

    #[test]
    fn http_wrong_device_is_explained() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            let (mut s, _) = listener.accept().unwrap();
            let mut buf = [0u8; 1024];
            let _ = s.read(&mut buf);
            write!(s, "HTTP/1.1 404 Not Found\r\n\r\nnot here").unwrap();
        });
        let mut link = HttpLink::open(&format!("127.0.0.1:{port}")).unwrap();
        match link.feedback() {
            Err(LinkError::Protocol(m)) => assert!(m.contains("RoArm-M2"), "{m}"),
            other => panic!("expected protocol error, got {other:?}"),
        }
    }

    #[test]
    fn host_parsing_accepts_only_host_and_port() {
        assert_eq!(parse_host("192.168.4.1").unwrap(), ("192.168.4.1".into(), 80));
        assert_eq!(parse_host(" http://192.168.4.1/ ").unwrap(), ("192.168.4.1".into(), 80));
        assert_eq!(parse_host("roarm.local:8080").unwrap(), ("roarm.local".into(), 8080));
        assert!(parse_host("").is_err());
        assert!(parse_host("192.168.4.1/js?json=1").is_err());
        assert!(parse_host("user@host").is_err());
    }

    #[test]
    fn json_is_percent_encoded() {
        assert_eq!(url_encode(r#"{"T":105}"#), "%7B%22T%22%3A105%7D");
    }

    /// Exercises the HTTP client against a local stand-in for the firmware's `/js`
    /// handler. This checks request/response handling only — not the real arm.
    #[test]
    fn http_link_round_trip_against_local_stub() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            for _ in 0..2 {
                let (mut s, _) = listener.accept().unwrap();
                let mut buf = [0u8; 1024];
                let n = s.read(&mut buf).unwrap();
                let req = String::from_utf8_lossy(&buf[..n]).to_string();
                tx.send(req.lines().next().unwrap().to_string()).unwrap();
                let body = r#"{"T":1051,"x":235,"y":0,"z":234,"b":0,"s":0,"e":1.57,"t":3.14}"#;
                write!(s, "HTTP/1.1 200 OK\r\nContent-Type: text/plane\r\n\r\n{body}").unwrap();
            }
        });
        let mut link = HttpLink::open(&format!("127.0.0.1:{port}")).unwrap();
        let fb = link.feedback().unwrap();
        assert_eq!(fb["T"], 1051);
        assert_eq!(rx.recv().unwrap(), "GET /js?json=%7B%22T%22%3A105%7D HTTP/1.1");
        assert_eq!(link.send(&serde_json::json!({"T":999})).unwrap(), Delivery::Confirmed);
        assert_eq!(rx.recv().unwrap(), "GET /js?json=%7B%22T%22%3A999%7D HTTP/1.1");
    }

    #[test]
    fn http_link_reports_unreachable_host_as_connection_error() {
        // Port 9 on localhost is closed on CI and dev machines.
        let mut link = HttpLink::open("127.0.0.1:9").unwrap();
        assert!(matches!(link.feedback(), Err(LinkError::Io(_))));
    }
}
