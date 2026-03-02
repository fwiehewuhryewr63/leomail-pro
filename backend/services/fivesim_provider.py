"""
Leomail v3 - 5sim.net SMS Provider
REST API integration: https://5sim.net/docs

Auth: Bearer token in Authorization header
Endpoints:
  - GET /v1/user/profile -> balance
  - GET /v1/user/buy/activation/{country}/any/{product} -> order number
  - GET /v1/user/check/{id} -> poll SMS status
  - GET /v1/user/cancel/{id} -> cancel order
"""
import time
import re
import random
import requests
from loguru import logger


# 5sim product codes (service names in their API)
FIVESIM_PRODUCTS = {
    "gmail": "google",
    "outlook": "microsoft",
    "hotmail": "microsoft",
    "yahoo": "yahoo",
    "aol": "aol",
    "any": "other",
}

# 5sim country names (lowercase, as used in API URLs)
FIVESIM_COUNTRIES = {
    "ru": "russia",
    "ua": "ukraine",
    "kz": "kazakhstan",
    "cn": "china",
    "ph": "philippines",
    "id": "indonesia",
    "ke": "kenya",
    "br": "brazil",
    "us": "usa",
    "il": "israel",
    "pl": "poland",
    "uk": "england",
    "ng": "nigeria",
    "eg": "egypt",
    "fr": "france",
    "ie": "ireland",
    "za": "southafrica",
    "ro": "romania",
    "se": "sweden",
    "ee": "estonia",
    "ca": "canada",
    "de": "germany",
    "nl": "netherlands",
    "at": "austria",
    "th": "thailand",
    "mx": "mexico",
    "es": "spain",
    "tr": "turkey",
    "cz": "czech",
    "pe": "peru",
    "nz": "newzealand",
    "in": "india",
    "it": "italy",
    "pt": "portugal",
    "co": "colombia",
    "ar": "argentina",
    "cl": "chile",
    "hu": "hungary",
    "bg": "bulgaria",
    "hr": "croatia",
    "be": "belgium",
    "ch": "switzerland",
    "no": "norway",
    "fi": "finland",
    "dk": "denmark",
    "au": "australia",
    "jp": "japan",
    "ae": "uae",
    "sa": "saudiarabia",
}

# Countries known to have quality real numbers
REAL_COUNTRIES = [
    "de", "uk", "pl", "nl", "se", "at", "cz", "ee",
    "fr", "es", "it", "pt", "ro", "bg", "hr",
    "ru", "ua", "kz", "br", "ca", "il", "us",
]


