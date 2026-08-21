from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Any


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    article_id: int
    score: float
    reason: str


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9’'/-]+")
_LATIN_ANCHOR_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9._+-]{2,}|[A-Z]{2,}[A-Z0-9._+-]*|[A-Za-z]+\d+[A-Za-z0-9._+-]*)\b")
_NUMBER_RE = re.compile(r"(?<![A-Za-zА-Яа-яІіЇїЄєҐґ])\d+(?:[.,]\d+)?(?:\s?%)?")

_STOPWORDS = {
    # Ukrainian
    "але", "аби", "або", "без", "був", "була", "були", "було", "буде", "будуть", "від", "він", "вона",
    "вони", "воно", "для", "до", "його", "її", "їх", "із", "коли", "ми", "на", "над", "не", "ні", "після",
    "під", "по", "про", "та", "так", "також", "той", "того", "тому", "у", "це", "цей", "ця", "ці", "що",
    "який", "яка", "яке", "які", "як", "чи", "ще", "вже", "може", "можуть", "має", "мають", "став", "стала",
    # English/source-title noise
    "the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "its", "new", "how", "what",
    "why", "into", "about", "has", "have", "was", "were", "will", "can", "could", "after", "before", "more",
}

_UA_SUFFIXES = (
    "уваннями", "юваннями", "ування", "ювання", "овувати", "ювати", "атися", "итися", "увати", "ювати",
    "ними", "ного", "ному", "ними", "ними", "ями", "ами", "ові", "еві", "єві", "ого", "ому", "ими", "ій",
    "ою", "ею", "ів", "їв", "ах", "ях", "ий", "ій", "а", "я", "у", "ю", "і", "и", "е", "о",
)


def _stem(token: str) -> str:
    value = token.casefold().replace("’", "'").strip("-'_/.")
    if len(value) < 5:
        return value
    if re.search(r"[а-яіїєґ]", value):
        for suffix in _UA_SUFFIXES:
            if len(value) - len(suffix) >= 4 and value.endswith(suffix):
                return value[: -len(suffix)]
        return value
    # Very light English normalization. It is only a similarity aid, never a
    # linguistic transformation used in published text.
    for suffix in ("ing", "edly", "ed", "ies", "es", "s"):
        if len(value) - len(suffix) >= 4 and value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _tokens(value: str) -> set[str]:
    out: set[str] = set()
    for raw in _TOKEN_RE.findall(str(value or "")):
        low = raw.casefold().strip("-'_/.")
        if len(low) < 3 or low in _STOPWORDS:
            continue
        stem = _stem(low)
        if len(stem) >= 3 and stem not in _STOPWORDS:
            out.add(stem)
    return out


def _numbers(value: str) -> set[str]:
    result = set()
    for raw in _NUMBER_RE.findall(str(value or "")):
        item = raw.replace(" ", "").replace("\u00a0", "").rstrip("%")
        if "," in item and "." not in item:
            item = item.replace(",", ".")
        result.add(item)
    return result


def _latin_anchors(value: str) -> set[str]:
    return {item.casefold() for item in _LATIN_ANCHOR_RE.findall(str(value or "")) if len(item) >= 3}


