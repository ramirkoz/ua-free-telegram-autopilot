from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "telegram_autopilot/v2/storage.py"
text = path.read_text(encoding="utf-8")
old = '''        con.execute(\n            """UPDATE channels SET source_attribution_mode=?\n               WHERE channel_mode='monitoring'\n                 AND source_attribution_mode='standard'\n                 AND instr(lower(name),'громад')>0""",\n            (str(SourceAttributionMode.NAMED_SOURCE),),\n        )\n'''
new = '''        # SQLite lower() is ASCII-only by default, so do the one-time legacy\n        # channel-name match in Python where Unicode casefolding is deterministic.\n        rows = con.execute(\n            "SELECT id,name,channel_mode,source_attribution_mode FROM channels"\n        ).fetchall()\n        for row in rows:\n            if str(row["channel_mode"] or "").casefold() != "monitoring":\n                continue\n            if str(row["source_attribution_mode"] or "standard") != str(SourceAttributionMode.STANDARD):\n                continue\n            if "громад" not in str(row["name"] or "").casefold():\n                continue\n            con.execute(\n                "UPDATE channels SET source_attribution_mode=? WHERE id=?",\n                (str(SourceAttributionMode.NAMED_SOURCE), int(row["id"])),\n            )\n'''
if text.count(old) != 1:
    raise SystemExit(f"expected one migration block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

for transient in (
    ROOT / "tools/rc35_unicode_migration_fix.py",
    ROOT / ".github/workflows/rc35-unicode-migration-fix.yml",
):
    if transient.exists():
        transient.unlink()

print("RC35_UNICODE_MIGRATION_FIXED")
