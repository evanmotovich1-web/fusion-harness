#!/usr/bin/env python3
"""Install the Pi self-compact extension and its loopback API on this Mac."""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

EXTENSION = Path(__file__).resolve().with_name("self-compact.ts")
API = Path(__file__).resolve().with_name("api.py")
LABEL = "com.evan.self-compact-api"


def install_pi_settings(path: Path, extension: Path = EXTENSION) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("Pi settings must be a JSON object")
    entries = data.setdefault("extensions", [])
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        raise ValueError("Pi extensions setting must be a string list")
    if str(extension) in entries:
        return False
    entries.append(str(extension))
    fd, name = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.chmod(name, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True


def plist(api: Path = API, python: str = sys.executable) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [python, str(api)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(Path.home() / "Library/Logs/self-compact-api.log"),
        "StandardErrorPath": str(Path.home() / "Library/Logs/self-compact-api.err"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Path.home() / ".pi/agent/settings.json"
    launch_agent = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if args.dry_run:
        print(json.dumps({"extension": str(EXTENSION), "settings": str(settings), "api": str(API),
                          "launch_agent": str(launch_agent)}, indent=2))
        return 0
    changed = install_pi_settings(settings)
    launch_agent.parent.mkdir(parents=True, exist_ok=True)
    desired = plistlib.dumps(plist())
    changed_plist = not launch_agent.exists() or launch_agent.read_bytes() != desired
    loaded = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
                            capture_output=True).returncode == 0
    if changed_plist:
        launch_agent.write_bytes(desired)
    if changed_plist or not loaded:
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(launch_agent)], check=True)
    print(json.dumps({"pi_setting_added": changed, "launch_agent": str(launch_agent)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
