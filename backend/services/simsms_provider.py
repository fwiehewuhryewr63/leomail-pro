"""
Leomail v3.0 — SimSMS.org Provider
Full API integration based on https://simsms.org/new_theme_api.html
Uses handler_api.php endpoint with text-based responses.
"""
import time
import re
import requests
from loguru import logger

BASE_URL = "https://simsms.org/stubs/handler_api.php"

# Service codes from SimSMS docs
SERVICE_CODES = {
    "gmail": "go",       # Google, YouTube, Gmail
    "outlook": "mm",     # Microsoft
    "hotmail": "mm",     # Microsoft
    "yahoo": "mb",       # Yahoo
    "aol": "pm",         # AOL
    "mail_ru": "ma",     # Mail.ru
    "any": "ot",         # Any other
}

# Country codes from SimSMS docs
COUNTRY_CODES = {
    "ru": "0",    # Russia
    "ua": "1",    # Ukraine
    "kz": "2",    # Kazakhstan
    "cn": "3",    # China
    "ph": "4",    # Philippines
    "id": "6",    # Indonesia
    "ke": "8",    # Kenya
    "br": "10",   # Brazil
    "us": "12",   # USA
    "il": "13",   # Israel
    "pl": "15",   # Poland
    "uk": "16",   # England
    "us_v": "17", # USA Virtual
    "ng": "19",   # Nigeria
    "eg": "21",   # Egypt
    "fr": "22",   # France
    "ie": "23",   # Ireland
    "za": "31",   # South Africa
    "ro": "32",   # Romania
    "se": "33",   # Sweden
    "ee": "34",   # Estonia
    "ca": "36",   # Canada
    "de": "43",   # Germany
    "nl": "48",   # Netherlands
    "at": "50",   # Austria
    "th": "52",   # Thailand
    "mx": "54",   # Mexico
    "es": "56",   # Spain
    "tr": "62",   # Turkey
    "cz": "63",   # Czech Republic
    "pe": "65",   # Peru
    "nz": "67",   # New Zealand
}


