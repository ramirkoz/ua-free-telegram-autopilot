from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
# entities. An older rule treated ordinary fragments such as `Bring`, `Own` and `Your` as
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
_URL_RE = re.compile(r"https?://[^\s<>()\]\[{}\"']+", re.I)
_ACTIONABLE_LINK_CUES = (
    "реєстрац", "зареєстр", "заявк", "подати", "подач", "анкета", "анкету", "форма", "форму",
    "заповн", "посилан", "квитк", "броню", "бронюван", "оплат", "донат", "детал", "довідк",
    "графік", "розклад", "дедлайн", "прийом", "запис", "приєдна", "register", "registration",
    "apply", "application", "sign up", "signup", "form", "ticket", "booking", "payment", "details",
    "deadline", "schedule",
)


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


_ATTRIBUTION_LINK_CUES = (
    "за інформацією", "за даними", "за матеріалами", "джерело:",
    "читати у", "читати на", "детальніше про це інформує",
    "детальніше про це повідомляє", "детальніше про це пише",
)


def _local_url_context(text: str, start: int, end: int, radius: int = 220) -> str:
    """Return the URL line plus its immediately preceding text line when needed.

    Telegram posts often put a URL on a separate line after «за посиланням:» or
    «детальніше ...:».  Looking only at the URL line loses exactly the distinction
    we need between reader-action links and source/article attribution links.
    """
    value = str(text or "")
    line_start = value.rfind("\n", 0, start) + 1
    line_end = value.find("\n", end)
    if line_end < 0:
        line_end = len(value)

    # If the URL is effectively alone on its line, include the previous non-empty
    # line, where Telegram captions normally keep the cue introducing that link.
    before_on_line = value[line_start:start].strip()
    if not before_on_line and line_start > 0:
        prev_end = line_start - 1
        while prev_end > 0 and value[prev_end - 1] == "\n":
            prev_end -= 1
        prev_start = value.rfind("\n", 0, prev_end) + 1
        line_start = max(prev_start, start - radius)

    return value[max(0, line_start):min(len(value), max(line_end, end))]


def source_urls_in_text(source: str) -> list[str]:
    result: list[str] = []
    for match in _URL_RE.finditer(str(source or "")):
        url = match.group(0).rstrip(".,;:!?")
        if url and url not in result:
            result.append(url)
    return result[:24]


_TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "yclid", "srsltid", "vero_conv", "vero_id",
}


def _url_identity(value: str) -> str:
    raw = str(value or "").strip().rstrip(".,;:!?©®™")
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
            return raw.casefold()
        path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
        query_pairs = []
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            low = key.casefold()
            if low.startswith("utm_") or low in _TRACKING_QUERY_KEYS:
                continue
            query_pairs.append((key, val))
        query_pairs.sort(key=lambda item: (item[0].casefold(), item[1]))
        query = urlencode(query_pairs, doseq=True)
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))
    except Exception:
        return raw.casefold()


def article_non_actionable_urls(article) -> set[str]:
    """URLs that identify the source/article or media already attached to the post.

    These must never be reinserted into body text as reader-action links.
    """
    result: set[str] = set()
    for key in ("source_url", "canonical_source_url"):
        value = _row_text(article, key)
        ident = _url_identity(value)
        if ident:
            result.add(ident)
    try:
        raw_media = json.loads(_row_text(article, "media_json") or "[]")
    except Exception:
        raw_media = []
    if isinstance(raw_media, list):
        for item in raw_media:
            raw = str(item or "").strip()
            if "|" in raw and raw.split("|", 1)[0].casefold() in {"image", "video"}:
                raw = raw.split("|", 1)[1]
            ident = _url_identity(raw)
            if ident:
                result.add(ident)
    try:
        layout = json.loads(_row_text(article, "article_layout_json") or "{}")
    except Exception:
        layout = {}
    if isinstance(layout, dict):
        blocks = layout.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                ident = _url_identity(str(block.get("url") or ""))
                if ident:
                    result.add(ident)
    return result


