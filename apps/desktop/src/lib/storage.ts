/** Per-machine UI preferences in localStorage. Every access tolerates storage being unavailable. */

export type ThemeName = "dark" | "light";

export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string | null) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

export function readStoredTheme(): ThemeName {
  const v = readStored("nt-theme");
  return v === "dark" ? "dark" : "light";
}
