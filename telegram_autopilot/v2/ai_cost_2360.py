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


def reserve_paid_attempt(store, article_id: int, *, editorial: bool = True, purpose: str = "") -> bool:
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
            # Reserve a final editor and a reader check within the existing cap.
            # Historical attempts are never reset; the USD admission threshold
            # is unchanged and does not guarantee the next invoice amount.
            phase = str(purpose or '').casefold()
            reserve = 3 if phase in {'editorial_selector', 'monitoring_selector'} else 2 if phase == 'writer' else 1 if phase in {'final_editor', 'rewrite', 'complex_rewrite'} else 0
            editorial_reserve = min(reserve, 2)
            total_limit = MAX_PAID_TOTAL_ATTEMPTS - reserve
            editorial_limit = MAX_PAID_EDITORIAL_ATTEMPTS - editorial_reserve
            selector_blocked = reserve == 3 and editorial_attempts >= MAX_PAID_EDITORIAL_ATTEMPTS - 2
            if attempts >= total_limit or (editorial and editorial_attempts >= editorial_limit) or selector_blocked or spend >= OBSERVED_USD_LIMIT:
                con.rollback()
                event('ai', 'article paid editorial budget exhausted 2360', article_id=article_id, attempts=attempts, editorial_attempts=editorial_attempts, actual_usd=round(spend,6), purpose=phase, reserved_attempts=reserve, total_limit=total_limit, editorial_limit=editorial_limit)
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
    # The source itself stays byte-identical. Only repeated literal evidence
    # hints can be replaced by a reference to the same text below.
    source = evidence.split("\nDRAFT:\n", 1)[0]
    normalized_source = " ".join(source.split())
    for line in header.splitlines():
        hint = re.match(r"^\s*- (?:Цитата SOURCE: |\[(?:ЦИФРА В КОНТЕКСТІ|АТРИБУЦІЯ/УМОВНІСТЬ|ПРАКТИЧНІ УМОВИ|ФАКТ ДЖЕРЕЛА), фрагмент \d+\] )(.*)$", line)
        if hint and len(hint[1]) >= 55 and "[уривок]" not in hint[1] and " ".join(hint[1].split()) in normalized_source:
            # Do not strip rule text, labels, facts outside SOURCE or protected contacts.
            line = line[:hint.start(1)] + "Дослівний фрагмент уже наведено у SOURCE нижче."
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


def writer_checkpoint(store, channel, article, prompt):
    """Draft only, never an approval or a reader receipt. Caller revalidates."""
    aid = int(_field(article, 'id') or 0)
    if not aid:
        return None
    with store.connect() as con:
        row = con.execute('SELECT draft,provider,model FROM ai_writer_checkpoint_2362 WHERE article_id=? AND digest=?',
                          (aid, review_key(channel, article, prompt))).fetchone()
    return tuple(row) if row else None


def save_writer_checkpoint(store, channel, article, prompt, draft, provider, model):
    aid = int(_field(article, 'id') or 0)
    if not aid or not draft.strip():
        return
    with store.connect() as con:
        con.execute('INSERT INTO ai_writer_checkpoint_2362(article_id,digest,draft,provider,model) VALUES(?,?,?,?,?) '
                    'ON CONFLICT(article_id) DO UPDATE SET digest=excluded.digest,draft=excluded.draft,provider=excluded.provider,model=excluded.model',
                    (aid, review_key(channel, article, prompt), draft, provider, model))


def clear_writer_checkpoint(store, article_id):
    with store.connect() as con:
        con.execute('DELETE FROM ai_writer_checkpoint_2362 WHERE article_id=?', (int(article_id),))


def prompt_shape_2363(prompt):
    """Counts only; no source, policy or personal information in events."""
    head, marker, tail = str(prompt).partition("\nSOURCE:\n")
    source, draft_marker, draft = tail.partition("\nDRAFT:\n")
    return {"prompt_chars": len(prompt), "instruction_chars": len(head),
            "source_section_chars": len(source) if marker else 0,
            "draft_section_chars": len(draft) if draft_marker else 0,
            "purpose": "final_editor" if draft_marker else "writer"}
