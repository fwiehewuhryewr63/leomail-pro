"""
Leomail Vision — Stage Detector for email registration flows.
Uses OCR text analysis to determine current registration stage.
"""
import re
from loguru import logger
from .ocr import OCR


# ─── Stage definitions per provider ─────────────────────────────────────────

YAHOO_STAGES = {
    "signup_form": {
        "keywords": ["first name", "last name", "email address", "password", "phone number"],
        "min_matches": 3,
        "description": "Main signup form (name + email + password + phone)",
    },
    "phone_verify": {
        "keywords": ["verify your account", "enter the code", "verification code", "text me a code", "code sent"],
        "min_matches": 1,
        "description": "SMS verification step",
    },
    "captcha": {
        "keywords": ["recaptcha", "i'm not a robot", "robot", "security check", "verify you"],
        "min_matches": 1,
        "description": "CAPTCHA challenge",
    },
    "success": {
        "keywords": ["welcome", "yahoo.com", "inbox", "continue to yahoo", "your account"],
        "min_matches": 1,
        "description": "Registration successful",
    },
    "error_blocked": {
        "keywords": ["try again later", "unable to process", "blocked", "suspicious", "temporarily"],
        "min_matches": 1,
        "description": "Registration blocked/rate limited",
    },
    "error_phone": {
        "keywords": ["invalid phone", "phone number is not valid", "try a different number", "cannot use this"],
        "min_matches": 1,
        "description": "Phone number rejected",
    },
    "error_username": {
        "keywords": ["already taken", "username is taken", "choose a different", "not available"],
        "min_matches": 1,
        "description": "Username already taken",
    },
    "age_gate": {
        "keywords": ["age requirement", "not old enough", "under 13", "parental consent"],
        "min_matches": 1,
        "description": "Age restriction",
    },
}

# AOL uses the same Yahoo backend
AOL_STAGES = YAHOO_STAGES.copy()

GMAIL_STAGES = {
    "name_form": {
        "keywords": ["first name", "last name", "create a google account", "what's your name"],
        "min_matches": 2,
        "description": "Name entry",
    },
    "birthday_gender": {
        "keywords": ["birthday", "gender", "month", "day", "year"],
        "min_matches": 2,
        "description": "Birthday and gender selection",
    },
    "username_choice": {
        "keywords": ["create a gmail address", "choose your gmail", "email address", "username"],
        "min_matches": 1,
        "description": "Username/email selection",
    },
    "password": {
        "keywords": ["create a password", "confirm", "strong password"],
        "min_matches": 1,
        "description": "Password creation",
    },
    "phone_add": {
        "keywords": ["add phone number", "verify your phone", "phone number"],
        "min_matches": 1,
        "description": "Phone number entry",
    },
    "sms_code": {
        "keywords": ["enter the code", "verification code", "g-", "6-digit"],
        "min_matches": 1,
        "description": "SMS code entry",
    },
    "terms": {
        "keywords": ["privacy and terms", "i agree", "privacy policy", "terms of service"],
        "min_matches": 1,
        "description": "Terms acceptance",
    },
    "success": {
        "keywords": ["welcome to", "gmail", "inbox", "your new google account"],
        "min_matches": 1,
        "description": "Registration successful",
    },
    "captcha": {
        "keywords": ["recaptcha", "i'm not a robot", "verify", "security"],
        "min_matches": 1,
        "description": "CAPTCHA",
    },
    "error_blocked": {
        "keywords": ["couldn't create", "try again", "unusual activity", "abuse"],
        "min_matches": 1,
        "description": "Blocked",
    },
}

