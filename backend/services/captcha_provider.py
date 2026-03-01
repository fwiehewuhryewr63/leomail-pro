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

    def solve_hcaptcha(self, sitekey: str, url: str) -> str | None:
        """Solve hCaptcha via CapGuru (used by ProtonMail)."""
        params = {
            "key": self.api_key,
            "method": "hcaptcha",
            "sitekey": sitekey,
            "pageurl": url,
            "json": 1,
        }
        try:
            resp = requests.get(f"{self.base_url}/in.php", params=params, timeout=30)
            data = resp.json()
            if data.get("status") != 1:
                logger.error(f"CapGuru hCaptcha submit failed: {data}")
                return None
            request_id = data.get("request")
            logger.info(f"CapGuru hCaptcha Task ID: {request_id}")
            for _ in range(40):
                time.sleep(3)
                res_params = {"key": self.api_key, "action": "get", "id": request_id, "json": 1}
                res_resp = requests.get(f"{self.base_url}/res.php", params=res_params, timeout=15)
                res_data = res_resp.json()
                if res_data.get("status") == 1:
                    return res_data.get("request")
                if res_data.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                    return None
            return None
        except Exception as e:
            logger.error(f"CapGuru hCaptcha Error: {e}")
            return None

    def solve_image(self, image_bytes: bytes) -> str | None:
        """Solve image captcha via CapGuru (base64 OCR). Used for Tuta clock CAPTCHA."""
        import base64
        body = base64.b64encode(image_bytes).decode("ascii")
        try:
            resp = requests.post(
                f"{self.base_url}/in.php",
                data={
                    "key": self.api_key,
                    "method": "base64",
                    "body": body,
                    "json": 1,
                },
                timeout=30,
            )
            data = resp.json()
            if data.get("status") != 1:
                logger.error(f"CapGuru image captcha submit failed: {data}")
                return None
            request_id = data.get("request")
            for _ in range(20):
                time.sleep(3)
                res = requests.get(
                    f"{self.base_url}/res.php",
                    params={"key": self.api_key, "action": "get", "id": request_id, "json": 1},
                    timeout=15,
                )
                res_data = res.json()
                if res_data.get("status") == 1:
                    return res_data.get("request")
                if "ERROR" in str(res_data.get("request", "")):
                    return None
            return None
        except Exception as e:
            logger.error(f"CapGuru image captcha Error: {e}")
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


# ═══════════════════════════════════════════════════════════════════════════════
# CapSolver — supports reCAPTCHA v2/v3, hCaptcha, FunCaptcha via createTask API
# ═══════════════════════════════════════════════════════════════════════════════

