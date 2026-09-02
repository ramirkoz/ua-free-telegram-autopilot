from __future__ import annotations

import json, logging, re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .models import Decision

LOG=logging.getLogger('telegram_autopilot.rc62')
_INSTALLED=False
_PREV={}
QUIET=(0,7)
CTRL_GAP,MARKETING_GAP=60,90
CTRL_CAP,MARKETING_CAP=12,8


def _v(row: Mapping[str,Any]|Any,key:str,default:Any='')->Any:
    try: value=row[key]
    except Exception: value=getattr(row,key,default)
    return default if value is None else value


def _marketing(policy:Any)->bool:
    text=' '.join(str(getattr(policy,k,'') or '') for k in ('purpose','audience','selection_rules','rejection_rules','positive_examples','negative_examples','extra_instructions','selector_extra_prompt')).casefold()
    return sum(t in text for t in ('продано','реклам','бренд','marketing','advertis','campaign','creator economy'))>=2


def _policy(db:Any,cid:int,channel:Any|None=None):
    try: return db.rc59_get_channel_policy(int(cid))
    except Exception:
        from .rc59_universal_policy import default_policy
        return default_policy(channel)


def _is_marketing_channel(db:Any,cid:int,channel:Any|None=None)->bool:
    return _marketing(_policy(db,cid,channel))


def score_feedback(article:Any,rows:list[Any]):
    from . import rc51_feedback as rc51, rc58_editorial_rebuild as rc58
    base=_PREV['feedback'](article,rows)
    kind='ctrlua'; db=rc51._ACTIVE_DB; cid=int(_v(article,'channel_id',0) or 0)
    if db is not None and cid and _is_marketing_channel(db,cid): kind='marketing'
    sem,pos,neg=rc58.semantic_editor_adjustment(article,rows,kind)
    return rc51.FeedbackScore(float(base.score)*.45+sem,float(base.positive)*.45+pos,float(base.negative)*.45+neg,bool(base.hard_suppress),int(base.matched_article_id),float(base.matched_similarity),float(base.matched_age_hours),int(base.rated_posts))


def selector_prompt(policy:Any,article:Any,*,channel_id:int=0)->str:
    base=_PREV['selector_prompt'](policy,article,channel_id=channel_id)
    try:
        from . import rc59_universal_policy as rc59
        s=score_feedback(article,rc59._feedback_rows(int(channel_id)))
        note=(f'RC62 SEMANTIC EDITOR SIGNAL: score={s.score:+.2f}; positive={s.positive:.2f}; negative={s.negative:.2f}. '
              "Це м'який сигнал із 👍/👎, не факт SOURCE і не автоматичне рішення. Сильний мінус означає: схожі теми редактор частіше не хотів; публікуй лише якщо ця історія має явно сильніший самостійний гачок. Сильний плюс дає помірну перевагу. 🔥 тут не враховується.")
    except Exception: note='RC62 SEMANTIC EDITOR SIGNAL: недоступний.'
    return base+'\n\n'+note


def _parse_marketing(raw:str)->dict[str,Any]:
    from . import rc59_universal_policy as rc59
    base=rc59._parse_selector(raw); text=re.sub(r'^```(?:json)?\s*|\s*```$','',str(raw or '').strip(),flags=re.I)
    a,b=text.find('{'),text.rfind('}')
    if a<0 or b<=a: raise ValueError('RC62 selector: invalid JSON')
    obj=json.loads(text[a:b+1])
    sc=lambda n:max(0,min(100,int(float(obj.get(n,0) or 0))))
    base.update(human_interest_score=sc('human_interest_score'),creative_surprise_score=sc('creative_surprise_score'),marketing_mechanic_score=sc('marketing_mechanic_score'),friend_share_score=sc('friend_share_score'),non_marketer_hook=' '.join(str(obj.get('non_marketer_hook') or '').split())[:500])
    return base


