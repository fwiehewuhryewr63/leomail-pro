import os
import sys
import zipfile
import urllib.request
import shutil
import re

# Configuration
UPDATE_URL = "https://example.com/leomail_update.zip"
TEMP_ZIP = "update.zip"
BACKUP_DIR = "backup_before_update"

# Files to ALWAYS keep
PROTECTED_PATHS = [
    "user_data",
    "backend/leomail.db",
    "backend/config.json",
    "remote_updater.py",
    "DEPLOY_REMOTE.bat",
    "backend/.env",         
    "frontend/.env"         
]

def log(msg):
    print(f"[*] {msg}")

def download_update():
    global UPDATE_URL
    
    # Auto-fix Dropbox links: dl=0 -> dl=1
    if "dropbox.com" in UPDATE_URL:
        if "dl=0" in UPDATE_URL:
            UPDATE_URL = UPDATE_URL.replace("dl=0", "dl=1")
            log("Auto-fixed Dropbox link (dl=0 -> dl=1)")
        elif "dl=1" not in UPDATE_URL:
            # Handle cases where there is no dl parameter at all
            sep = "&" if "?" in UPDATE_URL else "?"
            UPDATE_URL += f"{sep}dl=1"
            log("Added dl=1 to Dropbox link")

    log(f"Downloading from: {UPDATE_URL}")
    try:
        req = urllib.request.Request(UPDATE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(TEMP_ZIP, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
        log("Download successful.")
        return True
    except Exception as e:
        log(f"Failed to download update: {e}")
        return False

def apply_update():
    log("Applying update...")
    if not zipfile.is_zipfile(TEMP_ZIP):
        log("Error: Downloaded file is not a valid ZIP. Check your URL.")
        # Debug: show start of file to identify if it's HTML
        try:
            with open(TEMP_ZIP, 'r', errors='ignore') as f:
                log(f"Preview: {f.read(100)}...")
        except: pass
        return False
        
    with zipfile.ZipFile(TEMP_ZIP, 'r') as zip_ref:
        for member in zip_ref.namelist():
            path_str = str(member).replace('\\', '/')
            protected = any(path_str.startswith(p) for p in PROTECTED_PATHS)
            
            if protected:
                log(f"  [Skipped] {member}")
                continue
            
            try:
                 zip_ref.extract(member, path=".")
            except Exception as e:
                log(f"  [Error] {member}: {e}")
                
    log("Update applied successfully.")
    return True

if __name__ == "__main__":
    print("========================================")
    print("   LEOMAIL REMOTE UPDATER (Universal v2)")
    print("========================================")
    
    if len(sys.argv) > 1:
        UPDATE_URL = sys.argv[1]
    
    if download_update():
        if apply_update():
            if os.path.exists(TEMP_ZIP):
                os.remove(TEMP_ZIP)
            print("\n[SUCCESS] Updated! Restart START.bat.")
    else:
        print("\n[ERROR] Update failed.")
