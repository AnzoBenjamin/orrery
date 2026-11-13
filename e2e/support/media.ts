import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = join(tmpdir(), "orrery-e2e-media");

function ffmpeg(out: string, args: string[]): string {
  const path = join(dir, out);
  if (!existsSync(path)) {
    mkdirSync(dir, { recursive: true });
    execFileSync("ffmpeg", ["-loglevel", "error", "-y", ...args, path]);
  }
  return path;
}

/**
 * Real encoded footage made with FFmpeg (in the toolbox image). The synthetic lab's clips with
 * ground truth replace these for analysis tests (platform-foundation task 9.4); upload and probe
 * tests only need genuine video.
 */
export const media = {
  /** 2 s, 320 × 240, 30 fps, H.264 in MP4. */
  shortClip: () =>
    // biome-ignore format: FFmpeg arguments read as flag and value pairs
    ffmpeg("short.mp4", [
      "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-t", "2",
      "-c:v", "libx264", "-pix_fmt", "yuv420p",
    ]),
  /** About 35 MB of lossless noise, so the upload takes several 8 MiB parts. */
  largeClip: () =>
    // biome-ignore format: FFmpeg arguments read as flag and value pairs
    ffmpeg("large.mp4", [
      "-f", "lavfi", "-i", "nullsrc=size=640x360:rate=25,geq=random(1)*255:128:128", "-t", "4",
      "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", "-pix_fmt", "yuv420p",
    ]),
  /** A text file named like a video. */
  disguised: () => {
    const path = join(dir, "notes.mp4");
    mkdirSync(dir, { recursive: true });
    writeFileSync(path, "Bobbin winder seized; hand wheel turns. ".repeat(500));
    return path;
  },
};