def _enforce_marketing_interest(p:dict[str,Any])->dict[str,Any]:
    p=dict(p)
    if p.get('decision')!='publish': return p
    h,c,m,f=(int(p.get(k,0) or 0) for k in ('human_interest_score','creative_surprise_score','marketing_mechanic_score','friend_share_score'))
    if not ((h>=72 and f>=68 and c>=58 and m>=52) or (h>=80 and f>=72 and m>=58)):
        p.update(decision='reject',angle='',reason=f'RC62 HUMAN_INTEREST_REJECT: професійно релевантно, але недостатньо цікаво широкому читачеві (human={h}, share={f}, creative={c}, mechanic={m}).')
    return p


def run_selector(policy:Any,article:Any,*,channel_id:int=0):
    if not _marketing(policy): return _PREV['selector'](policy,article,channel_id=channel_id)
    from .ai_router import run_ai
    base=selector_prompt(policy,article,channel_id=channel_id)
    prompt=base+'''\n\nRC62 HUMAN-INTEREST GATE ДЛЯ ШИРОКОЇ АУДИТОРІЇ:
Це НЕ професійний журнал для рекламників і НЕ добірка Cannes Lions. Гарна кампанія ще не означає гарну історію.
Оціни 0..100: human_interest_score (цікаво не-маркетологу), creative_surprise_score (неочікуваність ідеї), marketing_mechanic_score (що саме зробили для впливу на увагу/бажання/поведінку), friend_share_score (чи хочеться переказати знайомому).
Ключовий тест: прибери назву агентства, фестиваль, професійний жаргон і ярлик «кампанія». Якщо історія перестає бути цікавою — REJECT.
Volvo-подібний парадокс/людський наслідок — сильний плюс. Звичайна колаборація із зіркою, AR-лінзи, mural чи стилізація під відому гру самі по собі НЕ достатні. Поведінкові історії на кшталт «візок/інтерфейс змусив витрачати більше» можуть пройти без фестивального creative.
Поверни ТІЛЬКИ JSON: {"decision":"publish" або "reject","fit_score":0..100,"reason":"коротко","angle":"кут","topic_tags":["2–5 тегів"],"human_interest_score":0..100,"creative_surprise_score":0..100,"marketing_mechanic_score":0..100,"friend_share_score":0..100,"non_marketer_hook":"гачок"}'''
    def validator(x:str)->None: _parse_marketing(x)
    r=run_ai(prompt,validator=validator,max_output_tokens=420,local_prompt=prompt,local_max_output_tokens=440,cloud_timeout_seconds=26,local_timeout_seconds=45,task_timeout_seconds=75,local_repair=False,suppress_provider_on_quota=False,allowed_providers={'codex','gemini','groq','nvidia','cloudflare','local'})
    return r,_enforce_marketing_interest(_parse_marketing(r.text))


def _dt(x:Any)->datetime|None:
    try: d=datetime.fromisoformat(str(x or '').replace('Z','+00:00'))
    except Exception: return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def _times(db:Any,cid:int)->list[datetime]:
    try:
        with db.connect() as con: rows=con.execute("SELECT published_at FROM articles WHERE channel_id=? AND status='published' AND published_at<>'' ORDER BY published_at DESC LIMIT 100",(cid,)).fetchall()
        return [d for r in rows if (d:=_dt(r[0])) is not None]
    except Exception: return []


def gap_ok(service:Any,channel:Any)->bool:
    now=datetime.now().astimezone()
    if QUIET[0]<=now.hour<QUIET[1]: return False
    marketing=_is_marketing_channel(service.db,int(channel.id),channel); times=_times(service.db,int(channel.id))
    gap=max(int(getattr(channel,'min_publish_interval_minutes',0) or 0),MARKETING_GAP if marketing else CTRL_GAP)
    cap=MARKETING_CAP if marketing else CTRL_CAP
    if sum(d.astimezone().date()==now.date() for d in times)>=cap: return False
    if times:
        newest=max(times).astimezone(now.tzinfo)
        if now-newest<timedelta(minutes=gap): return False
        if sum(now-d.astimezone(now.tzinfo)<timedelta(hours=4) for d in times)>=(2 if marketing else 3): return False
    return True


