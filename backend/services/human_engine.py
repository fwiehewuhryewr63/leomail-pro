"""
Leomail v2.2 — Human-Like Engine
Ensures natural, non-duplicate behavior with AI auto-config and manual delay overrides.
"""
import random
import hashlib
from datetime import datetime
from loguru import logger


class HumanEngine:
    """Human-like behavior for account registration and sending."""

    # Name databases by country (first names only, male/female)
    NAMES = {
        "us": {"m": ["James","John","Robert","Michael","David","William","Richard","Joseph","Thomas","Chris"],
               "f": ["Mary","Patricia","Jennifer","Linda","Barbara","Susan","Jessica","Sarah","Karen","Lisa"]},
        "uk": {"m": ["Oliver","Harry","George","Jack","Jacob","Noah","Charlie","Muhammad","Thomas","Oscar"],
               "f": ["Olivia","Amelia","Isla","Ava","Mia","Emily","Grace","Sophia","Lily","Ella"]},
        "de": {"m": ["Lukas","Leon","Finn","Paul","Jonas","Ben","Elias","Noah","Felix","Luis"],
               "f": ["Marie","Sophie","Maria","Hannah","Emma","Emilia","Anna","Lina","Mia","Lea"]},
        "fr": {"m": ["Gabriel","Louis","Raphaël","Jules","Adam","Lucas","Léo","Hugo","Arthur","Nathan"],
               "f": ["Emma","Louise","Jade","Alice","Chloé","Lina","Mila","Léa","Manon","Rose"]},
        "es": {"m": ["Hugo","Daniel","Martín","Pablo","Alejandro","Lucas","Álvaro","Adrián","David","Mario"],
               "f": ["Lucía","Sofía","Martina","María","Paula","Daniela","Valeria","Alba","Julia","Noa"]},
        "it": {"m": ["Leonardo","Francesco","Alessandro","Lorenzo","Mattia","Andrea","Gabriele","Riccardo","Tommaso","Edoardo"],
               "f": ["Sofia","Giulia","Aurora","Alice","Ginevra","Emma","Giorgia","Greta","Beatrice","Anna"]},
        "br": {"m": ["Miguel","Arthur","Heitor","Bernardo","Théo","Davi","Gabriel","Samuel","Pedro","Rafael"],
               "f": ["Helena","Alice","Laura","Maria","Valentina","Heloísa","Sophia","Isabella","Manuela","Júlia"]},
        "ru": {"m": ["Александр","Дмитрий","Максим","Артём","Михаил","Иван","Даниил","Кирилл","Андрей","Егор"],
               "f": ["Анастасия","Мария","Анна","Виктория","Полина","Елизавета","Екатерина","Дарья","Алиса","София"]},
        "pl": {"m": ["Antoni","Jakub","Jan","Szymon","Aleksander","Franciszek","Filip","Mikołaj","Wojciech","Kacper"],
               "f": ["Julia","Zuzanna","Zofia","Hanna","Maja","Lena","Alicja","Maria","Amelia","Oliwia"]},
        "tr": {"m": ["Yusuf","Eymen","Ömer","Mustafa","Emir","Ahmet","Kerem","Ali","Miraç","Hamza"],
               "f": ["Zeynep","Elif","Defne","Ebrar","Azra","Nehir","Ecrin","Asya","Ela","Meryem"]},
        "in": {"m": ["Aarav","Vivaan","Aditya","Vihaan","Arjun","Reyansh","Sai","Arnav","Ayaan","Krishna"],
               "f": ["Aadhya","Saanvi","Aanya","Ananya","Pari","Anika","Navya","Angel","Diya","Myra"]},
        "mx": {"m": ["Santiago","Mateo","Sebastián","Leonardo","Emiliano","Diego","Miguel","Daniel","Alexander","Matías"],
               "f": ["Sofía","Valentina","Regina","Camila","María","Renata","Isabella","Romina","Ximena","Victoria"]},
        "jp": {"m": ["Haruto","Sora","Riku","Ren","Yuto","Minato","Haruki","Hinata","Sota","Yuma"],
               "f": ["Yui","Hina","Mei","Aoi","Rio","Sakura","Himari","Mio","Koharu","Akari"]},
        "kr": {"m": ["Minjun","Seo-jun","Do-yun","Ye-jun","Si-woo","Ha-jun","Ji-ho","Jun-seo","Ju-won","Jae-min"],
               "f": ["Seo-yeon","Ha-eun","Ji-woo","Seo-yun","Min-seo","Su-ah","Ha-yoon","Ji-yoo","Ye-eun","Da-yoon"]},
    }

    SURNAMES = {
        "us": ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Taylor"],
        "uk": ["Smith","Jones","Williams","Brown","Taylor","Davies","Wilson","Evans","Thomas","Johnson"],
        "de": ["Müller","Schmidt","Schneider","Fischer","Weber","Meyer","Wagner","Becker","Schulz","Hoffmann"],
        "fr": ["Martin","Bernard","Dubois","Thomas","Robert","Richard","Petit","Durand","Leroy","Moreau"],
        "es": ["García","Rodríguez","Martínez","López","González","Hernández","Pérez","Sánchez","Ramírez","Torres"],
        "ru": ["Иванов","Петров","Сидоров","Смирнов","Кузнецов","Попов","Соколов","Лебедев","Козлов","Новиков"],
    }

    def __init__(self):
        self._sent_hashes: set = set()
        self._custom_delays: dict = {}  # day_key -> {min, max}

    def generate_identity(self, country: str = "us", gender: str = None) -> dict:
        """Generate a unique human-like identity for account registration."""
        if gender is None:
            gender = random.choice(["m", "f"])
        names = self.NAMES.get(country, self.NAMES["us"])
        surnames = self.SURNAMES.get(country, self.SURNAMES["us"])
        first = random.choice(names.get(gender, names["m"]))
        last = random.choice(surnames)
        year = random.randint(1985, 2003)
        month = random.randint(1, 12)
        day = random.randint(1, 28)

        # Generate email-friendly username variations
        r = random.randint(1, 99)
        patterns = [
            f"{first.lower()}.{last.lower()}{r}",
            f"{first.lower()}{last.lower()}{year % 100}",
            f"{first.lower()}_{last.lower()}{r}",
            f"{first[0].lower()}{last.lower()}{random.randint(100, 999)}",
        ]

        return {
            "first_name": first,
            "last_name": last,
            "gender": gender,
            "birth_year": year,
            "birth_month": month,
            "birth_day": day,
            "username": random.choice(patterns),
            "country": country,
        }

    def get_daily_volume(self, min_vol: int = 20, max_vol: int = 60) -> int:
        """Gaussian-distributed daily sending volume per account."""
        mean = (min_vol + max_vol) / 2
        std = (max_vol - min_vol) / 4
        vol = int(random.gauss(mean, std))
        return max(min_vol, min(max_vol, vol))

    def get_delay(self, min_sec: int = 30, max_sec: int = 120) -> float:
        """Human-like delay between actions (Gaussian distribution)."""
        mean = (min_sec + max_sec) / 2
        std = (max_sec - min_sec) / 4
        delay = random.gauss(mean, std)
        return max(min_sec * 0.8, min(max_sec * 1.2, delay))

    def get_custom_delay(self, day_key: str = None) -> dict:
        """
        Get delay config for a specific day. Allows manual overrides per day.
        day_key: 'today', 'tomorrow', or date string 'YYYY-MM-DD'
        Returns: {min, max} or default
        """
        if day_key is None:
            day_key = datetime.now().strftime("%Y-%m-%d")
        elif day_key == "today":
            day_key = datetime.now().strftime("%Y-%m-%d")

        if day_key in self._custom_delays:
            return self._custom_delays[day_key]
        return None  # Use default

    def set_custom_delays(self, delays: dict):
        """
        Set custom delay overrides per day.
        delays: {"2026-02-19": {"min": 330, "max": 360}, "2026-02-20": {"min": 380, "max": 440}}
        """
        self._custom_delays = delays
        logger.info(f"Custom delays set for {len(delays)} days: {delays}")

    def get_start_jitter(self, base_hour: int = 8, jitter_minutes: int = 20) -> float:
        """Add random jitter to start time per account."""
        jitter = random.uniform(-jitter_minutes, jitter_minutes)
        return base_hour + jitter / 60

    def is_duplicate(self, account_email: str, recipient_email: str) -> bool:
        """Check if we already sent from this account to this recipient."""
        key = f"{account_email}:{recipient_email}"
        h = hashlib.md5(key.encode()).hexdigest()[:16]
        if h in self._sent_hashes:
            return True
        self._sent_hashes.add(h)
        return False

    def distribute_recipients(self, recipients: list, accounts: list, per_day_min: int, per_day_max: int) -> dict:
        """
        Distribute recipients across accounts with random volumes.
        Returns: {account_email: [recipients]}
        """
        distribution = {}
        remaining = list(recipients)
        random.shuffle(remaining)

        for acc in accounts:
            if not remaining:
                break
            vol = self.get_daily_volume(per_day_min, per_day_max)
            batch = remaining[:vol]
            remaining = remaining[vol:]
            distribution[acc] = batch

        # Distribute leftovers round-robin
        idx = 0
        for r in remaining:
            acc = accounts[idx % len(accounts)]
            if acc not in distribution:
                distribution[acc] = []
            distribution[acc].append(r)
            idx += 1

        return distribution

    def auto_configure(self, task_type: str, recipients_count: int, accounts_count: int) -> dict:
        """
        AI-style auto-configuration of sending parameters.
        Calculates optimal delays, volumes, schedule based on volume and accounts.
        """
        if accounts_count == 0:
            accounts_count = 1

        per_account = recipients_count / accounts_count
        days_needed = 1

        # Strategy: conservative for small batches, aggressive for large
        if per_account <= 30:
            # Low volume — can be faster
            config = {
                "per_day_min": max(5, int(per_account * 0.6)),
                "per_day_max": max(10, int(per_account)),
                "delay_min": 45,
                "delay_max": 120,
                "start_hour": 9,
                "end_hour": 21,
                "strategy": "conservative",
                "days_estimate": 1,
                "risk_level": "low",
            }
        elif per_account <= 100:
            # Medium — balanced
            daily = min(50, int(per_account * 0.5))
            days_needed = max(1, int(per_account / daily))
            config = {
                "per_day_min": max(15, daily - 10),
                "per_day_max": daily + 10,
                "delay_min": 60,
                "delay_max": 180,
                "start_hour": 8,
                "end_hour": 22,
                "strategy": "balanced",
                "days_estimate": days_needed,
                "risk_level": "medium",
            }
        else:
            # High volume — spread across days
            daily = min(40, int(per_account * 0.3))
            days_needed = max(2, int(per_account / daily))
            config = {
                "per_day_min": max(20, daily - 10),
                "per_day_max": daily + 15,
                "delay_min": 90,
                "delay_max": 300,
                "start_hour": 8,
                "end_hour": 23,
                "strategy": "safe_spread",
                "days_estimate": days_needed,
                "risk_level": "high",
            }

        config["total_recipients"] = recipients_count
        config["accounts_count"] = accounts_count
        config["per_account_avg"] = round(per_account, 1)

        return config


# Singleton
human_engine = HumanEngine()
