//! Waveshare RoArm-M2-S integration, exposed to the UI as `robot_*` Tauri commands.
//!
//! The driver lives in the Rust shell rather than the Python backend so robot commands
//! (above all the emergency stop) never queue behind long-running analysis jobs on the
//! single-threaded backend socket.

// Limits like 1.57 / 3.14 rad are the values Waveshare documents, not stand-ins for π.
#![allow(clippy::approx_constant)]

pub mod controller;
pub mod link;
pub mod protocol;

use controller::{EegSource, MoveReport, Robot, Status};
use link::{HttpLink, Link, PortInfo, SerialLink};
use protocol::SafeCommand;
use serde::Deserialize;
use std::sync::Arc;
use std::time::Duration;

pub struct RobotState(pub Arc<Robot>);

const HEARTBEAT: Duration = Duration::from_millis(700);

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Target {
    Serial { port: String },
    Http { host: String },
}

fn spawn_heartbeat(robot: Arc<Robot>, generation: u64) {
    std::thread::Builder::new()
        .name("roarm-heartbeat".into())
        .spawn(move || loop {
            std::thread::sleep(HEARTBEAT);
            if !robot.poll(generation) {
                break;
            }
        })
        .ok();
}

#[tauri::command(async)]
pub fn robot_list_ports() -> Result<Vec<PortInfo>, String> {
    link::list_serial_ports()
}

/// Blocking I/O, so these run on Tauri's worker pool (`async`) instead of the main thread.
#[tauri::command(async)]
pub fn robot_connect(
    state: tauri::State<'_, RobotState>,
    target: Target,
    operator_confirmed_safe: bool,
) -> Result<Status, String> {
    // Opening a USB port can reboot some ESP32 boards, and the firmware moves to its
    // init pose on every boot — so even connecting needs the operator's go-ahead.
    if !operator_confirmed_safe {
        return Err("Confirm that the arm and its surroundings are clear before connecting.".into());
    }
    let link: Box<dyn Link> = match &target {
        Target::Serial { port } => Box::new(SerialLink::open(port).map_err(|e| e.to_string())?),
        Target::Http { host } => Box::new(HttpLink::open(host).map_err(|e| e.to_string())?),
    };
    let generation = state.0.connect(link)?;
    spawn_heartbeat(state.0.clone(), generation);
    Ok(state.0.status())
}

#[tauri::command(async)]
pub fn robot_disconnect(state: tauri::State<'_, RobotState>) -> Status {
    state.0.disconnect();
    state.0.status()
}

#[tauri::command(async)]
pub fn robot_status(state: tauri::State<'_, RobotState>) -> Status {
    state.0.status()
}

#[tauri::command(async)]
pub fn robot_arm(state: tauri::State<'_, RobotState>, operator_confirmed_safe: bool) -> Result<Status, String> {
    state.0.arm(operator_confirmed_safe)?;
    Ok(state.0.status())
}

#[tauri::command(async)]
pub fn robot_disarm(state: tauri::State<'_, RobotState>) -> Status {
    state.0.disarm();
    state.0.status()
}

#[tauri::command(async)]
pub fn robot_preset(state: tauri::State<'_, RobotState>, command: SafeCommand) -> Result<MoveReport, String> {
    state.0.preset(command)
}

#[tauri::command(async)]
pub fn robot_decoder_command(
    state: tauri::State<'_, RobotState>,
    command: SafeCommand,
    confidence: f64,
    threshold: f64,
    source: EegSource,
) -> Result<MoveReport, String> {
    state.0.decoder_command(command, confidence, threshold, source)
}

#[tauri::command(async)]
pub fn robot_estop(state: tauri::State<'_, RobotState>) -> Result<String, String> {
    state.0.estop()
}

#[tauri::command(async)]
pub fn robot_clear_estop(state: tauri::State<'_, RobotState>, operator_confirmed_safe: bool) -> Result<Status, String> {
    state.0.clear_estop(operator_confirmed_safe)?;
    Ok(state.0.status())
}