def _facet(row:Any,kind:str)->str:
    from . import rc58_editorial_rebuild as rc58
    fs=rc58.classify_facets(row,kind)
    order=('behavioral_insight','pr_stunt','viral_social','gamification','ugc_community','experiential_ooh','brand_activation','creator_economy','campaign_creative') if kind=='marketing' else ('cyber','space','ai','robotics','chips_compute','energy_infra','engineering','bigtech_policy','science')
    return next((x for x in order if x in fs),'')


def pending(db:Any,cid:int,limit:int=20):
    rows=list(_PREV['pending'](db,int(cid),max(80,min(320,int(limit)*4))))
    if not rows:return rows
    marketing=_is_marketing_channel(db,int(cid)); kind='marketing' if marketing else 'ctrlua'; now=datetime.now(timezone.utc)
    try:
        with db.connect() as con: recent=con.execute("""SELECT a.*,s.name AS source_name,s.priority AS source_priority FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.channel_id=? AND a.status='published' AND a.published_at<>'' AND datetime(a.published_at)>=datetime('now','-8 hours') ORDER BY a.published_at DESC LIMIT 100""",(int(cid),)).fetchall()
    except Exception: recent=[]
    sources={}; facets={}
    for old in recent:
        d=_dt(_v(old,'published_at'))
        if d is None:continue
        age=now-d.astimezone(timezone.utc); sid=int(_v(old,'source_id',0) or 0); f=_facet(old,kind)
        if age<=timedelta(hours=8 if marketing else 6):sources[sid]=sources.get(sid,0)+1
        if f and age<=timedelta(hours=5 if marketing else 4):facets[f]=facets.get(f,0)+1
    out=[]
    for row in rows:
        sid=int(_v(row,'source_id',0) or 0); f=_facet(row,kind); topic_cap=3 if (not marketing and f=='science') else 2
        if sources.get(sid,0)>=2 or (f and facets.get(f,0)>=topic_cap):continue
        out.append(row)
        if len(out)>=max(1,int(limit)):break
    return out


_VKEY=re.compile(r'\b([A-Za-z][A-Za-z0-9.+_-]{1,})[\s-]+([0-9]+(?:\.[0-9]+)?)\b')
def _keys(x:str)->set[str]: return {f'{a.casefold()} {b}' for a,b in _VKEY.findall(str(x or ''))}

def _same_product_cycle(title:str,body:str,row:Any):
    oldt=str(_v(row,'title','')); oldb=str(_v(row,'teaser_text','') or _v(row,'event_summary',''))
    shared=(_keys(title)|_keys(body))&(_keys(oldt)|_keys(oldb))
    if not shared:return None
    from .event_dedupe import _latin_anchors,_tokens
    if len(_latin_anchors(title+'\n'+body)&_latin_anchors(oldt+'\n'+oldb))>=1 and len(_tokens(body)&_tokens(oldb))>=5:return .94,f'той самий продукт/версія в одному новинному циклі ({sorted(shared)[0]})'
    return None


def find_duplicate(title:str,body:str,recent:Iterable[Any]):
    from . import event_dedupe as ev
    rows=list(recent); hit=_PREV['event'](title,body,rows)
    if hit is not None:return hit
    best=None
    for row in rows:
        x=_same_product_cycle(title,body,row)
        if x:
            aid=int(_v(row,'id',0) or 0); cand=ev.DuplicateMatch(aid,x[0],x[1]) if aid else None
            if cand and (best is None or cand.score>best.score):best=cand
    return best


def title_duplicate(article:Any,recent:list[Any])->int|None:
    hit=_PREV['title'](article,recent)
    if hit is not None:return hit
    keys=_keys(str(_v(article,'title','')))
    for row in recent:
        if keys&_keys(str(_v(row,'title',''))):
            try:return int(_v(row,'id',0) or 0) or None
            except Exception:pass
    return None


