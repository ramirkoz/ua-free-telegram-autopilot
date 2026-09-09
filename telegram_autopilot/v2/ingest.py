from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from .. import collector
from ..database import content_hash
from ..media import encode_media
from ..models import CollectedArticle, Source
from .loghub import event
from .storage import V2Store


@dataclass(slots=True)
class TelegramEntry:
    post: str
    text: str
    published: str | None
    media: list[str]=field(default_factory=list)
    forwarded: bool=False
    forwarded_from: str=""


class TelegramParser(HTMLParser):
    def __init__(self,username: str):
        super().__init__(convert_charrefs=True); self.username=username; self.depth=0; self.message_depth=None; self.text_depth=None; self.forward_depth=None; self.current=None; self.entries=[]
    @staticmethod
    def _classes(attrs: dict[str,str]) -> set[str]: return {x for x in attrs.get("class","").split() if x}
    def handle_starttag(self,tag: str,attrs):
        self.depth+=1; values={str(k).casefold():str(v or "") for k,v in attrs}; classes=self._classes(values)
        if tag.casefold()=="div" and "tgme_widget_message" in classes and values.get("data-post"):
            self._finish(); self.current={"post":values["data-post"],"text":[],"published":None,"media":[],"forwarded":False,"forward_parts":[]}; self.message_depth=self.depth
        if self.current is None: return
        if "tgme_widget_message_text" in classes: self.text_depth=self.depth
        if any("forwarded" in c.casefold() for c in classes):
            self.current["forwarded"]=True
            if self.forward_depth is None: self.forward_depth=self.depth
        if self.current.get("forwarded"):
            origin=values.get("title") or values.get("data-peer") or ""
            if origin: self.current["forward_parts"].append(origin)
        if tag.casefold()=="time" and values.get("datetime"): self.current["published"]=values["datetime"]
        media=self.current["media"]
        if tag.casefold()=="img" and values.get("src"):
            item=encode_media("image",values["src"])
            if item not in media: media.append(item[:3020])
        if tag.casefold() in {"video","source"} and values.get("src"):
            item=encode_media("video",values["src"])
            if item not in media: media.append(item[:3020])
        style=values.get("style","")
        if style:
            m=re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)",style,flags=re.I)
            if m:
                item=encode_media("image",m.group(1))
                if item not in media: media.append(item[:3020])
    def handle_data(self,data: str):
        if self.current is None: return
        if self.text_depth is not None and self.depth>=self.text_depth: self.current["text"].append(data)
        if self.forward_depth is not None and self.depth>=self.forward_depth: self.current["forward_parts"].append(data)
    def handle_endtag(self,tag: str):
        if self.current is not None and self.text_depth==self.depth: self.text_depth=None
        if self.current is not None and self.forward_depth==self.depth: self.forward_depth=None
        if self.current is not None and self.message_depth==self.depth and tag.casefold()=="div": self._finish()
        self.depth=max(0,self.depth-1)
    def close(self): super().close(); self._finish()
    def _finish(self):
        if not self.current: return
        post=str(self.current.get("post") or "").strip(); text=" ".join("".join(self.current.get("text") or []).split()); media=list(dict.fromkeys(self.current.get("media") or []))[:24]; forwarded_from=" ".join(" ".join(self.current.get("forward_parts") or []).split())[:500]
        if post and (text or media): self.entries.append(TelegramEntry(post,text,str(self.current.get("published") or "") or None,media,bool(self.current.get("forwarded")),forwarded_from))
        self.current=None; self.message_depth=self.text_depth=self.forward_depth=None


def _post_number(post: str) -> int | None:
    try:
        tail=str(post or "").rsplit("/",1)[-1]; return int(tail) if tail.isdigit() else None
    except Exception: return None


def _entry_dt(entry: TelegramEntry) -> datetime | None:
    try:
        dt=datetime.fromisoformat(str(entry.published or "").replace("Z","+00:00"));
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception: return None


def _adjacent(a: TelegramEntry,b: TelegramEntry,seconds: int=120) -> bool:
    ai,bi=_post_number(a.post),_post_number(b.post)
    if ai is not None and bi is not None and bi!=ai+1: return False
    ad,bd=_entry_dt(a),_entry_dt(b)
    if ad is not None and bd is not None: return 0<=(bd-ad).total_seconds()<=seconds
    return ai is not None and bi is not None and bi==ai+1


def _held(entry: TelegramEntry) -> bool:
    if entry.media or not entry.text: return False
    dt=_entry_dt(entry)
    return bool(dt and 0<=(datetime.now(timezone.utc)-dt).total_seconds()<=100)


