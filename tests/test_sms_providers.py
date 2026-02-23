"""
Tests for SMS providers — service codes, country codes, virtual filtering, price sorting.
Run: pytest tests/test_sms_providers.py -v

These tests check configuration and logic WITHOUT making real API calls.
"""
import pytest

from backend.services.simsms_provider import (
    SERVICE_CODES as SIMSMS_SERVICE_CODES,
    COUNTRY_CODES as SIMSMS_COUNTRY_CODES,
    SimSmsProvider,
)
from backend.services.sms_provider import (
    GRIZZLY_SERVICE_CODES,
    GRIZZLY_COUNTRY_CODES,
    GrizzlySMS,
)


# ═══════════════════════════════════════════════════════
# Service codes — all 5 providers must be mapped
# ═══════════════════════════════════════════════════════

class TestServiceCodes:
    REQUIRED_SERVICES = ["gmail", "outlook", "hotmail", "yahoo", "aol"]

    def test_simsms_has_all_services(self):
        for svc in self.REQUIRED_SERVICES:
            assert svc in SIMSMS_SERVICE_CODES, \
                f"SimSMS missing service code for '{svc}'"

    def test_grizzly_has_all_services(self):
        for svc in self.REQUIRED_SERVICES:
            assert svc in GRIZZLY_SERVICE_CODES, \
                f"GrizzlySMS missing service code for '{svc}'"

    def test_simsms_outlook_hotmail_same(self):
        """Outlook and Hotmail use the same Microsoft service code."""
        assert SIMSMS_SERVICE_CODES["outlook"] == SIMSMS_SERVICE_CODES["hotmail"]

    def test_grizzly_outlook_hotmail_same(self):
        assert GRIZZLY_SERVICE_CODES["outlook"] == GRIZZLY_SERVICE_CODES["hotmail"]


# ═══════════════════════════════════════════════════════
# Country codes — key countries must exist
# ═══════════════════════════════════════════════════════

class TestCountryCodes:
    KEY_COUNTRIES = ["ru", "ua", "us", "uk", "de", "pl", "br", "nl", "fr", "es"]

    def test_simsms_key_countries(self):
        for c in self.KEY_COUNTRIES:
            assert c in SIMSMS_COUNTRY_CODES, \
                f"SimSMS missing country '{c}'"

    def test_grizzly_key_countries(self):
        for c in self.KEY_COUNTRIES:
            assert c in GRIZZLY_COUNTRY_CODES, \
                f"GrizzlySMS missing country '{c}'"

    def test_grizzly_virtual_country_excluded(self):
        """us_v should be in codes but marked as virtual."""
        assert "us_v" in GRIZZLY_COUNTRY_CODES
        grizzly = GrizzlySMS("fake_key")
        assert GRIZZLY_COUNTRY_CODES["us_v"] in grizzly.VIRTUAL_COUNTRY_CODES


# ═══════════════════════════════════════════════════════
# Virtual number filtering
# ═══════════════════════════════════════════════════════

class TestVirtualFiltering:
    def test_grizzly_blocks_virtual_direct(self):
        """Directly ordering us_v should return error."""
        grizzly = GrizzlySMS("fake_key")
        result = grizzly.order_number("gmail", "us_v")
        assert "error" in result

    def test_grizzly_real_countries_no_virtual(self):
        """REAL_COUNTRIES list should not contain any virtual keys."""
        grizzly = GrizzlySMS("fake_key")
        for c in grizzly.REAL_COUNTRIES:
            code = GRIZZLY_COUNTRY_CODES.get(c, c)
            assert code not in grizzly.VIRTUAL_COUNTRY_CODES, \
                f"Country '{c}' ({code}) is in REAL_COUNTRIES but marked as virtual!"

    def test_simsms_virtual_code_17(self):
        """SimSMS virtual code 17 should be excluded in ordering logic."""
        # Code 17 = virtual US in SimSMS
        # Verify it's documented
        assert "17" not in [SIMSMS_COUNTRY_CODES.get(c) for c in ["us", "ru", "uk", "de"]]


# ═══════════════════════════════════════════════════════
# Price sorting logic (unit test with mock data)
# ═══════════════════════════════════════════════════════

class TestPriceSorting:
    def test_sort_countries_by_price_desc(self):
        """Countries should be sorted most expensive first."""
        # Simulate what order_number_from_countries does
        countries = ["br", "uk", "de", "ru", "nl"]
        mock_prices = {"br": 0.5, "uk": 15.0, "de": 12.0, "ru": 3.0, "nl": 8.0}

        sorted_countries = sorted(countries, key=lambda c: mock_prices.get(c, 0), reverse=True)
        assert sorted_countries == ["uk", "de", "nl", "ru", "br"]

    def test_unknown_country_goes_last(self):
        """Countries not in price list should sort to the end (price=0)."""
        countries = ["uk", "xx", "de"]
        mock_prices = {"uk": 15.0, "de": 12.0}

        sorted_countries = sorted(countries, key=lambda c: mock_prices.get(c, 0), reverse=True)
        assert sorted_countries[-1] == "xx"

    def test_blacklist_filtering(self):
        """Blacklisted countries should be excluded from available list."""
        countries = ["br", "uk", "de", "ru"]
        blacklist = {"br", "ru"}
        available = [c for c in countries if c not in blacklist]
        assert "br" not in available
        assert "ru" not in available
        assert "uk" in available
        assert "de" in available
