import { useCallback, useEffect, useRef, useState } from "react";
import { errorText } from "../lib/errors";
import { robot, type MoveReport, type RobotStatus } from "../lib/robot";

/** Robot arm session state, polled from the Rust driver.
 *  Lives in App so the emergency stop in the top bar works on every page. */
export function useRobot(active: boolean) {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const s = await robot.status();
      if (mounted.current) setStatus(s);
    } catch (e) {
      if (mounted.current) setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    // A freshly loaded UI has an unchecked safety list, so it must not inherit enabled motion
    // from an earlier page load (the driver outlives a webview reload).
    robot.disarm().catch(() => {});
    return () => {
      mounted.current = false;
    };
  }, []);

  // Poll quickly while the lab is open or an arm is connected, so loss shows up promptly.
  const connected = status?.state === "connected";
  // A result message from before the connection dropped no longer describes the arm.
  useEffect(() => {
    if (status?.state === "lost") setMessage(null);
  }, [status?.state]);
  useEffect(() => {
    void refresh();
    if (!active && !connected) return;
    const id = window.setInterval(() => void refresh(), 500);
    return () => window.clearInterval(id);
  }, [active, connected, refresh]);

  /** Run one driver call; errors become `error`, never thrown. */
  async function run<T>(label: string, fn: () => Promise<T>, done?: (r: T) => string | null): Promise<T | null> {
    setPending(label);
    setError(null);
    setMessage(null);
    try {
      const r = await fn();
      if (done) setMessage(done(r));
      return r;
    } catch (e) {
      setError(errorText(e));
      return null;
    } finally {
      setPending(null);
      await refresh();
    }
  }

  /** Emergency stop skips `run` so nothing (not even a pending call) delays it. */
  async function estop() {
    setError(null);
    try {
      setMessage(await robot.estop());
    } catch (e) {
      setError(errorText(e));
    }
    await refresh();
  }

  const moved = (r: MoveReport) =>
    r.delivery === "confirmed" ? "Command acknowledged by the arm's firmware." : "Command sent, but the firmware did not acknowledge it.";

  return { robot, status, error, message, pending, refresh, run, estop, moved, setError };
}

export type RobotSession = ReturnType<typeof useRobot>;
