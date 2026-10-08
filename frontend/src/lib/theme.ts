import { useEffect, useState } from "react";

export type ThemePref = "dark" | "light" | "system";
const KEY = "osint.theme";

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "system" ? v : "dark";
  } catch {
    return "dark";
  }
}

const prefersLight = () => window.matchMedia?.("(prefers-color-scheme: light)").matches ?? false;

export function resolveTheme(pref: ThemePref): "dark" | "light" {
  return pref === "system" ? (prefersLight() ? "light" : "dark") : pref;
}

function apply(pref: ThemePref) {
  document.documentElement.dataset.theme = resolveTheme(pref);
}

/** Apply the stored theme before React renders, to avoid a flash. */
export function initTheme() {
  apply(read());
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(read);
  useEffect(() => {
    apply(pref);
    try {
      localStorage.setItem(KEY, pref);
    } catch {
      /* storage unavailable: preference lasts this session only */
    }
    if (pref !== "system") return;
    const mq = window.matchMedia?.("(prefers-color-scheme: light)");
    const onChange = () => apply("system");
    mq?.addEventListener("change", onChange);
    return () => mq?.removeEventListener("change", onChange);
  }, [pref]);
  return { pref, setPref, resolved: resolveTheme(pref) };
}

/** Current resolved theme, kept in sync with the <html data-theme> attribute. */
export function useResolvedTheme(): "dark" | "light" {
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (document.documentElement.dataset.theme as "dark" | "light") ?? "dark",
  );
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme((document.documentElement.dataset.theme as "dark" | "light") ?? "dark"));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return theme;
}
