import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

shutil_which_original = shutil.which

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evidence-driven-testing" / "scripts" / "evidence.py"
SPEC = importlib.util.spec_from_file_location("evidence_cli", SCRIPT)
assert SPEC and SPEC.loader
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


SUPERVISED_ENV = {"EVIDENCE_PLATFORM": "darwin"}  # run the non-Linux (supervisor) code path on this host


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
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
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


def test_ps_identity_parser_and_strict_matching():
    ps = EVIDENCE.parse_ps_identity(4242, "  3100 Tue Sep  1 16:35:01 2026 S+\n")
    assert ps == {"pid": 4242, "process_group_id": 3100, "started": "Tue Sep  1 16:35:01 2026"}
    assert EVIDENCE.parse_ps_identity(4242, "") is None
    assert EVIDENCE.parse_ps_identity(4242, " 3100 Tue Sep  1 16:35:01 2026 Z\n") is None
    with pytest.raises(EVIDENCE.EvidenceError, match="cannot parse"):
        EVIDENCE.parse_ps_identity(4242, "garbage")

    stored = {"pid": 4242, "process_group_id": 3100, "started": "Tue Sep  1 16:35:01 2026"}
    assert EVIDENCE.identity_matches(stored, dict(stored))
    assert not EVIDENCE.identity_matches(stored, {**stored, "started": "Tue Sep  1 16:35:02 2026"})
    assert not EVIDENCE.identity_matches({"pid": 4242}, stored), "a live identity with extra fields must not match a sparse record"


def test_supervised_mode_records_annotates_and_stops_through_the_supervisor(tmp_path: Path):
    started = run_cli("start", "--output", str(tmp_path), "--source", "test", "--geometry", "320x180", env=SUPERVISED_ENV)
    assert started.returncode == 0, started.stderr
    payload = json.loads(started.stdout)
    assert payload["mode"] == "supervised"
    session_path = Path(payload["session"])
    session = json.loads(session_path.read_text())
    assert session["platform"] == "darwin" and session["mode"] == "supervised"
    assert set(session["supervisor_identity"]) == {"pid", "process_group_id", "started"}
    assert session["recorder_identity"]["pid"] == payload["pid"]
    assert EVIDENCE.process_identity(payload["pid"]) is not None  # ffmpeg is running under the supervisor

    assert run_cli("annotate", str(session_path), "--type", "setup", "--message", "Supervised run", env=SUPERVISED_ENV).returncode == 0
    time.sleep(1.2)
    stopped = run_cli("stop", str(session_path), env=SUPERVISED_ENV)
    assert stopped.returncode == 0, stopped.stderr
    result = json.loads(stopped.stdout)
    assert result["verified"] is True

    exit_record = json.loads((session_path.parent / "recorder-exit.json").read_text())
    assert exit_record["requested"] is True
    assert exit_record["returncode"] is not None
    deadline = time.time() + 5
    while time.time() < deadline and EVIDENCE.process_identity(session["supervisor_identity"]["pid"]) is not None:
        time.sleep(0.1)
    assert EVIDENCE.process_identity(session["supervisor_identity"]["pid"]) is None, "supervisor exits after the recorder"
    assert EVIDENCE.process_identity(payload["pid"]) is None


def test_supervised_stop_never_signals_by_pid_when_supervisor_is_gone(tmp_path: Path):
    started = run_cli("start", "--output", str(tmp_path), "--source", "test", "--geometry", "320x180", env=SUPERVISED_ENV)
    assert started.returncode == 0, started.stderr
    payload = json.loads(started.stdout)
    session_path = Path(payload["session"])
    session = json.loads(session_path.read_text())
    supervisor_pid = session["supervisor_identity"]["pid"]
    recorder_pid = payload["pid"]
    time.sleep(1.0)

    os.kill(supervisor_pid, 9)  # orphan the recorder
    time.sleep(0.3)
    assert EVIDENCE.process_identity(recorder_pid) is not None

    try:
        stopped = run_cli("stop", str(session_path), env=SUPERVISED_ENV)
        assert stopped.returncode != 0
        assert "still running" in stopped.stderr and "recorder_lost" in stopped.stderr
        assert EVIDENCE.process_identity(recorder_pid) is not None, "stop must not signal the orphaned recorder by PID"
        assert json.loads(session_path.read_text())["status"] == "recorder_lost"

        retry = run_cli("stop", str(session_path), env=SUPERVISED_ENV)
        assert retry.returncode != 0 and "still running" in retry.stderr
    finally:
        os.kill(recorder_pid, 9)
    time.sleep(0.3)

    finalized = run_cli("stop", str(session_path), env=SUPERVISED_ENV)
    assert finalized.returncode == 0, finalized.stderr
    assert json.loads(finalized.stdout)["verified"] is True


