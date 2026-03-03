"""
Leomail — Provider Test Script
Run: python test_providers.py
Visible browser, 1 account, detailed step logging.
"""
import asyncio
import sys
import threading
from loguru import logger

# Configure rich logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="DEBUG",
    colorize=True,
)

PROVIDERS = {
    "1": ("outlook",     "Outlook"),
    "2": ("hotmail",     "Hotmail"),
    "3": ("gmail",       "Gmail"),
    "4": ("yahoo",       "Yahoo"),
    "5": ("aol",         "AOL"),
    "6": ("proton",      "ProtonMail"),
}


async def test_birth(provider_key: str):
    """Test registration for one provider."""
    from backend.database import SessionLocal, engine, Base
    from backend.modules.browser_manager import BrowserManager
    from backend.modules.birth.outlook import register_single_outlook
    from backend.modules.birth.gmail import register_single_gmail
    from backend.modules.birth.yahoo import register_single_yahoo
    from backend.modules.birth.aol import register_single_aol
    from backend.modules.birth.protonmail import register_single_protonmail
    from backend.modules.birth._helpers import get_captcha_provider

    provider, name = PROVIDERS[provider_key]
    logger.info(f"{'='*50}")
    logger.info(f"  TESTING: {name} ({provider})")
    logger.info(f"{'='*50}")

    # Ensure all tables exist
    import backend.models  # noqa - registers models
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Simple name pool for testing
    name_pool = [
        ("James", "Wilson"), ("Emma", "Johnson"), ("Michael", "Brown"),
        ("Sophia", "Davis"), ("William", "Garcia"), ("Olivia", "Martinez"),
        ("Robert", "Anderson"), ("Isabella", "Thomas"), ("David", "Taylor"),
    ]

    # Get captcha provider from config
    captcha = None
    try:
        captcha = get_captcha_provider(db)
        if captcha:
            logger.info(f"CAPTCHA provider: {captcha.__class__.__name__}")
    except Exception as e:
        logger.warning(f"No CAPTCHA provider: {e}")

    cancel_event = threading.Event()
    active_pages = {}

    # Start browser (VISIBLE - headless=False)
    bm = BrowserManager(headless=False)
    await bm.start()
    logger.info("Browser started (visible mode)")

    try:
        # Route to provider
        account = None

        if provider == "outlook":
            account = await register_single_outlook(
                browser_manager=bm, proxy=None,
                name_pool=name_pool, captcha_provider=captcha,
                db=db, thread_log=None,
                domain="outlook.com",
                ACTIVE_PAGES=active_pages, BIRTH_CANCEL_EVENT=cancel_event,
            )
        elif provider == "hotmail":
            account = await register_single_outlook(
                browser_manager=bm, proxy=None,
                name_pool=name_pool, captcha_provider=captcha,
                db=db, thread_log=None,
                domain="hotmail.com",
                ACTIVE_PAGES=active_pages, BIRTH_CANCEL_EVENT=cancel_event,
            )
        elif provider == "gmail":
            account = await register_single_gmail(
                browser_manager=bm, proxy=None,
                name_pool=name_pool, captcha_provider=captcha,
                sms_provider=None,
                db=db, thread_log=None,
                ACTIVE_PAGES=active_pages, BIRTH_CANCEL_EVENT=cancel_event,
            )
        elif provider == "yahoo":
            account = await register_single_yahoo(
                browser_manager=bm, proxy=None,
                name_pool=name_pool, captcha_provider=captcha,
                sms_provider=None,
                db=db, thread_log=None,
                ACTIVE_PAGES=active_pages, BIRTH_CANCEL_EVENT=cancel_event,
            )
        elif provider == "aol":
            account = await register_single_aol(
                browser_manager=bm, proxy=None,
                name_pool=name_pool, captcha_provider=captcha,
                sms_provider=None,
                db=db, thread_log=None,
                ACTIVE_PAGES=active_pages, BIRTH_CANCEL_EVENT=cancel_event,
            )
        elif provider == "proton":
            account = await register_single_protonmail(
                browser_manager=bm, proxy=None,
                name_pool=name_pool, captcha_provider=captcha,
                db=db, thread_log=None,
                ACTIVE_PAGES=active_pages, BIRTH_CANCEL_EVENT=cancel_event,
            )

        # Result
        logger.info(f"{'='*50}")
        if account:
            logger.success(f"  ✅ SUCCESS: {account.email}")
            logger.info(f"  Password:  {account.password}")
            logger.info(f"  Provider:  {account.provider}")
            logger.info(f"  Status:    {account.status}")
        else:
            logger.error(f"  ❌ FAILED: registration returned None")
            logger.info(f"  Check screenshots in user_data/screenshots/")
        logger.info(f"{'='*50}")

    except Exception as e:
        logger.error(f"  ❌ EXCEPTION: {e}", exc_info=True)
    finally:
        await bm.stop()
        db.close()


def main():
    import os
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    print()
    print("  +======================================+")
    print("  |   LEOMAIL - Provider Birth Tester    |")
    print("  +======================================+")
    for key, (provider, name) in PROVIDERS.items():
        print(f"  |   {key}. {name:<32} |")
    print("  |   0. Exit                            |")
    print("  +======================================+")
    print()

    choice = input("  Provider [1-6]: ").strip()
    if choice == "0" or choice not in PROVIDERS:
        print("  Bye!")
        return

    asyncio.run(test_birth(choice))


if __name__ == "__main__":
    main()
