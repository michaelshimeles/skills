#!/usr/bin/env python3
"""Create and verify annotated UI evidence recordings.

Works on Linux (X11 via x11grab, Wayland via wf-recorder), macOS (avfoundation)
and Windows (gdigrab). The raw capture is written as MPEG-TS so that a hard
stop — SIGKILL, TerminateProcess, a crashed recorder — still leaves a playable,
probe-able file; `stop` remuxes or re-encodes it into a standard MP4.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Sequence

try:  # POSIX advisory locks
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
try:  # Windows byte-range locks
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]
try:
    import select
except ImportError:  # pragma: no cover
    select = None  # type: ignore[assignment]


ANNOTATION_TYPES = ("setup", "test_start", "assertion")
ASSERTION_RESULTS = ("passed", "failed", "untested")
CAPTURE_SOURCES = ("auto", "x11", "wayland", "avfoundation", "gdigrab", "test")
RAW_CONTAINER = "ts"  # MPEG-TS survives an unclean recorder exit; see module docstring
IDENTITY_POLL_SECONDS = {"linux": 0.05, "darwin": 0.1, "windows": 0.5}
SUBPROCESS_FLAGS: dict[str, Any] = {}
if sys.platform == "win32":  # pragma: no cover - Windows
    SUBPROCESS_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW


class EvidenceError(RuntimeError):
    """A user-actionable evidence workflow failure."""


def platform_name() -> str:
    """Return linux / darwin / windows (monkeypatched in tests)."""
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform in ("win32", "cygwin"):
        return "windows"
    return sys.platform


# --------------------------------------------------------------------------- #
# Toolchain and capture-source detection
# --------------------------------------------------------------------------- #


def executable_status(name: str) -> dict[str, object]:
    path = shutil.which(name)
    return {"available": path is not None, "path": path}


def ffmpeg_output(*arguments: str) -> str:
    if not shutil.which("ffmpeg"):
        return ""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", *arguments],
        text=True,
        capture_output=True,
        check=False,
        **SUBPROCESS_FLAGS,
    )
    return result.stdout + result.stderr


def ffmpeg_capability(argument: str, needle: str) -> dict[str, object]:
    if not shutil.which("ffmpeg"):
        return {"available": False}
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", argument],
        text=True,
        capture_output=True,
        check=False,
        **SUBPROCESS_FLAGS,
    )
    output = result.stdout + result.stderr
    return {"available": result.returncode == 0 and needle in output}


def ffmpeg_has_device(name: str) -> bool:
    return re.search(rf"^\s*[D ]E?\s+{re.escape(name)}\b", ffmpeg_output("-devices"), re.MULTILINE) is not None


def dependency_status() -> dict[str, Any]:
    ffmpeg = executable_status("ffmpeg")
    ffprobe = executable_status("ffprobe")
    libx264 = ffmpeg_capability("-encoders", "libx264")
    ass_filter = ffmpeg_capability("-filters", " ass ")
    ready = all(bool(item["available"]) for item in (ffmpeg, ffprobe, libx264, ass_filter))
    return {
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "libx264": libx264,
        "ass_filter": ass_filter,
        "ready": ready,
    }


def detect_avfoundation_screens() -> list[dict[str, Any]]:
    """List macOS screen-capture devices as exposed by ffmpeg's avfoundation input."""
    if platform_name() != "darwin" or not shutil.which("ffmpeg"):
        return []
    output = ffmpeg_output("-f", "avfoundation", "-list_devices", "true", "-i", "")
    screens = []
    for match in re.finditer(r"\[(\d+)\]\s+(Capture screen \d+)", output):
        screens.append({"index": int(match.group(1)), "name": match.group(2)})
    return screens


