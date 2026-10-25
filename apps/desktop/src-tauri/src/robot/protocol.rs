//! Waveshare RoArm-M2-S JSON protocol: command builders, limits, and validation.
//!
//! Source of truth: the official firmware (github.com/waveshareteam/roarm_m2,
//! `RoArm-M2_example/json_cmd.h`, `uart_ctrl.h`) and the Waveshare wiki pages
//! "RoArm-M2-S Robotic Arm Control" and "RoArm-M2-S JSON Command Meaning".
//!
//! Only the commands below are ever sent. Notably *not* used:
//! - `{"T":100}` (move to init): the firmware moves without app-controlled speed.
//! - `spd: 0` / `acc: 0`: the firmware treats 0 as *maximum* speed / acceleration.
//! - `T:104`/`T:1041` (IK) and `T:123` (continuous motion): not needed for the demo,
//!   and continuous motion keeps moving until a separate stop arrives.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

/// Feedback reply type the firmware sends for `{"T":105}` (`RoArmM2_infoFeedback`).
pub const FEEDBACK_REPLY_T: i64 = 1051;

/// Joint angles in radians, in the firmware's convention
/// (base +left, shoulder +forward/down, elbow +down, hand: larger = more closed).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Pose {
    pub base: f64,
    pub shoulder: f64,
    pub elbow: f64,
    pub hand: f64,
}

/// Inclusive [min, max] in radians.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct Range {
    pub min: f64,
    pub max: f64,
}

/// App-enforced joint limits. Each is a strict subset of the documented range
/// (base ±3.14, shoulder ±1.57, elbow 0..3.14, gripper 1.08..3.14) chosen so a
/// desk demo stays close to the power-on pose and away from the table surface.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct JointLimits {
    pub base: Range,
    pub shoulder: Range,
    pub elbow: Range,
    pub hand: Range,
}

pub const LIMITS: JointLimits = JointLimits {
    base: Range { min: -1.57, max: 1.57 },
    shoulder: Range { min: -0.50, max: 0.50 },
    elbow: Range { min: 1.00, max: 2.20 },
    hand: Range { min: 1.08, max: 3.14 },
};

/// The firmware's power-on pose (`RoArmM2_moveInit`), used as "home".
pub const HOME: Pose = Pose { base: 0.0, shoulder: 0.0, elbow: 1.5708, hand: 3.14 };

/// Speed in servo steps/s (4096 steps per revolution). 0 means "maximum" to the
/// firmware, so the minimum is 1. 400 steps/s ≈ 35°/s.
pub const SPEED_MIN: u32 = 20;
pub const SPEED_MAX: u32 = 400;
pub const SPEED_DEFAULT: u32 = 150;
/// Acceleration in units of 100 steps/s². 0 means "maximum" to the firmware.
pub const ACC_MIN: u32 = 1;
pub const ACC_MAX: u32 = 20;
pub const ACC_DEFAULT: u32 = 5;

/// Gripper presets (radians). The firmware documents 1.57 as "release" and 3.14 as "grab".
pub const GRIPPER_OPEN: f64 = 1.60;
pub const GRIPPER_CLOSED: f64 = 3.00;
/// Base offset for the decoder's "left"/"right" presets (≈ 34°).
pub const BASE_TURN: f64 = 0.60;

#[derive(Debug, Clone, Copy, Serialize)]
pub struct MotionSettings {
    pub speed: u32,
    pub acc: u32,
}

impl Default for MotionSettings {
    fn default() -> Self {
        Self { speed: SPEED_DEFAULT, acc: ACC_DEFAULT }
    }
}

fn check_range(name: &str, v: f64, r: Range) -> Result<(), String> {
    if !v.is_finite() {
        return Err(format!("{name} angle is not a number"));
    }
    if v < r.min || v > r.max {
        return Err(format!(
            "{name} angle {v:.2} rad is outside the safe range {:.2}..{:.2} rad",
            r.min, r.max
        ));
    }
    Ok(())
}

pub fn validate_pose(p: &Pose) -> Result<(), String> {
    check_range("base", p.base, LIMITS.base)?;
    check_range("shoulder", p.shoulder, LIMITS.shoulder)?;
    check_range("elbow", p.elbow, LIMITS.elbow)?;
    check_range("gripper", p.hand, LIMITS.hand)?;
    Ok(())
}

