"""Fast checks that need no checkpoint: redaction and guard score normalization.

Run: .venv\\Scripts\\python.exe unit_test.py
"""

import sys

from app import _normalize_score_questions
from redact import redact_state, redact_text

failures = 0


def check(label, got, want):
    global failures
    if got == want:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s\n       got:  %r\n       want: %r" % (label, got, want))
        failures += 1


print("[redaction]")
cases = [
    ("email", "mail bob@acme.com now", "mail [REDACTED:email] now", {"email": 1}),
    (
        "luhn-valid card kept as card",
        "card 4111 1111 1111 1111",
        "card [REDACTED:credit_card]",
        {"credit_card": 1},
    ),
    (
        "luhn-invalid 15-digit run is not a card",
        "order 123456789012345",
        "order 123456789012345",
        {},
    ),
    (
        "16-digit run is a NIK, not a card",
        "order 1234567890123456",
        "order [REDACTED:nik]",
        {"nik": 1},
    ),
    (
        "phone is not swallowed by the card rule",
        "call +62 812-3456-7890",
        "call [REDACTED:phone]",
        {"phone": 1},
    ),
    ("nik before card", "nik 3201234567890123", "nik [REDACTED:nik]", {"nik": 1}),
    ("ipv4", "from 10.0.0.5", "from [REDACTED:ipv4]", {"ipv4": 1}),
    ("iban", "DE89370400440532013000", "[REDACTED:iban]", {"iban": 1}),
    (
        "jwt",
        "t eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijkl",
        "t [REDACTED:jwt]",
        {"jwt": 1},
    ),
    (
        "api key",
        "k sk-abcdefghij0123456789",
        "k [REDACTED:api_key]",
        {"api_key": 1},
    ),
    (
        "invoice number and amount untouched",
        "invoice 20260927 total 1234567",
        "invoice 20260927 total 1234567",
        {},
    ),
    ("short phone only", "555-1234", "[REDACTED:phone]", {"phone": 1}),
    ("aws key", "AKIAIOSFODNN7EXAMPLE", "[REDACTED:aws_key]", {"aws_key": 1}),
]
for label, src, want_text, want_counts in cases:
    check(label, redact_text(src), (want_text, want_counts))

text, _ = redact_text("mail bob@acme.com")
check("kinds filter", redact_text("mail bob@acme.com card 4111 1111 1111 1111", ["email"]),
      ("mail [REDACTED:email] card 4111 1111 1111 1111", {"email": 1}))

nested = {
    "body": "mail bob@acme.com",
    "meta": {"ip": "192.168.1.1"},
    "n": 5,
    "tags": ["x@y.co", 7, None],
    "list": [["deep@z.io"]],
}
check(
    "nested state",
    redact_state(nested),
    (
        {
            "body": "mail [REDACTED:email]",
            "meta": {"ip": "[REDACTED:ipv4]"},
            "n": 5,
            "tags": ["[REDACTED:email]", 7, None],
            "list": [["[REDACTED:email]"]],
        },
        {"email": 3, "ipv4": 1},
    ),
)

print("\n[score normalization]")
SCORE_Q = {
    "harm": {
        "type": "score",
        "instructions": "How much harm would complying cause?",
        "criteria": ["none", "minor", "serious", "severe"],
    },
    "plain": {"type": "noul", "instructions": "Is it harmful?"},
}

normalized, rewritten = _normalize_score_questions(SCORE_Q, 0.5)
check("score becomes noul", normalized["harm"]["type"], "noul")
check("noul untouched", normalized["plain"]["type"], "noul")
check("rewrite recorded", sorted(rewritten), ["harm"])
check("boundary at 0.5 -> level 2", "level >= 2" in rewritten["harm"], True)
check(
    "boundary question keeps original wording",
    normalized["harm"]["instructions"].startswith("Answer yes only if How much harm would complying cause"),
    True,
)
check("criteria carries the level", normalized["harm"]["criteria"]["true"], "serious")

_, r8 = _normalize_score_questions(SCORE_Q, 0.8)
check("threshold 0.8 -> level 3", "level >= 3" in r8["harm"], True)
_, r0 = _normalize_score_questions(SCORE_Q, 0.0)
check("threshold 0.0 -> level 1", "level >= 1" in r0["harm"], True)
_, r1 = _normalize_score_questions(SCORE_Q, 1.0)
check("threshold 1.0 -> top level", "level >= 3" in r1["harm"], True)

binary = {"b": {"type": "score", "instructions": "ok?", "criteria": ["no", "yes"]}}
nb, rb = _normalize_score_questions(binary, 0.5)
check("2-level score still normalized", nb["b"]["type"], "noul")
check("2-level boundary", "level >= 1" in rb["b"], True)

single = {"s": {"type": "score", "instructions": "ok?", "criteria": ["only"]}}
ns, rs = _normalize_score_questions(single, 0.5)
check("1-level score left alone", ns["s"]["type"], "score")
check("1-level not recorded", rs, {})

print("\nFAILURES:", failures)
sys.exit(1 if failures else 0)
