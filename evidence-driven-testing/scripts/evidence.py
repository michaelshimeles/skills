#!/usr/bin/env python3
"""Create and verify annotated UI evidence recordings."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Sequence


ANNOTATION_TYPES = ("setup", "test_start", "assertion")
ASSERTION_RESULTS = ("passed", "failed", "untested")


class EvidenceError(RuntimeError):
    """A user-actionable evidence workflow failure."""


def executable_status(name: str) -> dict[str, object]:
    path = shutil.which(name)
    return {"available": path is not None, "path": path}


def ffmpeg_capability(argument: str, needle: str) -> dict[str, object]:
    if not shutil.which("ffmpeg"):
        return {"available": False}
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", argument],
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    return {"available": result.returncode == 0 and needle in output}


def dependency_status() -> dict[str, Any]:
    ffmpeg = executable_status("ffmpeg")
    ffprobe = executable_status("ffprobe")
    libx264 = ffmpeg_capability("-encoders", "libx264")
    ass_filter = ffmpeg_capability("-filters", " ass ")
    ready = all(
        bool(item["available"])
        for item in (ffmpeg, ffprobe, libx264, ass_filter)
    )
    return {
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "libx264": libx264,
        "ass_filter": ass_filter,
        "ready": ready,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


@contextlib.contextmanager
def session_lock(session_path: Path):
    """Serialize read-modify-write updates to a session across processes.

    atomic_write_json prevents torn files but not lost updates: two `annotate`
    commands can both load the same session, append locally, and the second
    replace discards the first. An advisory lock held across load + write
    makes each mutation a transaction.
    """
    lock_path = session_path.with_suffix(session_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_session(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as error:
        raise EvidenceError(f"session not found: {path}") from error
    except json.JSONDecodeError as error:
        raise EvidenceError(f"invalid session JSON: {path}: {error}") from error


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def command_doctor(as_json: bool) -> int:
    payload = dependency_status()
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name in ("ffmpeg", "ffprobe", "libx264", "ass_filter"):
            status = payload[name]
            assert isinstance(status, dict)
            marker = "ok" if status["available"] else "missing"
            location = f" ({status['path']})" if status.get("path") else ""
            print(f"{name}: {marker}{location}")
        print(f"ready: {'yes' if payload['ready'] else 'no'}")
    return 0 if payload["ready"] else 1


def recorder_command(args: argparse.Namespace, raw_video: Path) -> list[str]:
    common = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    if args.source == "test":
        source = ["-re", "-f", "lavfi", "-i", f"testsrc2=size={args.geometry}:rate={args.framerate}"]
    elif args.source == "x11":
        display = args.display or os.environ.get("DISPLAY")
        if not display:
            raise EvidenceError("X11 recording requires --display or DISPLAY")
        source = [
            "-f",
            "x11grab",
            "-framerate",
            str(args.framerate),
            "-video_size",
            args.geometry,
            "-i",
            f"{display}+{args.offset}",
        ]
    else:
        raise EvidenceError(f"unsupported source: {args.source}")
    return common + source + [
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(raw_video),
    ]


def wait_for_recorder(expected: dict[str, Any], raw_video: Path, log_path: Path) -> None:
    pid = int(expected["pid"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = process_identity(pid)
        if current is None:
            details = log_path.read_text(errors="replace") if log_path.exists() else ""
            raise EvidenceError(f"recorder exited during startup: {details.strip()}")
        if not identity_matches(expected, current):
            raise EvidenceError(f"recorder identity changed during startup for PID {pid}")
        if raw_video.exists() and raw_video.stat().st_size > 0:
            return
        time.sleep(0.05)
    raise EvidenceError(f"recorder did not create {raw_video} within 5 seconds")


def command_start(args: argparse.Namespace) -> int:
    dependencies = dependency_status()
    if not dependencies["ready"]:
        missing = ", ".join(
            name
            for name in ("ffmpeg", "ffprobe", "libx264", "ass_filter")
            if not dependencies[name]["available"]
        )
        raise EvidenceError(f"recording dependencies are missing: {missing}")

    output_root = Path(args.output).expanduser().resolve()
    session_dir = output_root / f"evidence-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    session_dir.mkdir(parents=True)
    raw_video = session_dir / "raw.mp4"
    log_path = session_dir / "recorder.log"
    session_path = session_dir / "session.json"
    command = recorder_command(args, raw_video)

    with log_path.open("wb") as log_file:
        recorder_env = os.environ.copy()
        if args.source == "x11":
            display = args.display or os.environ.get("DISPLAY")
            if display:
                recorder_env["DISPLAY"] = display
            if args.xauthority:
                recorder_env["XAUTHORITY"] = args.xauthority
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=recorder_env,
        )

    started_epoch = time.time()
    identity = process_identity(process.pid)
    session: dict[str, Any] = {
        "schema_version": 2,
        "status": "recording",
        "title": args.title,
        "commit": args.commit,
        "branch": args.branch,
        "environment": args.environment,
        "source": args.source,
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
    print(json.dumps({"session": str(session_path), "pid": process.pid}))
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


def process_identity(pid: int) -> dict[str, int] | None:
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


def process_exists(pid: int) -> bool:
    return process_identity(pid) is not None


def identity_matches(expected: dict[str, Any], current: dict[str, int]) -> bool:
    keys = ("pid", "process_group_id", "start_time_ticks")
    return all(int(expected.get(key, -1)) == current[key] for key in keys)


def wait_for_pidfd(pidfd: int, timeout_seconds: float) -> bool:
    poller = select.poll()
    poller.register(pidfd, select.POLLIN)
    return bool(poller.poll(max(1, round(timeout_seconds * 1000))))


def stop_recorder(expected: dict[str, Any], grace_seconds: float = 3.0) -> None:
    pid = int(expected["pid"])
    try:
        pidfd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        current = process_identity(pid)
        if current is None:
            return
        if not identity_matches(expected, current):
            raise EvidenceError(f"recorder identity does not match live PID {pid}; refusing to signal it")
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
    )
    if result.returncode != 0:
        raise EvidenceError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams:
        raise EvidenceError(f"recording has no video stream: {path}")
    duration = float(payload.get("format", {}).get("duration", 0))
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


def write_annotations(path: Path, annotations: list[dict[str, Any]], duration: float) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: setup,DejaVu Sans,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,38,1
Style: test_start,DejaVu Sans,30,&H0000FFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,38,1
Style: passed,DejaVu Sans,30,&H0048E06B,&H0048E06B,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,38,1
Style: failed,DejaVu Sans,30,&H004C4CFF,&H004C4CFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,38,1
Style: untested,DejaVu Sans,30,&H0000A5FF,&H0000A5FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,38,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
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
    path.write_text(header + "\n".join(events) + "\n")


def render_video(raw_video: Path, final_video: Path, subtitles: Path, has_annotations: bool) -> None:
    if not has_annotations:
        shutil.copy2(raw_video, final_video)
        return
    escaped_path = str(subtitles).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(raw_video),
            "-vf",
            f"ass='{escaped_path}'",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(final_video),
        ],
        text=True,
        capture_output=True,
        check=False,
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
    path.write_text("\n".join(lines))


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
            # missing, or it survived SIGKILL). Persist that instead of leaving the
            # session stuck in "recording"; a later `stop` skips the signal and
            # finalizes whatever the recorder managed to write.
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
        # process (PID + process group + start time) is still alive it may still be
        # writing raw.mp4, and rendering now would publish truncated evidence.
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check recording dependencies")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    start = subparsers.add_parser("start", help="Start a recording session")
    start.add_argument("--output", required=True, help="Directory for evidence artifacts")
    start.add_argument("--source", choices=("x11", "test"), default="x11")
    start.add_argument("--display", help="X11 display; defaults to DISPLAY")
    start.add_argument("--xauthority", help="X11 authority file; defaults to XAUTHORITY")
    start.add_argument("--geometry", default="1280x720", help="Capture size, WIDTHxHEIGHT")
    start.add_argument("--offset", default="0,0", help="X11 capture offset, X,Y")
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
