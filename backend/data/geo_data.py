"""
Leomail v2.1 — Full Geo & Language Database
50+ countries, 30+ languages, SimSMS mapping, timezone data, name databases
"""

# SimSMS country codes mapping
SIMSMS_COUNTRIES = {
    0: "RU", 1: "UA", 2: "KZ", 3: "CN", 4: "PH", 5: "GE", 6: "ID", 7: "BY",
    8: "KE", 10: "BR", 11: "KG", 12: "US", 13: "IL", 14: "PY", 15: "PL",
    16: "GB", 17: "US_V", 18: "FI", 19: "NG", 20: "MO", 21: "EG", 22: "FR",
    23: "IE", 24: "KH", 25: "LA", 26: "HT", 27: "CI", 28: "GM", 29: "RS",
    30: "YE", 31: "ZA", 32: "RO", 33: "SE", 34: "EE", 35: "AZ", 36: "CA",
    37: "MA", 38: "GH", 39: "AR", 40: "UZ", 41: "CM", 42: "TD", 43: "DE",
    44: "LT", 45: "HR", 47: "IQ", 48: "NL", 49: "LV", 50: "AT", 51: "BY",
    52: "TH", 53: "SA", 54: "MX", 55: "TW", 56: "ES", 57: "IR", 58: "DZ",
    59: "SI", 60: "BD", 61: "SN", 62: "TR", 63: "CZ", 64: "LK", 65: "PE",
    66: "PK", 67: "NZ", 68: "GN", 69: "ML", 70: "VE", 71: "ET",
}

# Reverse mapping: ISO code -> SimSMS code
ISO_TO_SIMSMS = {v: k for k, v in SIMSMS_COUNTRIES.items()}

# SimSMS service codes for email providers
SIMSMS_SERVICES = {
    "gmail": "go",      # Google/YouTube/Gmail
    "outlook": "mm",    # Microsoft (Outlook, Hotmail)
    "hotmail": "mm",    # Microsoft
    "yahoo": "mb",      # Yahoo
    "aol": "pm",        # AOL
}

