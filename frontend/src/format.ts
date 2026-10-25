export function money(v: number | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined) return "—";
  const abs = Math.abs(v);
  const sym = currency === "USD" ? "$" : currency === "INR" ? "₹" : "";
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}${sym}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${sym}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}${sym}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${sym}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${sym}${abs.toFixed(2)}`;
}

export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`;
}

export function date(s?: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(+d) ? s : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function axisMoney(v: number): string {
  const a = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (a >= 1e12) return `${s}${+(a / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `${s}${+(a / 1e9).toFixed(a >= 1e10 ? 0 : 1)}B`;
  if (a >= 1e6) return `${s}${+(a / 1e6).toFixed(0)}M`;
  if (a >= 1e3) return `${s}${+(a / 1e3).toFixed(0)}K`;
  return `${s}${+a.toFixed(0)}`;
}

export function price(v: number | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined) return "—";
  const sym = currency === "USD" ? "$" : currency === "INR" ? "₹" : "";
  return `${sym}${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function shortDate(s: string, long: boolean): string {
  const d = new Date(s + "T00:00:00");
  return isNaN(+d) ? s : d.toLocaleDateString("en-GB", long ? { month: "short", year: "2-digit" } : { day: "numeric", month: "short" });
}

export function csvDownload(filename: string, rows: (string | number | null | undefined)[][]) {
  const esc = (c: string | number | null | undefined) => {
    const s = c === null || c === undefined ? "" : String(c);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const blob = new Blob([rows.map((r) => r.map(esc).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
