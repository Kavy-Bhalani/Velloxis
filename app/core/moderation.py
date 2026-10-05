import re
from typing import Tuple

# Fast pre-inference regex patterns for safety policy violations
# This protects against obvious policy violations before any API call is made.
PROHIBITED_PATTERNS = [
    # CSAM & Child safety (Zero tolerance)
    re.compile(r"\b(child|underage|minor|infant|toddler|teen)\s*(porn|nude|nsfw|naked|erotic|sex|bikini)\b", re.IGNORECASE),
    re.compile(r"\blolita\b", re.IGNORECASE),
    # Extreme violence / Self-harm
    re.compile(r"\b(suicide|self-harm|hang\s*yourself|cut\s*wrists)\b", re.IGNORECASE),
    re.compile(r"\b(decapitat|beheading|snuff|torture\s*murder)\b", re.IGNORECASE),
    # Non-consensual explicit deepfakes
    re.compile(r"\b(deepfake\s*nude|nude\s*celebrity|upskirt|creepshot)\b", re.IGNORECASE),
    # Direct explicit sexual prompts (since text-to-image stores reject NSFW)
    re.compile(r"\b(hardcore\s*porn|penetration|gangbang|masturbat)\b", re.IGNORECASE),
]

def check_prompt_safety(prompt: str, max_length: int = 1000) -> Tuple[bool, str | None]:
    """
    Validates user prompt for length, empty content, and policy violations.
    Returns: (is_safe, error_message)
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return False, "Prompt cannot be empty."

    if len(clean_prompt) > max_length:
        return False, f"Prompt exceeds maximum allowed length of {max_length} characters."

    for pattern in PROHIBITED_PATTERNS:
        if pattern.search(clean_prompt):
            return False, "Prompt violates content safety guidelines."

    return True, None
