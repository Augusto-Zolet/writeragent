#!/usr/bin/env python3
"""
Harvest script for writeragent_vec Cython binaries.
Extracts .so and .pyd files from wheels and places them in plugin/contrib/vec_pack.
"""

import os
import shutil
import zipfile
import platform
import subprocess
from pathlib import Path
import argparse

REPO_ROOT = Path(__file__).parent.parent.resolve()
DEST_DIR = REPO_ROOT / "plugin" / "contrib" / "vec_pack"

def strip_binary(filepath):
    """Strip debug symbols from a binary file to reduce size."""
    filepath = Path(filepath)
    if not filepath.exists() or filepath.stat().st_size < 1024:
        return
    
    # Try llvm-strip first, then strip
    for stripper in ["llvm-strip", "strip"]:
        try:
            result = subprocess.run([stripper, str(filepath)], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"  Stripped {filepath.name}")
                return
        except (FileNotFoundError, OSError):
            continue

def main():
    parser = argparse.ArgumentParser(description="Harvest writeragent_vec binaries from wheels.")
    parser.add_argument("input_dir", help="Directory containing .whl files")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: Input directory {input_dir} does not exist.")
        return

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy __init__.py if it doesn't exist or to ensure it's up to date
    init_src = REPO_ROOT / "native" / "writeragent_vec" / "src" / "writeragent_vec" / "__init__.py"
    if init_src.exists():
        shutil.copy2(init_src, DEST_DIR / "__init__.py")

    found_wheels = list(input_dir.glob("*.whl"))
    print(f"Found {len(found_wheels)} wheels in {input_dir}")

    for wheel in found_wheels:
        print(f"Processing {wheel.name}...")
        with zipfile.ZipFile(wheel, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                filename = file_info.filename
                # Look for .so or .pyd files inside the package directory
                if (filename.startswith("writeragent_vec/") and 
                    (filename.endswith(".so") or filename.endswith(".pyd"))):
                    
                    target_name = os.path.basename(filename)
                    target_path = DEST_DIR / target_name
                    
                    with zip_ref.open(filename) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    
                    print(f"  Extracted {target_name}")
                    strip_binary(target_path)

    print(f"\nDone! Binaries are in {DEST_DIR}")

if __name__ == "__main__":
    main()