def _compact(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _row_value(row: Mapping[str, Any] | Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except Exception:
        return ""


def _pair_score(current_title: str, current_body: str, row: Mapping[str, Any] | Any) -> tuple[float, str] | None:
    old_body = (
        _row_value(row, "teaser_text")
        or _row_value(row, "event_summary")
        or _row_value(row, "full_article_uk")
    )
    if not old_body:
        return None

    cur_tokens = _tokens(current_body)
    old_tokens = _tokens(old_body)
    if len(cur_tokens) < 6 or len(old_tokens) < 6:
        return None

    shared = cur_tokens & old_tokens
    union = cur_tokens | old_tokens
    jaccard = len(shared) / max(1, len(union))
    containment = len(shared) / max(1, min(len(cur_tokens), len(old_tokens)))
    char_ratio = difflib.SequenceMatcher(None, _compact(current_body), _compact(old_body)).ratio()

    cur_title_tokens = _tokens(current_title)
    old_title_tokens = _tokens(_row_value(row, "title"))
    title_union = cur_title_tokens | old_title_tokens
    title_jaccard = len(cur_title_tokens & old_title_tokens) / max(1, len(title_union)) if title_union else 0.0

    cur_numbers = _numbers(current_body)
    old_numbers = _numbers(old_body)
    number_anchor = False
    if cur_numbers and old_numbers:
        number_anchor = bool(cur_numbers & old_numbers) and len(cur_numbers & old_numbers) / max(1, min(len(cur_numbers), len(old_numbers))) >= 0.5

    cur_anchors = _latin_anchors(current_title + "\n" + current_body)
    old_anchors = _latin_anchors(_row_value(row, "title") + "\n" + old_body)
    anchor_shared = cur_anchors & old_anchors

    # High-precision event duplicate rules. They intentionally require strong
    # overlap in the already-normalized Ukrainian rewrite, not merely the same
    # company/topic. This catches cross-source reports about one concrete event
    # while allowing separate stories about the same vendor.
    if char_ratio >= 0.80 and len(shared) >= 9:
        score = 0.55 * char_ratio + 0.45 * containment
        return score, f"дуже схожий опублікований текст (ratio={char_ratio:.2f}, shared={len(shared)})"

    if jaccard >= 0.56 and containment >= 0.72 and len(shared) >= 11:
        score = 0.58 * jaccard + 0.42 * containment
        return score, f"та сама подія за змістом (jaccard={jaccard:.2f}, containment={containment:.2f})"

    anchored = number_anchor or len(anchor_shared) >= 1 or title_jaccard >= 0.42
    if anchored and jaccard >= 0.48 and containment >= 0.68 and len(shared) >= 10:
        score = 0.50 * jaccard + 0.35 * containment + 0.15 * min(1.0, title_jaccard + 0.2 * len(anchor_shared))
        anchor_note = "числа" if number_anchor else ("сутності" if anchor_shared else "заголовки")
        return score, f"сильний змістовий збіг + {anchor_note} (jaccard={jaccard:.2f})"

    # Cross-source headlines can be lexically quite different even when both
    # stories describe the same concrete product/policy event. Require several
    # shared named anchors plus substantial body overlap before treating this
    # lower-Jaccard case as a duplicate.
    title_shared = cur_title_tokens & old_title_tokens
    if (
        len(anchor_shared) >= 2
        and len(title_shared) >= 2
        and len(shared) >= 12
        and containment >= 0.52
    ):
        score = 0.42 * containment + 0.28 * min(1.0, len(shared) / 16.0) + 0.30 * min(1.0, len(anchor_shared) / 3.0)
        return score, f"збіг події за сутностями й ключовими фактами (shared={len(shared)}, anchors={len(anchor_shared)})"

    # A short first report and a much longer follow-up about the same event can
    # have low Jaccard simply because the follow-up adds background.  RC29 missed
    # the Amazon Prime Air pool story for exactly this reason.  Require several
    # shared proper-name anchors, substantial overlap with the shorter story and
    # one extra event anchor (matching number or meaningful title overlap).
    if (
        len(anchor_shared) >= 3
        and len(shared) >= 15
        and containment >= 0.35
        and (number_anchor or title_jaccard >= 0.20)
    ):
        score = (
            0.46 * containment
            + 0.24 * min(1.0, len(shared) / 20.0)
            + 0.20 * min(1.0, len(anchor_shared) / 4.0)
            + 0.10 * max(title_jaccard, 0.35 if number_anchor else 0.0)
        )
        anchor_note = "числом" if number_anchor else "заголовком"
        return score, f"короткий/розширений опис тієї самої події ({anchor_note}, shared={len(shared)}, anchors={len(anchor_shared)})"

    return None


def find_event_duplicate(
    current_title: str,
    current_body: str,
    recent_published: Iterable[Mapping[str, Any] | Any],
) -> DuplicateMatch | None:
    best: DuplicateMatch | None = None
    for row in recent_published:
        result = _pair_score(current_title, current_body, row)
        if result is None:
            continue
        score, reason = result
        try:
            article_id = int(row["id"])
        except Exception:
            continue
        match = DuplicateMatch(article_id=article_id, score=score, reason=reason)
        if best is None or match.score > best.score:
            best = match
    return best
