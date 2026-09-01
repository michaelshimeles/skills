import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evidence-driven-testing" / "scripts" / "evidence.py"
SPEC = importlib.util.spec_from_file_location("evidence_cli", SCRIPT)
assert SPEC and SPEC.loader
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_doctor_reports_required_executables_as_json():
    result = run_cli("doctor", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ffmpeg"]["available"] is True
    assert payload["ffprobe"]["available"] is True
    assert payload["libx264"]["available"] is True
    assert payload["ass_filter"]["available"] is True
    assert payload["ready"] is True
    assert payload["platform"] in ("linux", "darwin", "windows")
    assert set(payload["capture"]["sources"]) == {"x11", "wayland", "avfoundation", "gdigrab"}
    assert payload["capture_ready"] is payload["capture"]["capture_ready"]


def test_assertion_requires_a_valid_result(tmp_path: Path):
    started = run_cli("start", "--output", str(tmp_path), "--source", "test")
    assert started.returncode == 0, started.stderr
    session = Path(json.loads(started.stdout)["session"])

    invalid = run_cli(
        "annotate",
        str(session),
        "--type",
        "assertion",
        "--message",
        "The page loaded",
    )
    assert invalid.returncode != 0
    assert "--result is required" in invalid.stderr

    stopped = run_cli("stop", str(session))
    assert stopped.returncode == 0, stopped.stderr


def test_synthetic_recording_is_annotated_verified_and_reported(tmp_path: Path):
    started = run_cli(
        "start",
        "--output",
        str(tmp_path),
        "--source",
        "test",
        "--title",
        "Evidence smoke test",
        "--commit",
        "abc123",
        "--branch",
        "feature/evidence",
        "--environment",
        "local synthetic source",
    )
    assert started.returncode == 0, started.stderr
    session = Path(json.loads(started.stdout)["session"])

    annotations = [
        ("setup", "Synthetic app is ready", None),
        ("test_start", "It should record visual proof", None),
        ("assertion", "Recording contains the expected state", "passed"),
    ]
    for kind, message, result in annotations:
        args = ["annotate", str(session), "--type", kind, "--message", message]
        if result:
            args.extend(["--result", result])
        annotated = run_cli(*args)
        assert annotated.returncode == 0, annotated.stderr
        time.sleep(0.2)

    time.sleep(0.8)
    stopped = run_cli("stop", str(session))
    assert stopped.returncode == 0, stopped.stderr
    payload = json.loads(stopped.stdout)

    video = Path(payload["video"])
    report = Path(payload["report"])
    manifest = Path(payload["manifest"])
    assert video.exists() and video.stat().st_size > 0
    assert report.exists()
    assert manifest.exists()
    assert payload["verified"] is True

    report_text = report.read_text()
    assert "Evidence smoke test" in report_text
    assert "abc123" in report_text
    assert "Recording contains the expected state" in report_text
    assert "PASSED" in report_text

    manifest_data = json.loads(manifest.read_text())
    assert manifest_data["status"] == "finalized"
    assert manifest_data["verification"]["duration_seconds"] > 0
    assert len(manifest_data["annotations"]) == 3


def test_concurrent_annotations_are_all_persisted(tmp_path: Path):
    started = run_cli("start", "--output", str(tmp_path), "--source", "test")
    assert started.returncode == 0, started.stderr
    session = Path(json.loads(started.stdout)["session"])

    count = 24
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "annotate",
                str(session),
                "--type",
                "assertion",
                "--result",
                "passed",
                "--message",
                f"Concurrent annotation {index:02d}",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(count)
    ]
    results = [proc.communicate() for proc in procs]
    assert all(proc.returncode == 0 for proc in procs), [err for _, err in results if err]

    stopped = run_cli("stop", str(session))
    assert stopped.returncode == 0, stopped.stderr
    manifest = json.loads(Path(json.loads(stopped.stdout)["manifest"]).read_text())
    messages = sorted(item["message"] for item in manifest["annotations"])
    assert messages == sorted(f"Concurrent annotation {index:02d}" for index in range(count))