def test_supervised_recorder_crash_is_recorded_and_finalizes(tmp_path: Path):
    started = run_cli("start", "--output", str(tmp_path), "--source", "test", "--geometry", "320x180", env=SUPERVISED_ENV)
    assert started.returncode == 0, started.stderr
    payload = json.loads(started.stdout)
    session_path = Path(payload["session"])
    time.sleep(1.2)
    os.kill(payload["pid"], 9)
    deadline = time.time() + 5
    exit_record = session_path.parent / "recorder-exit.json"
    while time.time() < deadline and not exit_record.exists():
        time.sleep(0.1)
    record = json.loads(exit_record.read_text())
    assert record["requested"] is False and record["returncode"] == -9

    stopped = run_cli("stop", str(session_path), env=SUPERVISED_ENV)
    assert stopped.returncode == 0, stopped.stderr
    assert json.loads(stopped.stdout)["verified"] is True


def test_stop_recorder_is_linux_only():
    with pytest.raises(EVIDENCE.EvidenceError, match="only supported on Linux"):
        os.environ["EVIDENCE_PLATFORM"] = "darwin"
        try:
            EVIDENCE.stop_recorder({"pid": os.getpid()})
        finally:
            del os.environ["EVIDENCE_PLATFORM"]


def test_wayland_readiness_requires_a_wlroots_compositor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "linux")
    monkeypatch.setattr(EVIDENCE, "ffmpeg_has_device", lambda name: False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    for name in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION"):
        monkeypatch.delenv(name, raising=False)
    tools = {"wf-recorder": "/usr/bin/wf-recorder"}
    monkeypatch.setattr(EVIDENCE.shutil, "which", lambda name: tools.get(name))

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    status = EVIDENCE.capture_status()
    assert status["sources"]["wayland"]["available"] is False
    assert "GNOME/KDE" in status["sources"]["wayland"]["reason"]
    assert status["default_source"] is None and status["capture_ready"] is False

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert EVIDENCE.capture_status()["sources"]["wayland"]["available"] is False

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "sway")
    assert EVIDENCE.capture_status()["default_source"] == "wayland"

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "some-new-compositor")  # unknown + no inspector: not ready
    unknown = EVIDENCE.capture_status()
    assert unknown["sources"]["wayland"]["available"] is False
    assert "install wayland-info" in unknown["sources"]["wayland"]["reason"]
    assert unknown["default_source"] is None
    assert EVIDENCE.resolve_source("wayland") == "wayland", "an explicit choice is still honoured"

    tools["wayland-info"] = "/usr/bin/wayland-info"
    monkeypatch.setattr(
        EVIDENCE.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="interface: 'wl_output'\n", stderr=""),
    )
    unsupported = EVIDENCE.capture_status()["sources"]["wayland"]
    assert unsupported["available"] is False and "wayland-info does not list" in unsupported["reason"]

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")  # the protocol probe outranks the desktop heuristic
    monkeypatch.setattr(
        EVIDENCE.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=f"interface: '{EVIDENCE.WLR_SCREENCOPY_PROTOCOL}'\n", stderr=""),
    )
    assert EVIDENCE.capture_status()["sources"]["wayland"]["available"] is True


