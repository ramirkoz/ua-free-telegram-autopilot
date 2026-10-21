"""Consistent, allowlisted SQLite diagnostics, not a restorable Data backup."""
from __future__ import annotations
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXPORT_TABLES={
 "channels":("id","name","enabled","channel_mode","editorial_profile","min_publish_interval_minutes","publish_start","publish_end","max_age_hours"),
 "sources":("id","channel_id","kind","name","url","enabled","priority","last_checked_at"),
 "articles":("id","channel_id","source_id","external_id","title","source_url","canonical_source_url","raw_text","source_published_at","discovered_at","stage","decision","blocked_by","status_detail","reject_reason","duplicate_of","event_key","event_summary","editorial_category","editorial_value_score","draft_text","final_text","ai_provider","ai_model","ready_at","published_at","telegram_message_id","telegram_media_count","last_error_code","retry_count","next_retry_at"),
 "jobs":("id","article_id","channel_id","job_type","state","priority","available_at","attempts","error_code","created_at","updated_at"),
 "publication_delivery_journal":("article_id","channel_id","state","mode","complete","expected_media_count","media_count","primary_message_id","message_ids_json","attempt_count","prepared_at","sending_at","acknowledged_at","committed_at","updated_at"),
 "delivery_receipt_archive":("article_id","channel_id","state","mode","complete","expected_media_count","media_count","primary_message_id","message_ids_json","attempt_count","prepared_at","sending_at","acknowledged_at","committed_at","updated_at","archived_at"),
 "editorial_actions":("id","article_id","channel_id","action","title","created_at"),
 "rewrite_revisions":("id","article_id","channel_id","revision","origin","reason","text","created_at"),
}

def export_operator_data_snapshot(db_path:Path,output:Path)->dict[str,object]:
    """Use online backup for transaction consistency; export only explicitly allowed fields."""
    db_path,output=Path(db_path),Path(output)
    if not db_path.is_file(): raise FileNotFoundError(db_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    counts={}
    with tempfile.TemporaryDirectory(prefix="autopilot-private-backup-") as td:
        private=Path(td)/"source.sqlite3"
        candidate=Path(td)/"diagnostics.sqlite3"
        with sqlite3.connect(str(db_path),timeout=30) as source:
            with sqlite3.connect(str(private),timeout=30) as backup:
                source.backup(backup,pages=256,sleep=0.05)
        with sqlite3.connect(str(private)) as original,sqlite3.connect(str(candidate)) as safe:
            original.row_factory=sqlite3.Row
            safe.execute("PRAGMA journal_mode=DELETE")
            for table,allowed in EXPORT_TABLES.items():
                existing={str(r[1]) for r in original.execute(f'PRAGMA table_info("{table}")')}
                if not existing: continue
                columns=[n for n in allowed if n in existing]
                if not columns: continue
                quoted=",".join('"'+n+'"' for n in columns)
                safe.execute('CREATE TABLE "'+table+'" ('+','.join('"'+n+'"' for n in columns)+')')
                rows=original.execute(f'SELECT {quoted} FROM "{table}"')
                marks=",".join("?" for _ in columns)
                query=f'INSERT INTO "{table}" ({quoted}) VALUES ({marks})'
                count=0
                for batch in iter(lambda:rows.fetchmany(500),[]):
                    safe.executemany(query,(tuple(r) for r in batch))
                    count+=len(batch)
                counts[table]=count
            safe.execute('CREATE TABLE export_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            safe.executemany('INSERT INTO export_metadata (key,value) VALUES (?,?)',[
                ("type","sanitized_analysis_snapshot"),
                ("schema","autopilot-operator-data-v1"),
                ("generated_at",datetime.now(timezone.utc).isoformat()),
                ("restorable","false"),
                ("redaction","allowlist_only_no_credentials_secrets_settings_or_error_bodies"),
            ])
            safe.commit()
            assert safe.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        with tempfile.NamedTemporaryFile(dir=output.parent,prefix=".snapshot.",suffix=".sqlite3",delete=False) as dest:
            staging=Path(dest.name)
        try:
            os.chmod(staging,0o600)
            with sqlite3.connect(str(candidate)) as source,sqlite3.connect(str(staging)) as target:
                source.backup(target)
                assert target.execute("PRAGMA quick_check").fetchone()[0]=="ok"
            os.replace(staging,output)
        finally:
            staging.unlink(missing_ok=True)
    return {"rows":counts,"size_bytes":output.stat().st_size,"path":str(output)}