def actionable_source_urls(source: str, *, source_name: str = "", excluded_urls=()) -> list[str]:
    """Return only reader-action URLs, excluding plain attribution/article links."""
    text = str(source or "")
    name = " ".join(str(source_name or "").split()).casefold()
    excluded = {_url_identity(value) for value in excluded_urls if _url_identity(value)}
    result: list[str] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?")
        if not url:
            continue
        if _url_identity(url) in excluded:
            continue
        context = _local_url_context(text, match.start(), match.end()).casefold()
        attribution = any(cue in context for cue in _ATTRIBUTION_LINK_CUES)
        if name and name in context and any(cue in context for cue in ("інформує", "повідомляє", "пише", "детальніше")):
            attribution = True
        if attribution:
            continue
        if not any(cue in context for cue in _ACTIONABLE_LINK_CUES):
            continue
        if url not in result:
            result.append(url)
    return result[:12]


# Compatibility for older callers/tests.
def _actionable_source_urls(source: str) -> list[str]:
    return actionable_source_urls(source)


_ORPHAN_SOURCE_LABEL_RE = re.compile(
    r"(?iu)^\s*(?:детальніше|деталі(?:\s*/\s*реєстрація)?|джерело|посилання|читати|більше)\s*[:：-]?\s*[©®™]*\s*$"
)


def strip_non_actionable_article_urls(article, text: str) -> str:
    """Remove source/canonical/already-attached-media URLs from body text.

    Reader-action URLs are preserved. Matching is identity-based, so tracking
    parameters, trailing slash differences and harmless suffix symbols cannot
    reintroduce the source URL under a slightly different spelling.
    """
    value = str(text or "")
    if not value.strip():
        return value.strip()
    excluded = article_non_actionable_urls(article)
    if not excluded:
        return value.strip()
    source = " ".join((_row_text(article, "source_name"), _row_text(article, "title"), _row_text(article, "raw_text")))
    actionable = {
        _url_identity(url)
        for url in actionable_source_urls(
            source,
            source_name=_row_text(article, "source_name"),
            excluded_urls=excluded,
        )
        if _url_identity(url)
    }

    out: list[str] = []
    last = 0
    seen_preserved: set[str] = set()
    for match in _URL_RE.finditer(value):
        out.append(value[last:match.start()])
        raw = match.group(0)
        ident = _url_identity(raw)
        end = match.end()
        if ident in excluded and ident not in actionable:
            while end < len(value) and value[end] in "©®™":
                end += 1
            # URL intentionally omitted.
        else:
            # Do not duplicate identical actionable URLs in the generated body.
            if ident and ident in seen_preserved:
                while end < len(value) and value[end] in "©®™":
                    end += 1
            else:
                out.append(raw.rstrip("©®™"))
                if ident:
                    seen_preserved.add(ident)
        last = end
    out.append(value[last:])
    cleaned = "".join(out)

    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        if _ORPHAN_SOURCE_LABEL_RE.match(line):
            continue
        # A removed URL may leave only punctuation/symbol noise on the line.
        if re.fullmatch(r"\s*[©®™:：;,.!?-]*\s*", line):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def validate_fact_guard(article: Row, output: str) -> FactGuardAssessment:
    # The operator-configured donor name is source evidence too. In the communities
    # lane it is deliberately the canonical community name that must survive rewrite.
    source = " ".join((_row_text(article, "source_name"), _row_text(article, "title"), _row_text(article, "raw_text")))
    source_low = f" {source.casefold()} "
    output_text = str(output or "")

    source_tokens = _protected_latin_tokens(source)
    output_tokens = _protected_latin_tokens(output_text)
    invented = sorted(output_tokens - source_tokens)
    if invented:
        raise FactGuardError("AI додав назву/модель, якої немає у джерелі: " + ", ".join(invented[:8]))

    # Reader-action links are protected facts too. A canonical source footer does
    # not satisfy this contract because it forces the reader to hunt for the actual
    # registration/form/payment target in somebody else's post.
    missing_action_urls = [url for url in actionable_source_urls(source, source_name=_row_text(article, "source_name"), excluded_urls=article_non_actionable_urls(article)) if url not in output_text]
    if missing_action_urls:
        raise FactGuardError(
            "AI прибрав практичне посилання з джерела: " + ", ".join(missing_action_urls[:4])
        )

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
