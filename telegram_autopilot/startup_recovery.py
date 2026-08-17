from __future__ import annotations

import json

from .database import Database
from .paths import ai_state_path


def _clear_stale_model_cooldowns_once(db: Database) -> int:
    """Clear model penalties created by the pre-one-rewrite AI pipeline.

    Provider-level cooldowns (quota/auth) are preserved. The cleanup is guarded
    by app_state so later legitimate model cooldowns survive normal restarts.
    """
    key = 'rc9_one_rewrite_model_cooldowns_reset_v2'
    if db.get_state(key, '') == '1':
        return 0
    path = ai_state_path()
    removed = 0
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            state = {}
        cooldowns = state.get('cooldowns') if isinstance(state, dict) else None
        if isinstance(cooldowns, dict):
            for cooldown_key in list(cooldowns):
                if str(cooldown_key).startswith('model:'):
                    cooldowns.pop(cooldown_key, None)
                    removed += 1
            if removed:
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                temp.replace(path)
    db.set_state(key, '1')
    return removed


def recover_interrupted_work(db: Database) -> dict[str, int]:
    """Recover transient rows after a previous process exit.

    ``processing`` happens before irreversible external writes, so it is safe to
    return it to the retry queue. Telegraph/Telegram write states are quarantined
    as ``unknown`` because their remote outcome may already have succeeded.
    """
    with db.connect() as con:
        processing = int(con.execute("SELECT COUNT(*) FROM articles WHERE status='processing'").fetchone()[0] or 0)
        external = int(con.execute("SELECT COUNT(*) FROM articles WHERE status IN ('telegraph_writing','telegram_writing')").fetchone()[0] or 0)
        if processing:
            con.execute(
                """UPDATE articles SET status='retry',next_retry_at=NULL,
                last_error=CASE WHEN COALESCE(last_error,'')='' THEN 'Відновлено після перерваної локальної обробки.' ELSE last_error END
                WHERE status='processing'"""
            )
        if external:
            con.execute(
                """UPDATE articles SET status='unknown',next_retry_at=NULL,
                last_error=CASE WHEN COALESCE(last_error,'')='' THEN 'Попередній процес завершився під час зовнішньої публікації; потрібна перевірка результату.' ELSE last_error END
                WHERE status IN ('telegraph_writing','telegram_writing')"""
            )
    stale = _clear_stale_model_cooldowns_once(db)
    return {"processing_to_retry": processing, "external_to_unknown": external, "stale_model_cooldowns_removed": stale}