/// Staged physical hardware checks. All are `#[ignore]`d and each needs its own explicit
/// operator approval in the environment; none runs on `cargo test` and none continues into
/// the next stage by itself. Run ONE stage at a time (see docs/guides/ROBOT_ARM.md):
///
/// ```text
/// # Stage A — connection and feedback only, no motion command is sent:
/// ROARM_SERIAL_PORT=/dev/cu.usbserial-XXXX ROARM_CONFIRM_CONNECT_SAFE=yes \
///   cargo test --lib robot::hardware::stage_a -- --ignored --nocapture --test-threads=1
/// # Stage B — one small, slow base move (+0.10 rad ≈ 6° at ≈5°/s), verified by feedback:
/// ... ROARM_CONFIRM_CONNECT_SAFE=yes ROARM_CONFIRM_MOTION_SAFE=yes [ROARM_STAGE_B_DIRECTION=-1] \
///   cargo test --lib robot::hardware::stage_b -- --ignored --nocapture --test-threads=1
/// # Stage C — interlocks on real hardware (disconnect, reconnect, no resume); no motion sent:
/// ... ROARM_CONFIRM_CONNECT_SAFE=yes cargo test --lib robot::hardware::stage_c_ -- --ignored --nocapture
/// # Stage C2 — firmware E-stop observation (servos go limp ~10 s, then re-engage). Supervised:
/// ... ROARM_CONFIRM_CONNECT_SAFE=yes ROARM_CONFIRM_ESTOP_SAFE=yes \
///   cargo test --lib robot::hardware::stage_c2 -- --ignored --nocapture
/// ```
/// `ROARM_HOST=192.168.4.1` may replace `ROARM_SERIAL_PORT` to test Wi-Fi.
#[cfg(test)]
mod hardware {
    use super::*;
    use controller::{Config, ConnState};
    use protocol::{max_joint_error, MotionSettings, Pose};

    fn require(var: &str, why: &str) {
        assert_eq!(std::env::var(var).as_deref(), Ok("yes"), "set {var}=yes only after the operator confirms {why}");
    }

    fn open_from_env() -> Box<dyn Link> {
        if let Ok(port) = std::env::var("ROARM_SERIAL_PORT") {
            return Box::new(SerialLink::open(&port).expect("open serial port"));
        }
        let host = std::env::var("ROARM_HOST").expect("set ROARM_SERIAL_PORT or ROARM_HOST");
        Box::new(HttpLink::open(&host).expect("resolve host"))
    }

    fn connect() -> (Robot, u64) {
        require("ROARM_CONFIRM_CONNECT_SAFE", "the arm is secured and clear, and its power switch is within reach (opening the port may reboot it, and a reboot runs its start-pose move)");
        let robot = Robot::new(Config::default());
        let generation = robot.connect(open_from_env()).expect("RoArm-M2-S feedback handshake");
        (robot, generation)
    }

    fn print_events(robot: &Robot) {
        for e in robot.status().events {
            println!("  [{}] {}", e.level, e.text);
        }
    }

    #[test]
    #[ignore = "Stage A: requires a powered RoArm-M2-S and operator approval; sends feedback queries only"]
    fn stage_a_connection_and_feedback() {
        let (robot, generation) = connect();
        for i in 0..5 {
            std::thread::sleep(Duration::from_millis(700));
            assert!(robot.poll(generation), "feedback stopped after {i} polls");
        }
        let st = robot.status();
        let fb = st.feedback.expect("feedback");
        println!("STAGE A transport: {:?}", st.transport);
        println!("STAGE A feedback: {fb:?} (age {:?} ms)", st.feedback_age_ms);
        println!("STAGE A inside app limits: {:?}", protocol::validate_pose(&fb.pose));
        print_events(&robot);
        assert_eq!(st.state, ConnState::Connected);
        assert!(!st.armed, "connecting must never enable motion");
        robot.disconnect();
    }