def test_finalization_failure_is_recorded_and_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    raw_video = tmp_path / "raw.mp4"
    raw_video.write_bytes(b"raw")
    session_path = tmp_path / "session.json"
    session = {
        "status": "recorded",
        "title": "Retry test",
        "commit": "abc123",
        "branch": "feature/retry",
        "environment": "test",
        "raw_video": str(raw_video),
        "annotations": [],
    }
    EVIDENCE.atomic_write_json(session_path, session)
    verification = {
        "duration_seconds": 1.0,
        "codec": "h264",
        "width": 320,
        "height": 180,
        "size_bytes": 3,
    }
    monkeypatch.setattr(EVIDENCE, "probe_video", lambda _path: verification)
    monkeypatch.setattr(EVIDENCE, "write_annotations", lambda *_args: None)

    attempts = 0

    def render_with_one_failure(*_args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise EVIDENCE.EvidenceError("forced render failure")

    monkeypatch.setattr(EVIDENCE, "render_video", render_with_one_failure)
    args = argparse.Namespace(session=str(session_path))

    with pytest.raises(EVIDENCE.EvidenceError, match="forced render failure"):
        EVIDENCE.command_stop(args)
    failed = json.loads(session_path.read_text())
    assert failed["status"] == "finalization_failed"
    assert "forced render failure" in failed["failure"]

    assert EVIDENCE.command_stop(args) == 0
    finalized = json.loads(session_path.read_text())
    assert finalized["status"] == "finalized"
    assert attempts == 2


def test_stop_marks_session_recorder_lost_on_identity_mismatch_and_finalizes_on_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    identity = EVIDENCE.process_identity(os.getpid())
    assert identity is not None
    stale = dict(identity)
    stale["start_time_ticks"] += 1
    raw_video = tmp_path / "raw.mp4"
    raw_video.write_bytes(b"raw")
    session_path = tmp_path / "session.json"
    EVIDENCE.atomic_write_json(
        session_path,
        {
            "status": "recording",
            "title": "Recorder lost",
            "commit": "abc123",
            "branch": "feature/recorder-lost",
            "environment": "test",
            "raw_video": str(raw_video),
            "recorder_identity": stale,
            "annotations": [],
        },
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        EVIDENCE.signal,
        "pidfd_send_signal",
        lambda pidfd, sig: signals.append((pidfd, sig)),
    )
    args = argparse.Namespace(session=str(session_path))

    with pytest.raises(EVIDENCE.EvidenceError, match="recorder_lost"):
        EVIDENCE.command_stop(args)
    assert signals == []
    lost = json.loads(session_path.read_text())
    assert lost["status"] == "recorder_lost"
    assert "identity does not match" in lost["failure"]
    assert "failed_at" in lost

    verification = {
        "duration_seconds": 1.0,
        "codec": "h264",
        "width": 320,
        "height": 180,
        "size_bytes": 3,
    }
    monkeypatch.setattr(EVIDENCE, "probe_video", lambda _path: verification)
    monkeypatch.setattr(EVIDENCE, "write_annotations", lambda *_args: None)
    monkeypatch.setattr(EVIDENCE, "render_video", lambda *_args: None)

    assert EVIDENCE.command_stop(args) == 0
    assert signals == []
    finalized = json.loads(session_path.read_text())
    assert finalized["status"] == "finalized"
    assert "failure" not in finalized


def test_recorder_lost_retry_refuses_to_finalize_while_recorder_is_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        time.sleep(0.1)
        identity = EVIDENCE.process_identity(process.pid)
        assert identity is not None
        raw_video = tmp_path / "raw.mp4"
        raw_video.write_bytes(b"raw")
        session_path = tmp_path / "session.json"
        EVIDENCE.atomic_write_json(
            session_path,
            {
                "status": "recorder_lost",
                "failure": f"recorder PID {process.pid} remained alive after SIGKILL",
                "title": "Survivor",
                "commit": "abc123",
                "branch": "feature/survivor",
                "environment": "test",
                "raw_video": str(raw_video),
                "recorder_identity": identity,
                "annotations": [],
            },
        )
        probed: list[Path] = []
        monkeypatch.setattr(EVIDENCE, "probe_video", lambda path: probed.append(path))
        args = argparse.Namespace(session=str(session_path))

        with pytest.raises(EVIDENCE.EvidenceError, match="still running"):
            EVIDENCE.command_stop(args)
        assert probed == []
        still_lost = json.loads(session_path.read_text())
        assert still_lost["status"] == "recorder_lost"

        process.kill()
        process.wait(timeout=2)
        verification = {"duration_seconds": 1.0, "codec": "h264", "width": 320, "height": 180, "size_bytes": 3}
        monkeypatch.setattr(EVIDENCE, "probe_video", lambda _path: verification)
        monkeypatch.setattr(EVIDENCE, "write_annotations", lambda *_args: None)
        monkeypatch.setattr(EVIDENCE, "render_video", lambda *_args: None)

        assert EVIDENCE.command_stop(args) == 0
        assert json.loads(session_path.read_text())["status"] == "finalized"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_stop_refuses_to_signal_a_reused_or_tampered_pid(monkeypatch: pytest.MonkeyPatch):
    identity = EVIDENCE.process_identity(os.getpid())
    assert identity is not None
    tampered = dict(identity)
    tampered["start_time_ticks"] += 1
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        EVIDENCE.signal,
        "pidfd_send_signal",
        lambda pidfd, sig: signals.append((pidfd, sig)),
    )

    with pytest.raises(EVIDENCE.EvidenceError, match="identity does not match"):
        EVIDENCE.stop_recorder(tampered)

    assert signals == []


