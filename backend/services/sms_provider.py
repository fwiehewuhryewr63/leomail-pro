"""
Leomail v3 — SMS Provider
Abstract base + GrizzlySMS implementation.
SimSMS is in a separate file: simsms_provider.py

GrizzlySMS API: https://grizzlysms.com/docs
  - Compatible with sms-activate API format
  - Base URL: https://api.grizzlysms.com/stubs/handler_api.php
  - Response format: ACCESS_NUMBER:id:number, STATUS_OK:code, etc.
"""
import time
import re
import random
import requests
from abc import ABC, abstractmethod
from loguru import logger


class SMSProvider(ABC):
    """Abstract SMS provider interface."""

    @abstractmethod
    def get_balance(self) -> float:
        ...

    @abstractmethod
    def order_number(self, service: str, country: str) -> dict:
        """Order a phone number. Returns {id, number} or {error}."""
        ...

    @abstractmethod
    def get_sms_code(self, order_id: str, timeout: int = 300, cancel_event=None) -> dict:
        """Wait for and return SMS code dict, or error dict on timeout."""
        ...

    @abstractmethod
    def cancel_number(self, order_id: str) -> bool:
        """Cancel/release a number order."""
        ...


# Grizzly SMS service codes (sms-activate compatible)
GRIZZLY_SERVICE_CODES = {
    "gmail": "go",       # Google / Gmail / YouTube
    "outlook": "mm",     # Microsoft / Outlook
    "hotmail": "mm",     # Microsoft / Hotmail
    "yahoo": "mb",       # Yahoo (sms-activate standard)
    "aol": "pm",         # AOL
    "yandex": "ya",      # Yandex
    "mail_ru": "ma",     # Mail.ru
    "any": "ot",         # Any other service
}

# Country codes from Grizzly API (getCountries endpoint)
# IMPORTANT: These are DIFFERENT from SimSMS codes!
GRIZZLY_COUNTRY_CODES = {
    "ru": "0",     # Russia
    "ua": "1",     # Ukraine
    "kz": "2",     # Kazakhstan
    "cn": "3",     # China
    "ph": "4",     # Philippines
    "mm_c": "5",   # Myanmar
    "id": "6",     # Indonesia
    "my": "7",     # Malaysia
    "ke": "8",     # Kenya
    "tz": "9",     # Tanzania
    "vn": "10",    # Vietnam
    "kg": "11",    # Kyrgyzstan
    "us": "12",    # USA (2)
    "il": "13",    # Israel
    "hk": "14",    # Hong Kong
    "pl": "15",    # Poland
    "uk": "16",    # United Kingdom
    "mg": "17",    # Madagascar
    "cd": "18",    # DR Congo
    "ng": "19",    # Nigeria
    "eg": "21",    # Egypt
    "in": "22",    # India
    "ie": "23",    # Ireland
    "kh": "24",    # Cambodia
    "la": "25",    # Lao
    "ht": "26",    # Haiti
    "ci": "27",    # Ivory Coast
    "gm": "28",    # Gambia
    "rs": "29",    # Serbia
    "ye": "30",    # Yemen
    "za": "31",    # South Africa
    "ro": "32",    # Romania
    "co": "33",    # Colombia (NOT Sweden!)
    "ee": "34",    # Estonia
    "az": "35",    # Azerbaijan
    "ca": "36",    # Canada
    "ma": "37",    # Morocco
    "gh": "38",    # Ghana
    "ar": "39",    # Argentina
    "uz": "40",    # Uzbekistan
    "cm": "41",    # Cameroon
    "td": "42",    # Chad
    "de": "43",    # Germany
    "lt": "44",    # Lithuania
    "hr": "45",    # Croatia
    "se": "46",    # Sweden (in Grizzly = 46, NOT 33!)
    "iq": "47",    # Iraq
    "nl": "48",    # Netherlands
    "lv": "49",    # Latvia
    "at": "50",    # Austria
    "by": "51",    # Belarus
    "th": "52",    # Thailand
    "sa": "53",    # Saudi Arabia
    "mx": "54",    # Mexico
    "tw": "55",    # Taiwan
    "es": "56",    # Spain
    "dz": "58",    # Algeria
    "si": "59",    # Slovenia
    "bd": "60",    # Bangladesh
    "sn": "61",    # Senegal
    "tr": "62",    # Turkey
    "cz": "63",    # Czech
    "lk": "64",    # Sri Lanka
    "pe": "65",    # Peru
    "pk": "66",    # Pakistan
    "nz": "67",    # New Zealand
    "gn": "68",    # Guinea
    "ml": "69",    # Mali
    "ve": "70",    # Venezuela
    "et": "71",    # Ethiopia
    "mn": "72",    # Mongolia
    "br": "73",    # Brazil (in Grizzly = 73, NOT 10!)
    "af": "74",    # Afghanistan
    "ug": "75",    # Uganda
    "ao": "76",    # Angola
    "cy": "77",    # Cyprus
    "fr": "78",    # France (in Grizzly = 78, NOT 22!)
    "pg": "79",    # Papua New Guinea
    "mz": "80",    # Mozambique
    "np": "81",    # Nepal
    "be": "82",    # Belgium
    "bg": "83",    # Bulgaria
    "hu": "84",    # Hungary
    "md": "85",    # Moldova
    "it": "86",    # Italy
    "py": "87",    # Paraguay
    "hn": "88",    # Honduras
    "tn": "89",    # Tunisia
    "ni": "90",    # Nicaragua
    "bo": "92",    # Bolivia
    "cr": "93",    # Costa Rica
    "gt": "94",    # Guatemala
    "ae": "95",    # UAE
    "zw": "96",    # Zimbabwe
    "pt": "117",   # Portugal
    "ge": "128",   # Georgia
    "gr": "129",   # Greece
    "is": "132",   # Iceland
    "sk": "141",   # Slovakia
    "tj": "143",   # Tajikistan
    "bh": "145",   # Bahrain
    "zm": "147",   # Zambia
    "am": "148",   # Armenia
    "cl": "151",   # Chile
    "lb": "153",   # Lebanon
    "al": "155",   # Albania
    "uy": "156",   # Uruguay
    "fi": "163",   # Finland
    "dk": "172",   # Denmark
    "ch": "173",   # Switzerland
    "no": "174",   # Norway
    "au": "175",   # Australia
    "jp": "182",   # Japan
    "us_v": "187", # USA (virtual)
}


