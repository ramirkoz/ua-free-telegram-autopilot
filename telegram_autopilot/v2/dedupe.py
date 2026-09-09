from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from typing import Any

from .domain import Decision, Stage
from .loghub import event
from .storage import V2Store

_GENERIC = {
    "the","and","for","with","from","this","that","into","about","after","before","new","how","why","what",
    "ad","ads","advert","advertising","campaign","campaigns","creative","creatives","brand","brands","marketing",
    "media","design","story","stories","work","launch","launches","latest","live","says","say","reveals","revealed",
    "про","для","та","або","що","цей","ця","це","новий","нова","нове","реклама","кампанія","бренд","маркетинг",
}
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9][A-Za-zА-Яа-яІіЇїЄєҐґ0-9'’.-]{2,}")
_CODE_RE = re.compile(r"\b(?:[A-Za-zА-Яа-яІіЇїЄєҐґ]{1,12}[-_ ]?\d+[A-Za-z0-9-]*|\d+[A-Za-z]{1,8}\d*)\b", re.I)


def _v(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _words(value: str) -> set[str]:
    out: set[str] = set()
    for token in _WORD_RE.findall(str(value or "")):
        low = token.casefold().strip(".'’-_")
        if len(low) >= 3 and low not in _GENERIC:
            out.add(low)
    return out


def _title_words(row: Any) -> set[str]:
    return _words(str(_v(row,"title",""))) - _words(str(_v(row,"source_name","")))


def _body_words(row: Any) -> set[str]:
    return _words(str(_v(row,"raw_text","") or _v(row,"event_summary",""))[:5000])


def _codes(row: Any) -> set[str]:
    text = f"{_v(row,'title','')} {_v(row,'raw_text','')}"
    out: set[str] = set()
    for token in _CODE_RE.findall(text[:3000]):
        normalized = re.sub(r"[\s_-]+", "", token).casefold()
        if len(normalized) >= 3 and not re.fullmatch(r"(?:19|20)\d{2}", normalized):
            out.add(normalized)
    return out


def _overlap(a: set[str], b: set[str]) -> tuple[int,float]:
    if not a or not b:
        return 0, 0.0
    shared = a & b
    return len(shared), len(shared) / max(1,min(len(a),len(b)))


def _same_event(current: Any, candidate: Any) -> tuple[bool,str]:
    au=str(_v(current,"canonical_source_url","") or _v(current,"source_url","")).strip()
    bu=str(_v(candidate,"canonical_source_url","") or _v(candidate,"source_url","")).strip()
    if au and bu and au==bu:
        return True,"same canonical URL"
    ah=str(_v(current,"content_hash","")).strip(); bh=str(_v(candidate,"content_hash","")).strip()
    if ah and bh and ah==bh:
        return True,"same content hash"

    ac,bc=_codes(current),_codes(candidate); shared_codes=ac&bc
    if shared_codes and (ac-shared_codes) and (bc-shared_codes):
        return False,"conflicting strong event/version/product codes"

    at,bt=_title_words(current),_title_words(candidate); shared_title,title_containment=_overlap(at,bt)
    title_ratio=difflib.SequenceMatcher(None," ".join(sorted(at))," ".join(sorted(bt))).ratio() if at and bt else 0.0
    ab,bb=_body_words(current),_body_words(candidate); shared_body,body_containment=_overlap(ab,bb)

    # Same-source separate rows are independent stories unless very high precision evidence proves otherwise.
    same_source=int(_v(current,"source_id",0) or 0)==int(_v(candidate,"source_id",0) or -1)
    if same_source:
        if shared_title>=4 and title_ratio>=0.90 and shared_body>=14 and body_containment>=0.82:
            return True,f"same-source exact event anchors title={title_ratio:.2f} body={body_containment:.2f}"
        return False,"different rows from same source without exact event confirmation"

    if shared_codes and shared_title>=2 and body_containment>=0.55:
        return True,"shared strong event code plus title/body anchors"
    if shared_title>=3 and title_ratio>=0.82:
        return True,f"high title anchors ratio={title_ratio:.2f}"
    if shared_title>=4 and title_containment>=0.76:
        return True,f"high title containment={title_containment:.2f}"
    if shared_title>=2 and shared_body>=12 and body_containment>=0.72:
        return True,f"title+body event overlap={body_containment:.2f}"
    return False,f"topic similarity only title_shared={shared_title} title_containment={title_containment:.2f} body={body_containment:.2f}"


def _media_list(row: Any) -> list[str]:
    try:
        value=json.loads(str(_v(row,"media_json","[]") or "[]"))
    except Exception:
        return []
    return [str(item) for item in value if str(item).strip()] if isinstance(value,list) else []


def _merge_media(store: V2Store, target_id: int, donor: Any) -> None:
    target=store.get_article(target_id)
    if target is None:return
    merged=[]
    for item in [*_media_list(target),*_media_list(donor)]:
        if item not in merged: merged.append(item)
    if merged!=_media_list(target):
        store.update_article(target_id,media_json=json.dumps(merged[:24],ensure_ascii=False,separators=(",",":")))


@dataclass(frozen=True,slots=True)
class DedupeResult:
    relation: str
    duplicate_of: int | None = None
    reason: str = ""


class DedupeEngine:
    def __init__(self,store: V2Store): self.store=store

    def evaluate(self,article_id: int) -> DedupeResult:
        current=self.store.get_article(article_id)
        if current is None: raise KeyError(article_id)
        channel=self.store.get_channel(int(current["channel_id"]))
        hours=channel.dedupe_window_hours if channel else 72
        candidates=self.store.recent_candidates(int(current["channel_id"]),article_id=article_id,hours=hours,limit=140)
        for candidate in candidates:
            # Never let an already-known duplicate bridge unrelated stories.
            if str(candidate["decision"])==str(Decision.DUPLICATE):
                continue
            same,reason=_same_event(current,candidate)
            if not same:
                continue
            candidate_id=int(candidate["id"])
            self._mark_duplicate(article_id,candidate_id,reason)
            _merge_media(self.store,candidate_id,current)
            event("editorial","duplicate confirmed",channel_id=int(current["channel_id"]),article_id=article_id,duplicate_of=candidate_id,reason=reason)
            return DedupeResult("DUPLICATE",candidate_id,reason)
        self.store.update_article(article_id,stage=str(Stage.DEDUPED))
        return DedupeResult("SINGLE",None,"no confirmed same event")

    def _mark_duplicate(self,article_id: int,candidate_id: int,reason: str) -> None:
        candidate=self.store.get_article(candidate_id)
        detail=f"Confirmed same event #{candidate_id}: {reason}"
        self.store.update_article(article_id,stage=str(Stage.DEDUPED),decision=str(Decision.DUPLICATE),duplicate_of=candidate_id,reject_reason=detail,status_detail=detail)
        # If candidate is still pending, donor media has already been merged. We deliberately do not
        # mutate its editorial state; the first concrete event row remains canonical.
