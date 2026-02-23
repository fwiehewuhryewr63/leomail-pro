"""
Tests for birth helpers — phone country maps, country-to-ISO2, constants.
Run: pytest tests/test_helpers.py -v
"""
import pytest

from backend.modules.birth._helpers import PHONE_COUNTRY_MAP, COUNTRY_TO_ISO2


# ═══════════════════════════════════════════════════════
# Phone country code maps
# ═══════════════════════════════════════════════════════

class TestPhoneCountryMap:
    def test_key_countries_present(self):
        """All commonly used SMS countries should have phone prefixes."""
        required = ["ru", "ua", "us", "uk", "de", "pl", "br", "nl", "fr", "es",
                     "it", "cz", "ee", "se", "at", "ca", "tr"]
        for c in required:
            assert c in PHONE_COUNTRY_MAP, \
                f"Missing phone prefix for '{c}'"

    def test_prefixes_are_numeric(self):
        """All phone prefixes should be numeric strings."""
        for country, prefix in PHONE_COUNTRY_MAP.items():
            assert prefix.isdigit(), \
                f"Country '{country}' has non-numeric prefix '{prefix}'"

    def test_known_prefixes(self):
        """Spot-check well-known country codes."""
        assert PHONE_COUNTRY_MAP["ru"] == "7"
        assert PHONE_COUNTRY_MAP["us"] == "1"
        assert PHONE_COUNTRY_MAP["uk"] == "44"
        assert PHONE_COUNTRY_MAP["de"] == "49"
        assert PHONE_COUNTRY_MAP["br"] == "55"
        assert PHONE_COUNTRY_MAP["fr"] == "33"
        assert PHONE_COUNTRY_MAP["pl"] == "48"

    def test_strip_prefix_logic(self):
        """Verify the prefix stripping logic used by Yahoo/AOL."""
        phone_number = "+447911123456"
        country = "uk"
        prefix = PHONE_COUNTRY_MAP[country]

        local = phone_number.lstrip("+")
        if local.startswith(prefix):
            local = local[len(prefix):]

        assert local == "7911123456"
        assert not local.startswith("44")


# ═══════════════════════════════════════════════════════
# Country to ISO2 map
# ═══════════════════════════════════════════════════════

class TestCountryToISO2:
    def test_all_phone_countries_have_iso2(self):
        """Every country in PHONE_COUNTRY_MAP should have an ISO2 mapping."""
        for country in PHONE_COUNTRY_MAP:
            assert country in COUNTRY_TO_ISO2, \
                f"Country '{country}' has phone prefix but no ISO2 mapping"

    def test_iso2_format(self):
        """ISO2 codes should be exactly 2 uppercase letters."""
        for country, iso2 in COUNTRY_TO_ISO2.items():
            assert len(iso2) == 2, f"ISO2 for '{country}' is '{iso2}' (not 2 chars)"
            assert iso2.isupper(), f"ISO2 for '{country}' is '{iso2}' (not uppercase)"

    def test_known_iso2(self):
        """Spot-check well-known ISO2 mappings."""
        assert COUNTRY_TO_ISO2["ru"] == "RU"
        assert COUNTRY_TO_ISO2["us"] == "US"
        assert COUNTRY_TO_ISO2["uk"] == "GB"  # UK → GB (ISO standard)
        assert COUNTRY_TO_ISO2["de"] == "DE"
        assert COUNTRY_TO_ISO2["br"] == "BR"

    def test_maps_same_size(self):
        """Both maps should have the same countries."""
        phone_keys = set(PHONE_COUNTRY_MAP.keys())
        iso2_keys = set(COUNTRY_TO_ISO2.keys())
        assert phone_keys == iso2_keys, \
            f"Mismatch: phone has {phone_keys - iso2_keys}, iso2 has {iso2_keys - phone_keys}"
