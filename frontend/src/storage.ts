import { useCallback, useEffect, useState } from "react";

// Per-browser conveniences only (watchlist, recents, theme). Every access is guarded: storage can be blocked.
function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

export function useStoredList(key: string, max = 20) {
  const [list, setList] = useState<string[]>(() => read<string[]>(key, []));
  useEffect(() => {
    const onChange = (e: Event) => { if ((e as CustomEvent).detail === key) setList(read<string[]>(key, [])); };
    window.addEventListener("fyntra-storage", onChange);
    return () => window.removeEventListener("fyntra-storage", onChange);
  }, [key]);
  const update = useCallback((fn: (l: string[]) => string[]) => {
    const next = fn(read<string[]>(key, [])).slice(0, max);
    write(key, next);
    setList(next);
    window.dispatchEvent(new CustomEvent("fyntra-storage", { detail: key }));
  }, [key, max]);
  return [list, update] as const;
}

export function useWatchlist() {
  const [list, update] = useStoredList("fyntra.watchlist", 30);
  const toggle = (t: string) => update((l) => (l.includes(t) ? l.filter((x) => x !== t) : [...l, t]));
  return { list, toggle, has: (t: string) => list.includes(t) };
}

export function useRecents() {
  const [list, update] = useStoredList("fyntra.recent", 8);
  const add = (t: string) => update((l) => [t, ...l.filter((x) => x !== t)]);
  return { list, add };
}

export type Theme = "light" | "dark";
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (read<Theme>("fyntra.theme", "light") === "dark" ? "dark" : "light"));
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    write("fyntra.theme", theme);
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))] as const;
}
