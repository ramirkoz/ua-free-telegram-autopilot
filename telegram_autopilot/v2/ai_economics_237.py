"""2.3.27: READ-ONLY economics for actual OpenRouter charges vs Telegram receipts.

Do not equate OpenRouter account's 30-day spend with Autopilot's calendar month.
Historic AI rows lack article identity; report them as unattributed, not zero.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from .loghub import event

# Scoped to the channel worker, never inherited by provider-health threads.
_ACTIVE_ARTICLE: ContextVar[tuple[int,int]] = ContextVar('autopilot_ai_article_237',default=(0,0))


@contextmanager
def ai_article_scope(channel_id: int, article_id: int):
    marker = _ACTIVE_ARTICLE.set((int(channel_id),int(article_id)))
    try:
        yield
    finally:
        _ACTIVE_ARTICLE.reset(marker)


def current_ai_article() -> tuple[int,int]:
    return _ACTIVE_ARTICLE.get()


def _local_day(value: str) -> str:
    dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo('Europe/Kyiv')).date().isoformat()
    except Exception:
        # An embedded Windows build may lack tzdata; never shift dates based
        # on arbitrary server defaults.  As of Nov 2026 Kyiv is UTC+2.
        return dt.astimezone(timezone(timedelta(hours=2))).date().isoformat()


def _round_cost(value: Any) -> float:
    return round(max(0.0,float(value or 0.0)),6)


def _delivery_rows(con) -> list[Any]:
    return con.execute('''
      SELECT article_id,channel_id,committed_at FROM publication_delivery_journal
       WHERE state='COMMITTED' AND committed_at<>''
      UNION ALL
      SELECT a.article_id,a.channel_id,a.committed_at FROM delivery_receipt_archive a
       WHERE a.state='COMMITTED' AND a.committed_at<>''
         AND NOT EXISTS(SELECT 1 FROM publication_delivery_journal p WHERE p.article_id=a.article_id)
    ''').fetchall()


def economics_snapshot(store: Any, *, now: datetime|None = None) -> dict[str,Any]:
    current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff=current-timedelta(hours=24)
    trailing=current-timedelta(days=5)
    # UTC timestamp supplied rather than SQLite NOW makes tests deterministic.
    with store.connect() as con:
        usage=con.execute('''
           SELECT created_at,provider,model,purpose,channel_id,article_id,
                  actual_openrouter_usd FROM ai_usage_events
            WHERE datetime(created_at)>=datetime(?) AND datetime(created_at)<=datetime(?)
        ''',(trailing.isoformat(),current.isoformat())).fetchall()
        deliveries=_delivery_rows(con)
        states={int(row['id']):str(row['decision']) for row in
                con.execute('SELECT id,decision FROM articles WHERE id IN '
                            '(SELECT DISTINCT article_id FROM ai_usage_events '
                            "WHERE article_id>0 AND datetime(created_at)>=datetime(?))",
                            (cutoff.isoformat(),)).fetchall()}
    delivered_24=set()
    daily_delivered: dict[str,set[int]]=defaultdict(set)
    posted_by_channel: dict[str,set[int]]=defaultdict(set)
    for row in deliveries:
        try: at=datetime.fromisoformat(str(row['committed_at']).replace('Z','+00:00'))
        except ValueError: continue
        if at.tzinfo is None: at=at.replace(tzinfo=timezone.utc)
        if at>current: continue
        day=_local_day(str(row['committed_at']))
        article_id=int(row['article_id'])
        daily_delivered[day].add(article_id)
        if at>=cutoff:
            delivered_24.add(article_id)
            posted_by_channel[str(row['channel_id'])].add(article_id)
    cost_24=0.0; calls_24=0; unassigned=0.0
    by_purpose:dict[str,float]=defaultdict(float)
    by_model:dict[str,float]=defaultdict(float)
    by_channel:dict[str,float]=defaultdict(float)
    by_article:dict[int,float]=defaultdict(float)
    calendar:dict[str,float]=defaultdict(float)
    for row in usage:
        if str(row['provider'])!='openrouter': continue
        try:at=datetime.fromisoformat(str(row['created_at']).replace('Z','+00:00'))
        except ValueError:continue
        if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
        amount=float(row['actual_openrouter_usd'] or 0.0)
        day=_local_day(str(row['created_at']))
        calendar[day]+=amount
        if at<cutoff:continue
        calls_24+=1; cost_24+=amount
        by_model[str(row['model'])]+=amount
        by_purpose[str(row['purpose'])]+=amount
        cid=int(row['channel_id'] or 0)
        aid=int(row['article_id'] or 0)
        if cid>0 and aid>0:
            by_channel[str(cid)]+=amount
            by_article[aid]+=amount
        else:
            unassigned+=amount
    unit=(round(cost_24/len(delivered_24),6) if delivered_24 else None)
    # 3 completed local calendar days, not today nor rolling-24h fiction.
    today=_local_day(current.isoformat())
    days=sorted(d for d in set(calendar)|set(daily_delivered) if d<today)[-3:]
    daily=[{'date':day,'actual_openrouter_usd':_round_cost(calendar.get(day,0)),
            'committed_posts':len(daily_delivered.get(day,set())),
            'usd_per_post':round(calendar[day]/len(daily_delivered[day]),6)
                if daily_delivered.get(day) else None}
           for day in days]
    # Pending drafts are not 'waste': published media gate may recover later.
    wasted_rejected=sum(val for aid,val in by_article.items() if states.get(aid)=='REJECT')
    spending_on_undelivered=sum(val for aid,val in by_article.items() if aid not in delivered_24)
    alerts=[]
    if unit is not None and unit>0.02:alerts.append('COST_PER_DELIVERED_GT_0_02')
    if cost_24>1.50:alerts.append('COST_LAST_24H_GT_1_50')
    if cost_24>0 and not delivered_24:alerts.append('SPEND_WITH_ZERO_DELIVERIES')
    if len(daily)==3 and all(r['committed_posts']>0 for r in daily):
        baseline=sum(r['usd_per_post'] for r in daily)/3
        if unit is not None and baseline>0 and unit>baseline*1.5:
            alerts.append('UNIT_COST_GT_3DAY_BASELINE_50_PERCENT')
    return {
        'scope':'operator_read_only_economics_237',
        'hours':24,'actual_openrouter_usd':_round_cost(cost_24),
        'openrouter_calls':calls_24,'committed_24h':len(delivered_24),
        'usd_per_committed_post':unit,
        'committed_by_channel':{cid:len(ids) for cid,ids in posted_by_channel.items()},
        'charged_by_channel_attributed':{k:_round_cost(v) for k,v in by_channel.items()},
        'charged_unattributed_legacy_or_non_article':_round_cost(unassigned),
        'charged_by_purpose':{k:_round_cost(v) for k,v in by_purpose.items()},
        'charged_by_model':{k:_round_cost(v) for k,v in by_model.items()},
        'rejected_article_cost_confirmed':_round_cost(wasted_rejected),
        'charged_to_articles_not_delivered_in_24h':_round_cost(spending_on_undelivered),
        'calendar_days':daily,'alerts':alerts,
        'quality_approved_count':None,
        'note':'Historic usage lacks article IDs; delivery is not editorial approval; uncommitted drafts may publish later',
    }