class GrizzlySMS(SMSProvider):
    """
    GrizzlySMS API — https://grizzlysms.com/docs
    Compatible with sms-activate API format.
    """

    BASE_URL = "https://api.grizzlysms.com/stubs/handler_api.php"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._last_country = None  # Track for blacklist

    def _request(self, action: str, **params) -> str:
        """Make API request. Returns raw text response."""
        params["api_key"] = self.api_key
        params["action"] = action
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            text = resp.text.strip()
            logger.debug(f"GrizzlySMS [{action}]: {text[:100]}")
            return text
        except Exception as e:
            logger.error(f"GrizzlySMS request error: {e}")
            return f"ERROR:{e}"

    def get_balance(self) -> float:
        result = self._request("getBalance")
        # Response: ACCESS_BALANCE:123.45
        if result.startswith("ACCESS_BALANCE:"):
            try:
                return float(result.split(":")[1])
            except ValueError:
                return 0.0
        return 0.0

    def order_number_from_countries(self, service: str = "gmail", countries: list = None, blacklist: set = None) -> dict:
        """
        Order a number from a list of allowed countries (random order).
        countries: list of country keys like ["ru", "kz", "br"]
        blacklist: set of country keys to skip (temp-failed)
        If countries is empty/None, falls back to order_number with auto.
        Retries up to 3 times with 5s delay if no numbers available.
        """
        if not countries:
            return self.order_number(service, "auto")

        service_code = GRIZZLY_SERVICE_CODES.get(service, "go")
        available = [c for c in countries if not blacklist or c not in blacklist]
        if not available:
            # All blacklisted — reset and try all
            available = list(countries)

        # Retry up to 3 times with 5s delay
        for attempt in range(3):
            order = list(available)
            random.shuffle(order)

            for country in order:
                country_code = GRIZZLY_COUNTRY_CODES.get(country, country)
                # Use getNumberV2 with maxPrice for premium real numbers
                result = self._request("getNumberV2", service=service_code, country=country_code, maxPrice=150)
                if result.startswith("ACCESS_NUMBER:"):
                    parts = result.split(":")
                    if len(parts) >= 3:
                        logger.info(f"GrizzlySMS: got number from {country} (country rotation)")
                        self._last_country = country
                        return {
                            "id": parts[1],
                            "number": parts[2],
                            "country": country,
                            "service": service,
                        }
                logger.debug(f"GrizzlySMS: {country} ({country_code}) → {result}")

            if attempt < 2:
                logger.info(f"GrizzlySMS: no numbers, retry {attempt+1}/3 in 5s...")
                time.sleep(5)

        return {"error": f"Нет номеров ни в одной из {len(available)} стран"}

    def order_number(self, service: str = "gmail", country: str = "auto") -> dict:
        """
        Order a phone number.
        service: gmail, yahoo, aol, outlook, etc.
        country: "auto" = let Grizzly auto-select, or country key
        """
        service_code = GRIZZLY_SERVICE_CODES.get(service, "go")

        if country == "auto":
            # Use getNumberV2 with maxPrice for premium real numbers (not virtual)
            result = self._request("getNumberV2", service=service_code, country="any", maxPrice=150)
            if result.startswith("ACCESS_NUMBER:"):
                parts = result.split(":")
                if len(parts) >= 3:
                    logger.info(f"GrizzlySMS: got PREMIUM number (auto, maxPrice=150)")
                    self._last_country = "auto"
                    return {"id": parts[1], "number": parts[2], "country": "auto", "service": service}

            # Map error (no cheap fallback — we want quality numbers only)
            error_map = {
                "NO_NUMBERS": "Нет свободных номеров (premium)",
                "NO_BALANCE": "Недостаточно средств",
                "BAD_KEY": "Неверный API ключ",
                "BAD_SERVICE": "Неверный сервис",
                "BAD_ACTION": "Неверное действие",
            }
            return {"error": error_map.get(result, f"GrizzlySMS: {result}")}

        # Specific country — use getNumberV2 with maxPrice for premium
        country_code = GRIZZLY_COUNTRY_CODES.get(country, country)
        result = self._request("getNumberV2", service=service_code, country=country_code, maxPrice=150)
        if result.startswith("ACCESS_NUMBER:"):
            parts = result.split(":")
            if len(parts) >= 3:
                self._last_country = country
                return {"id": parts[1], "number": parts[2], "country": country, "service": service}

        error_map = {
            "NO_NUMBERS": "Нет свободных номеров",
            "NO_BALANCE": "Недостаточно средств",
            "BAD_KEY": "Неверный API ключ",
        }
        return {"error": error_map.get(result, f"GrizzlySMS: {result}")}

    def get_sms_code(self, order_id: str, timeout: int = 300, cancel_event=None) -> dict:
        """
        Wait for SMS code with support for cancellation.
        timeout: seconds to wait (default 5 minutes)
        cancel_event: threading.Event — if set, abort immediately
        Response: STATUS_OK:code
        Waiting: STATUS_WAIT_CODE
        """
        # First, set status to "ready" (1)
        self._request("setStatus", id=order_id, status="1")

        start = time.time()
        while time.time() - start < timeout:
            # Check cancel event before each poll
            if cancel_event and cancel_event.is_set():
                try:
                    self.cancel_number(order_id)
                except Exception:
                    pass
                return {"error": "Отменено пользователем", "cancelled": True}

            result = self._request("getStatus", id=order_id)

            if result.startswith("STATUS_OK:"):
                code_raw = result.split(":", 1)[1]
                # Extract digits from SMS text
                digits = re.findall(r'\d{4,8}', code_raw)
                return {
                    "code": digits[0] if digits else code_raw,
                    "raw": code_raw,
                    "wait_time": round(time.time() - start, 1),
                }
            elif result == "STATUS_WAIT_CODE":
                # Sleep in small increments to check cancel faster
                for _ in range(8):  # 8 x 0.5s = 4s
                    if cancel_event and cancel_event.is_set():
                        try:
                            self.cancel_number(order_id)
                        except Exception:
                            pass
                        return {"error": "Отменено пользователем", "cancelled": True}
                    time.sleep(0.5)
                continue
            elif "STATUS_WAIT_RETRY" in result:
                time.sleep(3)
                continue
            elif result == "STATUS_CANCEL":
                return {"error": "Активация отменена"}
            else:
                logger.warning(f"GrizzlySMS unexpected status: {result}")
                return {"error": f"Ошибка: {result}"}

        return {"error": f"Таймаут {timeout}с — SMS не получено", "timeout": True}

    def set_status(self, order_id: str, status: int) -> str:
        """Set activation status: 1=ready, 3=retry, 6=complete, 8=cancel."""
        return self._request("setStatus", id=order_id, status=str(status))

    def cancel_number(self, order_id: str) -> bool:
        result = self._request("setStatus", id=order_id, status="8")
        return "ACCESS" in result

    def complete_activation(self, order_id: str) -> str:
        return self._request("setStatus", id=order_id, status="6")

    def get_prices(self, service: str = "gmail") -> dict:
        """Get prices for a service across countries."""
        service_code = GRIZZLY_SERVICE_CODES.get(service, "go")
        text = self._request("getPrices", service=service_code)
        try:
            import json
            data = json.loads(text)
            country_name_map = {v: k for k, v in GRIZZLY_COUNTRY_CODES.items()}
            prices = []
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
            prices.sort(key=lambda x: x["cost"])
            return {"prices": prices}
        except Exception as e:
            logger.error(f"GrizzlySMS getPrices error: {e}")
            return {"prices": [], "error": str(e)}
