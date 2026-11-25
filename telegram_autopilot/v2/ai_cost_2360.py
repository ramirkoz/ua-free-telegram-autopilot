"""Article-scoped paid admission and exact-text semantic review receipts.
No operator configuration changes; never overrides local/source/delivery gates.
"""
from __future__ import annotations
import hashlib
import json
import re
from .loghub import event

MAX_PAID_EDITORIAL_ATTEMPTS = 5
MAX_PAID_TOTAL_ATTEMPTS = 8
OBSERVED_USD_LIMIT = 0.010


def reserve_paid_attempt(store, article_id: int, *, editorial: bool = True) -> bool:
    """Persist BEFORE sending, including timeouts/invalid results; atomic across workers."""
    if not article_id:
        return True
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            row = con.execute("SELECT attempts, editorial_attempts FROM ai_article_budget_2360 WHERE article_id=?", (article_id,)).fetchone()
            attempts = int(row[0]) if row else 0
            editorial_attempts = int(row[1]) if row else 0
            spend = float(con.execute("SELECT COALESCE(SUM(actual_openrouter_usd),0) FROM ai_usage_events WHERE article_id=? AND provider='openrouter'", (article_id,)).fetchone()[0])
            if attempts >= MAX_PAID_TOTAL_ATTEMPTS or (editorial and editorial_attempts >= MAX_PAID_EDITORIAL_ATTEMPTS) or spend >= OBSERVED_USD_LIMIT:
                con.rollback()
                event('ai', 'article paid editorial budget exhausted 2360', article_id=article_id, attempts=attempts, editorial_attempts=editorial_attempts, actual_usd=round(spend,6))
                return False
            con.execute("INSERT INTO ai_article_budget_2360(article_id,attempts,editorial_attempts) VALUES(?,1,?) ON CONFLICT(article_id) DO UPDATE SET attempts=attempts+1, editorial_attempts=editorial_attempts+excluded.editorial_attempts", (article_id,int(editorial)))
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise


def _field(article, key):
    try:
        return str(article[key] or '')
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, '') or '')


def review_key(channel, article, text):
    # Exact source and exact body, including punctuation. Policy change invalidates receipt.
    parts = ['2360', str(channel.id), str(getattr(channel,'mode','')),
             str(getattr(channel,'editorial_runtime_profile','')), repr(getattr(channel,'policy',None)),
             _field(article,'title'), _field(article,'raw_text'),
             _field(article,'canonical_source_url'), _field(article,'source_url'), str(text).strip()]
    return hashlib.sha256(json.dumps(parts,ensure_ascii=False).encode()).hexdigest()


def review_receipt(store, channel, article, text):
    aid = int(_field(article,'id') or 0)
    if not aid:
        return ''
    with store.connect() as con:
        row=con.execute('SELECT reason FROM ai_reader_receipts_2360 WHERE article_id=? AND digest=?', (aid,review_key(channel,article,text))).fetchone()
    return str(row[0]) if row else ''


def save_review_receipt(store, channel, article, text, reason):
    aid = int(_field(article,'id') or 0)
    if not aid or not str(text).strip():
        return
    with store.connect() as con:
        con.execute('INSERT INTO ai_reader_receipts_2360(article_id,digest,reason) VALUES(?,?,?) ON CONFLICT(article_id) DO UPDATE SET digest=excluded.digest,reason=excluded.reason', (aid,review_key(channel,article,text),str(reason)[:700]))


def compact_prompt(prompt):
    """Remove only exact repeated instruction lines before SOURCE; never truncate evidence or policy."""
    header, sep, evidence = str(prompt).partition('SOURCE:\n')
    if not sep:
        return prompt
    seen=set(); out=[]
    for line in header.splitlines():
        key=line.strip()
        if len(key)>=35 and key in seen:
            continue
        if len(key)>=35:
            seen.add(key)
        out.append(line)
    return '\n'.join(out)+'\n'+sep+evidence


def compact_style_memory(block):
    # One complete owner-approved example; no source facts or rules removed.
    lines=str(block or '').splitlines()
    return '\n'.join(line for line in lines if not re.match(r'^🔥[2-9]\d*:',line))

COMBINED_EDITOR_RULE = """Виконай одночасно фінальне редагування та перевірку очима читача. Обов'язково: зрозуміло хто що зробив і чому це цікаво, послідовність, природна українська, ключові факти й важливі обмеження з SOURCE. Виправ істотні недоліки за один прохід; не вимагай усіх другорядних подробиць дослідження, якщо вони не змінюють висновку. Не переробляй текст заради синонімів. Для ПРОДАНО! якщо в SOURCE немає конкретної незвичайної ідеї, механізму, людської історії чи іншого широкого читацького інтересу, поверни тільки REJECT_READER_2360, не вигадуй гачок. Для ГРОМАД не змінюй правила відбору та не прибирай практичні подробиці. Поверни лише самодостатній перевірений фінальний текст."""
