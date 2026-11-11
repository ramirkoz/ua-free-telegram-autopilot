"""Measure the call-to-action veto on operator data (read-only).

Usage: python eval_cta.py <repo> <op.sqlite3> <labels.json>
"""
import collections, json, sqlite3, sys, types
from pathlib import Path

repo, db, labels = sys.argv[1:4]
sys.path.insert(0, repo)
import telegram_autopilot  # noqa: E402
v2 = types.ModuleType("telegram_autopilot.v2"); v2.__path__ = [str(Path(repo) / "telegram_autopilot" / "v2")]
sys.modules["telegram_autopilot.v2"] = v2
from telegram_autopilot.v2.monitoring_call_to_action import call_to_action_reason  # noqa: E402

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True); con.row_factory = sqlite3.Row
L = {a["id"]: a["label"] for a in json.load(open(labels, encoding="utf-8"))["articles"] if a["channel"] == 3}

print("== named regressions / controls")
for aid, want in ((95272, True), (95317, True), (95413, True), (95421, True)):
    r = con.execute("select title,raw_text from articles where id=?", (aid,)).fetchone()
    got = call_to_action_reason(r)
    print(f"  #{aid} block expected={want} got={got or '-'}  {'OK' if bool(got) == want else 'BAD'}")
for msg in (4737, 4750, 4751, 4724, 4741, 4755):
    r = con.execute("select id,title,raw_text from articles where channel_id=3 and telegram_message_id=?", (str(msg),)).fetchone()
    if r:
        got = call_to_action_reason(r)
        print(f"  msg {msg} (#{r['id']}) must pass: got={got or '-'}  {'OK' if not got else 'BAD'}")

rows = con.execute("select id,title,raw_text,stage,published_at,telegram_message_id from articles where channel_id=3").fetchall()
hit = [(r, call_to_action_reason(r)) for r in rows]
hit = [(r, c) for r, c in hit if c]
print(f"\n== all GR articles in snapshot: {len(rows)}; vetoed: {len(hit)}", dict(collections.Counter(c for _, c in hit)))
pub = [(r, c) for r, c in hit if r["stage"] == "PUBLISHED"]
print(f"   of them actually PUBLISHED by earlier versions: {len(pub)}")
lab = collections.Counter((c, L[r["id"]]) for r, c in hit if r["id"] in L)
print("   on labelled rows (code, human label 1=want):", dict(lab))
print("\n== sample of vetoed PUBLISHED posts")
for r, c in pub[-14:]:
    print(f"  #{r['id']} msg={r['telegram_message_id']} {c} | {(r['raw_text'] or '')[:150]!r}")
print("\n== sample of vetoed rows the operator marked WANT")
n = 0
for r, c in hit:
    if L.get(r["id"]) == 1:
        print(f"  #{r['id']} {c} | {(r['raw_text'] or '')[:170]!r}"); n += 1
        if n >= 16: break
