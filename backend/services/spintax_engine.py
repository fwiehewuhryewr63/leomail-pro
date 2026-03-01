"""
Leomail v3 - Spintax Engine
Generates unique email content from spintax templates.
{word1|word2|word3} -> random pick each time = millions of unique variants.
"""
import re
import random
import string


# Match nested spintax: {a|b|{c|d}} 
SPINTAX_PATTERN = re.compile(r'\{([^{}]+)\}')


def spin(text: str) -> str:
    """
    Process spintax in text. Each {a|b|c} is replaced with a random choice.
    Supports nested spintax via multiple passes.
    
    Example:
        spin("{Hi|Hello} {friend|mate}!") -> "Hello mate!"
    """
    # Multiple passes for nested spintax
    for _ in range(5):
        new_text = SPINTAX_PATTERN.sub(_spin_replace, text)
        if new_text == text:
            break
        text = new_text
    return text


def _spin_replace(match):
    """Replace a single spintax group with a random choice."""
    options = match.group(1).split("|")
    return random.choice(options).strip()


def add_uniqueness(html: str) -> str:
    """
    Add invisible uniqueness markers to HTML content.
    Makes each email unique even with the same visible text.
    """
    markers = []
    
    # 1. Random HTML comment
    rnd_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    markers.append(f"<!-- {rnd_id} -->")
    
    # 2. Zero-width spaces at random positions in text
    # (invisible but makes content hash unique)
    zwsp = '\u200b'  # zero-width space
    zwnj = '\u200c'  # zero-width non-joiner
    
    # Insert 2-5 invisible chars at word boundaries
    words = html.split(' ')
    if len(words) > 5:
        positions = random.sample(range(1, len(words)), min(4, len(words) - 1))
        for pos in sorted(positions, reverse=True):
            invisible = random.choice([zwsp, zwnj])
            words[pos] = invisible + words[pos]
        html = ' '.join(words)
    
    # 3. Random CSS micro-variation in style attr if HTML
    if '<' in html:
        # Add invisible span with random letter-spacing
        spacing = round(random.uniform(-0.01, 0.01), 3)
        markers.append(f'<span style="letter-spacing:{spacing}px"></span>')
    
    # Prepend comment, append invisible span
    return markers[0] + "\n" + html + "\n" + (markers[1] if len(markers) > 1 else "")


def estimate_combinations(text: str) -> int:
    """Estimate how many unique variants a spintax template can produce."""
    total = 1
    for match in SPINTAX_PATTERN.finditer(text):
        options = match.group(1).split("|")
        total *= len(options)
    return total