def test_startup_failure_marks_session_failed_and_stops_recorder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        EVIDENCE,
        "dependency_status",
        lambda: {
            "ffmpeg": {"available": True},
            "ffprobe": {"available": True},
            "libx264": {"available": True},
            "ass_filter": {"available": True},
            "ready": True,
        },
    )
    monkeypatch.setattr(
        EVIDENCE,
        "recorder_command",
        lambda _args, _raw, _source: [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    monkeypatch.setattr(
        EVIDENCE,
        "wait_for_recorder",
        lambda *_args: (_ for _ in ()).throw(EVIDENCE.EvidenceError("forced startup failure")),
    )
    args = argparse.Namespace(
        output=str(tmp_path),
        source="test",
        display=None,
        xauthority=None,
        geometry="320x180",
        offset="0,0",
        framerate=10,
        title="Startup failure",
        commit="abc123",
        branch="feature/startup-failure",
        environment="test",
    )

    with pytest.raises(EVIDENCE.EvidenceError, match="forced startup failure"):
        EVIDENCE.command_start(args)

    session_paths = list(tmp_path.glob("evidence-*/session.json"))
    assert len(session_paths) == 1
    session = json.loads(session_paths[0].read_text())
    try:
        assert session["status"] == "startup_failed"
        assert "forced startup failure" in session["failure"]
        assert EVIDENCE.process_identity(session["recorder_identity"]["pid"]) is None
    finally:
        identity = session.get("recorder_identity")
        if identity and EVIDENCE.process_identity(identity["pid"]):
            os.killpg(identity["process_group_id"], 9)
        elif session.get("recorder_pid") and EVIDENCE.process_identity(session["recorder_pid"]):
            os.killpg(session["recorder_pid"], 9)


def test_stop_escalates_to_sigkill_and_verifies_termination():
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        ],
        start_new_session=True,
    )
    try:
        time.sleep(0.1)
        identity = EVIDENCE.process_identity(process.pid)
        assert identity is not None

        EVIDENCE.stop_recorder(identity, grace_seconds=0.1)

        assert process.wait(timeout=2) == -9
        assert EVIDENCE.process_identity(process.pid) is None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=2)