def capture_status() -> dict[str, Any]:
    """Per-source availability on this machine, plus the source `auto` would pick."""
    system = platform_name()
    display = os.environ.get("DISPLAY")
    wayland = os.environ.get("WAYLAND_DISPLAY")
    sources: dict[str, dict[str, Any]] = {
        "x11": {
            "available": system == "linux" and bool(display) and ffmpeg_has_device("x11grab"),
            "display": display,
            "hint": "needs DISPLAY (X11 or XWayland) and an ffmpeg built with x11grab",
        },
        "wayland": {
            "available": system == "linux" and bool(wayland) and shutil.which("wf-recorder") is not None,
            "display": wayland,
            "hint": "needs WAYLAND_DISPLAY and wf-recorder (wlroots compositors: Sway, Hyprland, ...)",
        },
        "avfoundation": {
            "available": False,
            "screens": [],
            "hint": "macOS only; grant Screen Recording permission to the terminal/agent host app",
        },
        "gdigrab": {
            "available": system == "windows" and ffmpeg_has_device("gdigrab"),
            "hint": "Windows only; needs an ffmpeg built with gdigrab (all standard builds)",
        },
    }
    if system == "darwin":
        screens = detect_avfoundation_screens()
        sources["avfoundation"]["screens"] = screens
        sources["avfoundation"]["available"] = bool(screens)
    default = default_source(sources)
    return {"platform": system, "default_source": default, "sources": sources, "capture_ready": default is not None}


def default_source(sources: dict[str, dict[str, Any]] | None = None) -> str | None:
    sources = sources if sources is not None else capture_status()["sources"]
    system = platform_name()
    order = {"linux": ("x11", "wayland"), "darwin": ("avfoundation",), "windows": ("gdigrab",)}.get(system, ())
    for name in order:
        if sources[name]["available"]:
            return name
    return None


def resolve_source(requested: str) -> str:
    if requested != "auto":
        return requested
    status = capture_status()
    if status["default_source"] is None:
        hints = "; ".join(
            f"{name}: {info['hint']}"
            for name, info in status["sources"].items()
            if name in {"linux": ("x11", "wayland"), "darwin": ("avfoundation",), "windows": ("gdigrab",)}.get(status["platform"], ())
        )
        raise EvidenceError(f"no usable screen-capture source on {status['platform']} ({hints})")
    return status["default_source"]


# --------------------------------------------------------------------------- #
# Session persistence
# --------------------------------------------------------------------------- #


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