_BAD=((re.compile(r'\bзапік\s+селен',re.I),'зламане «запік селен…»'),(re.compile(r'\bсліду\s*вальник',re.I),'зламане «сліду вальник»'),(re.compile(r'\bвузькому\s+смуз',re.I),'узгодження «у вузькому смузі»'),(re.compile(r'\bмод\s+дер',re.I),'розірване «моддери»'),(re.compile(r'\bнепісн',re.I),'зламане «непісн…»'))
def obvious_language_corruption(text:str)->tuple[str,...]:return tuple(label for p,label in _BAD if p.search(str(text or '')))


def _judge(article:Any,body:str)->tuple[bool,tuple[str,...]]:
    from . import production_pipeline as production
    from .evidence_pack import build_evidence_pack
    source=build_evidence_pack(article,char_budget=4600).text
    prompt=f'''Ти фінальний коректор українського Telegram-поста. НЕ переписуй текст. Перевір лише грубі помилки: зламані/безглузді слова чи словосполучення; неправильне узгодження/відмінок або машинний переклад; спотворена одиниця виміру, технічний термін чи власна назва порівняно із SOURCE; фраза, що втратила сенс через переклад. Не чіпляйся до смаку. SOURCE еталон для термінів/одиниць.\n\nSOURCE:\n{source}\n\nPOST:\n{body}\n\nТІЛЬКИ JSON: {{"ok":true або false,"issues":["0–5 реальних грубих помилок"]}}'''
    def parse(raw:str):
        t=re.sub(r'^```(?:json)?\s*|\s*```$','',str(raw or '').strip(),flags=re.I); a,b=t.find('{'),t.rfind('}')
        if a<0 or b<=a:raise ValueError('RC62 language judge invalid JSON')
        o=json.loads(t[a:b+1]); xs=o.get('issues') or []; xs=xs if isinstance(xs,list) else []
        issues=tuple(' '.join(str(x or '').split())[:220] for x in xs if str(x or '').strip())[:5]
        return bool(o.get('ok')) and not issues,issues
    def val(x:str):parse(x)
    r=production.run_ai(prompt,validator=val,max_output_tokens=220,local_prompt=prompt,local_max_output_tokens=240,cloud_timeout_seconds=24,local_timeout_seconds=18,task_timeout_seconds=50,local_repair=False,suppress_provider_on_quota=False,allowed_providers={'codex','gemini','groq'})
    return parse(r.text)


def _repair(article:Any,body:str,issues:tuple[str,...],*,hard_limit:int)->str:
    from . import production_pipeline as production, rc40_policy as rc40
    from .evidence_pack import build_evidence_pack
    source=build_evidence_pack(article,char_budget=5600).text
    prompt='''Ти коректор. Виправ ТІЛЬКИ перелічені мовні/термінологічні помилки. Не змінюй кут і не додавай/не вилучай факти, числа, дати, сутності, причини чи оцінки. Спотворений термін/одиницю віднови за SOURCE.\n\nПОМИЛКИ:\n- '''+'\n- '.join(issues)+f'''\n\nSOURCE:\n{source}\n\nPOST:\n{body}\n\nТІЛЬКИ виправлений пост.'''
    years=rc40._rc40_allowed_years(article); nums=rc40._rc40_allowed_numbers(article)
    def val(x:str):
        checked=rc40._validated_ua_body(x,article=article,allowed_years=years,allowed_numbers=nums,hard_limit=hard_limit)
        if obvious_language_corruption(checked):raise production.ProductionPipelineError('RC62 corruption remains')
    r=production.run_ai(prompt,validator=val,max_output_tokens=620,local_prompt=prompt,local_max_output_tokens=620,cloud_timeout_seconds=28,local_timeout_seconds=18,task_timeout_seconds=70,local_repair=False,suppress_provider_on_quota=False,allowed_providers={'codex','gemini','groq'})
    return rc40._validated_ua_body(r.text,article=article,allowed_years=years,allowed_numbers=nums,hard_limit=hard_limit)


