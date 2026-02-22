"""
Leomail — Auto Pack for VPS Deployment
Creates a clean ZIP on Desktop with only the needed files.
Excludes: venv, node_modules, __pycache__, user_data, old zips, build scripts
"""
import zipfile
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
DESKTOP = Path.home() / "Desktop"

# Output filename with timestamp
timestamp = datetime.now().strftime("%m%d_%H%M")
ZIP_NAME = f"Leomail_v3_{timestamp}.zip"
ZIP_PATH = DESKTOP / ZIP_NAME

# Files/dirs to INCLUDE from project root
INCLUDE_DIRS = [
    "backend",
    "frontend/dist",
]

INCLUDE_FILES = [
    "START.bat",
    "SETUP.bat",
    "UPDATE.bat",
    "requirements.txt",
    ".env",
    "LEOMAIL_TEMPLATE_FORMAT.txt",
    "README.md",
]

# Patterns to EXCLUDE (inside included dirs)
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pyc",
    "node_modules",
    ".git",
    "venv",
    "user_data",
    ".spec",
    "build.py",
    "leomail_entry.py",
    "_check.py",
    "make_zip.py",
}


def should_exclude(path_str: str) -> bool:
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_str:
            return True
    return False


def main():
    print(f"{'='*50}")
    print(f"  LEOMAIL — PACK FOR VPS")
    print(f"{'='*50}")
    print()

    file_count = 0
    total_size = 0

    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add directories
        for dir_name in INCLUDE_DIRS:
            dir_path = PROJECT_ROOT / dir_name
            if not dir_path.exists():
                print(f"  [SKIP] {dir_name} — not found")
                continue
            
            for root, dirs, files in os.walk(dir_path):
                # Filter out excluded dirs
                dirs[:] = [d for d in dirs if not should_exclude(d)]
                
                for file in files:
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(PROJECT_ROOT)
                    
                    if should_exclude(str(rel_path)):
                        continue
                    
                    arcname = str(rel_path).replace("\\", "/")
                    zf.write(file_path, arcname)
                    file_count += 1
                    total_size += file_path.stat().st_size

        # Add individual files
        for file_name in INCLUDE_FILES:
            file_path = PROJECT_ROOT / file_name
            if file_path.exists():
                zf.write(file_path, file_name)
                file_count += 1
                total_size += file_path.stat().st_size
                print(f"  [+] {file_name}")
            else:
                print(f"  [SKIP] {file_name} — not found")

    zip_size = ZIP_PATH.stat().st_size
    print()
    print(f"  Files: {file_count}")
    print(f"  Raw size: {total_size / 1024:.0f} KB")
    print(f"  ZIP size: {zip_size / 1024:.0f} KB")
    print()
    print(f"  ✅ Saved to: {ZIP_PATH}")
    print()
    print(f"  На VPS:")
    print(f"    1. Разархивировать в папку Leomail")
    print(f"    2. SETUP.bat (первый раз)")
    print(f"    3. START.bat")
    print()


if __name__ == "__main__":
    main()
