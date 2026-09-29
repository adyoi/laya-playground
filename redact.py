from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from laya import BaseHook

PATTERNS: Dict[str, str] = {
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    "jwt": r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    "aws_key": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "api_key": r"\b(?:sk|pk|api|key|token)[-_][A-Za-z0-9]{16,}\b",
    "email": r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b",
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
    "nik": r"(?<![\d-])\d{16}(?![\d-])",
    "credit_card": r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])",
    "phone": r"(?<![\w.@-])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)?\d{2,4}(?:[ .-]\d{2,4}){1,3}(?![\w.@-])",
    "ipv4": r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])",
}

COMPILED: Dict[str, re.Pattern] = {k: re.compile(v) for k, v in PATTERNS.items()}

ORDER = [
    "private_key",
    "jwt",
    "aws_key",
    "api_key",
    "email",
    "iban",
    "nik",
    "credit_card",
    "phone",
    "ipv4",
]

# ORDER is the scan sequence and PATTERNS is what /redaction/kinds advertises, so a kind added
# to one but not the other is a silent hole: the endpoint would offer it while `redact_text`
# never matches it. Fail at import rather than shipping a redaction gap.
assert set(ORDER) == set(PATTERNS), "ORDER and PATTERNS disagree: %s" % (
    set(ORDER) ^ set(PATTERNS),
)


def _luhn(digits: str) -> bool:
    total = 0
    alternate = False
    for char in reversed(digits):
        value = int(char)
        if alternate:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        alternate = not alternate
    return total % 10 == 0


def _is_credit_card(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    return 13 <= len(digits) <= 19 and _luhn(digits)


def _is_phone(raw: str) -> bool:
    return len(re.sub(r"\D", "", raw)) >= 7


def _is_nik(raw: str) -> bool:
    return raw.isdigit() and len(raw) == 16


VALIDATORS = {
    "credit_card": _is_credit_card,
    "phone": _is_phone,
    "nik": _is_nik,
}


def redact_text(text: str, kinds: Optional[List[str]] = None) -> Tuple[str, Dict[str, int]]:
    """Replace every match in `text` with a labelled placeholder; return the text and per-kind counts.

    Order is significant: a 16-digit NIK is consumed before the credit-card rule can see it,
    and a digit run is only called a card when it passes Luhn, so ordinary phone numbers and
    invoice numbers survive as phone-shaped rather than being swallowed whole.
    """
    counts: Dict[str, int] = {}
    for kind in ORDER:
        if kinds is not None and kind not in kinds:
            continue
        validate = VALIDATORS.get(kind)

        def replace(match: "re.Match", kind: str = kind, validate: Any = validate) -> str:
            raw = match.group(0)
            if validate is not None and not validate(raw):
                return raw
            counts[kind] = counts.get(kind, 0) + 1
            return "[REDACTED:%s]" % kind

        text = COMPILED[kind].sub(replace, text)
    return text, counts


def redact_state(state: Any, kinds: Optional[List[str]] = None) -> Tuple[Any, Dict[str, int]]:
    """Redact every string in a state of type str, dict or list; leave other types alone."""
    if isinstance(state, str):
        return redact_text(state, kinds)
    if isinstance(state, dict):
        out: Dict[Any, Any] = {}
        counts: Dict[str, int] = {}
        for key, value in state.items():
            new_value, sub = redact_state(value, kinds)
            out[key] = new_value
            for k, n in sub.items():
                counts[k] = counts.get(k, 0) + n
        return out, counts
    if isinstance(state, list):
        out_list: List[Any] = []
        counts = {}
        for value in state:
            new_value, sub = redact_state(value, kinds)
            out_list.append(new_value)
            for k, n in sub.items():
                counts[k] = counts.get(k, 0) + n
        return out_list, counts
    return state, {}


def merge_counts(target: Dict[str, int], extra: Dict[str, int]) -> Dict[str, int]:
    for k, n in extra.items():
        target[k] = target.get(k, 0) + n
    return target


class RedactionHook(BaseHook):
    """Router-wide safety net: rewrite every state before the model ever sees it.

    Registered once on the Router, so it also covers calls that never pass through an
    endpoint here. The per-call counts are stashed on the context for hooks that run later.
    """

    def __init__(self, kinds: Optional[List[str]] = None) -> None:
        self.kinds = kinds
        self.total_redactions = 0

    def on_predict_start(self, ctx: Any) -> None:
        counts: Dict[str, int] = {}
        rewritten: List[Any] = []
        for state in ctx.states:
            new_state, sub = redact_state(state, self.kinds)
            rewritten.append(new_state)
            merge_counts(counts, sub)
        ctx.states = rewritten
        self.total_redactions += sum(counts.values())
        ctx.redaction = counts
