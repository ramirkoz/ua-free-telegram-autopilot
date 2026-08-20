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
    "OAuth", "DNS", "TCP", "IP", "VPN", "LAN", "WAN", "URL", "HTML", "JSON", "SQL", "SSH", "TLS",
}

# Capitalized English words at a sentence boundary are not automatically named
# entities. RC18 treated ordinary fragments such as `Bring`, `Own` and `Your` as
# hallucinated product names. Keep the entity guard focused on actual names/models
# while language QA remains responsible for accidental English prose.
_COMMON_ENGLISH = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could",
    "do", "does", "for", "from", "get", "gets", "got", "had", "has", "have", "how",
    "if", "in", "into", "is", "it", "its", "may", "more", "most", "new", "no", "not",
    "of", "on", "one", "or", "our", "out", "own", "said", "say", "says", "so", "than",
    "that", "the", "their", "them", "there", "these", "they", "this", "to", "up", "use",
    "used", "using", "was", "we", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your", "bring", "brings", "make", "makes",
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
    for raw_token in _LATIN_TOKEN_RE.findall(value or ""):
        # Hyphenated Ukrainian compounds such as ``AI-навантаження`` expose a
        # regex token ``AI-``.  Normalize harmless edge punctuation before entity
        # classification so common acronyms do not become invented models.
        token = raw_token.strip("._+/-")
        if not token:
            continue
        if token in _COMMON_LATIN or token.casefold() in _COMMON_ENGLISH:
            continue
        # Protect product/version-like tokens and proper-name shaped Latin tokens.
        if any(ch.isdigit() for ch in token) or (token[0].isupper() and any(ch.islower() for ch in token[1:])) or token.isupper():
            result.add(token.casefold())
    return result


def validate_fact_guard(article: Row, output: str) -> FactGuardAssessment:
    source = " ".join((_row_text(article, "title"), _row_text(article, "raw_text")))
    source_low = f" {source.casefold()} "
    output_text = str(output or "")

    source_tokens = _protected_latin_tokens(source)
    output_tokens = _protected_latin_tokens(output_text)
    invented = sorted(output_tokens - source_tokens)
    if invented:
        raise FactGuardError("AI додав назву/модель, якої немає у джерелі: " + ", ".join(invented[:8]))

    # Conservative relation-strengthening guards for failure modes seen live.
    # They do not try to understand every fact; they only block transformations
    # that are clearly stronger or technically different from SOURCE.
    output_low = output_text.casefold()
    purchase_words = ("придбав", "придбала", "придбали", "придбання", "купив", "купила", "купили", "купівл")
    source_purchase = (" buy ", " buys ", " bought ", " purchase", " acquire", " acquisition", " order")
    source_deal = ("agreement", " deal ", "develop", "deployment", "deploy")
    if any(word in output_low for word in purchase_words) and any(sig in source_low for sig in source_deal) and not any(sig in source_low for sig in source_purchase):
        raise FactGuardError("AI посилив тип домовленості: угода/розгортання перетворені на купівлю або придбання.")

    sodium_cooling = any(sig in source_low for sig in ("sodium-cooled", "sodium cooled", "cooled by sodium", "liquid sodium"))
    molten_salt = "molten salt" in source_low
    if sodium_cooling and molten_salt and re.search(r"охолоджу\w*.{0,60}розплавлен\w*\s+с(?:ол|іл)\w*", output_low, re.I | re.S):
        raise FactGuardError("AI переплутав зв'язок компонентів: натрієве охолодження реактора та накопичення тепла у розплавленій солі.")

    checked_claims = 0
    for pattern, source_signals, label in _CLAIM_RULES:
        if not pattern.search(output_text):
            continue
        checked_claims += 1
        if not any(signal.casefold() in source_low for signal in source_signals):
            raise FactGuardError(f"AI посилив факт без опори на джерело: {label}.")

    return FactGuardAssessment(checked_entities=len(output_tokens), checked_claims=checked_claims)
