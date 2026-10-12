import { useEffect, useState } from "react";
import { readStored, readStoredTheme, writeStored, type ThemeName } from "../lib/storage";

/** Per-machine display preferences (theme, navigation rail), persisted in localStorage. */
export function usePreferences() {
  const [theme, setTheme] = useState<ThemeName>(readStoredTheme);
  const [sidebarOpen, setSidebarOpen] = useState(() => readStored("nt-sidebar") !== "0");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writeStored("nt-theme", theme);
  }, [theme]);

  useEffect(() => {
    writeStored("nt-sidebar", sidebarOpen ? "1" : "0");
  }, [sidebarOpen]);

  return {
    theme,
    toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    sidebarOpen,
    toggleSidebar: () => setSidebarOpen((v) => !v),
  };
}
