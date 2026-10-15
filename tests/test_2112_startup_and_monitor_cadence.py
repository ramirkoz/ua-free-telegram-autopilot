"""Regression for operator-reported 2.1.11 first-run blocker and 30m policy."""
from pathlib import Path
from telegram_autopilot.v2.storage import V2Store


def test_release_launcher_never_blocks_on_codex():
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    script = workflow.read_text(encoding="utf-8")
    marker = "if os.path.basename(sys.executable).casefold() == 'ua_free_telegram_autopilot.exe':"
    section = script.split(marker, 1)[1].split("os._exit(int(main() or 0))", 1)[0]
    assert "_first_run_setup()" not in section.split("if os.environ.get('UA_FREE_CODEX_BOOTSTRAP_ONLY', '') == '1':")[0]
    assert "from telegram_autopilot.v2.main import main" in section
    assert "if os.environ.get('UA_FREE_CODEX_BOOTSTRAP_ONLY', '') == '1':" in section


def test_monitoring_cadence_migration_changes_only_old_default(tmp_path):
    store = V2Store(tmp_path / "monitor.sqlite3")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,poll_interval_minutes,created_at,updated_at) VALUES(1,'Monitor','@monitor','monitoring',15,'t','t')")
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,poll_interval_minutes,created_at,updated_at) VALUES(2,'Editor','@editor','editorial',15,'t','t')")
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,poll_interval_minutes,created_at,updated_at) VALUES(3,'Special','@special','monitoring',45,'t','t')")
        con.execute("DELETE FROM meta WHERE key='v2112_monitoring_30m_v1'")
        V2Store._ensure_v2112_monitoring_poll_interval(con)
        got = con.execute("SELECT id,poll_interval_minutes FROM channels ORDER BY id").fetchall()
        assert [(v[0], v[1]) for v in got] == [(1,30),(2,15),(3,45)]
        V2Store._ensure_v2112_monitoring_poll_interval(con)
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 30


def test_monitoring_edit_rejects_simultaneously_closed_and_restored_road():
    from telegram_autopilot.v2.editorial import _monitoring_grounding_blockers
    article = {"title": "Дорожні роботи", "raw_text": "О 14:00 проїзд перекрили. О 15:00 рух відновили."}
    bad = "Бульвар тимчасово перекритий. Рух уже відновлено."
    issues = _monitoring_grounding_blockers(article, bad)
    assert any("фази події" in issue for issue in issues)
    good = "Рух бульваром відновлено."
    assert not any("фази події" in issue for issue in _monitoring_grounding_blockers(article, good))
