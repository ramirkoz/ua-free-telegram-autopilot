#!/usr/bin/env python3
"""Strict, READ-ONLY 2.3.30 source-gate replay against 1472 owner decisions.

The 11 Nov ProductVault editorial corpus file documents 1472 decisions but
does NOT contain their rows. This command requires the four original operator
workbooks to first be consolidated into JSONL without inventing any label.

Each JSONL row: {"article_id":123,"channel_id":1,"selected":true,
"source_workbook":"RETURNED_FILE_NAME.xlsx"}.
Only explicit ☑ is selected=true; finalized empty/☐ is false.
The script compares source-only policy veto with actual owner choices. It does
not run AI or Telegram, and cannot by itself certify writing/media quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

EXPECTED = {1: 505, 2: 295, 3: 672}
EXPECTED_POSITIVE = {1: 352, 2: 146, 3: 332}
EXPECTED_NEGATIVE = {1: 153, 2: 149, 3: 340}


def evaluate(db_path: Path, labels_path: Path) -> dict:
    if not db_path.is_file() or not labels_path.is_file():
        raise ValueError("NO_GO: the operator SQLite and authentic 1472 label JSONL are both required")
    records = {}
    originals = set()
    for i, line in enumerate(labels_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        article_id = int(obj["article_id"])
        channel = int(obj["channel_id"])
        selected = obj["selected"]
        original_file = str(obj.get("source_workbook") or "").strip()
        if channel not in EXPECTED or type(selected) is not bool or not original_file:
            raise ValueError(f"NO_GO: invalid label/provenance on JSONL row {i}")
        key = (channel, article_id)
        if key in records:
            if records[key] != selected:
                raise ValueError(f"NO_GO: contradictory operator labels: {key}")
            raise ValueError(f"NO_GO: repeated label not independently unique: {key}")
        records[key] = selected
        originals.add(original_file)

    count = Counter(ch for ch, _ in records)
    positives = Counter(ch for (ch, _), value in records.items() if value)
    negatives = Counter(ch for (ch, _), value in records.items() if not value)
    if (dict(count) != EXPECTED or dict(positives) != EXPECTED_POSITIVE
            or dict(negatives) != EXPECTED_NEGATIVE or len(originals) != 4):
        raise ValueError(
            "NO_GO: expected exactly four authentic workbooks / 1472 unique labels, "
            f"got files={len(originals)}, count={dict(count)}, yes={dict(positives)}, no={dict(negatives)}"
        )

    from telegram_autopilot.v2.editorial_audience_2330 import editorial_audience_source_reason_2330
    from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322
    matrix = {str(ch): Counter() for ch in EXPECTED}
    suspicious = []
    db_uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(db_uri, uri=True) as con:
        con.row_factory = sqlite3.Row
        for (ch, article_id), selected in sorted(records.items()):
            article = con.execute(
                "SELECT id,title,raw_text,source_url FROM articles WHERE id=? AND channel_id=?",
                (article_id, ch),
            ).fetchone()
            if article is None:
                raise ValueError(f"NO_GO: operator article missing from read-only source DB: {ch}/{article_id}")
            role = "science" if ch == 1 else "creative" if ch == 2 else ""
            reason = (editorial_audience_source_reason_2330(role, article)
                      if ch in (1, 2) else no_announcement_reason_2322(article))
            item = matrix[str(ch)]
            item["total"] += 1
            item["owner_yes" if selected else "owner_no"] += 1
            if reason:
                item["source_veto_yes" if selected else "source_veto_no"] += 1
                if selected:
                    suspicious.append({"channel_id":ch,"article_id":article_id,"reason":reason,
                                       "policy_conflict":ch==3 and reason.startswith("MONITORING_")})
    # Historic GR-☑ announcements conflict with later binding no-ads policy.
    # Report them separately, never silently relabel or let them bypass safety.
    bad_positives = [x for x in suspicious if x["channel_id"] in (1, 2)]
    return {
        "schema":"editorial_source_gate_replay_2330",
        "source":"four-authentic-owner-worksheets",
        "labels":len(records),
        "workbooks":sorted(originals),
        "by_channel":{k:dict(v) for k,v in matrix.items()},
        "owner_yes_source_veto":suspicious,
        "go_for_source_gate_only":len(bad_positives)==0,
        "release_accepted":False,
        "release_note":"This is source-only; actual AI selectors, writing, media ownership, dedupe, backlog, LIVE post review are separate mandatory gates.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db",required=True,type=Path)
    ap.add_argument("--labels-jsonl",required=True,type=Path)
    ap.add_argument("--output",type=Path)
    args = ap.parse_args()
    try:
        result=evaluate(args.db,args.labels_jsonl)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(f"NO_GO: {exc}",file=sys.stderr)
        return 2
    rendered=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        args.output.write_text(rendered+"\n",encoding="utf-8")
    else:
        print(rendered)
    return 0 if result["go_for_source_gate_only"] else 1


if __name__=="__main__":
    raise SystemExit(main())