def _to_article(username: str,primary: TelegramEntry,attached: list[TelegramEntry]) -> CollectedArticle:
    group=[primary,*attached]; media=[]
    for e in group:
        for item in e.media:
            if item not in media: media.append(item)
    message_ids=[str(_post_number(e.post) or e.post.rsplit("/",1)[-1]) for e in group]
    forwarded_from=" | ".join(dict.fromkeys(e.forwarded_from for e in group if e.forwarded_from))[:800]
    blocks=[]
    from ..media import decode_media
    for idx,encoded in enumerate(media[:10],1):
        try: kind,url=decode_media(encoded)
        except Exception: continue
        if kind in {"image","video"} and url: blocks.append({"type":"media","index":idx,"kind":kind,"url":url,"caption":"","alt":"","context":primary.text[:700],"position":min(.35,.03+idx*.02)})
    layout=json.dumps({"version":2,"source_kind":"telegram","telegram":{"source_username":username,"message_ids":message_ids,"forwarded":any(e.forwarded for e in group),"forwarded_from":forwarded_from,"stitched":len(group)>1,"media_count":len(media)},"blocks":blocks},ensure_ascii=False,separators=(",",":"))
    title=primary.text[:220]+("…" if len(primary.text)>220 else ""); url="https://t.me/"+primary.post
    return CollectedArticle(primary.post[:1000],title or "Telegram",url,primary.text,primary.published,media[:24],layout)


def stitch_telegram(username: str,entries: list[TelegramEntry]) -> list[CollectedArticle]:
    result=[]; i=0
    while i<len(entries):
        current=entries[i]
        if not current.text and current.media:
            run=[current]; j=i+1
            while j<len(entries) and not entries[j].text and entries[j].media and _adjacent(run[-1],entries[j]): run.append(entries[j]); j+=1
            if j<len(entries) and entries[j].text and _adjacent(run[-1],entries[j]):
                primary=entries[j]; attached=run[:]; k=j+1
                while k<len(entries) and not entries[k].text and entries[k].media and _adjacent(entries[k-1],entries[k]): attached.append(entries[k]); k+=1
                result.append(_to_article(username,primary,attached)); i=k; continue
            i=j; continue
        if current.text:
            attached=[]; j=i+1; previous=current
            while j<len(entries) and not entries[j].text and entries[j].media and _adjacent(previous,entries[j]): attached.append(entries[j]); previous=entries[j]; j+=1
            if not current.media and not attached and j>=len(entries) and _held(current): i=j; continue
            result.append(_to_article(username,current,attached)); i=j; continue
        i+=1
    return result


def collect_telegram(source: Source) -> list[CollectedArticle]:
    username=collector._telegram_username(source.url)
    if not username: raise collector.CollectorError("Telegram-джерело має містити публічну адресу t.me/username")
    response=collector._source_fetch(f"https://t.me/s/{username}",max_bytes=8*1024*1024,allowed_content_types={"text/html","application/xhtml+xml"},timeout=35)
    parser=TelegramParser(username); parser.feed(response.body.decode("utf-8",errors="replace")); parser.close(); items=stitch_telegram(username,parser.entries)
    if not items: raise collector.CollectorError("Не вдалося прочитати Telegram-канал")
    return items[-40:]


def collect(source: Source) -> list[CollectedArticle]:
    return collect_telegram(source) if source.kind=="telegram" else collector.collect_source(source)


class IngestService:
    def __init__(self,store: V2Store): self.store=store
    def collect_channel(self,channel_id: int) -> dict[str,int]:
        added=seen=errors=0
        for row in self.store.sources_for_channel(channel_id,enabled_only=True):
            source=Source(id=int(row["id"]),channel_id=int(row["channel_id"]),kind=str(row["kind"]),name=str(row["name"]),url=str(row["url"]),enabled=bool(row["enabled"]),initialized=bool(row["initialized"]),last_checked_at=str(row["last_checked_at"] or "") or None,last_error=str(row["last_error"] or "") or None,priority=int(row["priority"] or 100))
            try:
                items=collect(source); seen+=len(items)
                for item in items:
                    media_json=json.dumps(list(item.media_urls or []),ensure_ascii=False,separators=(",",":")); before=self._existing(source.id,item.external_id)
                    self.store.insert_collected(channel_id=channel_id,source_id=source.id,external_id=item.external_id,title=item.title,source_url=item.url,raw_text=item.raw_text,content_hash=content_hash(item.title,item.raw_text),source_published_at=str(item.published_at or ""),media_json=media_json,article_layout_json=str(item.article_layout_json or "{}"))
                    if not before: added+=1
                with self.store.connect() as con: con.execute("UPDATE sources SET initialized=1,last_checked_at=?,last_error='' WHERE id=?",(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),source.id))
                event("ingest","source collected",channel_id=channel_id,source_id=source.id,source=source.name,items=len(items),added=added)
            except Exception as exc:
                errors+=1
                with self.store.connect() as con: con.execute("UPDATE sources SET last_checked_at=?,last_error=? WHERE id=?",(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),str(exc)[:1200],source.id))
                event("ingest","source collection failed",level=40,channel_id=channel_id,source_id=source.id,source=source.name,detail=str(exc)[:600])
        return {"seen":seen,"added":added,"errors":errors}
    def _existing(self,source_id: int,external_id: str) -> bool:
        with self.store.connect() as con: return con.execute("SELECT 1 FROM articles WHERE source_id=? AND external_id=?",(int(source_id),str(external_id))).fetchone() is not None