def _start_args(source: str = "auto", **overrides) -> argparse.Namespace:
    base = dict(
        output="out",
        source=source,
        display=None,
        xauthority=None,
        screen_index=None,
        output_name=None,
        geometry=None,
        offset="0,0",
        framerate=30,
        title="t",
        commit="c",
        branch="b",
        environment="e",
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_recorder_command_targets_each_platform_capture_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw = tmp_path / "raw.ts"

    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "linux")
    x11 = EVIDENCE.recorder_command(_start_args("x11", display=":7", geometry="1920x1080", offset="10,20"), raw, "x11")
    assert x11[:1] == ["ffmpeg"] and "x11grab" in x11
    assert x11[x11.index("-i") + 1] == ":7+10,20"
    assert x11[x11.index("-video_size") + 1] == "1920x1080"
    assert "mpegts" in x11 and "-flush_packets" in x11

    monkeypatch.setattr(EVIDENCE.shutil, "which", lambda name: "/usr/bin/wf-recorder" if name == "wf-recorder" else None)
    wayland = EVIDENCE.recorder_command(_start_args("wayland", output_name="DP-1"), raw, "wayland")
    assert wayland[0] == "wf-recorder"
    assert wayland[wayland.index("-m") + 1] == "mpegts"
    assert wayland[wayland.index("-o") + 1] == "DP-1"
    assert wayland[-2:] == ["-f", str(raw)]
    monkeypatch.undo()

    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "darwin")
    monkeypatch.setattr(EVIDENCE, "detect_avfoundation_screens", lambda: [{"index": 3, "name": "Capture screen 0"}])
    mac = EVIDENCE.recorder_command(_start_args("avfoundation"), raw, "avfoundation")
    assert "avfoundation" in mac and mac[mac.index("-i") + 1] == "3:none"
    assert "-capture_cursor" in mac
    explicit = EVIDENCE.recorder_command(_start_args("avfoundation", screen_index=5), raw, "avfoundation")
    assert explicit[explicit.index("-i") + 1] == "5:none"

    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "windows")
    win_full = EVIDENCE.recorder_command(_start_args("gdigrab"), raw, "gdigrab")
    assert "gdigrab" in win_full and win_full[win_full.index("-i") + 1] == "desktop"
    assert "-video_size" not in win_full
    win_region = EVIDENCE.recorder_command(_start_args("gdigrab", geometry="800x600", offset="5,6"), raw, "gdigrab")
    assert win_region[win_region.index("-offset_x") + 1] == "5"
    assert win_region[win_region.index("-offset_y") + 1] == "6"
    assert win_region[win_region.index("-video_size") + 1] == "800x600"

    for command in (x11, mac, win_full, win_region):
        assert command[-3:] == ["-f", "mpegts", str(raw)]


def test_default_source_follows_platform_and_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(EVIDENCE, "ffmpeg_has_device", lambda name: True)
    monkeypatch.setattr(EVIDENCE, "detect_avfoundation_screens", lambda: [{"index": 1, "name": "Capture screen 0"}])

    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert EVIDENCE.capture_status()["default_source"] == "x11"

    monkeypatch.delenv("DISPLAY")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setattr(EVIDENCE.shutil, "which", lambda name: "/usr/bin/wf-recorder" if name == "wf-recorder" else None)
    assert EVIDENCE.capture_status()["default_source"] == "wayland"
    monkeypatch.setattr(EVIDENCE.shutil, "which", lambda name: None)
    status = EVIDENCE.capture_status()
    assert status["default_source"] is None and status["capture_ready"] is False
    with pytest.raises(EVIDENCE.EvidenceError, match="no usable screen-capture source on linux"):
        EVIDENCE.resolve_source("auto")

    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "darwin")
    assert EVIDENCE.capture_status()["default_source"] == "avfoundation"

    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "windows")
    assert EVIDENCE.capture_status()["default_source"] == "gdigrab"

    assert EVIDENCE.resolve_source("test") == "test"


