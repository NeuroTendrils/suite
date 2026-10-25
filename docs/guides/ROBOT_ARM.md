# RoArm-M2-S and the BCI Lab

The **BCI Lab** page (navigation rail → *BCI Lab*) walks students through one brain–computer
interface loop: EEG input → AI prediction → safety gate → robot arm. This guide covers the
hardware, how to connect it, the safety design, and how to run the demonstration.

## Hardware and protocol

| Item | Value | Source |
| --- | --- | --- |
| Arm | Waveshare **RoArm-M2-S** (4 joints: base, shoulder, elbow, gripper/wrist), ESP32 controller | Waveshare wiki "RoArm-M2-S" |
| Firmware referenced | `waveshareteam/roarm_m2` `RoArm-M2_example` (OLED shows `version: 0.84`), commit `c6ccc5b` (Jan 2025) | GitHub |
| USB | ESP32 USB-C port, 115200 baud, one JSON object per line (`\n`) | wiki "RoArm-M2-S Python UART Communication" |
| Wi-Fi | AP SSID `RoArm-M2`, password `12345678`, `http://192.168.4.1/js?json=<JSON>` (GET) | wiki "RoArm-M2-S Python HTTP Request Communication" |

Commands the app sends — nothing else:

| JSON | Meaning | When |
| --- | --- | --- |
| `{"T":105}` | Read servo feedback; firmware replies `{"T":1051, x,y,z, b,s,e,t, torB…}` | Connect handshake, then every 0.7 s |
| `{"T":102,"base":…,"shoulder":…,"elbow":…,"hand":…,"spd":…,"acc":…}` | Move all joints (radians) | Manual presets and approved decoder commands |
| `{"T":0}` | Firmware emergency stop: releases servo torque for ~10 s | E-STOP |
| `{"T":999}` | Clear the firmware emergency flag | "Clear emergency stop" |

Deliberately **not** used: `{"T":100}` (move to init, no app speed control), any `spd:0`/`acc:0`
(the firmware treats 0 as *maximum*), IK and continuous-motion commands.

The driver is in the Rust shell (`apps/desktop/src-tauri/src/robot/`), not the Python backend, so
robot commands and E-stop never wait behind long analysis jobs.

## Safety design