# Full country database
COUNTRIES = [
    # Code, Name (EN), Name (RU), Primary Language, Timezone, SimSMS code
    {"code": "US", "name": "United States", "name_ru": "USA", "lang": "en", "tz": "America/New_York", "simsms": 12},
    {"code": "GB", "name": "United Kingdom", "name_ru": "Великобритания", "lang": "en", "tz": "Europe/London", "simsms": 16},
    {"code": "CA", "name": "Canada", "name_ru": "Canada", "lang": "en", "tz": "America/Toronto", "simsms": 36},
    {"code": "AU", "name": "Australia", "name_ru": "Австралия", "lang": "en", "tz": "Australia/Sydney", "simsms": None},
    {"code": "NZ", "name": "New Zealand", "name_ru": "Новая Зеландия", "lang": "en", "tz": "Pacific/Auckland", "simsms": 67},
    {"code": "IE", "name": "Ireland", "name_ru": "Ireland", "lang": "en", "tz": "Europe/Dublin", "simsms": 23},
    # German-speaking
    {"code": "DE", "name": "Germany", "name_ru": "Germany", "lang": "de", "tz": "Europe/Berlin", "simsms": 43},
    {"code": "AT", "name": "Austria", "name_ru": "Austria", "lang": "de", "tz": "Europe/Vienna", "simsms": 50},
    # French-speaking
    {"code": "FR", "name": "France", "name_ru": "France", "lang": "fr", "tz": "Europe/Paris", "simsms": 22},
    {"code": "SN", "name": "Senegal", "name_ru": "Сенегал", "lang": "fr", "tz": "Africa/Dakar", "simsms": 61},
    {"code": "CI", "name": "Côte d'Ivoire", "name_ru": "Кот-д'Ивуар", "lang": "fr", "tz": "Africa/Abidjan", "simsms": 27},
    {"code": "CM", "name": "Cameroon", "name_ru": "Камерун", "lang": "fr", "tz": "Africa/Douala", "simsms": 41},
    # Spanish-speaking
    {"code": "ES", "name": "Spain", "name_ru": "Spain", "lang": "es", "tz": "Europe/Madrid", "simsms": 56},
    {"code": "MX", "name": "Mexico", "name_ru": "Mexico", "lang": "es", "tz": "America/Mexico_City", "simsms": 54},
    {"code": "AR", "name": "Argentina", "name_ru": "Аргентина", "lang": "es", "tz": "America/Buenos_Aires", "simsms": 39},
    {"code": "PE", "name": "Peru", "name_ru": "Peru", "lang": "es", "tz": "America/Lima", "simsms": 65},
    {"code": "VE", "name": "Venezuela", "name_ru": "Венесуэла", "lang": "es", "tz": "America/Caracas", "simsms": 70},
    {"code": "PY", "name": "Paraguay", "name_ru": "Парагвай", "lang": "es", "tz": "America/Asuncion", "simsms": 14},
    # Portuguese-speaking
    {"code": "BR", "name": "Brazil", "name_ru": "Brazil", "lang": "pt", "tz": "America/Sao_Paulo", "simsms": 10},
    # Russian-speaking
    {"code": "RU", "name": "Russia", "name_ru": "Russia", "lang": "ru", "tz": "Europe/Moscow", "simsms": 0},
    {"code": "UA", "name": "Ukraine", "name_ru": "Ukraine", "lang": "uk", "tz": "Europe/Kiev", "simsms": 1},
    {"code": "BY", "name": "Belarus", "name_ru": "Беларусь", "lang": "ru", "tz": "Europe/Minsk", "simsms": 7},
    {"code": "KZ", "name": "Kazakhstan", "name_ru": "Kazakhstan", "lang": "ru", "tz": "Asia/Almaty", "simsms": 2},
    {"code": "KG", "name": "Kyrgyzstan", "name_ru": "Кыргызстан", "lang": "ru", "tz": "Asia/Bishkek", "simsms": 11},
    {"code": "UZ", "name": "Uzbekistan", "name_ru": "Узбекистан", "lang": "uz", "tz": "Asia/Tashkent", "simsms": 40},
    {"code": "AZ", "name": "Azerbaijan", "name_ru": "Азербайджан", "lang": "az", "tz": "Asia/Baku", "simsms": 35},
    {"code": "GE", "name": "Georgia", "name_ru": "Грузия", "lang": "ka", "tz": "Asia/Tbilisi", "simsms": 5},
    # Turkish
    {"code": "TR", "name": "Turkey", "name_ru": "Turkey", "lang": "tr", "tz": "Europe/Istanbul", "simsms": 62},
    # Arabic-speaking
    {"code": "SA", "name": "Saudi Arabia", "name_ru": "Сауд. Аравия", "lang": "ar", "tz": "Asia/Riyadh", "simsms": 53},
    {"code": "EG", "name": "Egypt", "name_ru": "Egypt", "lang": "ar", "tz": "Africa/Cairo", "simsms": 21},
    {"code": "IQ", "name": "Iraq", "name_ru": "Ирак", "lang": "ar", "tz": "Asia/Baghdad", "simsms": 47},
    {"code": "MA", "name": "Morocco", "name_ru": "Марокко", "lang": "ar", "tz": "Africa/Casablanca", "simsms": 37},
    {"code": "DZ", "name": "Algeria", "name_ru": "Алжир", "lang": "ar", "tz": "Africa/Algiers", "simsms": 58},
    {"code": "YE", "name": "Yemen", "name_ru": "Йемен", "lang": "ar", "tz": "Asia/Aden", "simsms": 30},
    # African
    {"code": "NG", "name": "Nigeria", "name_ru": "Nigeria", "lang": "en", "tz": "Africa/Lagos", "simsms": 19},
    {"code": "ZA", "name": "South Africa", "name_ru": "South Africa", "lang": "en", "tz": "Africa/Johannesburg", "simsms": 31},
    {"code": "GH", "name": "Ghana", "name_ru": "Гана", "lang": "en", "tz": "Africa/Accra", "simsms": 38},
    {"code": "KE", "name": "Kenya", "name_ru": "Kenya", "lang": "en", "tz": "Africa/Nairobi", "simsms": 8},
    {"code": "ET", "name": "Ethiopia", "name_ru": "Эфиопия", "lang": "am", "tz": "Africa/Addis_Ababa", "simsms": 71},
    # Asian
    {"code": "CN", "name": "China", "name_ru": "China", "lang": "zh", "tz": "Asia/Shanghai", "simsms": 3},
    {"code": "PH", "name": "Philippines", "name_ru": "Philippines", "lang": "tl", "tz": "Asia/Manila", "simsms": 4},
    {"code": "ID", "name": "Indonesia", "name_ru": "Indonesia", "lang": "id", "tz": "Asia/Jakarta", "simsms": 6},
    {"code": "TH", "name": "Thailand", "name_ru": "Thailand", "lang": "th", "tz": "Asia/Bangkok", "simsms": 52},
    {"code": "TW", "name": "Taiwan", "name_ru": "Тайвань", "lang": "zh", "tz": "Asia/Taipei", "simsms": 55},
    {"code": "KH", "name": "Cambodia", "name_ru": "Камбоджа", "lang": "km", "tz": "Asia/Phnom_Penh", "simsms": 24},
    {"code": "BD", "name": "Bangladesh", "name_ru": "Бангладеш", "lang": "bn", "tz": "Asia/Dhaka", "simsms": 60},
    {"code": "PK", "name": "Pakistan", "name_ru": "Пакистан", "lang": "ur", "tz": "Asia/Karachi", "simsms": 66},
    {"code": "LK", "name": "Sri Lanka", "name_ru": "Шри-Ланка", "lang": "si", "tz": "Asia/Colombo", "simsms": 64},
    {"code": "IR", "name": "Iran", "name_ru": "Иран", "lang": "fa", "tz": "Asia/Tehran", "simsms": 57},
    {"code": "IL", "name": "Israel", "name_ru": "Israel", "lang": "he", "tz": "Asia/Jerusalem", "simsms": 13},
    # European
    {"code": "NL", "name": "Netherlands", "name_ru": "Netherlands", "lang": "nl", "tz": "Europe/Amsterdam", "simsms": 48},
    {"code": "PL", "name": "Poland", "name_ru": "Poland", "lang": "pl", "tz": "Europe/Warsaw", "simsms": 15},
    {"code": "RO", "name": "Romania", "name_ru": "Romania", "lang": "ro", "tz": "Europe/Bucharest", "simsms": 32},
    {"code": "SE", "name": "Sweden", "name_ru": "Sweden", "lang": "sv", "tz": "Europe/Stockholm", "simsms": 33},
    {"code": "FI", "name": "Finland", "name_ru": "Финляндия", "lang": "fi", "tz": "Europe/Helsinki", "simsms": 18},
    {"code": "EE", "name": "Estonia", "name_ru": "Estonia", "lang": "et", "tz": "Europe/Tallinn", "simsms": 34},
    {"code": "LT", "name": "Lithuania", "name_ru": "Литва", "lang": "lt", "tz": "Europe/Vilnius", "simsms": 44},
    {"code": "LV", "name": "Latvia", "name_ru": "Латвия", "lang": "lv", "tz": "Europe/Riga", "simsms": 49},
    {"code": "HR", "name": "Croatia", "name_ru": "Хорватия", "lang": "hr", "tz": "Europe/Zagreb", "simsms": 45},
    {"code": "RS", "name": "Serbia", "name_ru": "Сербия", "lang": "sr", "tz": "Europe/Belgrade", "simsms": 29},
    {"code": "SI", "name": "Slovenia", "name_ru": "Словения", "lang": "sl", "tz": "Europe/Ljubljana", "simsms": 59},
    {"code": "CZ", "name": "Czechia", "name_ru": "Czechia", "lang": "cs", "tz": "Europe/Prague", "simsms": 63},
    # Caribbean / Other
    {"code": "HT", "name": "Haiti", "name_ru": "Гаити", "lang": "fr", "tz": "America/Port-au-Prince", "simsms": 26},
    {"code": "GM", "name": "Gambia", "name_ru": "Гамбия", "lang": "en", "tz": "Africa/Banjul", "simsms": 28},
    {"code": "TD", "name": "Chad", "name_ru": "Чад", "lang": "fr", "tz": "Africa/Ndjamena", "simsms": 42},
    {"code": "GN", "name": "Guinea", "name_ru": "Гвинея", "lang": "fr", "tz": "Africa/Conakry", "simsms": 68},
    {"code": "ML", "name": "Mali", "name_ru": "Мали", "lang": "fr", "tz": "Africa/Bamako", "simsms": 69},
    {"code": "MO", "name": "Macau", "name_ru": "Макао", "lang": "zh", "tz": "Asia/Macau", "simsms": 20},
    {"code": "LA", "name": "Laos", "name_ru": "Лаос", "lang": "lo", "tz": "Asia/Vientiane", "simsms": 25},
]

