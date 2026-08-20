#!/usr/bin/env python3
# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Installer and verification helper for FizzBee formal model checker.

Usage:
    python scripts/install_fizzbee.py --check
    python scripts/install_fizzbee.py --install
"""

import argparse
import os
import platform
import shutil
import stat
import sys
import urllib.request
import json
import tarfile
import tempfile


def get_venv_bin_dir() -> str:
    """Get the active virtual environment bin directory or fallback to ~/.local/bin."""
    if hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix):
        return os.path.join(sys.prefix, "bin" if sys.platform != "win32" else "Scripts")
    return os.path.expanduser("~/.local/bin")


def find_fizzbee_binary() -> str | None:
    """Check if fizzbee or fizz is available on PATH or in .venv/bin."""
    venv_bin = os.path.join(get_venv_bin_dir(), "fizzbee" if sys.platform != "win32" else "fizzbee.exe")
    if os.path.isfile(venv_bin) and os.access(venv_bin, os.X_OK):
        return venv_bin

    venv_fizz = os.path.join(get_venv_bin_dir(), "fizz" if sys.platform != "win32" else "fizz.exe")
    if os.path.isfile(venv_fizz) and os.access(venv_fizz, os.X_OK):
        return venv_fizz

    return shutil.which("fizzbee") or shutil.which("fizz")


def check_status() -> int:
    """Check if FizzBee is installed and print status."""
    bin_path = find_fizzbee_binary()
    if bin_path:
        print(f"FizzBee binary found at: {bin_path}")
        return 0
    else:
        print("FizzBee is NOT currently installed.")
        print("\nTo install FizzBee:")
        print("  1. Automated: python scripts/install_fizzbee.py --install")
        print("  2. macOS (Homebrew): brew tap fizzbee-io/fizzbee && brew install fizzbee")
        print("  3. Manual: Download from https://github.com/fizzbee-io/fizzbee/releases")
        return 1


def install_fizzbee() -> int:
    """Download and install FizzBee binary into .venv/bin."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system not in ("linux", "darwin"):
        print(f"Unsupported OS for automated install: {system}. Please download manually from https://github.com/fizzbee-io/fizzbee/releases")
        return 1

    arch_map = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    arch = arch_map.get(machine, "amd64")

    print(f"Detecting latest FizzBee release for {system}-{arch}...")
    api_url = "https://api.github.com/repos/fizzbee-io/fizzbee/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": "WriterAgent-Installer"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Failed to query GitHub releases: {e}")
        print("Fallback download: https://github.com/fizzbee-io/fizzbee/releases")
        return 1

    assets = data.get("assets", [])
    target_asset = None
    for asset in assets:
        name = asset.get("name", "").lower()
        if system in name and arch in name and (name.endswith(".tar.gz") or name.endswith(".zip") or "." not in name):
            target_asset = asset
            break

    if not target_asset and assets:
        target_asset = assets[0]

    if not target_asset:
        print(f"No suitable binary release asset found for {system}-{arch} in {data.get('tag_name')}")
        return 1

    download_url = target_asset["browser_download_url"]
    asset_name = target_asset["name"]
    print(f"Downloading {asset_name} from {download_url}...")

    dest_dir = get_venv_bin_dir()
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, "fizzbee")

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = os.path.join(tmp_dir, asset_name)
        urllib.request.urlretrieve(download_url, archive_path)

        if asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=tmp_dir)
            extracted_bin = None
            for root, _dirs, files in os.walk(tmp_dir):
                for f in files:
                    if f in ("fizzbee", "fizz") or f.startswith("fizz"):
                        extracted_bin = os.path.join(root, f)
                        break
            if extracted_bin:
                shutil.copy2(extracted_bin, dest_path)
            else:
                print("Could not find fizzbee binary inside archive.")
                return 1
        else:
            shutil.copy2(archive_path, dest_path)

    # Ensure executable permissions
    os.chmod(dest_path, os.stat(dest_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Successfully installed FizzBee to: {dest_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Install and check FizzBee formal verification tool")
    parser.add_argument("--check", action="store_true", help="Check if FizzBee is currently installed")
    parser.add_argument("--install", action="store_true", help="Download and install FizzBee into .venv/bin")
    args = parser.parse_args()

    if args.install:
        return install_fizzbee()
    return check_status()


if __name__ == "__main__":
    sys.exit(main())