pub fn validate_motion(m: &MotionSettings) -> Result<(), String> {
    if m.speed < SPEED_MIN || m.speed > SPEED_MAX {
        return Err(format!("speed {} is outside {SPEED_MIN}..{SPEED_MAX} steps/s", m.speed));
    }
    if m.acc < ACC_MIN || m.acc > ACC_MAX {
        return Err(format!("acceleration {} is outside {ACC_MIN}..{ACC_MAX}", m.acc));
    }
    Ok(())
}

fn round3(v: f64) -> f64 {
    (v * 1000.0).round() / 1000.0
}

/// `CMD_JOINTS_RAD_CTRL` — all joints at once, non-blocking in the firmware.
pub fn joints_cmd(p: &Pose, m: &MotionSettings) -> Value {
    json!({
        "T": 102,
        "base": round3(p.base),
        "shoulder": round3(p.shoulder),
        "elbow": round3(p.elbow),
        "hand": round3(p.hand),
        "spd": m.speed,
        "acc": m.acc,
    })
}

/// `CMD_SERVO_RAD_FEEDBACK` — read-only; the firmware replies with a `T:1051` object.
pub fn feedback_cmd() -> Value {
    json!({ "T": 105 })
}

/// `CMD_EMERGENCY_STOP` — the firmware releases all servo torque for ~10 s, then
/// re-enables it. While torque is off the arm is limp and can sag under gravity.
pub fn estop_cmd() -> Value {
    json!({ "T": 0 })
}

/// `CMD_RESET_EMERGENCY` — clears the firmware's emergency flag.
pub fn reset_estop_cmd() -> Value {
    json!({ "T": 999 })
}

/// Parsed `T:1051` feedback.
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct Feedback {
    pub pose: Pose,
    /// End-effector position in mm.
    pub x: f64,
    pub y: f64,
    pub z: f64,
    /// Servo load readings (firmware units).
    pub tor_base: f64,
    pub tor_shoulder: f64,
    pub tor_elbow: f64,
    pub tor_hand: f64,
}

/// Parse a feedback reply. An error here means the device did not answer the way
/// RoArm-M2-S firmware does, so the app treats it as unsupported.
pub fn parse_feedback(v: &Value) -> Result<Feedback, String> {
    let t = v.get("T").and_then(Value::as_i64);
    if t != Some(FEEDBACK_REPLY_T) {
        return Err(format!("expected a T:{FEEDBACK_REPLY_T} feedback reply, got {v}"));
    }
    let num = |k: &str| -> Result<f64, String> {
        v.get(k)
            .and_then(Value::as_f64)
            .filter(|x| x.is_finite())
            .ok_or_else(|| format!("feedback is missing numeric field \"{k}\""))
    };
    let opt = |k: &str| v.get(k).and_then(Value::as_f64).unwrap_or(0.0);
    Ok(Feedback {
        pose: Pose { base: num("b")?, shoulder: num("s")?, elbow: num("e")?, hand: num("t")? },
        x: num("x")?,
        y: num("y")?,
        z: num("z")?,
        tor_base: opt("torB"),
        tor_shoulder: opt("torS"),
        tor_elbow: opt("torE"),
        tor_hand: opt("torH"),
    })
}

/// The fixed set of commands an approved decoder prediction may trigger.
/// Each maps to an *absolute* pose, so repeating a prediction never accumulates motion.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SafeCommand {
    Home,
    TurnLeft,
    TurnRight,
    GripperOpen,
    GripperClose,
}

impl SafeCommand {
    /// Target pose for this command, keeping the joints it does not concern at `current`.
    pub fn target(self, current: &Pose) -> Pose {
        match self {
            SafeCommand::Home => Pose { hand: current.hand, ..HOME },
            SafeCommand::TurnLeft => Pose { base: BASE_TURN, ..*current },
            SafeCommand::TurnRight => Pose { base: -BASE_TURN, ..*current },
            SafeCommand::GripperOpen => Pose { hand: GRIPPER_OPEN, ..*current },
            SafeCommand::GripperClose => Pose { hand: GRIPPER_CLOSED, ..*current },
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            SafeCommand::Home => "home",
            SafeCommand::TurnLeft => "turn left",
            SafeCommand::TurnRight => "turn right",
            SafeCommand::GripperOpen => "open gripper",
            SafeCommand::GripperClose => "close gripper",
        }
    }
}

