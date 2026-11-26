"""Source-owned evidence IDs for a single selector request; never approve a story."""
from __future__ import annotations
import re
from .evidence_ledger import extract_source_evidence


def selector_evidence_2366(raw: str, packed: str) -> dict[str, str]:
    _, marker, body = str(packed).partition("SELECTED SOURCE PASSAGES:\n")
    if not marker:
        return {}
    body = " ".join(body.split())
    result = {}
    for entry in extract_source_evidence(raw, "selector-source").entries:
        quote = " ".join(entry.quote.split())
        if 20 <= len(quote) <= 180 and quote in body and quote not in result.values():
            result[f"Q{len(result)+1}"] = quote
            if len(result) >= 4:
                break
    return result


def evidence_hint_2366(options: dict[str, str]) -> str:
    if not options:
        return ""
    return ("\nДОКАЗИ (дослівні фрагменти SOURCE BODY; обери відповідний, не будь-який):\n"
            + "\n".join(f"{key}: {quote}" for key, quote in options.items())
            + "\nДля publish у source_quote можна повернути тільки відповідний ID Q1–Q4 замість повторного копіювання цитати; якщо жоден не доводить новину, процитуй інший дослівний фрагмент SOURCE BODY або reject.\n")


def resolve_evidence_2366(obj: dict, options: dict[str, str]) -> dict:
    # Exact IDs only, and only from THIS prompt. Existing original-source quote
    # validator must still run after expansion. Never repair or infer a verdict.
    quote = obj.get("source_quote")
    if isinstance(quote, str) and quote.strip() in options:
        obj = dict(obj, source_quote=options[quote.strip()])
    return obj
