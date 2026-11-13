import subprocess
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Real encoded media made with FFmpeg, one file per case."""
    root = tmp_path_factory.mktemp("clips")
    h264 = root / "h264.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-t", "2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(h264),
    )  # fmt: skip
    rotated = root / "rotated.mp4"
    ffmpeg("-display_rotation", "90", "-i", str(h264), "-c", "copy", str(rotated))
    webm = root / "vp9.webm"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25", "-t", "1",
        "-c:v", "libvpx-vp9", "-deadline", "realtime", str(webm),
    )  # fmt: skip
    audio = root / "tone.m4a"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:a", "aac", str(audio))
    disguised = root / "notes.mp4"
    disguised.write_text("Bobbin winder seized; hand wheel turns. " * 200)
    gif = root / "loop.gif"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x48:rate=10", "-t", "1", str(gif))
    return {
        "h264": h264,
        "rotated": rotated,
        "webm": webm,
        "audio": audio,
        "disguised": disguised,
        "gif": gif,
    }


@pytest.fixture(scope="session")
def file_server(clips: dict[str, Path]) -> Iterator[str]:
    """A real HTTP server for the clips, standing in for the object store's presigned GETs."""
    directory = next(iter(clips.values())).parent
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
