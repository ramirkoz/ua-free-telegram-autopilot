"""Bounded, read-only direct AI pilot. Never routes publishable copy.

Limits are conservative application admission ceilings, NOT provider plan quotas.
The operator remains responsible for using free-tier credentials.
"""
from __future__ import annotations
import time

SUPPORT_PURPOSES = frozenset({'editorial_selector', 'monitoring_selector', 'commercial_value_gate', 'value_gate'})
# Exact models observed responding in the authenticated operator probe. Gemini
# alias resolution and reasoning-only Gemma are excluded; reader approval stays paid.
SUPPORT_MODELS = {
    ('groq', 'qwen/qwen3.8-27b'): 0,
    ('groq', 'openai/gpt-oss-120b'): 1,
    ('nvidia', 'nvidia/nemotron-3-ultra-550b-a55b'): 2,
    ('cloudflare', '@cf/zai-org/glm-4.7-flash'): 3,
}
MAX_HOURLY = 8
MAX_DAILY = 60
MAX_DAILY_BYTES = 400_000
MAX_PROMPT_BYTES = 32_000


def support_slots(slots, purpose, validator, prompt, max_output_tokens):
    if (purpose not in SUPPORT_PURPOSES or validator is None or not 0 < int(max_output_tokens) <= 260
            or len(prompt.encode('utf-8')) > MAX_PROMPT_BYTES):
        return []
    return sorted((s for s in slots if (s.provider, s.model) in SUPPORT_MODELS),
                  key=lambda s: SUPPORT_MODELS[(s.provider, s.model)])


def reserve_support(store, provider, prompt, *, now=None):
    """Atomic per-provider rolling admission; counted before sending, survives restart."""
    if provider not in {p for p, _ in SUPPORT_MODELS}:
        return False
    stamp = float(time.time() if now is None else now)
    # Includes a conservative output/system framing allowance. Not token billing.
    size = len(prompt.encode('utf-8')) + 8192
    if len(prompt.encode('utf-8')) > MAX_PROMPT_BYTES:
        return False
    with store.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute('CREATE TABLE IF NOT EXISTS ai_support_admission_2364 (provider TEXT NOT NULL, sent_at REAL NOT NULL, bytes_reserved INTEGER NOT NULL)')
            con.execute('DELETE FROM ai_support_admission_2364 WHERE sent_at <= ?', (stamp-86400,))
            hour, day, used = con.execute('SELECT COALESCE(SUM(sent_at > ?),0), COUNT(*), COALESCE(SUM(bytes_reserved),0) FROM ai_support_admission_2364 WHERE provider=?', (stamp-3600, provider)).fetchone()
            if hour >= MAX_HOURLY or day >= MAX_DAILY or used + size > MAX_DAILY_BYTES:
                con.commit()
                return False
            con.execute('INSERT INTO ai_support_admission_2364 VALUES (?,?,?)', (provider,stamp,size))
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise

_VALUE_KEYS = ('novelty','consequence_or_insight','mechanism','reader_payoff','retellability','concrete_stakes','why_now')
_COMMERCIAL_KEYS = ('commercial_mechanism','consumer_behavior','creative_execution','measurable_result','strategic_transferability','why_now','general_interest','retellability','culture_signal','surprise_or_conflict','consumer_relevance')


def validate_support_response(raw, purpose):
    """Additional strict wire contract for the pilot; existing validators still run.

    Do not silently turn missing scores into zero or accept schema placeholders.
    No direct model can emit a publishable body through this route.
    """
    import json
    obj = json.loads(raw.strip())
    if not isinstance(obj, dict):
        raise ValueError('SUPPORT_2364_INVALID_OBJECT')
    reason = obj.get('reason')
    if (not isinstance(reason, str) or not reason.strip() or len(reason) > 700
            or reason.strip().casefold().strip(' .') in {'коротко','reason','причина','одне речення'}
            or reason.strip().startswith('<')):
        raise ValueError('SUPPORT_2364_INVALID_REASON')
    if purpose == 'monitoring_selector':
        if not isinstance(obj.get('event_type'), str) or any(type(obj.get(k)) is not bool for k in ('included','excluded','settled')):
            raise ValueError('SUPPORT_2364_MISSING_MONITORING_FIELDS')
    elif purpose == 'editorial_selector':
        if obj.get('decision') not in {'publish','reject'}:
            raise ValueError('SUPPORT_2364_INVALID_DECISION')
    elif purpose in {'value_gate','commercial_value_gate'}:
        keys = _VALUE_KEYS if purpose == 'value_gate' else _COMMERCIAL_KEYS
        if any(type(obj.get(k)) not in {int,float} or not 0 <= obj[k] <= 100 for k in keys):
            raise ValueError('SUPPORT_2364_MISSING_OR_INVALID_VALUE')
        flags = ('curiosity_only',) if purpose == 'value_gate' else ('shareable_to_friend','product_only')
        if any(type(obj.get(k)) is not bool for k in flags):
            raise ValueError('SUPPORT_2364_MISSING_VALUE_FLAG')