@contextlib.contextmanager
def session_lock(session_path: Path) -> Iterator[None]:
    """Serialize read-modify-write updates to a session across processes.

    atomic_write_json prevents torn files but not lost updates: two `annotate`
    commands can both load the same session, append locally, and the second
    replace discards the first. A lock held across load + write makes each
    mutation a transaction. POSIX uses flock; Windows uses msvcrt byte locks.
    """
    lock_path = session_path.with_suffix(session_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:  # pragma: no cover - Windows
            lock_file.seek(0)
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover
            yield


def load_session(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as error:
        raise EvidenceError(f"session not found: {path}") from error
    except json.JSONDecodeError as error:
        raise EvidenceError(f"invalid session JSON: {path}: {error}") from error


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


def command_doctor(as_json: bool) -> int:
    payload = dependency_status()
    capture = capture_status()
    payload["platform"] = capture["platform"]
    payload["capture"] = capture
    payload["capture_ready"] = capture["capture_ready"]
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"platform: {payload['platform']}")
        for name in ("ffmpeg", "ffprobe", "libx264", "ass_filter"):
            status = payload[name]
            assert isinstance(status, dict)
            marker = "ok" if status["available"] else "missing"
            location = f" ({status['path']})" if status.get("path") else ""
            print(f"{name}: {marker}{location}")
        print(f"ready: {'yes' if payload['ready'] else 'no'}  (toolchain)")
        for name, info in capture["sources"].items():
            marker = "ok" if info["available"] else "unavailable"
            extra = ""
            if info.get("screens"):
                extra = " " + ", ".join(f"[{s['index']}] {s['name']}" for s in info["screens"])
            print(f"capture/{name}: {marker}{extra}")
        chosen = capture["default_source"] or "none"
        print(f"capture_ready: {'yes' if capture['capture_ready'] else 'no'}  (auto source: {chosen})")
        if not capture["capture_ready"]:
            for name, info in capture["sources"].items():
                if name in {"linux": ("x11", "wayland"), "darwin": ("avfoundation",), "windows": ("gdigrab",)}.get(capture["platform"], ()):
                    print(f"  {name}: {info['hint']}")
    return 0 if payload["ready"] else 1


# --------------------------------------------------------------------------- #
# Recorder command construction
# --------------------------------------------------------------------------- #


def encoder_arguments(framerate: int) -> list[str]:
    return [
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(framerate),  # a keyframe every second bounds what an unclean stop can lose
        "-flush_packets",
        "1",
        "-f",
        "mpegts",
    ]


def recorder_command(args: argparse.Namespace, raw_video: Path, source: str) -> list[str]:
    common = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    framerate = int(args.framerate)
    geometry = getattr(args, "geometry", None)
    offset = getattr(args, "offset", None) or "0,0"

    if source == "test":
        size = geometry or "1280x720"
        return common + ["-re", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={framerate}"] + encoder_arguments(framerate) + [str(raw_video)]

    if source == "x11":
        display = args.display or os.environ.get("DISPLAY")
        if not display:
            raise EvidenceError("X11 recording requires --display or DISPLAY")
        grab = ["-f", "x11grab", "-framerate", str(framerate), "-draw_mouse", "1"]
        if geometry:
            grab += ["-video_size", geometry]
        grab += ["-i", f"{display}+{offset}"]
        return common + grab + encoder_arguments(framerate) + [str(raw_video)]

    if source == "wayland":
        if not shutil.which("wf-recorder"):
            raise EvidenceError("Wayland recording requires wf-recorder on PATH")
        command = [
            "wf-recorder",
            "-m",
            "mpegts",
            "-c",
            "libx264",
            "-p",
            "preset=ultrafast",
            "-p",
            "crf=20",
            "-x",
            "yuv420p",
            "-r",
            str(framerate),
        ]
        if geometry:
            x, y = offset.split(",")
            command += ["-g", f"{x},{y} {geometry}"]
        if getattr(args, "output_name", None):
            command += ["-o", args.output_name]
        return command + ["-f", str(raw_video)]

    if source == "avfoundation":
        index = args.screen_index
        if index is None:
            screens = detect_avfoundation_screens()
            if not screens:
                raise EvidenceError("no avfoundation screen device found; is Screen Recording permission granted?")
            index = screens[0]["index"]
        grab = ["-f", "avfoundation", "-framerate", str(framerate), "-capture_cursor", "1", "-i", f"{index}:none"]
        # Screens can have odd dimensions; yuv420p needs even ones.
        scale = ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        return common + grab + scale + encoder_arguments(framerate) + [str(raw_video)]

    if source == "gdigrab":
        grab = ["-f", "gdigrab", "-framerate", str(framerate), "-draw_mouse", "1"]
        if geometry:
            x, y = offset.split(",")
            grab += ["-offset_x", x, "-offset_y", y, "-video_size", geometry]
        grab += ["-i", "desktop"]
        return common + grab + encoder_arguments(framerate) + [str(raw_video)]

    raise EvidenceError(f"unsupported source: {source}")


def recorder_environment(args: argparse.Namespace, source: str) -> dict[str, str]:
    env = os.environ.copy()
    if source == "x11":
        display = args.display or os.environ.get("DISPLAY")
        if display:
            env["DISPLAY"] = display
        if args.xauthority:
            env["XAUTHORITY"] = args.xauthority
    return env


def spawn_recorder(command: list[str], log_file: Any, env: dict[str, str]) -> subprocess.Popen[bytes]:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if platform_name() == "windows":  # pragma: no cover - Windows
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


# --------------------------------------------------------------------------- #
# Process identity (so we never signal a PID that has been reused)
# --------------------------------------------------------------------------- #


def process_identity(pid: int) -> dict[str, Any] | None:
    """Describe the live process at `pid` well enough to notice PID reuse, or None if gone."""
    system = platform_name()
    if system == "linux":
        return _identity_linux(pid)
    if system == "windows":
        return _identity_windows(pid)
    return _identity_ps(pid)


def _identity_linux(pid: int) -> dict[str, Any] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    except OSError as error:
        raise EvidenceError(f"cannot inspect recorder process {pid}: {error}") from error
    try:
        fields = stat.rsplit(")", 1)[1].strip().split()
        if fields[0] == "Z":
            return None
        return {
            "pid": pid,
            "process_group_id": int(fields[2]),
            "start_time_ticks": int(fields[19]),
        }
    except (IndexError, ValueError) as error:
        raise EvidenceError(f"cannot parse recorder process identity for PID {pid}") from error


def parse_ps_identity(pid: int, output: str) -> dict[str, Any] | None:
    """Parse `ps -o pgid= -o lstart= -o stat= -p PID` output (macOS, BSD, Linux fallback)."""
    line = output.strip()
    if not line:
        return None
    parts = line.split(None, 1)
    if len(parts) < 2:
        raise EvidenceError(f"cannot parse recorder process identity for PID {pid}: {line!r}")
    rest = parts[1].rsplit(None, 1)
    started, state = (rest[0], rest[1]) if len(rest) == 2 else (rest[0], "")
    if state.startswith("Z"):
        return None
    try:
        return {"pid": pid, "process_group_id": int(parts[0]), "started": started.strip()}
    except ValueError as error:
        raise EvidenceError(f"cannot parse recorder process identity for PID {pid}: {line!r}") from error


def _identity_ps(pid: int) -> dict[str, Any] | None:
    result = subprocess.run(
        ["ps", "-o", "pgid=", "-o", "lstart=", "-o", "stat=", "-p", str(pid)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 and not result.stdout.strip():
        return None
    return parse_ps_identity(pid, result.stdout)


WINDOWS_IDENTITY_SCRIPT = (
    "$p = Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; "
    "if ($p) {{ '{{0}}|{{1}}' -f $p.CreationDate.ToFileTimeUtc(), $p.ParentProcessId }}"
)


def parse_windows_identity(pid: int, output: str) -> dict[str, Any] | None:
    line = output.strip()
    if not line:
        return None
    try:
        creation, parent = line.split("|")
        return {"pid": pid, "creation_filetime": int(creation), "parent_pid": int(parent)}
    except ValueError as error:
        raise EvidenceError(f"cannot parse recorder process identity for PID {pid}: {line!r}") from error


def _identity_windows(pid: int) -> dict[str, Any] | None:  # pragma: no cover - Windows
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_IDENTITY_SCRIPT.format(pid=pid)],
        text=True,
        capture_output=True,
        check=False,
        **SUBPROCESS_FLAGS,
    )
    if result.returncode != 0:
        raise EvidenceError(f"cannot inspect recorder process {pid}: {result.stderr.strip()}")
    return parse_windows_identity(pid, result.stdout)


def process_exists(pid: int) -> bool:
    return process_identity(pid) is not None


def identity_matches(expected: dict[str, Any], current: dict[str, Any]) -> bool:
    """True only if every field of the live identity equals the stored one."""
    return all(key in expected and str(expected[key]) == str(current[key]) for key in current)


def wait_for_original_exit(expected: dict[str, Any], timeout_seconds: float) -> bool:
    """Poll until the recorded process is gone (or its PID belongs to someone else)."""
    interval = IDENTITY_POLL_SECONDS.get(platform_name(), 0.1)
    deadline = time.monotonic() + timeout_seconds
    while True:
        current = process_identity(int(expected["pid"]))
        if current is None or not identity_matches(expected, current):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


# --------------------------------------------------------------------------- #
# Stopping the recorder
# --------------------------------------------------------------------------- #


def wait_for_pidfd(pidfd: int, timeout_seconds: float) -> bool:
    poller = select.poll()
    poller.register(pidfd, select.POLLIN)
    return bool(poller.poll(max(1, round(timeout_seconds * 1000))))


def stop_recorder(expected: dict[str, Any], grace_seconds: float = 3.0) -> None:
    """Stop the recorder described by `expected`, escalating gently, verifying exit.

    Refuses to signal when the live process at that PID is not the one we
    started. Linux uses a pidfd so the check and the signal cannot race.
    """
    system = platform_name()
    if system == "linux" and hasattr(os, "pidfd_open"):
        _stop_linux(expected, grace_seconds)
    elif system == "windows":
        _stop_windows(expected, grace_seconds)
    else:
        _stop_posix(expected, grace_seconds)


def _check_identity_or_raise(expected: dict[str, Any]) -> dict[str, Any] | None:
    pid = int(expected["pid"])
    current = process_identity(pid)
    if current is None:
        return None
    if not identity_matches(expected, current):
        raise EvidenceError(f"recorder identity does not match live PID {pid}; refusing to signal it")
    return current


def _stop_linux(expected: dict[str, Any], grace_seconds: float) -> None:
    pid = int(expected["pid"])
    try:
        pidfd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        current = _check_identity_or_raise(expected)
        if current is None:
            return
        if current["process_group_id"] != int(expected["process_group_id"]):
            raise EvidenceError(f"recorder process-group identity changed for PID {pid}")
        escalation = (
            (signal.SIGINT, grace_seconds),
            (signal.SIGTERM, grace_seconds),
            (signal.SIGKILL, max(1.0, grace_seconds)),
        )
        for stop_signal, timeout in escalation:
            try:
                signal.pidfd_send_signal(pidfd, stop_signal)
            except ProcessLookupError:
                return
            if wait_for_pidfd(pidfd, timeout):
                return
        raise EvidenceError(f"recorder PID {pid} remained alive after SIGKILL")
    finally:
        os.close(pidfd)


def _stop_posix(expected: dict[str, Any], grace_seconds: float) -> None:
    """macOS / BSD: os.kill with an identity re-check before every signal."""
    pid = int(expected["pid"])
    escalation = (
        (signal.SIGINT, grace_seconds),
        (signal.SIGTERM, grace_seconds),
        (signal.SIGKILL, max(1.0, grace_seconds)),
    )
    for stop_signal, timeout in escalation:
        if _check_identity_or_raise(expected) is None:
            return
        try:
            os.kill(pid, stop_signal)
        except ProcessLookupError:
            return
        if wait_for_original_exit(expected, timeout):
            return
    raise EvidenceError(f"recorder PID {pid} remained alive after SIGKILL")


def _stop_windows(expected: dict[str, Any], grace_seconds: float) -> None:  # pragma: no cover - Windows
    """Windows: Ctrl+Break lets ffmpeg flush; TerminateProcess is the fallback.

    Ctrl+Break only reaches a process that shares our console, which is why
    the raw capture is MPEG-TS: a TerminateProcess'd recorder still leaves a
    playable file.
    """
    pid = int(expected["pid"])
    attempts: list[tuple[int, float]] = []
    ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
    if ctrl_break is not None:
        attempts.append((ctrl_break, grace_seconds))
    attempts.append((signal.SIGTERM, max(1.0, grace_seconds)))  # TerminateProcess on Windows
    for stop_signal, timeout in attempts:
        if _check_identity_or_raise(expected) is None:
            return
        try:
            os.kill(pid, stop_signal)
        except (ProcessLookupError, OSError, SystemError):
            if stop_signal == signal.SIGTERM:
                if wait_for_original_exit(expected, 0.5):
                    return
                raise
            continue  # no shared console: Ctrl+Break is impossible, fall through
        if wait_for_original_exit(expected, timeout):
            return
    raise EvidenceError(f"recorder PID {pid} remained alive after TerminateProcess")


# --------------------------------------------------------------------------- #
# start / annotate
# --------------------------------------------------------------------------- #


def wait_for_recorder(expected: dict[str, Any], raw_video: Path, log_path: Path, timeout_seconds: float = 10.0) -> None:
    pid = int(expected["pid"])
    deadline = time.monotonic() + timeout_seconds
    interval = IDENTITY_POLL_SECONDS.get(platform_name(), 0.1)
    while time.monotonic() < deadline:
        current = process_identity(pid)
        if current is None:
            details = log_path.read_text(errors="replace") if log_path.exists() else ""
            raise EvidenceError(f"recorder exited during startup: {details.strip()}")
        if not identity_matches(expected, current):
            raise EvidenceError(f"recorder identity changed during startup for PID {pid}")
        if raw_video.exists() and raw_video.stat().st_size > 0:
            return
        time.sleep(interval)
    raise EvidenceError(f"recorder did not create {raw_video} within {timeout_seconds:g} seconds")


def command_start(args: argparse.Namespace) -> int:
    dependencies = dependency_status()
    if not dependencies["ready"]:
        missing = ", ".join(
            name for name in ("ffmpeg", "ffprobe", "libx264", "ass_filter") if not dependencies[name]["available"]
        )
        raise EvidenceError(f"recording dependencies are missing: {missing}")
    source = resolve_source(args.source)

    output_root = Path(args.output).expanduser().resolve()
    session_dir = output_root / f"evidence-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    session_dir.mkdir(parents=True)
    raw_video = session_dir / f"raw.{RAW_CONTAINER}"
    log_path = session_dir / "recorder.log"
    session_path = session_dir / "session.json"
    command = recorder_command(args, raw_video, source)

    with log_path.open("wb") as log_file:
        process = spawn_recorder(command, log_file, recorder_environment(args, source))

    started_epoch = time.time()
    identity = process_identity(process.pid)
    session: dict[str, Any] = {
        "schema_version": 3,
        "status": "recording",
        "title": args.title,
        "commit": args.commit,
        "branch": args.branch,
        "environment": args.environment,
        "platform": platform_name(),
        "source": source,
        "started_at": utc_now(),
        "started_epoch": started_epoch,
        "recorder_pid": process.pid,
        "recorder_identity": identity,
        "recorder_command": command,
        "raw_video": str(raw_video),
        "annotations": [],
    }
    atomic_write_json(session_path, session)
    if identity is None:
        session["status"] = "startup_failed"
        session["failed_at"] = utc_now()
        session["failure"] = "recorder exited before its identity could be captured"
        atomic_write_json(session_path, session)
        raise EvidenceError(session["failure"])
    try:
        wait_for_recorder(identity, raw_video, log_path)
    except Exception as error:
        stop_failure = None
        try:
            stop_recorder(identity)
        except EvidenceError as stop_error:
            stop_failure = str(stop_error)
        session["status"] = "startup_failed"
        session["failed_at"] = utc_now()
        session["failure"] = str(error)
        if stop_failure:
            session["stop_failure"] = stop_failure
        atomic_write_json(session_path, session)
        if isinstance(error, EvidenceError):
            raise
        raise EvidenceError(f"recorder startup failed: {error}") from error
    print(json.dumps({"session": str(session_path), "pid": process.pid, "source": source}))
    return 0


def command_annotate(args: argparse.Namespace) -> int:
    session_path = Path(args.session).expanduser().resolve()
    message = args.message.strip()
    if not message:
        raise EvidenceError("annotation message cannot be empty")
    if len(message) > 80:
        raise EvidenceError("annotation message must be 80 characters or fewer")
    if args.type == "assertion" and not args.result:
        raise EvidenceError("--result is required for assertion annotations")
    if args.type != "assertion" and args.result:
        raise EvidenceError("--result is only valid for assertion annotations")

    with session_lock(session_path):
        session = load_session(session_path)
        if session.get("status") != "recording":
            raise EvidenceError("annotations can only be added while recording")
        annotation: dict[str, Any] = {
            "type": args.type,
            "message": message,
            "timestamp_seconds": round(max(0.0, time.time() - float(session["started_epoch"])), 3),
            "created_at": utc_now(),
        }
        if args.result:
            annotation["result"] = args.result
        session["annotations"].append(annotation)
        atomic_write_json(session_path, session)
    print(json.dumps(annotation, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- #
# Rendering and verification
# --------------------------------------------------------------------------- #


def probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height:format=duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
        **SUBPROCESS_FLAGS,
    )
    if result.returncode != 0:
        raise EvidenceError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams:
        raise EvidenceError(f"recording has no video stream: {path}")
    duration = float(payload.get("format", {}).get("duration", 0) or 0)
    if duration <= 0:
        raise EvidenceError(f"recording duration is not positive: {path}")
    stream = streams[0]
    return {
        "duration_seconds": duration,
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "size_bytes": path.stat().st_size,
    }


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def ass_font() -> str:
    return {"darwin": "Helvetica", "windows": "Arial"}.get(platform_name(), "DejaVu Sans")


def write_annotations(path: Path, annotations: list[dict[str, Any]], duration: float) -> None:
    font = ass_font()
    style_line = "Style: {name},{font},30,{colour},{colour},&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,38,1"
    colours = {
        "setup": "&H00FFFFFF",
        "test_start": "&H0000FFFF",
        "passed": "&H0048E06B",
        "failed": "&H004C4CFF",
        "untested": "&H0000A5FF",
    }
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1280",
            "PlayResY: 720",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            *[style_line.format(name=name, font=font, colour=colour) for name, colour in colours.items()],
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            "",
        ]
    )
    events: list[str] = []
    for index, annotation in enumerate(annotations):
        start = min(float(annotation["timestamp_seconds"]), max(0.0, duration - 0.1))
        next_start = duration
        if index + 1 < len(annotations):
            next_start = float(annotations[index + 1]["timestamp_seconds"])
        end = min(duration, max(start + 0.5, min(start + 3.0, next_start)))
        kind = annotation["type"]
        style = annotation.get("result", kind)
        prefix = {
            "setup": "SETUP",
            "test_start": "TEST",
            "passed": "PASSED",
            "failed": "FAILED",
            "untested": "UNTESTED",
        }[style]
        text = ass_escape(f"{prefix} · {annotation['message']}")
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def filter_path(path: Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter argument."""
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def render_video(raw_video: Path, final_video: Path, subtitles: Path, has_annotations: bool) -> None:
    common = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-i", str(raw_video)]
    if has_annotations:
        encode = [
            "-vf",
            f"ass='{filter_path(subtitles)}'",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
    else:
        encode = ["-an", "-c:v", "copy"]  # remux the MPEG-TS capture into a seekable MP4
    result = subprocess.run(
        common + encode + ["-movflags", "+faststart", str(final_video)],
        text=True,
        capture_output=True,
        check=False,
        **SUBPROCESS_FLAGS,
    )
    if result.returncode != 0:
        raise EvidenceError(f"annotation render failed: {result.stderr.strip()}")


def write_report(path: Path, session: dict[str, Any], verification: dict[str, Any]) -> None:
    annotations = session["annotations"]
    assertions = [item for item in annotations if item["type"] == "assertion"]
    counts = {result: sum(item.get("result") == result for item in assertions) for result in ASSERTION_RESULTS}
    lines = [
        f"# {session['title']}",
        "",
        "## Tested artifact",
        "",
        f"- Commit: `{session['commit']}`",
        f"- Branch: `{session['branch']}`",
        f"- Environment: {session['environment']}",
        f"- Recorder: {session.get('platform', 'unknown')} / {session.get('source', 'unknown')}",
        f"- Recording: `evidence.mp4` ({verification['duration_seconds']:.2f}s)",
        "",
        "## Result",
        "",
        f"- Passed: {counts['passed']}",
        f"- Failed: {counts['failed']}",
        f"- Untested: {counts['untested']}",
        "",
        "## Timeline",
        "",
    ]
    if not annotations:
        lines.append("No annotations were recorded.")
    for annotation in annotations:
        timestamp = float(annotation["timestamp_seconds"])
        if annotation["type"] == "assertion":
            label = annotation["result"].upper()
        else:
            label = annotation["type"].upper()
        lines.append(f"- `{timestamp:06.2f}s` **{label}** — {annotation['message']}")
    lines.extend(["", "## Caveats", "", "- None recorded. Add manual caveats before publishing if needed.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# stop
# --------------------------------------------------------------------------- #


def command_stop(args: argparse.Namespace) -> int:
    session_path = Path(args.session).expanduser().resolve()
    with session_lock(session_path):
        return finalize_session(session_path)


def finalize_session(session_path: Path) -> int:
    session = load_session(session_path)
    status = session.get("status")
    if status == "recording":
        try:
            identity = session.get("recorder_identity")
            if not isinstance(identity, dict):
                raise EvidenceError("session has no validated recorder identity; refusing to signal a PID")
            stop_recorder(identity)
        except EvidenceError as error:
            # The recorder can no longer be signalled safely (PID reused, identity
            # missing, or it survived the last-resort kill). Persist that instead of
            # leaving the session stuck in "recording"; a later `stop` skips the
            # signal and finalizes whatever the recorder managed to write.
            session["status"] = "recorder_lost"
            session["failed_at"] = utc_now()
            session["failure"] = str(error)
            atomic_write_json(session_path, session)
            raise EvidenceError(
                f"{error}; session marked recorder_lost — run `stop` again to finalize the captured video"
            ) from error
        session["status"] = "recorded"
        session["stopped_at"] = utc_now()
        session.pop("failure", None)
        atomic_write_json(session_path, session)
    elif status == "recorder_lost":
        # Only finalize once the original recorder is confirmed gone. If the same
        # process is still alive it may still be writing the raw capture, and
        # rendering now would publish truncated evidence.
        identity = session.get("recorder_identity")
        if isinstance(identity, dict):
            current = process_identity(int(identity["pid"]))
            if current is not None and identity_matches(identity, current):
                raise EvidenceError(
                    f"recorder PID {identity['pid']} is still running; stop it before finalizing "
                    "(session stays recorder_lost)"
                )
    elif status not in ("recorded", "finalizing", "finalization_failed"):
        raise EvidenceError(f"session cannot be finalized (status: {status})")

    session["status"] = "finalizing"
    session.pop("failure", None)
    atomic_write_json(session_path, session)

    raw_video = Path(session["raw_video"])
    session_dir = session_path.parent
    subtitles = session_dir / "annotations.ass"
    final_video = session_dir / "evidence.mp4"
    report = session_dir / "report.md"
    manifest = session_dir / "manifest.json"

    try:
        raw_verification = probe_video(raw_video)
        write_annotations(subtitles, session["annotations"], raw_verification["duration_seconds"])
        render_video(raw_video, final_video, subtitles, bool(session["annotations"]))
        verification = probe_video(final_video)
        write_report(report, session, verification)
    except Exception as error:
        session["status"] = "finalization_failed"
        session["failed_at"] = utc_now()
        session["failure"] = str(error)
        atomic_write_json(session_path, session)
        if isinstance(error, EvidenceError):
            raise
        raise EvidenceError(f"finalization failed: {error}") from error

    session["status"] = "finalized"
    session["finalized_at"] = utc_now()
    session["video"] = str(final_video)
    session["report"] = str(report)
    session["verification"] = verification
    session.pop("failure", None)
    atomic_write_json(session_path, session)
    atomic_write_json(manifest, session)
    print(
        json.dumps(
            {
                "video": str(final_video),
                "report": str(report),
                "manifest": str(manifest),
                "verified": True,
                "verification": verification,
            },
            sort_keys=True,
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check recording dependencies and capture sources")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    start = subparsers.add_parser("start", help="Start a recording session")
    start.add_argument("--output", required=True, help="Directory for evidence artifacts")
    start.add_argument(
        "--source",
        choices=CAPTURE_SOURCES,
        default="auto",
        help="auto picks x11/wayland on Linux, avfoundation on macOS, gdigrab on Windows; test is a synthetic pattern",
    )
    start.add_argument("--display", help="X11 display (x11 source); defaults to DISPLAY")
    start.add_argument("--xauthority", help="X11 authority file (x11 source); defaults to XAUTHORITY")
    start.add_argument("--screen-index", type=int, dest="screen_index", help="avfoundation screen device index (see doctor)")
    start.add_argument("--output-name", dest="output_name", help="Wayland output name to record (wf-recorder -o)")
    start.add_argument("--geometry", help="Capture size WIDTHxHEIGHT; default is the full screen")
    start.add_argument("--offset", default="0,0", help="Capture offset X,Y (x11, wayland, gdigrab)")
    start.add_argument("--framerate", type=int, default=30)
    start.add_argument("--title", default="UI evidence")
    start.add_argument("--commit", default="unknown")
    start.add_argument("--branch", default="unknown")
    start.add_argument("--environment", default="local")

    annotate = subparsers.add_parser("annotate", help="Add a timestamped annotation")
    annotate.add_argument("session")
    annotate.add_argument("--type", choices=ANNOTATION_TYPES, required=True)
    annotate.add_argument("--message", required=True)
    annotate.add_argument("--result", choices=ASSERTION_RESULTS)

    stop = subparsers.add_parser("stop", help="Stop, render, and verify evidence")
    stop.add_argument("session")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return command_doctor(args.as_json)
        if args.command == "start":
            return command_start(args)
        if args.command == "annotate":
            return command_annotate(args)
        if args.command == "stop":
            return command_stop(args)
        raise AssertionError(f"Unhandled command: {args.command}")
    except EvidenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
