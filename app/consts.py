
# regex patterns that indicate someone trying to override system prompts
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"system\s*:\s*",
    r"override\s+instructions",
    r"forget\s+(all\s+)?prior",
    r"disregard\s+(all\s+)?instructions",
    r"new\s+instructions?\s*:",
    r"prompt\s+injection",
    r"act\s+as\s+(if|a|an)\s+",
    r"pretend\s+you\s+are",
    r"jailbreak",
    r"DAN\s+mode",
]


PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-.\s]?){3}\d{4}\b",
}

REDACTED = {
    "email": "[EMAIL_REDACTED]",
    "phone": "[PHONE_REDACTED]",
    "ssn": "[SSN_REDACTED]",
    "credit_card": "[CARD_REDACTED]",
}


MAX_ITERS = 3