/** Types and calls for the RoArm-M2-S driver in the Rust shell (src-tauri/src/robot). */

import { robotCall } from "../ipc";
import type { EegSource, SafeCommand } from "./decoder";

export type Pose = { base: number; shoulder: number; elbow: number; hand: number };
export type Range = { min: number; max: number };
export type RobotEvent = { at_ms: number; level: "info" | "warn" | "error"; text: string };
export type Delivery = "confirmed" | "unconfirmed";

export type RobotStatus = {
  state: "disconnected" | "connected" | "lost";
  transport: string | null;
  armed: boolean;
  estop_latched: boolean;
  estop_recent: boolean;
  feedback: { pose: Pose; x: number; y: number; z: number } | null;
  feedback_age_ms: number | null;
  target: Pose | null;
  at_target: boolean | null;
  last_delivery: Delivery | null;
  /** Firmware echoed the last E-stop (USB); null when the transport cannot tell (Wi-Fi) or none was sent. */
  estop_confirmed: boolean | null;
  lost_reason: string | null;
  events: RobotEvent[];
  limits: { base: Range; shoulder: Range; elbow: Range; hand: Range };
  home: Pose;
  speed_min: number;
  speed_max: number;
  speed_default: number;
  min_decoder_confidence: number;
  decoder_cooldown_ms: number;
  motion_interval_ms: number;
};

export type MoveReport = { target: Pose; delivery: Delivery; command: Record<string, unknown> };
export type PortInfo = { path: string; description: string; likely_roarm: boolean };
export type RobotTarget = { kind: "serial"; port: string } | { kind: "http"; host: string };

export const robot = {
  listPorts: () => robotCall<PortInfo[]>("robot_list_ports"),
  status: () => robotCall<RobotStatus>("robot_status"),
  connect: (target: RobotTarget, operatorConfirmedSafe: boolean) =>
    robotCall<RobotStatus>("robot_connect", { target, operatorConfirmedSafe }),
  disconnect: () => robotCall<RobotStatus>("robot_disconnect"),
  arm: (operatorConfirmedSafe: boolean) => robotCall<RobotStatus>("robot_arm", { operatorConfirmedSafe }),
  disarm: () => robotCall<RobotStatus>("robot_disarm"),
  preset: (command: SafeCommand) => robotCall<MoveReport>("robot_preset", { command }),
  decoder: (command: SafeCommand, confidence: number, threshold: number, source: EegSource) =>
    robotCall<MoveReport>("robot_decoder_command", { command, confidence, threshold, source }),
  estop: () => robotCall<string>("robot_estop"),
  clearEstop: (operatorConfirmedSafe: boolean) => robotCall<RobotStatus>("robot_clear_estop", { operatorConfirmedSafe }),
};

/** Radians → whole degrees, for display. */
export const deg = (rad: number) => `${Math.round((rad * 180) / Math.PI)}°`;
