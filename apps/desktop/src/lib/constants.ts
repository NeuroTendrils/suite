/** Fixed values the UI sends or offers. Processing parameters here are shown to the user
 *  and must not be changed as part of UI work: they define what the analyses compute. */

export const NEW_SUBJECT = "__new_subject__";
export const NEW_RECORDING = "__new_recording__";

export const EEG_EXTENSIONS = ["fif", "edf", "bdf", "gdf", "set", "vhdr", "cnt", "mat", "txt", "csv", "tsv", "asc"];
export const STREAM_EXTENSIONS = ["txt", "csv", "tsv", "asc", "mat", "npy"];
export const STREAM_MODALITIES = [
  "gyroscope",
  "accelerometer",
  "ecg",
  "emg",
  "eog",
  "eye_tracking",
  "motion",
  "behavioral",
  "trigger",
  "gsr",
  "respiration",
  "misc",
];

/** Fixed parameters the existing UI has always sent. Shown to the user, not changed. */
export const EPOCH_WINDOW = { tmin: -0.2, tmax: 0.8 };
export const ICA_COMPONENTS = 15;
export const CLEAN_Z_THRESH = 5;
