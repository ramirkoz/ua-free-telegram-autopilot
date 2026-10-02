from __future__ import annotations

from dataclasses import dataclass

from .domain import BlockedBy, Decision, Stage
from .loghub import event
from .storage import V2Store, now_iso
from .editorial_state import ensure_editorial_state_schema, preserve_current_rewrite, record_rewrite_revision


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
    """Human review queue and local editorial-memory recorder.

    RC100 queue invariant: once a material has a completed rewrite (``final_text``),
    it remains visible to the human editor until it is actually published or the
    editor explicitly rejects it. Automatic selector rejection, semantic duplicate
    detection, media/quality/config/Telegram blockers, channel mode and age are not
    allowed to silently remove a rewritten material from review.
    """

    def __init__(self, store: V2Store):
        self.store = store

    def ensure_schema(self) -> None:
        ensure_editorial_state_schema(self.store)

    def candidates(self, *, limit: int = 250) -> list[ReviewItem]:
        """Return every unresolved rewrite that has not reached the air.

        A system decision is not a human editorial decision. In particular,
        ``DUPLICATE`` and ``REJECT`` remain reviewable when a rewrite already exists.
        The only terminal states for this queue are a real ``PUBLISHED`` stage or an
        explicit latest human ``reject`` action.
        """
        self.ensure_schema()
        with self.store.connect() as con:
            rows = con.execute("""
                SELECT a.id,a.channel_id,c.name channel_name,a.title,a.stage,a.blocked_by,
                       COALESCE(NULLIF(a.status_detail,''),NULLIF(a.last_error_detail,''),NULLIF(a.reject_reason,''),'') reason,
                       a.final_text,s.name source_name,a.discovered_at
                FROM articles a
                JOIN channels c ON c.id=a.channel_id
                JOIN sources s ON s.id=a.source_id
                WHERE TRIM(COALESCE(a.final_text,''))<>''
                  AND a.stage<>'PUBLISHED'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM editorial_actions ea
                      WHERE ea.article_id=a.id
                        AND ea.id=(
                            SELECT MAX(ea2.id)
                            FROM editorial_actions ea2
                            WHERE ea2.article_id=a.id
                        )
                        AND ea.action IN ('approve','edit','reject')
                  )
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

    @staticmethod
    def _unknown_delivery(row) -> bool:
        return str(row["last_error_code"] or "").strip().upper() == "TELEGRAM_OUTCOME_UNKNOWN"

    def _guard_unknown_delivery(self, row) -> None:
        if self._unknown_delivery(row):
            raise ValueError(
                "Telegram не підтвердив результат попередньої відправки. "
                "Не можна погоджувати або редагувати матеріал для повторної публікації, "
                "доки оператор не підтвердить, що поста в каналі немає."
            )

    def edit(self, article_id: int, text: str) -> None:
        row=self.store.get_article(int(article_id))
        if row is None: raise KeyError(article_id)
        self._guard_unknown_delivery(row)
        new_text=str(text or '').strip()
        if not new_text: raise ValueError('Фінальний текст не може бути порожнім')
        before=str(row['final_text'] or '')
        preserve_current_rewrite(self.store, int(article_id), origin='editor', reason='before_manual_edit')
        self.store.update_article(int(article_id),final_text=new_text,stage=str(Stage.READY),decision=str(Decision.PUBLISH),
            blocked_by=str(BlockedBy.NONE),status_detail='Погоджено редактором після ручного редагування',
            last_error_code='',last_error_detail='',next_retry_at='',ready_at=now_iso())
        record_rewrite_revision(self.store, int(article_id), new_text, origin='editor', reason='manual_edit_approved')
        self._record(article_id,'edit',before=before,after=new_text)

    def approve(self, article_id: int) -> None:
        row=self.store.get_article(int(article_id))
        if row is None: raise KeyError(article_id)
        self._guard_unknown_delivery(row)
        final_text=str(row['final_text'] or '').strip()
        if not final_text: raise ValueError('Немає готового рерайту для погодження')
        preserve_current_rewrite(self.store, int(article_id), origin='editor', reason='manual_approve')
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