def test_geometry_and_offset_are_validated_before_the_session_directory_exists(tmp_path: Path):
    for bad_offset in ("10", "1,2,3", "a,b", "10;20"):
        result = run_cli("start", "--output", str(tmp_path), "--source", "test", "--geometry", "320x180", "--offset", bad_offset)
        assert result.returncode == 2, result.stdout
        assert "--offset must be X,Y" in result.stderr and "Traceback" not in result.stderr
    for bad_geometry in ("320", "320x", "0x180", "321x180", "wide"):
        result = run_cli("start", "--output", str(tmp_path), "--source", "test", "--geometry", bad_geometry)
        assert result.returncode == 2, result.stdout
        assert "--geometry" in result.stderr and "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == [], "a rejected start must not leave a session directory behind"

    assert EVIDENCE.parse_offset(None) == (0, 0)
    assert EVIDENCE.parse_offset(" -5 , 20 ") == (-5, 20)
    assert EVIDENCE.parse_geometry(" 1920X1080 ") == "1920x1080"
    raw = tmp_path / "raw.ts"
    os.environ["EVIDENCE_PLATFORM"] = "windows"
    try:
        for source in ("gdigrab", "wayland"):
            with pytest.raises(EVIDENCE.EvidenceError, match="--offset must be X,Y"):
                if source == "wayland":
                    os.environ["EVIDENCE_PLATFORM"] = "linux"
                    EVIDENCE.shutil.which = lambda name, _w=EVIDENCE.shutil.which: "/usr/bin/wf-recorder" if name == "wf-recorder" else _w(name)
                EVIDENCE.recorder_command(_start_args(source, geometry="800x600", offset="1,2,3"), raw, source)
    finally:
        del os.environ["EVIDENCE_PLATFORM"]
        EVIDENCE.shutil.which = shutil_which_original


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


def test_supervisor_lost_before_identity_is_not_a_confirmed_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(EVIDENCE, "platform_name", lambda: "darwin")
    monkeypatch.setattr(EVIDENCE, "RAW_QUIESCENCE_SECONDS", 0.4)
    raw_video = tmp_path / "raw.ts"
    writer = subprocess.Popen(
        [sys.executable, "-c", f"import time\nwhile True:\n open({str(raw_video)!r}, 'ab').write(b'x' * 512); time.sleep(0.05)"],
    )
    try:
        time.sleep(0.3)
        dead = subprocess.run([sys.executable, "-c", "pass"])  # a PID that has exited
        session_path = tmp_path / "session.json"
        EVIDENCE.atomic_write_json(
            session_path,
            {
                "status": "recording",
                "mode": "supervised",
                "title": "Lost supervisor",
                "commit": "abc123",
                "branch": "feature/lost",
                "environment": "test",
                "raw_video": str(raw_video),
                "supervisor_identity": {"pid": 999999999, "process_group_id": 1, "started": "never"},
                "recorder_identity": None,
                "annotations": [],
            },
        )
        probed: list[Path] = []
        monkeypatch.setattr(EVIDENCE, "probe_video", lambda path: probed.append(path))

        with pytest.raises(EVIDENCE.EvidenceError, match="before recording the recorder's identity"):
            EVIDENCE.finalize_session(session_path)
        assert json.loads(session_path.read_text())["status"] == "recorder_lost"
        assert probed == []

        # A quiet-looking raw file is never authorization on its own...
        with pytest.raises(EVIDENCE.EvidenceError, match="cannot confirm the untracked recorder exited"):
            EVIDENCE.finalize_session(session_path)
        # ...and even the explicit override refuses while something is still writing.
        with pytest.raises(EVIDENCE.EvidenceError, match="still being written"):
            EVIDENCE.finalize_session(session_path, accept_untracked=True)
        assert probed == [] and json.loads(session_path.read_text())["status"] == "recorder_lost"
    finally:
        writer.kill()
        writer.wait(timeout=2)

    # Writer gone, but still no proof: stays blocked without the operator's explicit decision.
    with pytest.raises(EVIDENCE.EvidenceError, match="--accept-untracked-recorder"):
        EVIDENCE.finalize_session(session_path)
    assert json.loads(session_path.read_text())["status"] == "recorder_lost"

    verification = {"duration_seconds": 1.0, "codec": "h264", "width": 320, "height": 180, "size_bytes": 3}
    monkeypatch.setattr(EVIDENCE, "probe_video", lambda _path: verification)
    monkeypatch.setattr(EVIDENCE, "write_annotations", lambda *_args: None)
    monkeypatch.setattr(EVIDENCE, "render_video", lambda *_args: None)
    assert EVIDENCE.finalize_session(session_path, accept_untracked=True) == 0
    finalized = json.loads(session_path.read_text())
    assert finalized["status"] == "finalized" and finalized["untracked_recorder_accepted_at"]
    assert "never recorded" in (tmp_path / "report.md").read_text()


