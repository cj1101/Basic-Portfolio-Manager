"""One-shot dev launcher — starts uvicorn + vite together with verbose logs.

Run from the repo root:

    python scripts/dev.py                  # backend + frontend, DEBUG logs
    python scripts/dev.py --no-frontend    # backend only
    python scripts/dev.py --no-backend     # frontend only
    python scripts/dev.py --port 9000      # override backend port

Every stdout/stderr line is prefixed with a colored ``[backend]`` /
``[frontend]`` tag and tee'd to ``backend/.logs/dev-<timestamp>.log`` so
you can rewind after a crash. SIGINT (Ctrl+C) gracefully terminates both
children.

This launcher deliberately uses only the Python standard library so it
works on a clean venv without any new dependency.
"""

from __future__ import annotations

import argparse
import io
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import IO, Any

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
LOG_DIR = BACKEND_DIR / ".logs"

IS_WINDOWS = platform.system().lower().startswith("win")

# ANSI colors — graceful no-op on terminals that don't support them.
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
COLORS = {
    "backend": "\033[38;5;39m",   # cyan-blue
    "frontend": "\033[38;5;213m",  # pink
    "launcher": "\033[38;5;247m",  # grey
}

_shutdown = threading.Event()


def _color(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def _log(tag: str, msg: str, log_file: IO[str]) -> None:
    color = COLORS.get(tag, "")
    prefix = f"[{tag}]".ljust(10)
    line = f"{_color(prefix, color)} {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # Windows terminals commonly use cp1252; replace unsupported symbols
        # (for example Vite's arrow glyph) so the launcher doesn't crash.
        encoding = sys.stdout.encoding or "utf-8"
        safe_line = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_line, flush=True)
    try:
        log_file.write(f"[{datetime.now().isoformat(timespec='seconds')}] {prefix} {msg}\n")
        log_file.flush()
    except Exception:
        pass


def _stream_reader(proc: subprocess.Popen[bytes], tag: str, q: Queue[tuple[str, str]]) -> None:
    assert proc.stdout is not None
    reader = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace")
    try:
        for raw in reader:
            line = raw.rstrip("\r\n")
            if line:
                q.put((tag, line))
            if _shutdown.is_set():
                break
    finally:
        q.put((tag, f"<process exited with code {proc.poll()}>"))


def _locate_backend_command(port: int) -> list[str]:
    """Pick the best way to invoke uvicorn.

    Order: ``uv run uvicorn`` → ``python -m uvicorn``. We leave the cwd to
    the caller (spawn sets cwd=BACKEND_DIR).
    """

    uv_path = shutil.which("uv")
    if uv_path:
        return [
            uv_path,
            "run",
            "--active",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            str(port),
            "--log-level",
            "debug",
        ]
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--port",
        str(port),
        "--log-level",
        "debug",
    ]


def _locate_frontend_command() -> list[str]:
    """Pick the best package manager for Vite dev."""

    pnpm_path = shutil.which("pnpm")
    if pnpm_path:
        # `--` separates pnpm args from the nested vite flags
        return [pnpm_path, "--filter", "portfolio-manager-frontend", "run", "dev"]
    npm_path = shutil.which("npm")
    if npm_path:
        return [npm_path, "--prefix", "frontend", "run", "dev"]
    raise RuntimeError(
        "Neither pnpm nor npm is on PATH. Install one of them to launch the frontend."
    )


def _spawn(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    creationflags = 0
    preexec_fn: Any = None
    if IS_WINDOWS:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        preexec_fn = os.setsid  # type: ignore[assignment]

    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        creationflags=creationflags,
        preexec_fn=preexec_fn,
    )


def _terminate(proc: subprocess.Popen[bytes], tag: str, log_file: IO[str]) -> None:
    if proc.poll() is not None:
        return
    _log("launcher", f"terminating {tag}…", log_file)
    try:
        if IS_WINDOWS:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        _log("launcher", f"{tag} did not exit; killing.", log_file)
        try:
            proc.kill()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Portfolio Manager dev launcher")
    parser.add_argument("--no-backend", action="store_true", help="Skip the FastAPI server.")
    parser.add_argument("--no-frontend", action="store_true", help="Skip the Vite dev server.")
    parser.add_argument("--port", type=int, default=None, help="Backend port (default 8000).")
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        help="App log level exported as LOG_LEVEL (default DEBUG).",
    )
    args = parser.parse_args()

    if args.no_backend and args.no_frontend:
        print("nothing to run; pass neither --no-backend nor --no-frontend.", file=sys.stderr)
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"dev-{ts}.log"
    log_file = log_path.open("w", encoding="utf-8")

    _log("launcher", f"logging to {log_path}", log_file)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["LOG_LEVEL"] = args.log_level
    env.setdefault("UVICORN_LOG_LEVEL", args.log_level.lower())
    # Tell the frontend where to find the backend when running on a non-default port.
    if args.port:
        env.setdefault("VITE_API_BASE_URL", f"http://localhost:{args.port}/api")

    q: Queue[tuple[str, str]] = Queue()
    procs: list[tuple[str, subprocess.Popen[bytes]]] = []

    try:
        if not args.no_backend:
            port = args.port or 8000
            cmd = _locate_backend_command(port)
            _log("launcher", "starting backend: " + " ".join(cmd), log_file)
            proc = _spawn(cmd, BACKEND_DIR, env)
            procs.append(("backend", proc))
            threading.Thread(
                target=_stream_reader, args=(proc, "backend", q), daemon=True
            ).start()

        if not args.no_frontend:
            cmd = _locate_frontend_command()
            _log("launcher", "starting frontend: " + " ".join(cmd), log_file)
            proc = _spawn(cmd, ROOT, env)
            procs.append(("frontend", proc))
            threading.Thread(
                target=_stream_reader, args=(proc, "frontend", q), daemon=True
            ).start()

        _install_signal_handlers(log_file)

        alive_tags = {t for t, _ in procs}
        last_health = time.monotonic()

        while alive_tags and not _shutdown.is_set():
            try:
                tag, line = q.get(timeout=0.5)
            except Exception:
                # timeout — poll children for exit so we don't hang forever.
                for tag, proc in list(procs):
                    if proc.poll() is not None and tag in alive_tags:
                        alive_tags.discard(tag)
                        _log(
                            "launcher",
                            f"{tag} exited with code {proc.returncode}",
                            log_file,
                        )
                # emit a faint heartbeat every 30 s so the user knows we're alive.
                now = time.monotonic()
                if now - last_health > 30:
                    last_health = now
                    _log("launcher", _color("…still running", DIM), log_file)
                continue
            if line.startswith("<process exited"):
                alive_tags.discard(tag)
                _log("launcher", f"{tag} {line}", log_file)
                continue
            _log(tag, line, log_file)
    except KeyboardInterrupt:
        _log("launcher", "KeyboardInterrupt — shutting down.", log_file)
    finally:
        _shutdown.set()
        for tag, proc in procs:
            _terminate(proc, tag, log_file)
        try:
            log_file.flush()
            log_file.close()
        except Exception:
            pass

    return 0


def _install_signal_handlers(log_file: IO[str]) -> None:
    def _handler(signum: int, _frame: Any) -> None:
        _log("launcher", f"received signal {signum}", log_file)
        _shutdown.set()

    signal.signal(signal.SIGINT, _handler)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, _handler)


if __name__ == "__main__":
    sys.exit(main())