class CapSolverProvider:
    """CapSolver.com — modern multi-captcha solver (AI-based, faster than 2captcha)."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://api.capsolver.com"

    def get_balance(self) -> float:
        try:
            res = requests.post(
                f"{self.base_url}/getBalance",
                json={"clientKey": self.api_key},
                timeout=10,
            )
            return res.json().get("balance", 0.0)
        except Exception:
            return 0.0

    def _create_and_poll(self, task: dict, max_attempts: int = 60) -> str | None:
        """Generic createTask + poll getTaskResult."""
        try:
            resp = requests.post(
                f"{self.base_url}/createTask",
                json={"clientKey": self.api_key, "task": task},
                timeout=30,
            )
            data = resp.json()
            if data.get("errorId", 0) != 0:
                logger.error(f"CapSolver createTask error: {data.get('errorDescription', data)}")
                return None

            task_id = data.get("taskId")
            if not task_id:
                logger.error(f"CapSolver: no taskId in response: {data}")
                return None

            logger.info(f"CapSolver Task: {task_id} ({task.get('type', '?')})")

            for attempt in range(max_attempts):
                time.sleep(2)
                res = requests.post(
                    f"{self.base_url}/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=15,
                )
                result = res.json()
                status = result.get("status")
                if status == "ready":
                    solution = result.get("solution", {})
                    # Different captcha types return token in different fields
                    token = (
                        solution.get("gRecaptchaResponse")
                        or solution.get("token")
                        or solution.get("text")
                    )
                    logger.info(f"CapSolver solved in {attempt + 1} attempts")
                    return token
                if result.get("errorId", 0) != 0:
                    logger.error(f"CapSolver error: {result.get('errorDescription')}")
                    return None
            logger.error("CapSolver: timeout")
            return None
        except Exception as e:
            logger.error(f"CapSolver Error: {e}")
            return None

    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str | None:
        return self._create_and_poll({
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        })

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "", min_score: float = 0.7) -> str | None:
        task = {
            "type": "ReCaptchaV3TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "pageAction": action or "submit",
        }
        return self._create_and_poll(task)

    def solve_hcaptcha(self, sitekey: str, url: str) -> str | None:
        return self._create_and_poll({
            "type": "HCaptchaTaskProxyLess",
            "websiteURL": url,
            "websiteKey": sitekey,
        })

    def solve_funcaptcha(self, public_key: str, page_url: str, surl: str = "") -> str | None:
        task = {
            "type": "FunCaptchaTaskProxyLess",
            "websiteURL": page_url,
            "websitePublicKey": public_key,
        }
        if surl:
            task["funcaptchaApiJSSubdomain"] = surl
        return self._create_and_poll(task, max_attempts=80)

    def solve_captcha(self, website_url: str, website_key: str) -> str | None:
        """Compatibility alias for reCAPTCHA v2."""
        return self.solve_recaptcha_v2(website_key, website_url)

    def solve_image(self, image_bytes: bytes) -> str | None:
        """Solve image captcha (OCR)."""
        import base64
        return self._create_and_poll({
            "type": "ImageToTextTask",
            "body": base64.b64encode(image_bytes).decode("ascii"),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# CapMonster Cloud — same createTask API as CapSolver, different endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class CapMonsterProvider(CapSolverProvider):
    """CapMonster.cloud — same API structure as CapSolver, different base URL."""

    def __init__(self, api_key: str = ""):
        super().__init__(api_key)
        self.base_url = "https://api.capmonster.cloud"


# ═══════════════════════════════════════════════════════════════════════════════
# CaptchaChain — tries solvers in priority order with auto-fallback
# ═══════════════════════════════════════════════════════════════════════════════

class CaptchaChain:
    """
    Multi-solver chain with auto-fallback.
    Tries each configured provider in order until one succeeds.
    
    Usage:
        chain = get_captcha_chain()
        token = chain.solve("recaptcha_v2", site_key="...", page_url="...")
        token = chain.solve("funcaptcha", public_key="...", page_url="...")
        token = chain.solve("hcaptcha", sitekey="...", url="...")
    """

    def __init__(self):
        self.providers = []  # list of (name, provider_instance)
        self._load_providers()

    def _load_providers(self):
        """Load all configured captcha providers in priority order."""
        PROVIDER_ORDER = [
            ("capguru", CaptchaProvider, "capguru"),
            ("capsolver", CapSolverProvider, "capsolver"),
            ("capmonster", CapMonsterProvider, "capmonster"),
            ("twocaptcha", TwoCaptchaProvider, "twocaptcha"),
        ]
        for name, cls, config_key in PROVIDER_ORDER:
            key = get_api_key(config_key)
            if key:
                self.providers.append((name, cls(api_key=key)))
                logger.debug(f"CaptchaChain: {name} loaded")

    def solve(self, captcha_type: str, **kwargs) -> str | None:
        """
        Solve a captcha using chain fallback.
        
        captcha_type: "recaptcha_v2", "recaptcha_v3", "hcaptcha", "funcaptcha", "image"
        kwargs: passed to the solver method
        """
        method_map = {
            "recaptcha_v2": "solve_captcha",
            "recaptcha_v3": "solve_recaptcha_v3",
            "hcaptcha": "solve_hcaptcha",
            "funcaptcha": "solve_funcaptcha",
            "image": "solve_image",
        }
        method_name = method_map.get(captcha_type)
        if not method_name:
            logger.error(f"CaptchaChain: unknown type '{captcha_type}'")
            return None

        for name, provider in self.providers:
            method = getattr(provider, method_name, None)
            if not method:
                continue  # this provider doesn't support this type
            try:
                logger.info(f"CaptchaChain: trying {name} for {captcha_type}")
                result = method(**kwargs)
                if result:
                    logger.info(f"CaptchaChain: {name} solved {captcha_type} ✓")
                    return result
                logger.warning(f"CaptchaChain: {name} returned None for {captcha_type}")
            except Exception as e:
                logger.error(f"CaptchaChain: {name} error: {e}")
                continue

        logger.error(f"CaptchaChain: all providers failed for {captcha_type}")
        return None

    def get_balances(self) -> dict:
        """Get balance from all configured providers."""
        balances = {}
        for name, provider in self.providers:
            try:
                balances[name] = provider.get_balance()
            except Exception:
                balances[name] = -1
        return balances


def get_captcha_provider() -> CaptchaProvider | None:
    """Get CapGuru provider instance."""
    key = get_api_key("capguru")
    return CaptchaProvider(api_key=key) if key else None


def get_twocaptcha_provider() -> TwoCaptchaProvider | None:
    """Get 2Captcha provider instance."""
    key = get_api_key("twocaptcha")
    return TwoCaptchaProvider(api_key=key) if key else None


def get_capsolver_provider() -> CapSolverProvider | None:
    """Get CapSolver provider instance."""
    key = get_api_key("capsolver")
    return CapSolverProvider(api_key=key) if key else None


def get_capmonster_provider() -> CapMonsterProvider | None:
    """Get CapMonster provider instance."""
    key = get_api_key("capmonster")
    return CapMonsterProvider(api_key=key) if key else None


def get_captcha_chain() -> CaptchaChain:
    """Get the multi-solver chain (auto-loads all configured providers)."""
    return CaptchaChain()

