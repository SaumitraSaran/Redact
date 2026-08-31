"""
Default redaction rules for RedactPro.

This configuration file defines what patterns RedactPro considers
sensitive when the user does not provide specific instructions.

Rules are organized by category. Each category contains a list of
regex patterns that match potentially sensitive text.

To add new patterns:
  1. Choose or create a category.
  2. Add a compiled regex pattern to the list.
  3. Restart the backend.

The detector applies these rules as a secondary filter on OCR text:
if detected text matches ANY enabled rule, it is marked for redaction.
"""

import re


# ============================================================
# DEFAULT REDACTION RULES
# ============================================================

DEFAULT_REDACTION_RULES = {

    # --------------------------------------------------------
    # Currency amounts
    # --------------------------------------------------------
    # Matches: ₹500, $12,500.00, €500, £250, ¥1000
    "currency": [
        re.compile(
            r"[₹$€£¥]\s*[\d,]+\.?\d*",
            re.IGNORECASE
        ),
        re.compile(
            r"[\d,]+\.?\d*\s*[₹$€£¥]",
            re.IGNORECASE
        ),
        re.compile(
            r"(?:Rs\.?|INR|USD|EUR|GBP)\s*[\d,]+\.?\d*",
            re.IGNORECASE
        ),
    ],

    # --------------------------------------------------------
    # Account identifiers
    # --------------------------------------------------------
    # Matches: Account No: 1234567890, A/C: 1234567890
    "account_ids": [
        re.compile(
            r"(?:A/?C|Account)\s*(?:No\.?|Number|#)?\s*:?\s*\d{4,}",
            re.IGNORECASE
        ),
        re.compile(
            r"(?:IBAN|IFSC|SWIFT|MICR)\s*:?\s*[A-Z0-9]{4,}",
            re.IGNORECASE
        ),
    ],

    # --------------------------------------------------------
    # Password-like strings
    # --------------------------------------------------------
    # Matches: Password: abc123, Pass: XyZ123456, PIN: 1234
    "passwords": [
        re.compile(
            r"(?:Pass(?:word)?|PIN|OTP|CVV|CVC)\s*:?\s*\S+",
            re.IGNORECASE
        ),
    ],

    # --------------------------------------------------------
    # Identifiers
    # --------------------------------------------------------
    # Matches: ID: 123456, Employee ID: EMP12345, PAN: ABCDE1234F
    "identifiers": [
        re.compile(
            r"(?:Employee|Customer|User|Staff|Member|Patient|Student|Client)"
            r"\s*(?:ID|Id|id|No\.?|Number|#)\s*:?\s*\w+",
            re.IGNORECASE
        ),
        re.compile(
            r"(?:PAN|SSN|Aadhaar|Aadhar|NIN|TIN|EIN|GST(?:IN)?)\s*:?\s*[\w\-]+",
            re.IGNORECASE
        ),
        re.compile(
            r"(?:License|Licence|Passport|Voter\s*ID)\s*(?:No\.?|Number|#)?\s*:?\s*[\w\-]+",
            re.IGNORECASE
        ),
    ],

    # --------------------------------------------------------
    # Numeric sequences (4+ digits)
    # --------------------------------------------------------
    # Catches standalone multi-digit numbers that could be
    # phone numbers, card numbers, reference numbers, etc.
    "numeric_sequences": [
        re.compile(
            r"\b\d{4,}\b"
        ),
        re.compile(
            r"\b\d{3,4}[\s\-]\d{3,4}[\s\-]?\d{0,4}\b"
        ),
    ],

    # --------------------------------------------------------
    # Percentages
    # --------------------------------------------------------
    # Matches: 25%, 99.9%, 100 %, -5.5%, 0.05%
    "percentages": [
        re.compile(
            r"(?:[+\-]?\s*\d+(?:\.\d+)?\s*%)"
        ),
        re.compile(
            r"(?:\b\d+(?:\.\d+)?\s*(?:percent|percentage)\b)",
            re.IGNORECASE
        ),
    ],

    # --------------------------------------------------------
    # Phone numbers
    # --------------------------------------------------------
    "phone_numbers": [
        re.compile(
            r"(?:\+?\d{1,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}",
        ),
    ],

    # --------------------------------------------------------
    # Email addresses
    # --------------------------------------------------------
    "email_addresses": [
        re.compile(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        ),
    ],
}


# ============================================================
# RULE MATCHING
# ============================================================

def matches_any_rule(
    text: str,
    rules: dict = None
) -> bool:
    """
    Check if text matches any redaction rule.

    Args:
        text: The OCR-detected text to check.
        rules: Rule dictionary. Defaults to DEFAULT_REDACTION_RULES.

    Returns:
        True if the text matches at least one rule pattern.
    """
    if rules is None:
        rules = DEFAULT_REDACTION_RULES

    for category, patterns in rules.items():
        for pattern in patterns:
            if pattern.search(text):
                return True

    return False


def get_matching_categories(
    text: str,
    rules: dict = None
) -> list:
    """
    Return list of rule categories that match the given text.

    Useful for logging which rules triggered redaction
    (without logging the actual sensitive content).
    """
    if rules is None:
        rules = DEFAULT_REDACTION_RULES

    matched = []

    for category, patterns in rules.items():
        for pattern in patterns:
            if pattern.search(text):
                matched.append(category)
                break

    return matched
