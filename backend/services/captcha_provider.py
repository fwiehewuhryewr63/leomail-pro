"""
Captcha providers:
 - CapGuru: reCAPTCHA v2/v3 (Gmail, Yahoo, AOL)
 - 2Captcha: FunCaptcha / Arkose Labs (Outlook, Hotmail)
"""
import requests
import time
from loguru import logger
from ..config import load_config, get_api_key


class CaptchaProvider:
    """CapGuru — solves reCAPTCHA v2/v3."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "http://api.cap.guru"

    def get_balance(self) -> float:
        """Check CapGuru balance."""
        try:
            res = requests.get(
                f"{self.base_url}/res.php",
                params={"key": self.api_key, "action": "getbalance"},
                timeout=10,
            )
            return float(res.text.strip())
        except Exception:
            return 0.0

    def solve_recaptcha_v2(self, site_key, page_url):
        logger.info(f"Solving ReCaptcha v2 for {page_url}")
        try:
            res = requests.get(
                f"{self.base_url}/in.php?key={self.api_key}"
                f"&method=userrecaptcha&googlekey={site_key}&pageurl={page_url}"
            )
            if "OK|" in res.text:
                task_id = res.text.split("|")[1]
                return task_id
        except Exception as e:
            logger.error(f"Captcha submit failed: {e}")
        return None

    def solve_captcha(self, website_url: str, website_key: str) -> str | None:
        """Solve reCAPTCHA via CapGuru (polling)."""
        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": website_key,
            "pageurl": website_url,
            "json": 1,
        }
        try:
            resp = requests.get(f"{self.base_url}/in.php", params=params)
            data = resp.json()
            if data.get("status") != 1:
                logger.error(f"CapGuru Create Task Failed: {data}")
                return None

            request_id = data.get("request")
            logger.info(f"CapGuru Task ID: {request_id}")

            # Poll for Result
            for _ in range(30):
                time.sleep(2)
                res_params = {"key": self.api_key, "action": "get", "id": request_id, "json": 1}
                res_resp = requests.get(f"{self.base_url}/res.php", params=res_params)
                res_data = res_resp.json()

                if res_data.get("status") == 1:
                    return res_data.get("request")
                if res_data.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                    return None

            return None
        except Exception as e:
            logger.error(f"CapGuru Error: {e}")
            return None


class TwoCaptchaProvider:
    """2Captcha — solves FunCaptcha / Arkose Labs (for Outlook/Hotmail)."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "http://2captcha.com"

    def solve_funcaptcha(self, public_key: str, page_url: str, surl: str = "") -> str | None:
        """
        Solve Arkose Labs / FunCaptcha.
        public_key: FC public key (e.g. 'B7D8911C-5CC8-A9A3-35B0-554ACEE604DA')
        page_url: the page URL where captcha appears
        surl: optional service URL (Arkose API endpoint)
        """
        logger.info(f"2Captcha: solving FunCaptcha for {page_url}")
        params = {
            "key": self.api_key,
            "method": "funcaptcha",
            "publickey": public_key,
            "pageurl": page_url,
            "json": 1,
        }
        if surl:
            params["surl"] = surl

        try:
            resp = requests.post(f"{self.base_url}/in.php", data=params, timeout=30)
            data = resp.json()

            if data.get("status") != 1:
                logger.error(f"2Captcha submit failed: {data}")
                return None

            task_id = data.get("request")
            logger.info(f"2Captcha Task ID: {task_id}")

            # Poll (FunCaptcha can take 20-60s)
            for attempt in range(45):
                time.sleep(3)
                res = requests.get(
                    f"{self.base_url}/res.php",
                    params={"key": self.api_key, "action": "get", "id": task_id, "json": 1},
                    timeout=15,
                )
                res_data = res.json()

                if res_data.get("status") == 1:
                    token = res_data.get("request")
                    logger.info(f"2Captcha FunCaptcha solved (attempt {attempt + 1})")
                    return token
                if "CAPCHA_NOT_READY" not in str(res_data.get("request", "")):
                    logger.error(f"2Captcha error: {res_data}")
                    return None

            logger.error("2Captcha: timeout after 45 attempts")
            return None
        except Exception as e:
            logger.error(f"2Captcha Error: {e}")
            return None

    def get_balance(self) -> float:
        """Check 2Captcha balance."""
        try:
            res = requests.get(
                f"{self.base_url}/res.php",
                params={"key": self.api_key, "action": "getbalance", "json": 1},
                timeout=10,
            )
            return float(res.json().get("request", 0))
        except Exception:
            return 0.0


def get_captcha_provider() -> CaptchaProvider | None:
    """Get CapGuru provider instance."""
    key = get_api_key("capguru")
    return CaptchaProvider(api_key=key) if key else None


def get_twocaptcha_provider() -> TwoCaptchaProvider | None:
    """Get 2Captcha provider instance."""
    key = get_api_key("twocaptcha")
    return TwoCaptchaProvider(api_key=key) if key else None
