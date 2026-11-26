"""Explicit, isolated comparison of a direct AI writer with stored published text.

Not imported by runtime; no Telegram, paid OpenRouter, promotion or state writes.
Use only on public-source articles with an operator-approved provider/account.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from ..secrets_store import load_secrets_from_files
from .domain import Decision
from .editorial import EditorialEngine, EditorialOutcome, prepublish_quality_issues
from .provider_api import gemini_generate, openai_compatible_chat
from .storage import V2Store

MODELS = {
    'gemini': ('gemini-3.5-flash',),
    'nvidia': ('nvidia/nemotron-3-ultra-550b-a55b',),
    'groq': ('openai/gpt-oss-120b', 'qwen/qwen3.8-27b'),
    'cloudflare': ('@cf/google/gemma-4-26b-a4b-it', '@cf/zai-org/glm-4.7-flash'),
}


class ReadOnlyStore(V2Store):
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        try:
            yield con
        finally:
            con.close()

    def transaction(self):
        raise RuntimeError('Trial database is read-only')

    def initialize(self):
        raise RuntimeError('Trial database is read-only')


class _WriterCaptured(Exception):
    pass


class CaptureWriter:
    """Stop at the FIRST writer call, before AI or final editing can occur."""
    def __init__(self):
        self.prompt = ''
        self.validator = None
        self.max_output_tokens = 0

    def run(self, prompt, *, validator, max_output_tokens, purpose, **kwargs):
        if purpose != 'writer' or self.prompt:
            raise RuntimeError('Unexpected trial stage')
        self.prompt = prompt
        self.validator = validator
        self.max_output_tokens = max_output_tokens
        raise _WriterCaptured()


def capture_writer(store, channel, article):
    gateway = CaptureWriter()
    try:
        EditorialEngine(store, gateway).write(
            channel, article, EditorialOutcome(decision=Decision.PUBLISH,
                angle='Головний підтверджений факт із джерела')
        )
    except _WriterCaptured:
        return gateway
    raise RuntimeError('No production writer prompt captured')


def direct_reply(provider, model, cfg, writer):
    if model not in MODELS.get(provider, ()):
        raise ValueError('Unreviewed or paid route is not allowed in this trial')
    kw = dict(model=model, prompt=writer.prompt, max_output_tokens=writer.max_output_tokens,
              timeout_seconds=35, exact_model=True)
    if provider == 'gemini':
        return gemini_generate(api_key=cfg.gemini_api_key, **kw)
    key = {'nvidia':cfg.nvidia_api_key, 'groq':cfg.groq_api_key,
           'cloudflare':cfg.cloudflare_api_token}[provider]
    return openai_compatible_chat(provider, api_key=key, account_id=cfg.cloudflare_account_id, **kw)


def trial_article(store, cfg, provider, model, article_id):
    article = store.get_article(article_id)
    if article is None or not article['published_at'] or not article['final_text'] or not article['raw_text']:
        raise ValueError('Select a published article with stored source and final text')
    channel = store.get_channel(article['channel_id'])
    if channel is None:
        raise ValueError('Channel not found')
    row = {'article_id':article_id, 'channel':channel.name, 'source_url':article['source_url'],
           'source_title':article['title'], 'source_text':article['raw_text'],
           'baseline_final':article['final_text'], 'provider':provider, 'requested_model':model,
           'qa_pass':False, 'candidate':'', 'status':'not_run'}
    start = time.monotonic()
    try:
        writer = capture_writer(store, channel, article)
        reply = direct_reply(provider, model, cfg, writer)
        row.update(candidate=reply.text, actual_model=reply.model,
                   input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)
        if reply.model != model:
            raise ValueError('Returned model identity differs from requested model')
        writer.validator(reply.text)
        issues = prepublish_quality_issues(channel, article, reply.text)
        if issues:
            row.update(status='qa_rejected', qa_issues=list(issues))
        else:
            row.update(status='manual_review_required', qa_pass=True)
    except Exception as exc:
        # Do not copy provider error envelopes or credentials into the report.
        row.update(status='qa_rejected' if row['candidate'] else 'trial_failed',
                   error_type=type(exc).__name__)
    row['elapsed_seconds'] = round(time.monotonic()-start, 2)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path.cwd()/'Data')
    parser.add_argument('--provider', required=True, choices=tuple(MODELS))
    parser.add_argument('--model', required=True)
    parser.add_argument('--article', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--confirm-direct-api', action='store_true', help='Confirm source data may be sent and account quota/billing checked')
    args = parser.parse_args(argv)
    ids = list(dict.fromkeys(args.article))
    if not args.confirm_direct_api or len(ids)>9 or any(x<=0 for x in ids) or args.model not in MODELS[args.provider]:
        parser.error('Explicit API confirmation, reviewed model and 1–9 positive article IDs required')
    data = args.data.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(data):
        parser.error('Output must be outside Data')
    if output.exists():
        parser.error('Output already exists')
    store = ReadOnlyStore(data/'telegram_autopilot_v2.sqlite3')
    # This load is strictly read-only and will never create a replacement key.
    cfg = load_secrets_from_files(data/'secrets.key', data/'secrets.secure')
    report = {'version':'2.3.61','mode':'manual_writer_comparison_only','auto_promotion':False,
              'warning':'Stored baseline is the final published text; trial is a draft with current policy and reconstructed angle. QA pass is NOT editorial approval or evidence of equivalent cost/quality. Direct accounts may have their own billing.', 'results':[]}
    for aid in ids:
        try:
            report['results'].append(trial_article(store,cfg,args.provider,args.model,aid))
        except Exception as exc:
            report['results'].append({'article_id':aid,'status':'trial_failed','error_type':type(exc).__name__})
    with output.open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(str(output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
