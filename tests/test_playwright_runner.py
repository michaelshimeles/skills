import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "evidence-driven-testing/scripts/run-playwright.sh"
pytestmark = pytest.mark.skipif(not shutil.which("node") or not shutil.which("bash"), reason="requires Node and Bash")


@pytest.fixture
def capture_environment(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(f"#!{sys.executable}\n" + '''import json, os, pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index('--prefix') + 1])
assert sys.argv[1] == 'ci', 'Capture must install the committed dependency selection'
manifest = json.loads((root / 'package.json').read_text())
lock = json.loads((root / 'package-lock.json').read_text())
assert lock['packages']['node_modules/playwright']['version'] == manifest['dependencies']['playwright']
pathlib.Path(os.environ['INSTALL_LOG']).write_text(str(root))
if os.environ.get('FAIL_INSTALL'):
    sys.exit(9)
module = root / 'node_modules/playwright'
module.mkdir(parents=True)
(module / 'package.json').write_text(json.dumps({'type': 'module', 'exports': './index.mjs'}))
(module / 'index.mjs').write_text('export const chromium = { name: "fixture-browser" };')
cli = root / 'node_modules/.bin/playwright'
cli.parent.mkdir()
cli.write_text('#!/bin/sh\\nexit 0\\n')
cli.chmod(0o755)
''')
    npm.chmod(0o755)
    project = tmp_path / "project with spaces"
    project.mkdir()
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "INSTALL_LOG": str(tmp_path / "installed-at.txt")}
    return project, env


def test_self_contained_script_imports_dependency_and_preserves_working_directory(capture_environment):
    project, env = capture_environment
    script = project / "capture source.mjs"
    script.write_text('''import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
writeFileSync("capture.json", JSON.stringify({ browser: chromium.name, cwd: process.cwd(), argument: process.argv[2] }));
''')
    result = subprocess.run(["bash", str(RUNNER), str(script), "argument with spaces"], cwd=project, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((project / "capture.json").read_text()) == {
        "browser": "fixture-browser", "cwd": str(project), "argument": "argument with spaces",
    }
    assert not (project / "node_modules").exists()
    assert not (project / "package.json").exists()
    assert not Path(Path(env["INSTALL_LOG"]).read_text()).exists()


@pytest.mark.parametrize("install_fails", [True, False])
def test_failure_is_propagated_and_temporary_installation_is_removed(capture_environment, install_fails):
    project, env = capture_environment
    script = project / "record.mjs"
    script.write_text('throw new Error("capture failed");')
    if install_fails:
        env["FAIL_INSTALL"] = "1"
    result = subprocess.run(["bash", str(RUNNER), str(script)], cwd=project, env=env, capture_output=True, text=True)
    assert result.returncode == (9 if install_fails else 1)
    assert not Path(Path(env["INSTALL_LOG"]).read_text()).exists()


def test_missing_script_is_rejected_before_installing(capture_environment):
    project, env = capture_environment
    result = subprocess.run(["bash", str(RUNNER), "missing.mjs"], cwd=project, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Usage:" in result.stderr
    assert not Path(env["INSTALL_LOG"]).exists()
