"""Commercial campaign duplicate safety, limited to distinctive confirmed campaign keys."""
def campaign_key(text):
    t=str(text or "").casefold()
    if ("orange" in t or "оранж" in t) and any(w in t for w in ("scamcophony","scamcophon","скамкофон","какофон","шахрайськ")):
        return "orange:scamcophony"
    return ""

def prior_published_campaign(store, channel_id, article_id, article):
    if channel_id != 2:
        return 0
    key=campaign_key(" ".join(str(article[c] or "") for c in ("title","raw_text","final_text")))
    if not key:
        return 0
    with store.connect() as con:
        rows=con.execute("SELECT id,title,raw_text,final_text FROM articles WHERE channel_id=? AND stage='PUBLISHED' AND id<>? ORDER BY id DESC LIMIT 1000",(channel_id,article_id)).fetchall()
    for row in rows:
        if campaign_key(" ".join(str(row[c] or "") for c in ("title","raw_text","final_text"))) == key:
            return int(row["id"])
    return 0
