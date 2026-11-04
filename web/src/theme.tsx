import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ConfigProvider, theme as antdTheme } from "antd";
import zhCN from "antd/locale/zh_CN";

export type ThemeMode = "light" | "dark" | "system";
export type AccentKey = "blue" | "cyan" | "purple" | "green";

export interface ThemeSettings {
  mode: ThemeMode;
  accent: AccentKey;
}

const STORAGE_KEY = "satellite_theme";

export const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
  { value: "system", label: "跟随系统" },
];

export const ACCENT_OPTIONS: { key: AccentKey; label: string; color: string }[] = [
  { key: "blue", label: "科技蓝", color: "#1677ff" },
  { key: "cyan", label: "深空青", color: "#13c2c2" },
  { key: "purple", label: "星云紫", color: "#722ed1" },
  { key: "green", label: "生态绿", color: "#52c41a" },
];

const DEFAULT_SETTINGS: ThemeSettings = { mode: "light", accent: "blue" };

function loadSettings(): ThemeSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<ThemeSettings>;
    const mode = ["light", "dark", "system"].includes(parsed.mode || "")
      ? parsed.mode as ThemeMode : DEFAULT_SETTINGS.mode;
    const accent = ACCENT_OPTIONS.some((item) => item.key === parsed.accent)
      ? parsed.accent as AccentKey : DEFAULT_SETTINGS.accent;
    return { mode, accent };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

interface ThemeContextValue extends ThemeSettings {
  resolved: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
  setAccent: (accent: AccentKey) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<ThemeSettings>(loadSettings);
  const [systemDark, setSystemDark] = useState<boolean>(() =>
    window.matchMedia("(prefers-color-scheme: dark)").matches);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const resolved: "light" | "dark" = settings.mode === "system"
    ? (systemDark ? "dark" : "light")
    : settings.mode;
  const accentColor = ACCENT_OPTIONS.find((item) => item.key === settings.accent)?.color
    ?? ACCENT_OPTIONS[0].color;

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.setProperty("--accent", accentColor);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }, [resolved, accentColor, settings]);

  const value = useMemo<ThemeContextValue>(() => ({
    ...settings,
    resolved,
    setMode: (mode) => setSettings((previous) => ({ ...previous, mode })),
    setAccent: (accent) => setSettings((previous) => ({ ...previous, accent })),
  }), [settings, resolved]);

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: resolved === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token: { colorPrimary: accentColor, borderRadius: 8 },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme 必须在 ThemeProvider 内使用");
  return value;
}
