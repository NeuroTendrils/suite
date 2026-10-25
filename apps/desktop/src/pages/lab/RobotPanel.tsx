import { useEffect, useRef, useState } from "react";
import { Badge, Field } from "../../components/ui";
import { SAFE_COMMANDS } from "../../lib/decoder";
import { deg, type PortInfo } from "../../lib/robot";
import type { RobotSession } from "../../hooks/useRobot";

const SAFETY_ITEMS = [
  "The arm is on a stable, flat surface and its base is secured.",
  "Nothing and no one is within 50 cm of the arm, and the gripper holds nothing.",
  "The arm may move without warning when it connects (some boards reboot and return to their start pose).",
  "I can reach the arm's power switch, and an adult supervisor is present.",
];

/** Connection, safety confirmation, status, manual presets, and emergency stop for the RoArm-M2-S. */
export function RobotPanel({ r }: { r: RobotSession }) {
  const { status, pending } = r;
  const [kind, setKind] = useState<"serial" | "http">("serial");
  const [ports, setPorts] = useState<PortInfo[] | null>(null);
  const [port, setPort] = useState("");
  const [host, setHost] = useState("192.168.4.1");
  const [checked, setChecked] = useState<boolean[]>(SAFETY_ITEMS.map(() => false));
  const confirmed = checked.every(Boolean);
  const connected = status?.state === "connected";
  const latched = !!status?.estop_latched;

  // The safety check covers one session: reconfirm after a disconnect, loss, or E-stop.
  const prev = useRef({ connected, latched });
  useEffect(() => {
    const was = prev.current;
    if ((was.connected && !connected) || (!was.latched && latched)) setChecked(SAFETY_ITEMS.map(() => false));
    prev.current = { connected, latched };
  }, [connected, latched]);

  async function scan() {
    const found = await r.run("Looking for serial ports", () => r.robot.listPorts());
    if (found) {
      setPorts(found);
      setPort((cur) => (found.some((p) => p.path === cur) ? cur : (found.find((p) => p.likely_roarm)?.path ?? found[0]?.path ?? "")));
    }
  }

  useEffect(() => {
    if (kind === "serial" && ports === null) void scan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  const target = kind === "serial" ? { kind, port } : { kind, host };
  const canConnect = !connected && confirmed && !pending && (kind === "serial" ? !!port : !!host.trim());
  const fb = status?.feedback;

  return (
    <div className="robot">
      <div className="robot-estop-row">
        <button type="button" className="btn robot-estop" onClick={() => void r.estop()} aria-describedby="estop-help">
          EMERGENCY STOP
        </button>
        <p id="estop-help" className="help">
          Software stop: the servos go limp (firmware command <code>{"{\"T\":0}"}</code>), so support the arm — it may sag. After about
          10 seconds the firmware turns torque back on by itself. <strong>The arm's power switch is the real emergency stop</strong>:
          use it if anything looks wrong or the app does not respond.
        </p>
      </div>

      <p className="robot-physical">
        There is no simulated arm. When connected, these controls move the <strong>real</strong> RoArm-M2-S, whatever the EEG source.
      </p>
      {r.error && <p className="inline-error" role="alert">{r.error}</p>}
      {r.message && <p className="robot-message" role="status">{r.message}</p>}

      <div className="robot-grid">
        <section aria-labelledby="robot-conn">
          <h4 id="robot-conn" className="lab-sub">Connection</h4>
          <fieldset className="lab-sources" disabled={connected}>
            <legend className="sr-only">Interface</legend>
            <label><input type="radio" name="link" checked={kind === "serial"} onChange={() => setKind("serial")} /> USB cable</label>
            <label><input type="radio" name="link" checked={kind === "http"} onChange={() => setKind("http")} /> Wi-Fi</label>
          </fieldset>
          {kind === "serial" ? (
            <div className="form-row">
              <Field label="Serial port" hint="Plug the arm's ESP32 USB-C port into this computer.">
                <select value={port} onChange={(e) => setPort(e.target.value)} disabled={connected || !ports?.length}>
                  {!ports?.length && <option value="">No serial ports found</option>}
                  {ports?.map((p) => (
                    <option key={p.path} value={p.path}>{p.likely_roarm ? "Likely the arm · " : ""}{p.path} · {p.description}</option>
                  ))}
                </select>
              </Field>
              <button type="button" className="btn btn-sm" onClick={() => void scan()} disabled={connected || !!pending}>Rescan</button>
            </div>
          ) : (
            <Field label="Arm IP address" hint="Join the arm's Wi-Fi “RoArm-M2” (default address 192.168.4.1), or use the address on its screen.">
              <input value={host} onChange={(e) => setHost(e.target.value)} disabled={connected} spellCheck={false} />
            </Field>
          )}

          <fieldset className="robot-safety">
            <legend>Before connecting or moving, confirm:</legend>
            {SAFETY_ITEMS.map((text, i) => (
              <label key={text}>
                <input
                  type="checkbox"
                  checked={checked[i]}
                  onChange={(e) => setChecked(checked.map((v, j) => (j === i ? e.target.checked : v)))}
                />{" "}
                {text}
              </label>
            ))}
          </fieldset>

          <div className="form-row">
            {!connected ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={!canConnect}
                onClick={() => void r.run("Connecting to arm", () => r.robot.connect(target, confirmed), () => "Connected. The arm answered with servo feedback and was not moved.")}
              >
                {pending === "Connecting to arm" ? "Connecting…" : "Connect"}
              </button>
            ) : (
              <button type="button" className="btn" disabled={!!pending} onClick={() => void r.run("Disconnecting", () => r.robot.disconnect(), () => "Disconnected. Nothing was sent to the arm.")}>
                Disconnect
              </button>
            )}
            {connected && !status?.armed && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={!confirmed || latched || !!pending}
                onClick={() => void r.run("Enabling motion", () => r.robot.arm(confirmed), () => "Motion enabled.")}
              >
                Enable motion
              </button>
            )}
            {connected && status?.armed && (
              <button type="button" className="btn" onClick={() => void r.run("Disabling motion", () => r.robot.disarm())}>Disable motion</button>
            )}
            {latched && (
              <button
                type="button"
                className="btn"
                disabled={!confirmed || !!pending}
                title={confirmed ? undefined : "Re-check the safety list first"}
                onClick={() => void r.run("Clearing emergency stop", () => r.robot.clearEstop(confirmed), () => "Emergency stop cleared. Enable motion again when ready.")}
              >
                Clear emergency stop
              </button>
            )}
          </div>
        </section>

        <section aria-labelledby="robot-status">
          <h4 id="robot-status" className="lab-sub">Status</h4>
          <dl className="facts robot-facts">
            <div>
              <dt>Connection</dt>
              <dd>
                {status?.state === "connected" && <Badge tone="ok">connected</Badge>}
                {status?.state === "disconnected" && <Badge>not connected</Badge>}
                {status?.state === "lost" && <Badge tone="danger">connection lost</Badge>}
                {!status && <Badge>unknown</Badge>} {status?.transport}
              </dd>
            </div>
            {status?.lost_reason && status.state === "lost" && (
              <div><dt>Why</dt><dd>{status.lost_reason} Check the cable, power, or Wi-Fi, then connect again.</dd></div>
            )}
            <div>
              <dt>Motion</dt>
              <dd>
                {latched ? <Badge tone="danger">emergency stop latched</Badge> : status?.armed ? <Badge tone="warn">enabled</Badge> : <Badge>disabled</Badge>}
                {latched && status?.estop_confirmed === true && <span className="muted"> · firmware confirmed the stop</span>}
                {latched && status?.estop_confirmed === false && <strong className="robot-ev-error"> · firmware did not confirm — switch off the arm's power</strong>}
                {latched && status?.estop_confirmed == null && status?.state === "connected" && <span className="muted"> · not confirmable over Wi-Fi — watch the arm</span>}
              </dd>
            </div>
            <div>
              <dt>Servo feedback</dt>
              <dd className="num">
                {fb
                  ? `base ${deg(fb.pose.base)} · shoulder ${deg(fb.pose.shoulder)} · elbow ${deg(fb.pose.elbow)} · gripper ${deg(fb.pose.hand)}`
                  : "—"}
                {fb && status?.feedback_age_ms != null && <span className="muted"> ({(status.feedback_age_ms / 1000).toFixed(1)} s ago)</span>}
              </dd>
            </div>
            <div>
              <dt>Last command</dt>
              <dd>
                {status?.at_target === true && <Badge tone="ok">reached, per the arm's servo sensors</Badge>}
                {status?.at_target === false && <Badge tone="warn">moving or not reached</Badge>}
                {status?.at_target == null && "—"}
                {status?.last_delivery === "unconfirmed" && <span className="muted"> · firmware did not acknowledge</span>}
              </dd>
            </div>
          </dl>
          <h4 className="lab-sub">Manual commands</h4>
          <div className="form-row robot-presets">
            {SAFE_COMMANDS.map((c) => (
              <button
                key={c.id}
                type="button"
                className="btn btn-sm"
                disabled={!status?.armed || latched || !!pending}
                onClick={() => void r.run(`Sending “${c.label}”`, () => r.robot.preset(c.id), r.moved)}
              >
                {c.label}
              </button>
            ))}
          </div>
          <p className="help">
            Moves are limited to safe joint ranges and a speed of at most {status ? Math.round((status.speed_max / 4096) * 360) : "—"}°/s,
            with at least {status ? status.motion_interval_ms : "—"} ms between commands.
          </p>
        </section>
      </div>

      {!!status?.events.length && (
        <details className="robot-log">
          <summary>Arm activity ({status.events.length})</summary>
          <ol>
            {[...status.events].reverse().map((e) => (
              <li key={`${e.at_ms}-${e.text}`} className={`robot-ev-${e.level}`}>
                <span className="muted">{new Date(e.at_ms).toLocaleTimeString()}</span> {e.text}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