def test_ps_and_windows_identity_parsers():
    ps = EVIDENCE.parse_ps_identity(4242, "  3100 Tue Sep  1 16:35:01 2026 S+\n")
    assert ps == {"pid": 4242, "process_group_id": 3100, "started": "Tue Sep  1 16:35:01 2026"}
    assert EVIDENCE.parse_ps_identity(4242, "") is None
    assert EVIDENCE.parse_ps_identity(4242, " 3100 Tue Sep  1 16:35:01 2026 Z\n") is None
    with pytest.raises(EVIDENCE.EvidenceError, match="cannot parse"):
        EVIDENCE.parse_ps_identity(4242, "garbage")

    win = EVIDENCE.parse_windows_identity(77, "133700000000000000|4321\r\n")
    assert win == {"pid": 77, "creation_filetime": 133700000000000000, "parent_pid": 4321}
    assert EVIDENCE.parse_windows_identity(77, "") is None
    with pytest.raises(EVIDENCE.EvidenceError, match="cannot parse"):
        EVIDENCE.parse_windows_identity(77, "not|a|number")

    stored = {"pid": 4242, "process_group_id": 3100, "started": "Tue Sep  1 16:35:01 2026"}
    assert EVIDENCE.identity_matches(stored, dict(stored))
    assert not EVIDENCE.identity_matches(stored, {**stored, "started": "Tue Sep  1 16:35:02 2026"})
    assert not EVIDENCE.identity_matches({"pid": 4242}, stored), "a live identity with extra fields must not match a sparse record"


def test_posix_stop_path_escalates_and_refuses_reused_pid(monkeypatch: pytest.MonkeyPatch):
    """Exercise the macOS/BSD code path (ps-based identity, os.kill) on this host."""
    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "darwin")
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        ],
        start_new_session=True,
    )
    try:
        time.sleep(0.2)
        identity = EVIDENCE.process_identity(process.pid)
        assert identity is not None and set(identity) == {"pid", "process_group_id", "started"}
        assert identity["process_group_id"] == process.pid

        sent: list[int] = []
        real_kill = os.kill
        monkeypatch.setattr(EVIDENCE.os, "kill", lambda pid, sig: sent.append(sig))
        with pytest.raises(EVIDENCE.EvidenceError, match="identity does not match"):
            EVIDENCE.stop_recorder({**identity, "started": "Thu Jan  1 00:00:00 1970"})
        assert sent == []
        monkeypatch.setattr(EVIDENCE.os, "kill", real_kill)

        EVIDENCE.stop_recorder(identity, grace_seconds=0.2)
        assert process.wait(timeout=2) == -9
        assert EVIDENCE.process_identity(process.pid) is None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=2)


def test_unclean_recorder_exit_still_finalizes_from_mpegts(tmp_path: Path):
    started = run_cli("start", "--output", str(tmp_path), "--source", "test", "--geometry", "320x180")
    assert started.returncode == 0, started.stderr
    payload = json.loads(started.stdout)
    session = Path(payload["session"])
    assert run_cli("annotate", str(session), "--type", "setup", "--message", "Synthetic source running").returncode == 0
    time.sleep(1.5)

    os.kill(payload["pid"], 9)  # simulate a crashed / TerminateProcess'd recorder
    time.sleep(0.3)

    stopped = run_cli("stop", str(session))
    assert stopped.returncode == 0, stopped.stderr
    result = json.loads(stopped.stdout)
    assert result["verified"] is True and result["verification"]["duration_seconds"] > 0
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["status"] == "finalized"
    assert manifest["raw_video"].endswith(".ts")
