from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_rc76_rc51_preserves_operator_editorial_weights_across_restart(tmp_path: Path):
    db_path = tmp_path / "autopilot.sqlite3"
    code = r"""
from pathlib import Path
from telegram_autopilot.database import Database
from telegram_autopilot import rc42_policy as rc42
from telegram_autopilot import rc45_policy as rc45
from telegram_autopilot import rc46_policy as rc46
from telegram_autopilot.rc42_policy import install_rc42_policy
from telegram_autopilot.rc51_feedback import install_rc51_feedback

path = Path(DB_PATH)
install_rc42_policy()
original_parse = rc42.parse_editorial_weights
install_rc51_feedback()
assert rc42.parse_editorial_weights is original_parse
assert rc45.parse_editorial_weights is not None
assert rc46.parse_editorial_weights is not None

db = Database(path)
cid = db.save_channel(
    channel_id=None,
    name="Test channel",
    telegram_chat_id="@test",
    editorial_profile="test",
    enabled=True,
    include_source_link=False,
    poll_interval_minutes=5,
    min_publish_interval_minutes=30,
    dedupe_window_hours=72,
    max_age_hours=24,
    max_posts_per_cycle=3,
)
expected = [
    {"name": "Science", "weight": 55.0},
    {"name": "Technology", "weight": 45.0},
]
db.set_channel_editorial_weights(cid, expected)
assert rc42.parse_editorial_weights(db.get_channel(cid)) == expected

# A fresh Database() re-runs every installed _init wrapper. RC51 must not clear weights.
db2 = Database(path)
assert rc42.parse_editorial_weights(db2.get_channel(cid)) == expected
""".replace("DB_PATH", repr(str(db_path)))
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).resolve().parents[1])


def test_rc76_rc51_source_contains_no_weight_erasure_backdoor():
    source = Path("telegram_autopilot/rc51_feedback.py").read_text(encoding="utf-8")
    assert "editorial_weights_json='[]'" not in source
    assert "Database.set_channel_editorial_weights = set_channel_editorial_weights_rc51" not in source
    assert "parse_editorial_weights = no_weights" not in source
