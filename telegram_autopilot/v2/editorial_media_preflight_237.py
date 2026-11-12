"""Preflight required source-owned media AFTER selection, BEFORE paid writer.

This is the existing publication media safety gate shifted earlier for eligible
editorial stories. It must never synthesize imagery or degrade to text-only.
"""
from __future__ import annotations

from typing import Any

from .domain import ChannelMode
from .loghub import event


class MediaPreflightPending(RuntimeError):
    pass


def ensure_media_for_editorial_writer(store: Any, channel: Any, article: Any) -> Any:
    if channel.mode != ChannelMode.EDITORIAL or channel.policy.normalized_media_policy() != 'required':
        return article
    from .media_pipeline import build_publication_media_bundle
    prepared=build_publication_media_bundle(channel, article)
    if prepared.count:
        return article
    from .publisher import Publisher
    source_url=str(article['canonical_source_url'] or article['source_url'] or '')
    # Publisher's existing exact-story verification, no random stock searches.
    updated, bundle, outcome=Publisher(store)._recover_missing_source_media(
        channel, article, source_url, excluded_urls=set())
    if not bundle.count:
        event('media','2.3.27 editorial media preflight deferred before paid writer',
              channel_id=int(channel.id),article_id=int(article['id']),
              outcome=outcome, paid_writer_skipped=True,
              no_media_policy_bypass=True)
        raise MediaPreflightPending(f'MEDIA_PREWRITE: {outcome}')
    event('media','2.3.27 editorial media validated before writer',
          channel_id=int(channel.id),article_id=int(article['id']),
          media_count=bundle.count,outcome=outcome)
    return updated
