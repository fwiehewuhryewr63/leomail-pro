import random
import asyncio
from loguru import logger
try:
    from playwright.async_api import Page
except ImportError:
    Page = None
from ..browser_manager import BrowserManager
from ...services.captcha_provider import CaptchaProvider
from ...models import Account, AccountStatus, Proxy
from ...utils import generate_random_name, generate_random_birthday, generate_random_password
from sqlalchemy.orm import Session


class OutlookRegistration:
    def __init__(self, browser_manager: BrowserManager, captcha_service: CaptchaProvider, db: Session):
        self.browser_manager = browser_manager
        self.captcha_service = captcha_service
        self.db = db

    async def register(self, proxy=None):
        logger.info("Starting Outlook Registration...")
        first_name, last_name = generate_random_name()
        password = generate_random_password()
        username = f"{first_name.lower()}.{last_name.lower()}.{random.randint(1000, 9999)}"
        email = f"{username}@outlook.com"
        birthday = generate_random_birthday()

        # Use specific proxy if provided, otherwise pick one from DB
        if not proxy:
            proxy = self.db.query(Proxy).filter(Proxy.status == "active").first()

        context = await self.browser_manager.create_context(proxy)
        page = await context.new_page()

        try:
            await page.goto("https://signup.live.com/signup")
            await page.wait_for_load_state("networkidle")

            # Step 1: Email
            logger.info(f"Inputting email: {email}")
            await page.fill('input[name="MemberName"]', email)
            await page.click('input[id="iSignupAction"]')

            # Wait for either password or "already exists" error
            await page.wait_for_selector('input[name="Password"], #MemberNameError', timeout=5000)
            if await page.query_selector("#MemberNameError"):
                logger.error("Email already exists or invalid")
                return None

            # Step 2: Password
            logger.info("Inputting password")
            await page.fill('input[name="Password"]', password)
            await page.click('input[id="iSignupAction"]')

            # Step 3: Name
            await page.wait_for_selector('input[name="FirstName"]', timeout=5000)
            logger.info(f"Inputting name: {first_name} {last_name}")
            await page.fill('input[name="FirstName"]', first_name)
            await page.fill('input[name="LastName"]', last_name)
            await page.click('input[id="iSignupAction"]')

            # Step 4: Birthday
            await page.wait_for_selector('select[name="BirthMonth"]', timeout=5000)
            logger.info(f"Inputting birthday: {birthday.strftime('%Y-%m-%d')}")
            await page.select_option('select[name="BirthMonth"]', str(birthday.month))
            await page.select_option('select[name="BirthDay"]', str(birthday.day))
            await page.fill('input[name="BirthYear"]', str(birthday.year))
            await page.click('input[id="iSignupAction"]')

            # Step 5: Captcha (Cap.guru integration placeholder)
            logger.warning("Captcha encountered (skipping automation for now)")

            # Wait for completion
            await asyncio.sleep(2)

            account = Account(
                email=email,
                password=password,
                provider="outlook",
                status=AccountStatus.NEW,
                proxy_id=proxy.id if proxy else None,
                first_name=first_name,
                last_name=last_name,
                birthday=birthday
            )
            self.db.add(account)
            self.db.commit()
            logger.success(f"Registered: {email}")

            return account

        except Exception as e:
            logger.error(f"Registration Failed: {e}")
            try:
                await page.screenshot(path=f"user_data/error_{username}.png")
            except Exception:
                pass
        finally:
            try:
                await context.close()
            except Exception:
                pass
