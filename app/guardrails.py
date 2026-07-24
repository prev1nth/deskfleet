from app.model import ResolveRequest, ResolveResponse
from app.consts import INJECTION_PATTERNS, PII_PATTERNS, REDACTED

import re

def detect_injection(text : str) -> bool:
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower) :
            return True
    return False

def redact_pii(text: str) -> str:
    redacted = text
    for pii_type,pattern in PII_PATTERNS.items() :
        redacted = re.sub(pattern, REDACTED.get(pii_type), redacted)
    return redacted

def scan_input(text : str) -> dict:
    injected = detect_injection(text)
    cleaned = redact_pii(text)

    return {
        "injection_detected": injected,
        "original": text,
        "cleaned": cleaned
    }

def scan_resolve_request(req: ResolveRequest) -> dict:
    return scan_input(req.ticket)