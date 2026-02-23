"""
Tests for backend.utils — password, username, birthday generators.
Run: pytest tests/test_utils.py -v
"""
import re
import string
from datetime import datetime

from backend.utils import generate_password, generate_username, generate_birthday


# ═══════════════════════════════════════════════════════
# generate_password
# ═══════════════════════════════════════════════════════

class TestGeneratePassword:
    def test_default_length(self):
        pwd = generate_password()
        assert len(pwd) == 14

    def test_custom_length(self):
        pwd = generate_password(length=20)
        assert len(pwd) == 20

    def test_has_lowercase(self):
        pwd = generate_password()
        assert any(c in string.ascii_lowercase for c in pwd)

    def test_has_uppercase(self):
        pwd = generate_password()
        assert any(c in string.ascii_uppercase for c in pwd)

    def test_has_digits(self):
        pwd = generate_password()
        assert any(c.isdigit() for c in pwd)

    def test_has_exclamation(self):
        pwd = generate_password()
        assert "!" in pwd

    def test_no_forbidden_specials(self):
        """Only ! is allowed, no other special chars."""
        for _ in range(50):  # Run multiple times (random)
            pwd = generate_password()
            for c in pwd:
                assert c in string.ascii_letters + string.digits + "!", \
                    f"Forbidden char '{c}' in password '{pwd}'"

    def test_uniqueness(self):
        """10 passwords should all be different."""
        passwords = {generate_password() for _ in range(10)}
        assert len(passwords) == 10


# ═══════════════════════════════════════════════════════
# generate_username
# ═══════════════════════════════════════════════════════

class TestGenerateUsername:
    def test_basic_format(self):
        username = generate_username("John", "Smith")
        assert len(username) > 0
        assert username.isascii()

    def test_starts_with_letter(self):
        """Yahoo requires username to start with a letter."""
        for _ in range(50):
            username = generate_username("Test", "User")
            assert username[0].isalpha(), \
                f"Username '{username}' starts with non-letter"

    def test_only_lowercase_and_digits(self):
        """No dots, underscores, hyphens, or special chars."""
        for _ in range(50):
            username = generate_username("Maria", "Garcia")
            assert re.match(r'^[a-z0-9]+$', username), \
                f"Username '{username}' has forbidden chars"

    def test_cyrillic_transliteration(self):
        """Cyrillic names should be converted to ASCII."""
        username = generate_username("Иван", "Петров")
        assert username.isascii()
        # Should fallback to "user"/"mail" if transliteration fails
        assert len(username) > 0

    def test_empty_name_fallback(self):
        """Empty names should fallback to 'user'/'mail'."""
        username = generate_username("", "")
        assert "user" in username or "mail" in username

    def test_uniqueness(self):
        """Usernames should vary (random suffix)."""
        usernames = {generate_username("Alex", "Brown") for _ in range(10)}
        assert len(usernames) >= 5  # At least 5 unique out of 10


# ═══════════════════════════════════════════════════════
# generate_birthday
# ═══════════════════════════════════════════════════════

class TestGenerateBirthday:
    def test_returns_datetime(self):
        bd = generate_birthday()
        assert isinstance(bd, datetime)

    def test_default_year_range(self):
        for _ in range(50):
            bd = generate_birthday()
            assert 1985 <= bd.year <= 2003

    def test_custom_year_range(self):
        bd = generate_birthday(min_year=1990, max_year=1990)
        assert bd.year == 1990

    def test_valid_date(self):
        """Day should be 1-28 (safe for all months)."""
        for _ in range(50):
            bd = generate_birthday()
            assert 1 <= bd.month <= 12
            assert 1 <= bd.day <= 28

    def test_age_reasonable(self):
        """Generated age should be 22-40 years (for autoreg)."""
        bd = generate_birthday()
        age = datetime.now().year - bd.year
        assert 22 <= age <= 42  # 2026 - 2003 = 23, 2026 - 1985 = 41