def test_supervised_startup_failure_is_recoverable_through_recorder_lost(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Simulate `start` failing to see the supervisor it just launched, while that supervisor really runs."""
    monkeypatch.setenv("EVIDENCE_PLATFORM", "darwin")  # both this process and the spawned supervisor
    spawned: dict[str, int] = {}
    real_spawn = EVIDENCE.spawn_detached

    def spawn(command, log_file, env):
        process = real_spawn(command, log_file, env)
        spawned["pid"] = process.pid
        return process

    real_identity = EVIDENCE.process_identity
    monkeypatch.setattr(EVIDENCE, "spawn_detached", spawn)
    monkeypatch.setattr(EVIDENCE, "process_identity", lambda pid: None if pid == spawned.get("pid") else real_identity(pid))

    with pytest.raises(EVIDENCE.EvidenceError, match="supervisor exited before its identity"):
        EVIDENCE.command_start(_start_args("test", output=str(tmp_path), geometry="320x180"))
    session_path = next(tmp_path.glob("evidence-*/session.json"))
    session = json.loads(session_path.read_text())
    assert session["status"] == "recorder_lost", "a supervised startup failure must land in the recoverable state"
    assert session["supervisor_identity"] is None

    # Meanwhile the real supervisor is alive and its recorder is writing. Give it a moment...
    time.sleep(1.5)
    monkeypatch.setattr(EVIDENCE, "process_identity", real_identity)
    live = json.loads(session_path.read_text())
    assert live["recorder_identity"] and EVIDENCE.identity_alive(live["recorder_identity"])

    # ...then repair the record so the supervisor is recognised, exactly as an operator
    # would after `ps`, and let `stop` recover through the supervisor rather than by PID.
    with EVIDENCE.session_lock(session_path):
        live = json.loads(session_path.read_text())
        live["supervisor_identity"] = real_identity(spawned["pid"])
        EVIDENCE.atomic_write_json(session_path, live)
    assert EVIDENCE.finalize_session(session_path) == 0
    final = json.loads(session_path.read_text())
    assert final["status"] == "finalized"
    assert json.loads((session_path.parent / "recorder-exit.json").read_text())["requested"] is True
    assert not EVIDENCE.identity_alive(live["recorder_identity"])


def test_supervised_startup_failure_without_any_recorder_stays_guarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EVIDENCE_PLATFORM", "darwin")
    # A supervisor that dies instantly, before launching anything.
    monkeypatch.setattr(
        EVIDENCE, "spawn_detached", lambda command, log_file, env: subprocess.Popen([sys.executable, "-c", "pass"])
    )
    with pytest.raises(EVIDENCE.EvidenceError, match="supervisor exited"):
        EVIDENCE.command_start(_start_args("test", output=str(tmp_path), geometry="320x180"))
    session_path = next(tmp_path.glob("evidence-*/session.json"))
    assert json.loads(session_path.read_text())["status"] == "recorder_lost"
    with pytest.raises(EVIDENCE.EvidenceError, match="--accept-untracked-recorder"):
        EVIDENCE.finalize_session(session_path)
    with pytest.raises(EVIDENCE.EvidenceError, match="ffprobe failed|recording has no video stream|duration is not positive"):
        EVIDENCE.finalize_session(session_path, accept_untracked=True)  # nothing was ever recorded
    assert json.loads(session_path.read_text())["status"] == "finalization_failed"