    #[test]
    #[ignore = "Stage B: MOVES THE ARM once (base ≈6°, slow); requires operator approval"]
    fn stage_b_single_small_move() {
        require("ROARM_CONFIRM_MOTION_SAFE", "the arm is in a safe starting pose, nothing is within reach of it, and someone has a hand on the power switch");
        let (robot, generation) = connect();
        robot.arm(true).expect("enable motion (arm must start inside the safe range)");
        let start = robot.status().feedback.expect("feedback").pose;
        let dir: f64 = std::env::var("ROARM_STAGE_B_DIRECTION").ok().and_then(|v| v.parse().ok()).unwrap_or(1.0);
        let target = Pose { base: start.base + 0.10 * dir.signum(), ..protocol::clamp_pose(&start) };
        println!("STAGE B start {start:?}\nSTAGE B target {target:?}");
        let report = robot.move_to(target, MotionSettings { speed: 60, acc: 2 }).expect("send move");
        println!("STAGE B delivery: {:?}", report.delivery);
        let mut reached = false;
        for _ in 0..40 {
            std::thread::sleep(Duration::from_millis(250));
            assert!(robot.poll(generation), "connection lost during the move");
            let pose = robot.status().feedback.expect("feedback").pose;
            let off_axis = max_joint_error(&Pose { base: start.base, ..pose }, &start);
            if off_axis > 0.15 {
                robot.estop().ok();
                panic!("STOPPED: a joint other than the base moved by {off_axis:.2} rad — {pose:?}");
            }
            if robot.status().at_target == Some(true) {
                reached = true;
                break;
            }
        }
        robot.disarm();
        let end = robot.status().feedback.expect("feedback").pose;
        println!("STAGE B end {end:?}; base moved {:.3} rad", end.base - start.base);
        print_events(&robot);
        robot.disconnect();
        assert!(reached, "servo feedback did not reach the target within 10 s");
    }

    #[test]
    #[ignore = "Stage C: requires a powered RoArm-M2-S and operator approval; sends no motion and no E-stop"]
    fn stage_c_interlocks_without_motion() {
        let (robot, _) = connect();
        robot.arm(true).expect("enable motion");
        let before = robot.status().feedback.expect("feedback").pose;
        robot.disconnect();
        assert!(robot.preset(SafeCommand::TurnLeft).is_err(), "no motion after disconnect");
        // Latch the E-stop while disconnected, so nothing is sent to the arm.
        robot.estop().expect("latch");
        let generation = robot.connect(open_from_env()).expect("reconnect");
        assert!(!robot.status().armed, "reconnect must start with motion disabled");
        assert!(robot.arm(true).is_err(), "a latched E-stop must block re-enabling after reconnect");
        assert!(robot.preset(SafeCommand::TurnLeft).is_err(), "no motion while latched");
        std::thread::sleep(Duration::from_secs(2));
        assert!(robot.poll(generation));
        let after = robot.status().feedback.expect("feedback").pose;
        println!("STAGE C pose before {before:?}\nSTAGE C pose after  {after:?}");
        assert!(max_joint_error(&before, &after) < 0.05, "the arm moved although no motion was sent");
        robot.clear_estop(true).expect("clear latch");
        assert!(!robot.status().armed, "clearing the E-stop must not re-enable motion");
        print_events(&robot);
        robot.disconnect();
    }

    #[test]
    #[ignore = "Stage C2: sends the firmware E-stop — servos go LIMP ~10 s then re-engage; supervised only"]
    fn stage_c2_firmware_estop_observation() {
        require(
            "ROARM_CONFIRM_ESTOP_SAFE",
            "the arm is at a low pose with an operator's hand supporting it, and another person is on the power switch",
        );
        let (robot, generation) = connect();
        let before = robot.status().feedback.expect("feedback").pose;
        println!("STAGE C2 sending {{\"T\":0}} now. Pose before: {before:?}");
        println!("{:?}", robot.estop());
        for s in 0..14 {
            std::thread::sleep(Duration::from_secs(1));
            robot.poll(generation);
            let st = robot.status();
            println!("t={:>2}s state={:?} feedback={:?}", s + 1, st.state, st.feedback.map(|f| f.pose));
        }
        println!("STAGE C2 firmware confirmed E-stop: {:?}", robot.status().estop_confirmed);
        println!("Record by eye: did the arm sag? Did it move again when torque returned (~10 s)?");
        print_events(&robot);
        robot.disconnect();
    }
}
