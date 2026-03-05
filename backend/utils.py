"""
Leomail v3 - Utilities
Name generation by language (with fallback to built-in dictionaries).
"""
import random
import string
from datetime import datetime


# Multilingual name dictionaries
NAMES_BY_LANGUAGE = {
    "en": {
        "first_male": ["James", "Robert", "John", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Christopher",
                       "Daniel", "Matthew", "Anthony", "Mark", "Andrew", "Joshua", "Steven", "Brian", "Kevin", "Jason"],
        "first_female": ["Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen",
                         "Lisa", "Nancy", "Betty", "Margaret", "Sandra", "Ashley", "Dorothy", "Kimberly", "Emily", "Donna"],
        "last": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                 "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White"],
    },
    "ru": {
        "first_male": ["Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Артём", "Иван", "Никита", "Михаил",
                       "Даниил", "Егор", "Кирилл", "Владимир", "Олег", "Денис", "Павел", "Роман", "Евгений", "Илья"],
        "first_female": ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Екатерина", "Татьяна", "Ирина", "Светлана", "Юлия",
                         "Дарья", "Алина", "Виктория", "Полина", "Ксения", "Марина", "Валерия", "Анастасия", "Софья", "Диана"],
        "last": ["Иванов", "Смирнов", "Кузнецов", "Попов", "Соколов", "Лебедев", "Козлов", "Новиков", "Морозов", "Петров",
                 "Волков", "Соловьёв", "Васильев", "Зайцев", "Павлов", "Семёнов", "Голубев", "Виноградов", "Богданов", "Воробьёв"],
    },
    "es": {
        "first_male": ["Carlos", "Juan", "Miguel", "José", "Luis", "Diego", "Pedro", "Andrés", "Santiago", "Fernando",
                       "Pablo", "Manuel", "Alejandro", "Jorge", "Ricardo", "Sergio", "Ramón", "Daniel", "Mario", "Roberto"],
        "first_female": ["María", "Ana", "Carmen", "Laura", "Isabel", "Lucía", "Elena", "Rosa", "Gabriela", "Patricia",
                         "Andrea", "Sofía", "Valentina", "Daniela", "Natalia", "Camila", "Victoria", "Adriana", "Paula", "Sara"],
        "last": ["García", "Rodríguez", "Martínez", "López", "González", "Hernández", "Pérez", "Sánchez", "Ramírez", "Torres",
                 "Flores", "Rivera", "Gómez", "Díaz", "Reyes", "Morales", "Jiménez", "Ruiz", "Álvarez", "Romero"],
    },
    "pt": {
        "first_male": ["João", "Pedro", "Lucas", "Gabriel", "Miguel", "Rafael", "Daniel", "Bruno", "Mateus", "Guilherme",
                       "Felipe", "André", "Leonardo", "Ricardo", "Tiago", "Carlos", "Fernando", "Paulo", "Rodrigo", "Marcos"],
        "first_female": ["Ana", "Maria", "Juliana", "Fernanda", "Camila", "Adriana", "Beatriz", "Carolina", "Gabriela", "Larissa",
                         "Letícia", "Mariana", "Patrícia", "Raquel", "Renata", "Tatiana", "Vanessa", "Amanda", "Bruna", "Daniela"],
        "last": ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Ferreira", "Costa", "Rodrigues", "Almeida",
                 "Nascimento", "Araújo", "Melo", "Barbosa", "Ribeiro", "Martins", "Carvalho", "Gomes", "Rocha", "Cardoso"],
    },
    "de": {
        "first_male": ["Thomas", "Michael", "Andreas", "Stefan", "Christian", "Martin", "Daniel", "Markus", "Sebastian", "Matthias",
                       "Alexander", "Peter", "Frank", "Jan", "Wolfgang", "Klaus", "Jürgen", "Lukas", "Bernd", "Hans"],
        "first_female": ["Anna", "Maria", "Laura", "Julia", "Sarah", "Sandra", "Christina", "Stefanie", "Nicole", "Petra",
                         "Katharina", "Sabrina", "Monika", "Andrea", "Claudia", "Martina", "Birgit", "Heike", "Anja", "Lisa"],
        "last": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
                 "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann"],
    },
    "fr": {
        "first_male": ["Jean", "Pierre", "Michel", "Nicolas", "François", "Julien", "Thomas", "Antoine", "Marc", "Philippe",
                       "Laurent", "Alexandre", "Christophe", "Guillaume", "Sébastien", "David", "Maxime", "Éric", "Mathieu", "Olivier"],
        "first_female": ["Marie", "Isabelle", "Nathalie", "Sophie", "Julie", "Claire", "Camille", "Émilie", "Aurélie", "Céline",
                         "Valérie", "Sandrine", "Florence", "Catherine", "Stéphanie", "Charlotte", "Léa", "Manon", "Chloé", "Alice"],
        "last": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau",
                 "Simon", "Laurent", "Lefebvre", "Michel", "Garcia", "David", "Bertrand", "Roux", "Vincent", "Fournier"],
    },
    "tr": {
        "first_male": ["Mehmet", "Mustafa", "Ahmet", "Ali", "Hasan", "Hüseyin", "Murat", "İbrahim", "Ömer", "İsmail",
                       "Yusuf", "Ramazan", "Osman", "Kadir", "Fatih", "Emre", "Burak", "Serkan", "Onur", "Cem"],
        "first_female": ["Fatma", "Ayşe", "Emine", "Hatice", "Zeynep", "Elif", "Merve", "Esra", "Büşra", "Seda",
                         "Derya", "Gamze", "Sibel", "Tuğba", "Özlem", "Gül", "Ebru", "Pınar", "Dilek", "Asya"],
        "last": ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın", "Özdemir",
                 "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek"],
    },
    "it": {
        "first_male": ["Marco", "Alessandro", "Giuseppe", "Andrea", "Giovanni", "Antonio", "Luca", "Francesco", "Stefano", "Roberto",
                       "Davide", "Matteo", "Lorenzo", "Simone", "Riccardo", "Federico", "Nicola", "Fabio", "Paolo", "Massimo"],
        "first_female": ["Maria", "Anna", "Giulia", "Francesca", "Sara", "Valentina", "Chiara", "Alessia", "Martina", "Federica",
                         "Elena", "Laura", "Elisa", "Giorgia", "Silvia", "Roberta", "Claudia", "Simona", "Cristina", "Monica"],
        "last": ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco",
                 "Bruno", "Gallo", "Conti", "De Luca", "Costa", "Giordano", "Mancini", "Rizzo", "Lombardi", "Moretti"],
    },
    "pl": {
        "first_male": ["Jan", "Andrzej", "Tomasz", "Piotr", "Krzysztof", "Paweł", "Marcin", "Michał", "Grzegorz", "Adam",
                       "Marek", "Wojciech", "Łukasz", "Robert", "Jakub", "Mateusz", "Kamil", "Dawid", "Rafał", "Daniel"],
        "first_female": ["Anna", "Maria", "Katarzyna", "Agnieszka", "Barbara", "Ewa", "Małgorzata", "Joanna", "Dorota", "Magdalena",
                         "Monika", "Beata", "Krystyna", "Elżbieta", "Aleksandra", "Karolina", "Natalia", "Dominika", "Justyna", "Weronika"],
        "last": ["Nowak", "Kowalski", "Wiśniewski", "Dąbrowski", "Lewandowski", "Wójcik", "Kamiński", "Kowalczyk", "Zieliński", "Szymański",
                 "Woźniak", "Kozłowski", "Jankowski", "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski", "Grabowski", "Nowakowski", "Pawłowski"],
    },
    "nl": {
        "first_male": ["Jan", "Peter", "Johannes", "Willem", "Hendrik", "Jeroen", "Pieter", "Cornelis", "Maarten", "Marc",
                       "Bas", "Tom", "Sander", "Lars", "Daan", "Bram", "Thijs", "Stijn", "Ruben", "Max"],
        "first_female": ["Maria", "Anna", "Elisabeth", "Johanna", "Cornelia", "Margriet", "Sophie", "Emma", "Sara", "Lisa",
                         "Eva", "Julia", "Lotte", "Iris", "Sanne", "Fleur", "Laura", "Kim", "Maaike", "Femke"],
        "last": ["De Jong", "Jansen", "De Vries", "Van den Berg", "Van Dijk", "Bakker", "Janssen", "Visser", "Smit", "Meijer",
                 "De Boer", "Mulder", "De Groot", "Bos", "Vos", "Peters", "Hendriks", "Van Leeuwen", "Dekker", "Brouwer"],
    },
}


