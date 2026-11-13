/** Display formatting. Stored values are SI (seconds, bytes); conversion happens only here. */

const bytesFormat = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  const units = ["kB", "MB", "GB", "TB"];
  let value = bytes / 1000;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${bytesFormat.format(value)} ${units[unit]}`;
}

/** 83.4 → "1:23". */
export function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

export function formatFps(fps: number): string {
  return `${Number.isInteger(fps) ? fps : fps.toFixed(2)} fps`;
}
