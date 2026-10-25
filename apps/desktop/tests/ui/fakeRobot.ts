/** In-memory stand-in for the Rust RoArm-M2-S driver, behind the same `robotCall` boundary.
 *  Response shapes follow src-tauri/src/robot. The real interlocks are tested in Rust
 *  (`cargo test`); this fake only enforces enough of them to exercise the UI. */

type Pose = { base: number; shoulder: number; elbow: number; hand: number };
export type RobotCall = { command: string; args: Record<string, any> };

const HOME: Pose = { base: 0, shoulder: 0, elbow: 1.5708, hand: 3.14 };

export class FakeRobot {
  calls: RobotCall[] = [];
  state: "disconnected" | "connected" | "lost" = "disconnected";
  armed = false;
  estop = false;
  target: Pose | null = null;
  lostReason: string | null = null;
  ports = [{ path: "/dev/cu.usbserial-0001", description: "CP2102 USB to UART (USB 10c4:ea60)", likely_roarm: true }];
  /** Make the next connect fail with this message. */
  connectError: string | null = null;

  callsOf(command: string) {
    return this.calls.filter((c) => c.command === command);
  }

  /** Simulate the driver detecting a dead link. */
  loseConnection(reason = "No feedback from the arm 3 times in a row.") {
    this.state = "lost";
    this.armed = false;
    this.lostReason = reason;
  }

  status() {
    return {
      state: this.state,
      transport: this.state === "connected" ? "USB serial /dev/cu.usbserial-0001" : null,
      armed: this.armed,
      estop_latched: this.estop,
      estop_recent: false,
      feedback: this.state === "connected" ? { pose: this.target ?? HOME, x: 235, y: 0, z: 234 } : null,
      feedback_age_ms: this.state === "connected" ? 200 : null,
      target: this.target,
      at_target: this.target ? true : null,
      last_delivery: null,
      estop_confirmed: this.estop && this.state === "connected" ? true : null,
      lost_reason: this.lostReason,
      events: [],
      limits: { base: { min: -1.57, max: 1.57 }, shoulder: { min: -0.5, max: 0.5 }, elbow: { min: 1, max: 2.2 }, hand: { min: 1.08, max: 3.14 } },
      home: HOME,
      speed_min: 20,
      speed_max: 400,
      speed_default: 150,
      min_decoder_confidence: 0.6,
      decoder_cooldown_ms: 2500,
      motion_interval_ms: 600,
    };
  }

  private move(cmd: string): unknown {
    if (this.estop) throw "Emergency stop is latched. Clear it after checking the arm.";
    if (this.state !== "connected" || !this.armed) throw "Motion is disabled. Confirm the area is safe to enable it.";
    const base = this.target ?? HOME;
    this.target = cmd === "turn_left" ? { ...base, base: 0.6 } : cmd === "turn_right" ? { ...base, base: -0.6 } : base;
    return { target: this.target, delivery: "confirmed", command: { T: 102 } };
  }

  async call(command: string, args: Record<string, any>): Promise<unknown> {
    this.calls.push({ command, args });
    await Promise.resolve();
    switch (command) {
      case "robot_status":
        return this.status();
      case "robot_list_ports":
        return this.ports;
      case "robot_connect":
        if (!args.operatorConfirmedSafe) throw "Confirm that the arm and its surroundings are clear before connecting.";
        if (this.connectError) throw this.connectError;
        this.state = "connected";
        this.lostReason = null;
        return this.status();
      case "robot_disconnect":
        this.state = "disconnected";
        this.armed = false;
        return this.status();
      case "robot_arm":
        if (!args.operatorConfirmedSafe) throw "Confirm that the arm and its surroundings are clear before enabling motion.";
        if (this.estop) throw "Emergency stop is latched. Clear it first.";
        this.armed = true;
        return this.status();
      case "robot_disarm":
        this.armed = false;
        return this.status();
      case "robot_preset":
        return this.move(args.command);
      case "robot_decoder_command":
        if (args.confidence < args.threshold) throw `Rejected: confidence ${args.confidence} is below the threshold.`;
        return this.move(args.command);
      case "robot_estop":
        this.estop = true;
        this.armed = false;
        return this.state === "connected" ? "Emergency stop sent." : "Emergency stop latched. The arm is not connected, so nothing was sent.";
      case "robot_clear_estop":
        if (!args.operatorConfirmedSafe) throw "confirm first";
        this.estop = false;
        return this.status();
      default:
        throw `unknown robot command: ${command}`;
    }
  }
}
