"""
Lightweight test: Yahoo registration via Leomail birth module.
Calls register_single_yahoo() directly — same function as Birth task.
No web server needed.
"""
import asyncio
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.modules.browser_manager import BrowserManager
from backend.modules.birth.yahoo import register_single_yahoo
from backend.services.simsms_provider import SimSmsProvider
from backend.services.captcha_provider import CaptchaProvider
from backend.models import Base, Proxy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── Config ──
DESKTOP_DB = r"C:\Users\admin\Desktop\user_data\leomail.db"
DESKTOP_CONFIG = r"C:\Users\admin\Desktop\user_data\config.json"

# Load API keys from Desktop config
with open(DESKTOP_CONFIG, "r") as f:
    config = json.load(f)

SIMSMS_KEY = config["sms"]["simsms"]["api_key"]
CAPGURU_KEY = config["captcha"]["capguru"]["api_key"]

print(f"SimSMS key: {SIMSMS_KEY[:8]}...")
print(f"CapGuru key: {CAPGURU_KEY[:8]}...")

# ── DB (Desktop user_data) ──
engine = create_engine(f"sqlite:///{DESKTOP_DB}", echo=False)
Session = sessionmaker(bind=engine)
db = Session()

# ── Pick a random active proxy from DB ──
proxies = db.query(Proxy).filter(Proxy.status == "active").all()
if not proxies:
    print("ERROR: No active proxies in DB!")
    sys.exit(1)

import random
proxy = random.choice(proxies)
print(f"Using proxy: {proxy.protocol}://{proxy.username[:15]}...@{proxy.host}:{proxy.port} [{proxy.proxy_type}]")

# ── Name pool (load from names dir or use fallback) ──
names_dir = r"C:\Users\admin\Desktop\user_data\names"
name_pool = []
if os.path.isdir(names_dir):
    for f in os.listdir(names_dir):
        if f.endswith(".json"):
            with open(os.path.join(names_dir, f), "r", encoding="utf-8") as nf:
                try:
                    data = json.load(nf)
                    if isinstance(data, list):
                        for entry in data:
                            if isinstance(entry, dict) and "first" in entry and "last" in entry:
                                name_pool.append((entry["first"], entry["last"]))
                            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                                name_pool.append((entry[0], entry[1]))
                except Exception:
                    pass

if not name_pool:
    # Fallback names
    name_pool = [
        ("James", "Wilson"), ("Emily", "Parker"), ("Michael", "Johnson"),
        ("Sarah", "Davis"), ("David", "Martinez"), ("Jessica", "Brown"),
        ("Daniel", "Taylor"), ("Ashley", "Anderson"), ("Robert", "Thomas"),
        ("Jennifer", "Garcia"), ("William", "Rodriguez"), ("Amanda", "Lee"),
    ]
    print(f"Using fallback name pool ({len(name_pool)} names)")
else:
    print(f"Loaded {len(name_pool)} names from {names_dir}")

# ── SMS Provider ──
sms = SimSmsProvider(SIMSMS_KEY)
balance = sms.get_balance()
print(f"SimSMS balance: {balance}")

# ── Captcha Provider ──
captcha = CaptchaProvider(CAPGURU_KEY)

# ── Run ──
async def main():
    bm = BrowserManager(headless=False)  # headless=True for less RAM
    await bm.start()
    print("\n" + "="*60)
    print("STARTING YAHOO REGISTRATION TEST")
    print("="*60 + "\n")

    try:
        account = await register_single_yahoo(
            browser_manager=bm,
            proxy=proxy,
            device_type="desktop",
            name_pool=name_pool,
            sms_provider=sms,
            db=db,
            thread_log=None,
            captcha_provider=captcha,
        )

        if account:
            print("\n" + "="*60)
            print(f"SUCCESS! Account registered:")
            print(f"  Email:    {account.email}")
            print(f"  Password: {account.password}")
            print(f"  Name:     {account.first_name} {account.last_name}")
            print(f"  Birthday: {account.birthday}")
            print(f"  Proxy:    {proxy.host}:{proxy.port}")
            print("="*60)
        else:
            print("\n" + "="*60)
            print("FAILED — account is None. Check logs above for details.")
            print("="*60)
    finally:
        await bm.stop()
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