def generate_random_name(db=None, language: str = "en", country: str = None, gender: str = "any") -> tuple[str, str]:
    """
    Generate a random name based on language.
    Returns: (first_name, last_name)
    """
    # Use language (priority) or fall back to country mapping
    lang = language or "en"
    if country and country != "any" and not language:
        country_to_lang = {"US": "en", "GB": "en", "RU": "ru", "ES": "es", "BR": "pt", "DE": "de", "FR": "fr", "TR": "tr", "IT": "it", "PL": "pl", "NL": "nl"}
        lang = country_to_lang.get(country.upper(), "en")

    # Pick gender randomly if not specified
    if gender == "any" or not gender:
        gender = random.choice(["male", "female"])

    # Get name lists for language
    names = NAMES_BY_LANGUAGE.get(lang, NAMES_BY_LANGUAGE["en"])
    first_key = f"first_{gender}"
    first_list = names.get(first_key, names.get("first_male", ["Alex"]))
    last_list = names.get("last", ["Johnson"])

    return (random.choice(first_list), random.choice(last_list))


def generate_birthday(min_year: int = 1985, max_year: int = 2003) -> datetime:
    """Generate a random birthday."""
    year = random.randint(min_year, max_year)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return datetime(year, month, day)


def generate_password(length: int = 14) -> str:
    """Generate a strong random password.
    
    Only uses: uppercase, lowercase, digits, and ! (exclamation mark).
    No other special characters allowed.
    """
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits

    # Ensure at least one of each type + one !
    password = [
        random.choice(lower),
        random.choice(lower),
        random.choice(lower),
        random.choice(upper),
        random.choice(upper),
        random.choice(digits),
        random.choice(digits),
        "!",
    ]

    # Fill remaining with letters and digits only (no extra specials)
    all_chars = lower + upper + digits
    password += [random.choice(all_chars) for _ in range(length - len(password))]

    random.shuffle(password)
    return ''.join(password)


