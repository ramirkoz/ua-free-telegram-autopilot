from __future__ import annotations

import re
from dataclasses import dataclass
from sqlite3 import Row


class FactGuardError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FactGuardAssessment:
    checked_entities: int
    checked_claims: int


_COMMON_LATIN = {
    "AI", "API", "CPU", "GPU", "RAM", "SSD", "USB", "GPS", "NASA", "ESA", "EU", "US", "USA", "UK",
    "CEO", "CVE", "WiFi", "Wi-Fi", "HTTP", "HTTPS", "RSS", "PDF", "LLM", "VR", "AR", "OS",
}

# High-risk claims are deliberately conservative. They are blocked only when the
# Ukrainian output strengthens a claim that has no matching signal in SOURCE.
_CLAIM_RULES: tuple[tuple[re.Pattern[str], tuple[str, ...], str], ...] = (
    (re.compile(
        r"\bвперше\b|\bперш(?:ий|а|е|і|ого|ому|ою)\b(?=\s+(?:у\s+світі|в\s+історії|такого|подібного|польов|серійн|комерційн|модел|пристро|систем|тест))",
        re.I,
    ),
     (" first ", "first-", "first-ever", "for the first time", "world's first", "world first", "1st ", " вперше ", " перш"),
     "твердження про «перший/вперше»"),
    (re.compile(r"\bнайбільш(?:ий|а|е|і|ою|ого|ому)\b|\bнайбіль(?:ший|ша|ше|ші|шого)\b", re.I),
     ("largest", "biggest", "most large", "найбільш", "найбіль"),
     "твердження про «найбільший»"),
    (re.compile(r"\bнайшвидш(?:ий|а|е|і|ого|ому)\b", re.I),
     ("fastest", "найшвидш"), "твердження про «найшвидший»"),
    (re.compile(r"\bнайпотужн(?:іший|іша|іше|іші|ішого)\b", re.I),
     ("most powerful", "powerful ever", "найпотужн"), "твердження про «найпотужніший»"),
    (re.compile(r"\bрекорд(?:ний|на|не|ні|у|ом|ів)?\b", re.I),
     ("record", "рекорд"), "твердження про рекорд"),
)

_LATIN_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9.+_/-]{2,}\b")


def _row_text(article: Row, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return ""


def _protected_latin_tokens(value: str) -> set[str]:
    result: set[str] = set()
    for token in _LATIN_TOKEN_RE.findall(value or ""):
        if token in _COMMON_LATIN:
            continue
        # Protect product/version-like tokens and proper-name shaped Latin tokens.
        if any(ch.isdigit() for ch in token) or (token[0].isupper() and any(ch.islower() for ch in token[1:])) or token.isupper():
            result.add(token.casefold())
    return result


def validate_fact_guard(article: Row, output: str) -> FactGuardAssessment:
    source = " ".join((_row_text(article, "title"), _row_text(article, "raw_text"), _row_text(article, "source_published_at")))
    source_low = f" {source.casefold()} "
    output_text = str(output or "")

    source_tokens = _protected_latin_tokens(source)
    output_tokens = _protected_latin_tokens(output_text)
    invented = sorted(output_tokens - source_tokens)
    if invented:
        raise FactGuardError("AI додав назву/модель, якої немає у джерелі: " + ", ".join(invented[:8]))

    checked_claims = 0
    for pattern, source_signals, label in _CLAIM_RULES:
        if not pattern.search(output_text):
            continue
        checked_claims += 1
        if not any(signal.casefold() in source_low for signal in source_signals):
            raise FactGuardError(f"AI посилив факт без опори на джерело: {label}.")

    return FactGuardAssessment(checked_entities=len(output_tokens), checked_claims=checked_claims)
