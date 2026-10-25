fn main() {
  tauri_build::try_build(
    tauri_build::Attributes::new().app_manifest(
      tauri_build::AppManifest::new().commands(&[
        "suite_call",
        "robot_list_ports",
        "robot_connect",
        "robot_disconnect",
        "robot_status",
        "robot_arm",
        "robot_disarm",
        "robot_preset",
        "robot_decoder_command",
        "robot_estop",
        "robot_clear_estop",
      ]),
    ),
  )
  .expect("failed to run tauri-build");
}