def generate_username(first_name: str, last_name: str, provider: str = "outlook") -> str:
    """Generate unique-looking email username for registration.
    
    Strategy:
    - Min 8 chars total (avoids "already taken" for short names)
    - Numeric suffix 2-4 digits for uniqueness (year-like: 94, 2001, 847)
    - 12 natural-looking pattern variants
    - Provider-specific separator rules
    - Always starts with a letter (Yahoo/AOL requirement)
    
    Examples: aaronsmith847, aaron.smith94, smithaaron2001, aaron_smith23
    """
    import unicodedata
    import re

    MIN_LENGTH = 10

    def to_ascii(s):
        normalized = unicodedata.normalize('NFKD', s)
        ascii_str = ''.join(c for c in normalized if not unicodedata.combining(c)).encode('ascii', 'ignore').decode()
        return re.sub(r'[^a-zA-Z]', '', ascii_str)

    first = to_ascii(first_name).lower()
    last = to_ascii(last_name).lower()

    if not first:
        first = "user"
    if not last:
        last = "mail"

    # Numeric suffix: 2-4 digits, weighted toward longer for uniqueness
    # 30% chance: 2 digits (like birth year suffix: 94, 01, 87)
    # 45% chance: 3 digits (like 847, 203, 519)
    # 25% chance: 4 digits (like birth year: 1994, 2001)
    r = random.random()
    if r < 0.30:
        digits = str(random.randint(10, 99))       # 2 digits
    elif r < 0.75:
        digits = str(random.randint(100, 999))      # 3 digits
    else:
        digits = str(random.randint(1985, 2005))    # 4 digits (birth year)

    # Provider-specific separator chars
    prov = provider.lower() if provider else "outlook"
    if prov in ("yahoo", "aol"):
        # Yahoo/AOL: letters, digits, dots, underscores (no hyphens)
        seps = [".", "_"]
    elif prov == "gmail":
        # Gmail: letters, digits, dots only
        seps = ["."]
    else:
        # Outlook/Hotmail/Proton: letters, digits, dots, underscores, hyphens
        seps = [".", "_", "-"]

    sep = random.choice(seps) if random.random() < 0.4 else ""

    # 12 pattern variants — all look like natural real usernames
    patterns = [
        f"{first}{last}{digits}",               # aaronsmith847
        f"{first}{sep}{last}{digits}",          # aaron.smith94
        f"{first}{last[0]}{digits}",            # aarons2001
        f"{first}{sep}{last[0]}{digits}",       # aaron.s94  (may need padding)
        f"{last}{first}{digits}",               # smithaaron847
        f"{first}{digits}{last}",               # aaron94smith
        f"{first[0]}{last}{digits}",            # asmith847
        f"{last}{first[0]}{digits}",            # smitha2001
        f"{first}{sep}{last}{sep}{digits}",     # aaron.smith.23
        f"{last}{sep}{first}{digits}",          # smith.aaron94
        f"{first}{last}{digits}{random.choice(string.ascii_lowercase)}",  # aaronsmith847k
        f"{last}{sep}{first[0]}{sep}{digits}",  # smith.a.847
    ]

    result = random.choice(patterns)

    # Remove consecutive/leading/trailing separators
    result = re.sub(r'[._-]{2,}', '.', result)   # no double dots
    result = result.strip('._-')                   # no leading/trailing separators

    # Ensure starts with a letter (Yahoo/AOL requirement)
    if result and not result[0].isalpha():
        result = random.choice(string.ascii_lowercase) + result

    # Pad to MIN_LENGTH with digits if too short
    while len(result) < MIN_LENGTH:
        result += str(random.randint(0, 9))

    return result