# All languages
LANGUAGES = [
    {"code": "en", "name": "English", "name_ru": "Английский"},
    {"code": "es", "name": "Spanish", "name_ru": "Испанский"},
    {"code": "pt", "name": "Portuguese", "name_ru": "Португальский"},
    {"code": "fr", "name": "French", "name_ru": "Французский"},
    {"code": "de", "name": "German", "name_ru": "Немецкий"},
    {"code": "ru", "name": "Russian", "name_ru": "Русский"},
    {"code": "uk", "name": "Ukrainian", "name_ru": "Украинский"},
    {"code": "tr", "name": "Turkish", "name_ru": "Турецкий"},
    {"code": "ar", "name": "Arabic", "name_ru": "Арабский"},
    {"code": "zh", "name": "Chinese", "name_ru": "Chinaский"},
    {"code": "ja", "name": "Japanese", "name_ru": "Японский"},
    {"code": "ko", "name": "Korean", "name_ru": "Корейский"},
    {"code": "hi", "name": "Hindi", "name_ru": "Хинди"},
    {"code": "bn", "name": "Bengali", "name_ru": "Бенгальский"},
    {"code": "ur", "name": "Urdu", "name_ru": "Урду"},
    {"code": "fa", "name": "Persian", "name_ru": "Персидский"},
    {"code": "he", "name": "Hebrew", "name_ru": "Иврит"},
    {"code": "id", "name": "Indonesian", "name_ru": "Индонезийский"},
    {"code": "th", "name": "Thai", "name_ru": "Тайский"},
    {"code": "vi", "name": "Vietnamese", "name_ru": "Вьетнамский"},
    {"code": "tl", "name": "Filipino", "name_ru": "Филиппинский"},
    {"code": "pl", "name": "Polish", "name_ru": "Польский"},
    {"code": "nl", "name": "Dutch", "name_ru": "Голландский"},
    {"code": "sv", "name": "Swedish", "name_ru": "Шведский"},
    {"code": "fi", "name": "Finnish", "name_ru": "Финский"},
    {"code": "ro", "name": "Romanian", "name_ru": "Румынский"},
    {"code": "cs", "name": "Czech", "name_ru": "Чешский"},
    {"code": "hr", "name": "Croatian", "name_ru": "Хорватский"},
    {"code": "sr", "name": "Serbian", "name_ru": "Сербский"},
    {"code": "sl", "name": "Slovenian", "name_ru": "Словенский"},
    {"code": "et", "name": "Estonian", "name_ru": "Эстонский"},
    {"code": "lt", "name": "Lithuanian", "name_ru": "Литовский"},
    {"code": "lv", "name": "Latvian", "name_ru": "Латышский"},
    {"code": "ka", "name": "Georgian", "name_ru": "Грузинский"},
    {"code": "az", "name": "Azerbaijani", "name_ru": "Азербайджанский"},
    {"code": "uz", "name": "Uzbek", "name_ru": "Узбекский"},
    {"code": "am", "name": "Amharic", "name_ru": "Амхарский"},
    {"code": "sw", "name": "Swahili", "name_ru": "Суахили"},
    {"code": "it", "name": "Italian", "name_ru": "Итальянский"},
    {"code": "el", "name": "Greek", "name_ru": "Греческий"},
    {"code": "da", "name": "Danish", "name_ru": "Датский"},
    {"code": "no", "name": "Norwegian", "name_ru": "Норвежский"},
]

# Helper functions
def get_country(code: str) -> dict | None:
    return next((c for c in COUNTRIES if c["code"] == code), None)

def get_simsms_country_code(iso_code: str) -> int | None:
    country = get_country(iso_code)
    return country["simsms"] if country else None

def get_simsms_service(provider: str) -> str:
    return SIMSMS_SERVICES.get(provider, "ot")

def get_countries_for_api():
    """Return countries with SimSMS availability flag for frontend"""
    return [{
        "code": c["code"],
        "name": c["name"],
        "name_ru": c["name_ru"],
        "lang": c["lang"],
        "tz": c["tz"],
        "sms_available": c["simsms"] is not None
    } for c in COUNTRIES]

def get_languages_for_api():
    return LANGUAGES