class SimSmsProvider:
    """SimSMS.org API wrapper using handler_api.php endpoint."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _request(self, action: str, **extra_params) -> str:
        """Make API request. Returns raw text response."""
        params = {
            "api_key": self.api_key,
            "action": action,
        }
        params.update(extra_params)

        try:
            resp = requests.get(BASE_URL, params=params, timeout=20)
            text = resp.text.strip()
            logger.debug(f"SimSMS [{action}]: {text[:200]}")
            return text
        except Exception as e:
            logger.error(f"SimSMS request error: {e}")
            return f"ERROR:{e}"

    def get_balance(self) -> float:
        """Get current balance. Response: ACCESS_BALANCE:123.45"""
        text = self._request("getBalance")
        if text.startswith("ACCESS_BALANCE:"):
            try:
                return float(text.split(":")[1])
            except (ValueError, IndexError):
                return -1
        logger.error(f"SimSMS balance error: {text}")
        return -1

    def get_available_count(self, service: str = "gmail", country: str = "ru") -> dict:
        """
        Get available numbers count for service+country.
        Response is JSON: {"go_0": "323", "mm_0": "330", ...}
        """
        country_code = COUNTRY_CODES.get(country, country)
        text = self._request("getNumbersStatus", country=country_code)

        try:
            import json
            data = json.loads(text)
            service_code = SERVICE_CODES.get(service, "go")
            key = f"{service_code}_{country_code}"
            count = int(data.get(key, 0))
            return {"available": count, "country": country, "service": service}
        except Exception as e:
            logger.error(f"SimSMS count parse error: {e}, raw: {text[:200]}")
            return {"available": 0, "error": str(e)}

    def get_prices(self, service: str = "gmail") -> dict:
        """
        Get prices for a service across all countries.
        API: getPrices — returns {country_code: {service_code: {cost, count}}}
        """
        service_code = SERVICE_CODES.get(service, "go")
        text = self._request("getPrices", service=service_code)
        try:
            import json
            data = json.loads(text)
            # data = {"0": {"go": {"cost": "10.00", "count": 500}}, "1": {"go": {...}}, ...}
            prices = []
            country_name_map = {v: k for k, v in COUNTRY_CODES.items()}
            for country_code, services in data.items():
                if service_code in services:
                    info = services[service_code]
                    cost = float(info.get("cost", 9999))
                    count = int(info.get("count", 0))
                    if count > 0:
                        prices.append({
                            "country_code": country_code,
                            "country": country_name_map.get(country_code, country_code),
                            "cost": cost,
                            "count": count,
                        })
            # Sort by cost ascending
            prices.sort(key=lambda x: x["cost"])
            return {"prices": prices}
        except Exception as e:
            logger.error(f"SimSMS getPrices error: {e}")
            return {"prices": [], "error": str(e)}

    def order_number_from_countries(self, service: str = "gmail", countries: list = None, blacklist: set = None) -> dict:
        """
        Order a number from a list of allowed countries (random order).
        Retries up to 3 times with 5s delay if no numbers available.
        """
        import random
        if not countries:
            return self.order_cheapest_number(service)

        service_code = SERVICE_CODES.get(service, "go")
        available = [c for c in countries if not blacklist or c not in blacklist]
        if not available:
            # All blacklisted — reset and try all
            available = list(countries)

        # Retry up to 3 times with 5s delay
        for attempt in range(3):
            order = list(available)
            random.shuffle(order)

            for country in order:
                country_code = COUNTRY_CODES.get(country, country)
                result = self._request("getNumber", service=service_code, country=country_code)
                if result.startswith("ACCESS_NUMBER:"):
                    parts = result.split(":")
                    if len(parts) >= 3:
                        logger.info(f"SimSMS: got number from {country} (country rotation)")
                        self._last_country = country  # Track for blacklist
                        return {
                            "id": parts[1],
                            "number": parts[2],
                            "country": country,
                            "service": service,
                        }
                logger.debug(f"SimSMS: {country} ({country_code}) → {result}")

            if attempt < 2:
                logger.info(f"SimSMS: no numbers, retry {attempt+1}/3 in 5s...")
                time.sleep(5)

        return {"error": f"Нет номеров ни в одной из {len(available)} стран"}

    def order_cheapest_number(self, service: str = "gmail") -> dict:
        """
        Auto-select cheapest country and order number.
        Tries getPrices first, falls back to cheap country list.
        """
        service_code = SERVICE_CODES.get(service, "go")

        # Try to get prices and find cheapest
        price_data = self.get_prices(service)
        cheap_countries = price_data.get("prices", [])

        if cheap_countries:
            # Try top 5 cheapest countries
            for entry in cheap_countries[:5]:
                country_code = entry["country_code"]
                logger.info(f"SimSMS: trying {entry['country']} ({country_code}) — ${entry['cost']} ({entry['count']} avail)")
                result = self._request("getNumber", service=service_code, country=country_code)
                if result.startswith("ACCESS_NUMBER:"):
                    parts = result.split(":")
                    if len(parts) >= 3:
                        return {
                            "id": parts[1],
                            "number": parts[2],
                            "country": entry["country"],
                            "cost": entry["cost"],
                            "service": service,
                        }
                logger.info(f"SimSMS: {entry['country']} failed: {result}")

        # Fallback: try a list of typically cheap countries
        fallback_countries = ["id", "ph", "ke", "ng", "ru", "ua", "kz", "br", "mx"]
        for country in fallback_countries:
            country_code = COUNTRY_CODES.get(country, country)
            result = self._request("getNumber", service=service_code, country=country_code)
            if result.startswith("ACCESS_NUMBER:"):
                parts = result.split(":")
                if len(parts) >= 3:
                    logger.info(f"SimSMS: got number from {country} (fallback)")
                    return {
                        "id": parts[1],
                        "number": parts[2],
                        "country": country,
                        "service": service,
                    }

        return {"error": "Нет доступных номеров ни в одной стране"}

    def order_number(self, service: str = "gmail", country: str = "auto") -> dict:
        """
        Order a phone number.
        country="auto" → auto-select cheapest country.
        Response: ACCESS_NUMBER:$id:$number
        Errors: NO_NUMBERS, NO_BALANCE, BAD_KEY, BAD_SERVICE
        """
        # Auto-cheapest mode
        if country == "auto":
            return self.order_cheapest_number(service)

        service_code = SERVICE_CODES.get(service, "go")
        country_code = COUNTRY_CODES.get(country, country)

        text = self._request(
            "getNumber",
            service=service_code,
            country=country_code,
        )

        if text.startswith("ACCESS_NUMBER:"):
            parts = text.split(":")
            if len(parts) >= 3:
                return {
                    "id": parts[1],
                    "number": parts[2],
                    "country": country,
                    "service": service,
                }

        # Error mapping
        error_map = {
            "NO_NUMBERS": "Нет свободных номеров",
            "NO_BALANCE": "Недостаточно средств",
            "BAD_KEY": "Неверный API ключ",
            "BAD_SERVICE": "Неверный сервис",
            "BAD_ACTION": "Неверное действие",
            "ERROR_SQL": "Ошибка сервера SimSMS",
        }
        error_msg = error_map.get(text, f"Ошибка SimSMS: {text}")
        return {"error": error_msg}

    def get_sms_code(self, order_id: str, timeout: int = 300, cancel_event=None) -> dict:
        """
        Wait for SMS code.
        Response: STATUS_OK:code
        Waiting: STATUS_WAIT_CODE
        cancel_event: threading.Event — if set, abort immediately
        """
        start = time.time()
        while time.time() - start < timeout:
            # Check cancel event before each poll
            if cancel_event and cancel_event.is_set():
                try:
                    self.cancel_order(order_id)
                except Exception:
                    pass
                return {"error": "Отменено пользователем", "cancelled": True}

            text = self._request("getStatus", id=order_id)

            if text.startswith("STATUS_OK:"):
                code_raw = text.split(":", 1)[1]
                # Extract digits from SMS text
                digits = re.findall(r'\d{4,8}', code_raw)
                return {
                    "code": digits[0] if digits else code_raw,
                    "raw": code_raw,
                    "wait_time": round(time.time() - start, 1),
                }
            elif text == "STATUS_WAIT_CODE":
                # Sleep in small increments to check cancel faster
                for _ in range(6):  # 6 x 0.5s = 3s
                    if cancel_event and cancel_event.is_set():
                        try:
                            self.cancel_order(order_id)
                        except Exception:
                            pass
                        return {"error": "Отменено пользователем", "cancelled": True}
                    time.sleep(0.5)
                continue
            elif text == "STATUS_WAIT_RETRY":
                # SMS sent again, keep waiting
                time.sleep(3)
                continue
            elif text == "STATUS_CANCEL":
                return {"error": "Активация отменена"}
            else:
                return {"error": f"Ошибка получения SMS: {text}"}

        return {"error": f"Таймаут {timeout}с — SMS не получено", "timeout": True}

    def set_status(self, order_id: str, status: int) -> str:
        """
        Set activation status.
        1 = ready (number received, waiting for SMS)
        3 = request another SMS
        6 = activation complete
        8 = cancel activation
        """
        return self._request("setStatus", id=order_id, status=status)

    def cancel_number(self, order_id: str) -> str:
        """Cancel/deny an ordered number."""
        return self.set_status(order_id, 8)

    def complete_activation(self, order_id: str) -> str:
        """Mark activation as complete."""
        return self.set_status(order_id, 6)