OUTLOOK_STAGES = {
    "email_create": {
        "keywords": ["create account", "new email", "outlook.com", "hotmail.com"],
        "min_matches": 1,
        "description": "Email creation",
    },
    "password": {
        "keywords": ["create a password", "password"],
        "min_matches": 1,
        "description": "Password entry",
    },
    "name_form": {
        "keywords": ["what's your name", "first name", "last name"],
        "min_matches": 1,
        "description": "Name entry",
    },
    "birthday": {
        "keywords": ["birthdate", "birth date", "date of birth", "month", "day", "year"],
        "min_matches": 2,
        "description": "Birthday entry",
    },
    "captcha": {
        "keywords": ["puzzle", "verify", "prove you", "not a robot", "security"],
        "min_matches": 1,
        "description": "CAPTCHA",
    },
    "success": {
        "keywords": ["welcome", "outlook", "inbox", "get started"],
        "min_matches": 1,
        "description": "Success",
    },
    "error_blocked": {
        "keywords": ["try again", "blocked", "suspicious", "limit"],
        "min_matches": 1,
        "description": "Blocked",
    },
}

PROVIDER_STAGES = {
    "yahoo": YAHOO_STAGES,
    "aol": AOL_STAGES,
    "gmail": GMAIL_STAGES,
    "outlook": OUTLOOK_STAGES,
}


class StageDetector:
    """Detect current registration stage from a screenshot."""

    def __init__(self, provider: str = "yahoo"):
        self.provider = provider.lower()
        self.stages = PROVIDER_STAGES.get(self.provider, YAHOO_STAGES)

    def detect_from_bytes(self, img_bytes: bytes) -> dict:
        """
        Detect stage from raw screenshot bytes (Playwright).
        
        Returns: {
            "stage": "signup_form",
            "confidence": 0.85,
            "description": "Main signup form",
            "all_text": "First name Last name ...",
            "matched_keywords": ["first name", "last name", "password"],
            "text_boxes": [...]
        }
        """
        # Get all text from screenshot
        all_text = OCR.extract_from_bytes(img_bytes)
        boxes = OCR.extract_boxes_from_bytes(img_bytes)
        all_text_lower = all_text.lower()

        # Score each stage
        best_stage = "unknown"
        best_score = 0
        best_matches = []
        best_desc = "Failed to detect stage"

        for stage_name, stage_def in self.stages.items():
            matches = []
            for kw in stage_def["keywords"]:
                if kw.lower() in all_text_lower:
                    matches.append(kw)

            if len(matches) >= stage_def["min_matches"]:
                # Score: matched keywords / total keywords
                score = len(matches) / len(stage_def["keywords"])
                if score > best_score:
                    best_score = score
                    best_stage = stage_name
                    best_matches = matches
                    best_desc = stage_def["description"]

        return {
            "stage": best_stage,
            "confidence": round(best_score, 2),
            "description": best_desc,
            "all_text": all_text[:500],
            "matched_keywords": best_matches,
            "text_boxes": boxes,
        }

    def detect_from_file(self, image_path: str) -> dict:
        """Detect stage from image file."""
        with open(image_path, "rb") as f:
            return self.detect_from_bytes(f.read())

    def find_button(self, img_bytes: bytes, button_texts: list[str]) -> dict | None:
        """
        Find a button by its text on screen.
        Tries each text in order, returns first match.
        
        Returns: {"x": center_x, "y": center_y, "text": matched_text} or None
        """
        for text in button_texts:
            loc = OCR.find_text_location(img_bytes, text)
            if loc:
                return {**loc, "text": text}
        return None

    def find_input_near_label(self, img_bytes: bytes, label_text: str, offset_y: int = 40) -> dict | None:
        """
        Find an input field by looking for its label text, then guessing
        the input is directly below it.
        
        Returns: {"x": label_x, "y": label_y + offset, "label": label_text} or None
        """
        loc = OCR.find_text_location(img_bytes, label_text)
        if loc:
            return {
                "x": loc["x"],
                "y": loc["y"] + offset_y,
                "label": label_text,
            }
        return None

    def is_error(self, img_bytes: bytes) -> dict | None:
        """
        Quick check if screen shows any error.
        Returns: {"type": "blocked"|"phone"|"username"|"age_gate", "text": "..."} or None
        """
        result = self.detect_from_bytes(img_bytes)
        if result["stage"].startswith("error_"):
            return {
                "type": result["stage"].replace("error_", ""),
                "text": result["description"],
                "keywords": result["matched_keywords"],
            }
        if result["stage"] == "age_gate":
            return {
                "type": "age_gate",
                "text": result["description"],
                "keywords": result["matched_keywords"],
            }
        return None
