from __future__ import annotations

from dataclasses import dataclass

from .domain import BlockedBy, Decision, Stage
from .loghub import event
from .storage import V2Store, now_iso


@dataclass(slots=True)
class ReviewItem:
    article_id: int
    channel_id: int
    channel_name: str
    title: str
    stage: str
    blocked_by: str
    reason: str
    final_text: str
    source_name: str
    discovered_at: str


class EditorialReviewService:
    """Human review queue and local editorial-memory recorder."""

    def __init__(self, store: V2Store):
        self.store = store

    def ensure_schema(self) -> None:
        with self.store.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS editorial_actions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                    action TEXT NOT NULL,title TEXT NOT NULL DEFAULT '',
                    before_text TEXT NOT NULL DEFAULT '',after_text TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_editorial_actions_channel_time
                    ON editorial_actions(channel_id,created_at DESC,id DESC);
            """)

    def candidates(self, *, limit: int = 250) -> list[ReviewItem]:
        self.ensure_schema()
        with self.store.connect() as con:
            rows = con.execute("""
                SELECT a.id,a.channel_id,c.name channel_name,a.title,a.stage,a.blocked_by,
                       COALESCE(NULLIF(a.status_detail,''),NULLIF(a.last_error_detail,''),NULLIF(a.reject_reason,''),'') reason,
                       a.final_text,s.name source_name,a.discovered_at
                FROM articles a
                JOIN channels c ON c.id=a.channel_id
                JOIN sources s ON s.id=a.source_id
                WHERE c.channel_mode='editorial' AND a.final_text<>''
                  AND a.stage<>'PUBLISHED' AND a.decision<>'DUPLICATE'
                  AND datetime(a.discovered_at)>=datetime('now','-72 hours')
                  AND (a.stage IN ('WRITTEN','QA_PASSED','READY')
                       OR a.blocked_by IN ('QUALITY','MEDIA','CONFIG','TELEGRAM'))
                ORDER BY datetime(a.discovered_at) DESC,a.id DESC LIMIT ?
            """,(max(1,min(1000,int(limit))),)).fetchall()
        return [ReviewItem(int(r['id']),int(r['channel_id']),str(r['channel_name']),str(r['title'] or ''),
            str(r['stage'] or ''),str(r['blocked_by'] or ''),str(r['reason'] or ''),str(r['final_text'] or ''),
            str(r['source_name'] or ''),str(r['discovered_at'] or '')) for r in rows]

    def _record(self, article_id: int, action: str, *, before: str='', after: str='', detail: str='') -> None:
        row=self.store.get_article(int(article_id))
        if row is None: return
        with self.store.connect() as con:
            con.execute("""INSERT INTO editorial_actions(article_id,channel_id,action,title,before_text,after_text,detail,created_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                (int(article_id),int(row['channel_id']),str(action),str(row['title'] or ''),before,after,str(detail)[:1800],now_iso()))
        event('learning','editorial action recorded',channel_id=int(row['channel_id']),article_id=int(article_id),action=str(action))

    def edit(self, article_id: int, text: str) -> None:
        row=self.store.get_article(int(article_id))
        if row is None: raise KeyError(article_id)
        new_text=str(text or '').strip()
        if not new_text: raise ValueError('Фінальний текст не може бути порожнім')
        before=str(row['final_text'] or '')
        self.store.update_article(int(article_id),final_text=new_text,stage=str(Stage.READY),decision=str(Decision.PUBLISH),
            blocked_by=str(BlockedBy.NONE),status_detail='Погоджено редактором після ручного редагування',
            last_error_code='',last_error_detail='',next_retry_at='',ready_at=now_iso())
        self._record(article_id,'edit',before=before,after=new_text)

    def approve(self, article_id: int) -> None:
        row=self.store.get_article(int(article_id))
        if row is None: raise KeyError(article_id)
        final_text=str(row['final_text'] or '').strip()
        if not final_text: raise ValueError('Немає готового рерайту для погодження')
        self.store.update_article(int(article_id),stage=str(Stage.READY),decision=str(Decision.PUBLISH),blocked_by=str(BlockedBy.NONE),
            status_detail='Погоджено редактором вручну',last_error_code='',last_error_detail='',next_retry_at='',ready_at=now_iso())
        self._record(article_id,'approve',before=final_text,after=final_text)

    def reject(self, article_id: int, reason: str='Відхилено редактором вручну') -> None:
        row=self.store.get_article(int(article_id))
        if row is None: raise KeyError(article_id)
        final_text=str(row['final_text'] or '')
        self.store.update_article(int(article_id),stage=str(Stage.ARCHIVED),decision=str(Decision.REJECT),blocked_by=str(BlockedBy.NONE),
            reject_reason=reason,status_detail=reason,last_error_code='',last_error_detail='',next_retry_at='')
        self._record(article_id,'reject',before=final_text,detail=reason)

    def record_publish_now(self, article_id: int, result: str) -> None:
        row=self.store.get_article(int(article_id))
        text=str(row['final_text'] or '') if row is not None else ''
        self._record(article_id,'publish_now' if result=='PUBLISHED' else 'publish_attempt',before=text,after=text,detail=result)