/// Clamp each joint into the app limits. Used only to derive a starting target from
/// measured feedback (e.g. someone moved the arm by hand); commands are validated, never clamped.
pub fn clamp_pose(p: &Pose) -> Pose {
    let c = |v: f64, r: Range| v.clamp(r.min, r.max);
    Pose {
        base: c(p.base, LIMITS.base),
        shoulder: c(p.shoulder, LIMITS.shoulder),
        elbow: c(p.elbow, LIMITS.elbow),
        hand: c(p.hand, LIMITS.hand),
    }
}

/// Largest per-joint distance between two poses, in radians.
pub fn max_joint_error(a: &Pose, b: &Pose) -> f64 {
    [
        (a.base - b.base).abs(),
        (a.shoulder - b.shoulder).abs(),
        (a.elbow - b.elbow).abs(),
        (a.hand - b.hand).abs(),
    ]
    .into_iter()
    .fold(0.0, f64::max)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn home_and_presets_are_inside_limits() {
        validate_pose(&HOME).unwrap();
        for cmd in [
            SafeCommand::Home,
            SafeCommand::TurnLeft,
            SafeCommand::TurnRight,
            SafeCommand::GripperOpen,
            SafeCommand::GripperClose,
        ] {
            validate_pose(&cmd.target(&HOME)).unwrap_or_else(|e| panic!("{cmd:?}: {e}"));
        }
    }

    #[test]
    fn rejects_out_of_range_and_non_finite_angles() {
        let bad = [
            Pose { base: 2.0, ..HOME },
            Pose { shoulder: -0.9, ..HOME },
            Pose { elbow: 0.2, ..HOME },
            Pose { hand: 0.5, ..HOME },
            Pose { base: f64::NAN, ..HOME },
            Pose { elbow: f64::INFINITY, ..HOME },
        ];
        for p in bad {
            assert!(validate_pose(&p).is_err(), "{p:?} should be rejected");
        }
    }

    #[test]
    fn zero_speed_or_acc_is_rejected_because_firmware_treats_it_as_max() {
        assert!(validate_motion(&MotionSettings { speed: 0, acc: 5 }).is_err());
        assert!(validate_motion(&MotionSettings { speed: 100, acc: 0 }).is_err());
        assert!(validate_motion(&MotionSettings { speed: SPEED_MAX + 1, acc: 5 }).is_err());
        assert!(validate_motion(&MotionSettings::default()).is_ok());
    }

    #[test]
    fn joint_command_matches_firmware_schema() {
        let cmd = joints_cmd(&HOME, &MotionSettings { speed: 150, acc: 5 });
        assert_eq!(
            cmd,
            json!({"T":102,"base":0.0,"shoulder":0.0,"elbow":1.571,"hand":3.14,"spd":150,"acc":5})
        );
        assert_eq!(feedback_cmd(), json!({"T":105}));
        assert_eq!(estop_cmd(), json!({"T":0}));
        assert_eq!(reset_estop_cmd(), json!({"T":999}));
    }

    #[test]
    fn parses_firmware_feedback_and_rejects_other_replies() {
        // Shape produced by RoArmM2_infoFeedback().
        let fb = json!({"T":1051,"x":235.1,"y":0.0,"z":234.8,"b":0.01,"s":-0.02,"e":1.57,"t":3.14,
                        "torB":0,"torS":12,"torE":-4,"torH":0});
        let parsed = parse_feedback(&fb).unwrap();
        assert!((parsed.pose.elbow - 1.57).abs() < 1e-9);
        assert!(parse_feedback(&json!({"T":105})).is_err(), "an echo is not feedback");
        assert!(parse_feedback(&json!({"T":1051,"x":1})).is_err(), "missing joints");
        assert!(parse_feedback(&json!({"status":"ok"})).is_err());
    }

    #[test]
    fn presets_are_absolute_so_repeats_do_not_accumulate() {
        let once = SafeCommand::TurnLeft.target(&HOME);
        let twice = SafeCommand::TurnLeft.target(&once);
        assert_eq!(once, twice);
        assert_eq!(SafeCommand::Home.target(&once).base, 0.0);
    }
}