- **Connecting never moves the arm by itself.** The only thing sent is the read-only feedback
  query. A device that does not answer like RoArm-M2-S firmware is rejected as *unsupported firmware*.
  - Caveat: on some ESP32 boards opening the USB port reboots the board, and the firmware moves to
    its start pose on every boot. The app releases RTS before DTR (as Waveshare's demo does) to avoid
    this, and it detects the boot banner and warns. **This is why connecting also requires the safety
    confirmation.**
- **Motion must be enabled** after the operator ticks the safety checklist. Disconnecting, a lost
  connection, a failed send, a detected reboot, and E-stop all disable motion. The checklist resets
  after disconnect/loss/E-stop.
- **Limits** (radians; each a subset of the documented range): base ±1.57, shoulder ±0.50,
  elbow 1.00–2.20, gripper 1.08–3.14. Out-of-range or non-numeric targets are rejected, never clamped.
- **Speed** 20–400 steps/s (≤ ~35°/s), default 150; acceleration 1–20, default 5.
- **Rate limits:** ≥ 600 ms between any two motion commands; ≥ 2.5 s between decoder-driven commands.
- **Decoder commands** map only to five fixed, *absolute* presets (home, base left/right ±0.60 rad,
  gripper open/close), so repeated predictions never accumulate motion. The driver rejects
  confidence below 0.60 or below the UI threshold, whatever the UI sends.
- **Connection loss:** three missed feedback replies in a row end the session. Nothing is retried or
  replayed; you must reconnect and re-enable motion.
- **E-stop** is on the BCI Lab page and in the top bar on every page while connected. It latches in the
  app first, then sends `{"T":0}` on a dedicated handle (prefixed with a newline so it cannot merge
  with a half-written heartbeat line). Over USB the app checks the firmware's echo and reports whether
  the stop was received; over Wi-Fi it cannot tell.
- **The software E-stop is not a physical emergency stop.** In the firmware it releases servo torque,
  waits 10 s, then *re-enables torque by itself* (`emergencyStopProcessing()`). While limp the arm can
  sag; when torque returns the servos may drive back toward their last goal (not verified on hardware).
  **The arm's power switch is the real emergency stop.** Keep someone's hand on it during demos.
- **Motion is refused if the arm is outside the safe range** when you enable it, because every move
  command sets all four joints and would swing the out-of-range joint back. Power-cycle the arm: the
  firmware returns it to its start pose at boot.
- **Reloading the UI disables motion** in the driver, so the safety checklist always has to be ticked
  again. Restarting the app starts disconnected; nothing reconnects or moves automatically.
- Only the five presets can be sent from the UI; there is no free-form pose command.

## Connecting

1. Place the arm on a flat, stable surface with 50 cm clear around it. Power it with its 12 V supply.
   Wait for the OLED to show `RoArm-M2 started` / the Wi-Fi info.
2. **USB (recommended):** connect the ESP32 USB-C port to the computer. On macOS the port appears as
   `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial-*` (CP210x or CH34x bridge). If nothing appears,
   install the CP210x or CH34x driver.
   **Wi-Fi:** join the `RoArm-M2` network (password `12345678`); the address is `192.168.4.1`, or the
   address shown on the OLED in station mode.
3. Start the app (`npm run dev:suite` from the repo root, or the built app) and open **BCI Lab**.
4. In *5 · Robot arm*: choose USB or Wi-Fi, pick the port (marked "likely the arm") or enter the IP,
   tick every safety item, press **Connect**. Status should show *connected* and live servo angles.
   If it says *unsupported firmware* or *did not answer*, see Troubleshooting.
5. Press **Enable motion**, then try **Return home** and **Turn base left**. *Last command* shows
   "reached, per the arm's servo sensors" only when the arm's own feedback matches the target.

## Demonstration script (EEG → AI → robot)

1. **Learn:** open *Learn* and take *Introduction to EEGs*; then open *BCI Lab* and read *1 · The science*.
2. **EEG input (simulated):** keep *Simulated EEG* (the banner says it is generated by the app).
   Choose *Left-hand imagery*, noise ≈ 10 µV, **Generate simulated trial**. Point out the lower
   mu power at C4 (opposite hemisphere).
3. **AI prediction:** read the predicted class, the probability bars, and the model's held-out
   accuracy at this noise level.
4. **Safety gate:** threshold 80%, 2 agreeing predictions. Generate a second left-hand trial; the
   gate approves *Turn base left*. Raise noise to 30 µV to show confident-wrong and rejected
   predictions.
5. **Robot:** connect and enable motion as above, then **Send approved command to arm**. The arm
   turns left; *Last command* confirms it from servo feedback. Press **E-STOP** to show the stop,
   then **Clear emergency stop** after re-checking the list.
6. **Prerecorded (optional):** with a study that has a trained NeuroStudio model, choose
   *Prerecorded EEG* → **Run model on held-out trials**, map classes to commands, and step through
   trials. The banner states the data is replayed, not real time.

Live EEG is not supported in this build; the option is shown disabled.

## Before the first hardware session

1. **Power:** the servos run from the arm's own 12 V DC adapter, not from USB. Plug the adapter in and
   switch the arm on; the OLED should light and show `RoArm-M2` and its start-up lines. USB alone
   powers the ESP32 board but not the servos.
2. **Find the USB port:** with the arm's USB cable *unplugged*, run `ls /dev/cu.*`. Plug the cable into
   the board's USB-C port that Waveshare labels for ESP32 communication, run `ls /dev/cu.*` again,
   and note the new entry (`/dev/cu.usbserial-…`, `/dev/cu.wchusbserial…` or `/dev/cu.SLAB_USBtoUART`).
   `system_profiler SPUSBHostDataType | grep -i -A6 -E 'cp210|ch34|uart'` should list a CP210x
   (vendor 0x10c4) or CH34x (0x1a86) bridge. Nothing new appearing usually means a charge-only cable or
   a missing CP210x/CH34x driver. Listing ports does not open them.
3. **Wi-Fi caution:** the arm's address 192.168.4.1 is also used by some home routers (this
   development Mac's eero router uses it). Join the `RoArm-M2` network first; otherwise the app
   reports that the device at that address is not the arm.

## Staged hardware verification

Run one stage at a time, stopping if anything unexpected happens. Each stage needs its own
`yes` from the operator and never continues into the next. All commands run in `apps/desktop/src-tauri`;
replace `ROARM_SERIAL_PORT=…` with `ROARM_HOST=192.168.4.1` to test Wi-Fi.

| Stage | What it does | Command |
| --- | --- | --- |
| **A — Connection** | Opens the link, sends only feedback queries, prints joint angles, checks the app stays disarmed. **No motion command.** (Opening USB may reboot the board, which runs its start-pose move.) | `ROARM_SERIAL_PORT=/dev/cu.… ROARM_CONFIRM_CONNECT_SAFE=yes cargo test --lib robot::hardware::stage_a -- --ignored --nocapture --test-threads=1` |
| **B — One small move** | Enables motion, moves the base +0.10 rad (≈6°) at ≈5°/s, checks servo feedback reaches it, E-stops if another joint moves > 0.15 rad. Add `ROARM_STAGE_B_DIRECTION=-1` to move back. | `… ROARM_CONFIRM_CONNECT_SAFE=yes ROARM_CONFIRM_MOTION_SAFE=yes cargo test --lib robot::hardware::stage_b -- --ignored --nocapture --test-threads=1` |
| **C — Interlocks** | Disconnect blocks motion; reconnect starts disarmed; an E-stop latched while disconnected blocks re-enabling; the arm's pose does not change. **No motion and no E-stop is sent.** | `… ROARM_CONFIRM_CONNECT_SAFE=yes cargo test --lib robot::hardware::stage_c_ -- --ignored --nocapture` |
| **C2 — Firmware E-stop (supervised)** | Sends `{"T":0}` and logs feedback for 14 s. Only with the arm at a low pose, a hand supporting it, and a second person on the power switch. Record by eye whether it sags and whether it moves when torque returns. | `… ROARM_CONFIRM_CONNECT_SAFE=yes ROARM_CONFIRM_ESTOP_SAFE=yes cargo test --lib robot::hardware::stage_c2 -- --ignored --nocapture` |
| **D — EEG demonstration (in the app)** | Follow the demonstration script above: generate a simulated trial, read the prediction and confidence, pass the gate, connect, enable motion, send one approved command, confirm *Last command: reached, per the arm's servo sensors*. | manual |

Also in the app: unplug the USB cable while connected — expect *connection lost* within about 2 s,
motion disabled, and nothing resent after you plug it back in until you reconnect and re-enable.

## What was checked against the firmware source

- Feedback and command angle conventions match (base/shoulder/elbow/gripper convert to the same
  radians within 0.0015 rad), so "reached" compares like with like.
- `{"T":105}` returns feedback over USB (printed line) and over Wi-Fi (`/js` returns the same
  `T:1051` object). Not yet confirmed on a physical unit.
- The firmware has no motion lock-out after `{"T":0}` (its emergency flag is set but never checked);
  the app's own latch is what blocks further commands.
- Shipped units may run newer factory firmware than the GitHub source; the connect handshake detects a
  different feedback format but not other command differences. Stage A/B on the real arm settles it.

## Troubleshooting

- **"did not answer the RoArm-M2-S feedback query"** — wrong port, arm unpowered, or still booting.
  Wait for the OLED, then retry.
- **"cannot open … in use by another program"** — close Arduino's serial monitor or any other app
  using the port, or re-plug the cable.
- **"… is probably a different device"** (Wi-Fi) — you are on another network that also uses that
  address; join `RoArm-M2`.
- **"outside the app's safe range"** when enabling motion — power-cycle the arm so it returns to its
  start pose.
- **"unsupported firmware"** — the device answered but not with a `T:1051` feedback object. Check the
  firmware is Waveshare's RoArm-M2-S firmware; re-flash from the Waveshare wiki if needed.
- **Arm moved when connecting** — the board rebooted when the port opened (the app logs a warning).
  Use Wi-Fi if this is a problem for the venue.
- **Wi-Fi errors after re-flashing** — Waveshare's FAQ recommends sending `{"T":604}` over serial to
  clear NVS.
