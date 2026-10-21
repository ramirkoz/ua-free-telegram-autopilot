"""Non-mutating, privacy-preserving delivery-ledger fingerprint for operator LIVE.

A digest allows comparing two version snapshots by receipt identity rather than
misleading total counters alone. Never triggers a Telegram replay or a DB repair.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any


def delivery_integrity_snapshot(store: Any) -> dict[str, object]:
    digest = sha256()
    total = 0
    highest = 0
    with store.connect() as con:
        rows = con.execute(
            """SELECT article_id,channel_id,primary_message_id,committed_at FROM (
                  SELECT article_id,channel_id,primary_message_id,committed_at FROM publication_delivery_journal WHERE state='COMMITTED'
                  UNION ALL
                  SELECT a.article_id,a.channel_id,a.primary_message_id,a.committed_at FROM delivery_receipt_archive a
                   WHERE a.state='COMMITTED' AND NOT EXISTS
                         (SELECT 1 FROM publication_delivery_journal j WHERE j.article_id=a.article_id)
               ) ORDER BY article_id ASC"""
        )
        for row in rows:
            total += 1
            highest = max(highest, int(row["article_id"]))
            # Length-prefix fields to avoid ambiguous concatenation.
            for value in (row["article_id"], row["channel_id"], row["primary_message_id"], row["committed_at"]):
                raw = str(value or "").encode("utf-8")
                digest.update(len(raw).to_bytes(4, "big"))
                digest.update(raw)
        archived_receipts = int(con.execute(
            "SELECT COUNT(*) FROM delivery_receipt_archive WHERE state='COMMITTED'"
        ).fetchone()[0] or 0)
        published_stage = int(con.execute(
            "SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED'"
        ).fetchone()[0] or 0)
    return {
        "mode": "read_only",
        "committed_count": total,
        "archived_committed_receipts": archived_receipts,
        "committed_receipts_sha256": digest.hexdigest(),
        "max_committed_article_id": highest,
        "published_stage_count": published_stage,
        "auto_replay": False,
        "auto_restore": False,
        "comparison_note": "Compare receipt digest against preceding operator versions; a count decrease alone is not proof of lost Telegram messages.",
    }
