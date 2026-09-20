import re
import unicodedata

# Categorized patterns to detect prompt injection
# We use \b to ensure word boundaries and allow flexible spacing.

CATEGORIES = {
    "IGNORE_INSTRUCTIONS": [
        r"(?i)\bзабудь(те)?\s*(?:(?:вс[её]|свои|предыдущие|текущие)\s+)*(?:системные\s+)?(настройки|правила|инструкции|контекст)\b",
        r"(?i)\bигнорируй(те)?\s*(?:(?:вс[её]|свои|предыдущие|текущие)\s+)*(?:системные\s+)?(настройки|правила|инструкции|контекст)\b",
        r"(?i)\bignore\s*(?:all\s*)?(?:previous\s*)?(?:system\s*)?(instructions|rules)\b",
        r"(?i)\bdisregard\s*(?:all\s*)?(?:previous\s*)?(?:system\s*)?(instructions|rules)\b",
        r"(?i)\bforget\s*(?:all\s*)?(?:previous\s*)?(?:system\s*)?(instructions|rules)\b",
    ],
    "IMITATE_SYSTEM": [
        r"(?i)\bновая системная инструкция\s*:",
        r"(?i)\bсистемная инструкция\s*:",
        r"(?i)\bсистемный промпт\s*:",
        r"(?i)\bинструкция разработчика\s*:",
        r"(?i)\bsystem prompt\s*:",
        r"(?i)\bsystem instruction\s*:",
        r"(?i)\bdeveloper message\s*:",
        r"(?i)\bdeveloper instruction\s*:",
        r"(?i)\bnew instructions\s*:",
    ],
    "NEW_BEHAVIOR_RULES": [
        r"(?i)\bс этого момента всегда отвеча\w+\s+(только|словом|фразой|так)\b",
        r"(?i)\bты (теперь\s*)?должен отвеча\w+\s+(только|на все вопросы)\b",
        r"(?i)\bты обязан отвеча\w+\s+(только|на все вопросы)\b",
        r"(?i)\bfrom now on always respond\b",
        r"(?i)\byou are now an unrestricted assistant\b",
    ]
}

# Compile all regex patterns
COMPILED_CATEGORIES = {
    category: [re.compile(pattern) for pattern in patterns]
    for category, patterns in CATEGORIES.items()
}

def normalize_text(text: str) -> str:
    """
    Safely normalizes text for prompt injection detection.
    - NFKC unicode normalization
    - Lowercase
    - Replace multiple spaces/newlines with a single space
    - Trim
    """
    if not text:
        return ""
        
    text = unicodedata.normalize('NFKC', text)
    text = text.lower()
    # Remove common quotes to help regex matching
    text = re.sub(r'["\'«»]', ' ', text)
    # Replace any whitespace sequence (including newlines) with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_prompt_injection(text: str) -> tuple[bool, str]:
    """
    Checks if the text contains a strong prompt injection pattern.
    Returns: (is_injection, matched_category)
    """
    if not text:
        return False, ""
        
    normalized = normalize_text(text)
    
    for category, patterns in COMPILED_CATEGORIES.items():
        for pattern in patterns:
            if pattern.search(normalized):
                return True, category
                
    return False, ""