def decide(channel:Any,article:Any,recent:list[Any],*,hard_limit:int,format_marker:str|None=None)->Decision:
    from . import production_pipeline as production
    d=_PREV['decide'](channel,article,recent,hard_limit=hard_limit,format_marker=format_marker)
    if d.decision!='publish':return d
    bad=obvious_language_corruption(d.telegram_teaser); ok=False; issues=()
    try:ok,issues=_judge(article,d.telegram_teaser)
    except Exception as exc:
        LOG.warning('RC62 language judge unavailable article_id=%s: %s',_v(article,'id','?'),exc)
        if not bad:return replace(d,reason=d.reason+' RC62 language judge degraded; deterministic gate PASS.')
    all_issues=tuple(dict.fromkeys(bad+issues))
    if ok and not all_issues:return replace(d,reason=d.reason+' RC62 final language QA PASS.')
    if not all_issues:all_issues=('фінальний коректор позначив текст як непридатний',)
    try:
        fixed=_repair(article,d.telegram_teaser,all_issues,hard_limit=hard_limit); ok2,i2=_judge(article,fixed); remain=obvious_language_corruption(fixed)+i2
        if not ok2 or remain:raise production.ProductionPipelineError('; '.join(remain or ('language judge FAIL',)))
    except Exception as exc:raise production.PostAIQAExhausted('RC62 final Ukrainian QA: '+str(exc),(str(exc),),provider_outage='Немає доступного AI-провайдера' in str(exc)) from exc
    return replace(d,telegram_teaser=fixed,full_article_uk=fixed,event_summary=fixed[:1000],reason=d.reason+' RC62 final language repair PASS.')


def source_link_entities(text:str,source_url:str)->str:
    url=str(source_url or '').strip(); value=str(text or '')
    if not url:return ''
    ms=list(re.finditer(r'(?m)(?<!\S)Джерело(?!\S)',value))
    if not ms:return ''
    from .telegram import _utf16_units
    m=ms[-1]; return json.dumps([{'type':'text_link','offset':_utf16_units(value[:m.start()]),'length':_utf16_units('Джерело'),'url':url}],ensure_ascii=False,separators=(',',':'))


def install_rc62_editorial_control()->None:
    global _INSTALLED
    if _INSTALLED:return
    from . import event_dedupe as ev, production_pipeline as prod, rc51_feedback as rc51, rc59_universal_policy as rc59, service as svc, telegram as tg
    from .database import Database
    _PREV.update(pending=Database.pending_articles,gap=svc.AutopilotService._gap_ok,selector=rc59._run_selector,selector_prompt=rc59._selector_prompt,feedback=rc59.score_against_feedback_rc59,decide=prod.decide,event=ev.find_event_duplicate,title=prod._title_duplicate,source_entities=tg._source_link_entities)
    Database.pending_articles=pending; svc.AutopilotService._gap_ok=gap_ok
    rc59.score_against_feedback_rc59=score_feedback; rc51.score_against_feedback=score_feedback; rc59._selector_prompt=selector_prompt; rc59._run_selector=run_selector
    ev.find_event_duplicate=find_duplicate; svc.find_event_duplicate=find_duplicate; prod._title_duplicate=title_duplicate
    def wrapped(channel,article,recent,*,hard_limit=prod.MEDIA_POST_HARD_LIMIT,format_marker=None):return decide(channel,article,recent,hard_limit=hard_limit,format_marker=format_marker)
    prod.decide=wrapped; svc.decide=wrapped; tg._source_link_entities=source_link_entities
    prod.POST_FORMAT_PREFIX='telegram-post-v38:'; svc.POST_FORMAT_PREFIX='telegram-post-v38:'