class FiveSimProvider:
    """
    5sim.net API wrapper.
    REST JSON API with Bearer token auth.
    """

    BASE_URL = "https://5sim.net/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._last_country = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def _get(self, path: str, **params) -> dict | None:
        """Make GET request, return JSON or None on error."""
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            logger.debug(f"5sim [{path}]: {resp.status_code} {resp.text[:200]}")
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 400:
                return {"error": resp.json().get("message", "Bad request")}
            elif resp.status_code == 401:
                return {"error": "Invalid 5sim API key"}
            else:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:100]}"}
        except Exception as e:
            logger.error(f"5sim request error: {e}")
            return {"error": str(e)}

    def get_balance(self) -> float:
        """Get account balance."""
        data = self._get("/user/profile")
        if data and "balance" in data:
            return float(data["balance"])
        return 0.0

    def order_number(self, service: str = "gmail", country: str = "auto") -> dict:
        """
        Order a phone number.
        service: gmail, yahoo, aol, outlook, etc.
        country: "auto" = try real-country list, or specific country key
        """
        product = FIVESIM_PRODUCTS.get(service, "other")

        if country == "auto":
            # Try real countries, shuffled
            real_order = list(REAL_COUNTRIES)
            random.shuffle(real_order)

            for c in real_order:
                country_name = FIVESIM_COUNTRIES.get(c)
                if not country_name:
                    continue
                result = self._get(f"/user/buy/activation/{country_name}/any/{product}")
                if result and "id" in result and "phone" in result:
                    phone = result["phone"]
                    # 5sim returns phone with + prefix
                    if phone.startswith("+"):
                        phone = phone[1:]
                    logger.info(f"5sim: [OK] got number from {c} - {phone}")
                    self._last_country = c
                    return {
                        "id": str(result["id"]),
                        "number": phone,
                        "country": c,
                        "service": service,
                    }
                err = result.get("error", "") if result else ""
                logger.debug(f"5sim auto: {c} -> {err}")

            return {"error": "5sim: no real numbers"}

        # Specific country
        country_name = FIVESIM_COUNTRIES.get(country, country)
        result = self._get(f"/user/buy/activation/{country_name}/any/{product}")
        if result and "id" in result and "phone" in result:
            phone = result["phone"]
            if phone.startswith("+"):
                phone = phone[1:]
            self._last_country = country
            return {
                "id": str(result["id"]),
                "number": phone,
                "country": country,
                "service": service,
            }
        return {"error": result.get("error", "5sim: order error") if result else "5sim: no response"}

    def order_number_from_countries(self, service: str = "gmail", countries: list = None, blacklist: set = None) -> dict:
        """
        Order a number from allowed countries list.
        Tries each country in order, skipping blacklisted.
        """
        if not countries:
            return self.order_number(service, "auto")

        product = FIVESIM_PRODUCTS.get(service, "other")
        available = [c for c in countries if not blacklist or c not in blacklist]

        for attempt in range(3):
            for c in available:
                country_name = FIVESIM_COUNTRIES.get(c)
                if not country_name:
                    continue
                result = self._get(f"/user/buy/activation/{country_name}/any/{product}")
                if result and "id" in result and "phone" in result:
                    phone = result["phone"]
                    if phone.startswith("+"):
                        phone = phone[1:]
                    logger.info(f"5sim: [OK] {c} - {phone}")
                    self._last_country = c
                    return {
                        "id": str(result["id"]),
                        "number": phone,
                        "country": c,
                        "service": service,
                    }

            if attempt < 2:
                logger.info(f"5sim: no numbers, retry {attempt+1}/3 in 5s...")
                time.sleep(5)

        return {"error": f"5sim: no numbers in any of {len(available)} countries"}

    def get_sms_code(self, order_id: str, timeout: int = 300, cancel_event=None) -> dict:
        """
        Poll for SMS code.
        5sim /check/{id} returns JSON with 'sms' array when code arrives.
        Status: PENDING -> RECEIVED -> FINISHED / CANCELED / TIMEOUT
        """
        start = time.time()

        while time.time() - start < timeout:
            # Check cancel
            if cancel_event and cancel_event.is_set():
                try:
                    self.cancel_number(order_id)
                except Exception:
                    pass
                return {"error": "Cancelled by user", "cancelled": True}

            result = self._get(f"/user/check/{order_id}")
            if not result:
                time.sleep(4)
                continue

            status = result.get("status", "")

            if status == "RECEIVED" and result.get("sms"):
                sms_list = result["sms"]
                if sms_list:
                    sms_text = sms_list[0].get("text", "")
                    code = sms_list[0].get("code", "")
                    if not code:
                        # Extract digits from SMS text
                        digits = re.findall(r'\d{4,8}', sms_text)
                        code = digits[0] if digits else sms_text
                    logger.info(f"5sim: SMS received - code={code}")

                    # Finish the order
                    self._get(f"/user/finish/{order_id}")

                    return {
                        "code": code,
                        "raw": sms_text,
                        "wait_time": round(time.time() - start, 1),
                    }

            elif status == "CANCELED":
                return {"error": "Activation cancelled"}
            elif status == "TIMEOUT":
                return {"error": "5sim: timeout on service side"}
            elif status == "FINISHED":
                # Already finished, try to get code from sms
                sms_list = result.get("sms", [])
                if sms_list:
                    code = sms_list[0].get("code", "")
                    return {"code": code, "raw": str(sms_list[0]), "wait_time": round(time.time() - start, 1)}
                return {"error": "Activation finished but code not found"}

            # PENDING - wait and retry
            for _ in range(8):  # 8 x 0.5s = 4s
                if cancel_event and cancel_event.is_set():
                    try:
                        self.cancel_number(order_id)
                    except Exception:
                        pass
                    return {"error": "Cancelled by user", "cancelled": True}
                time.sleep(0.5)

        # Timeout - cancel the number
        try:
            self.cancel_number(order_id)
        except Exception:
            pass
        return {"error": f"Timeout {timeout}с - SMS not received", "timeout": True}

    def cancel_number(self, order_id: str) -> bool:
        """Cancel an order."""
        result = self._get(f"/user/cancel/{order_id}")
        return result is not None and "error" not in result

    def complete_activation(self, order_id: str) -> str:
        """Mark order as finished."""
        result = self._get(f"/user/finish/{order_id}")
        return "ok" if result and "error" not in result else "error"

    def get_prices(self, service: str = "gmail") -> dict:
        """Get prices for a product across countries."""
        product = FIVESIM_PRODUCTS.get(service, "other")
        result = self._get(f"/guest/prices", product=product)
        if not result or "error" in result:
            return {"prices": [], "error": result.get("error", "") if result else "no response"}

        prices = []
        country_key_map = {v: k for k, v in FIVESIM_COUNTRIES.items()}
        for country_name, operators in result.items():
            if not isinstance(operators, dict):
                continue
            for operator, data in operators.items():
                if isinstance(data, dict) and data.get("cost", 0) > 0:
                    prices.append({
                        "country": country_key_map.get(country_name, country_name),
                        "country_name": country_name,
                        "operator": operator,
                        "cost": float(data.get("cost", 0)),
                        "count": int(data.get("count", 0)),
                    })
                    break  # One per country (cheapest operator)

        prices.sort(key=lambda x: x["cost"])
        return {"prices": prices}

    def order_best_number(self, service: str = "gmail") -> dict:
        """
        Auto-select MOST EXPENSIVE country for best quality real numbers.
        Sorts by price descending - premium real-SIM providers first.
        Falls back to hardcoded premium country list if prices unavailable.
        """
        product = FIVESIM_PRODUCTS.get(service, "other")

        # Step 1: Get prices and sort by cost DESC (most expensive = best quality)
        try:
            prices_data = self.get_prices(service)
            prices = prices_data.get("prices", [])
            if prices:
                # Sort by cost DESC - most expensive first = highest quality
                prices.sort(key=lambda x: x["cost"], reverse=True)
                logger.info(f"5sim: {len(prices)} countries, top prices: "
                           f"{[(p['country'], p['cost']) for p in prices[:5]]}")

                # Try each country, most expensive first
                for p in prices:
                    if p.get("count", 0) <= 0:
                        continue
                    country = p["country"]
                    country_name = FIVESIM_COUNTRIES.get(country, p.get("country_name", country))
                    result = self._get(f"/user/buy/activation/{country_name}/any/{product}")
                    if result and "id" in result and "phone" in result:
                        phone = result["phone"]
                        if phone.startswith("+"):
                            phone = phone[1:]
                        logger.info(f"5sim: [BEST] {country} @ {p['cost']}₽ - {phone}")
                        self._last_country = country
                        return {
                            "id": str(result["id"]),
                            "number": phone,
                            "country": country,
                            "service": service,
                        }
                    logger.debug(f"5sim best: {country} @ {p['cost']}₽ -> no numbers")
        except Exception as e:
            logger.warning(f"5sim: prices unavailable ({e}), falling back to premium list")

        # Step 2: Fallback to premium countries (hardcoded, sorted by typical quality)
        premium_countries = ["de", "uk", "nl", "se", "at", "fr", "it", "us", "ca", "pl"]
        for c in premium_countries:
            country_name = FIVESIM_COUNTRIES.get(c)
            if not country_name:
                continue
            result = self._get(f"/user/buy/activation/{country_name}/any/{product}")
            if result and "id" in result and "phone" in result:
                phone = result["phone"]
                if phone.startswith("+"):
                    phone = phone[1:]
                logger.info(f"5sim: [FALLBACK] {c} - {phone}")
                self._last_country = c
                return {
                    "id": str(result["id"]),
                    "number": phone,
                    "country": c,
                    "service": service,
                }

        return {"error": "5sim: no premium numbers available"}
