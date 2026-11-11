"""Offline replay of the DETERMINISTIC monitoring gates of one code version.

Usage: python replay_monitoring.py <repo> <op.sqlite3> <labels.json> <policy.json> <out.json>

Read-only. No AI call is made: the gateway is a stub, so an article either gets
a deterministic reject code or reaches the AI selector ("AI"). The sanitized
operator snapshot has no Telegram layout, so the forwarded flag is restored from
the recorded reject reason of the live run.
"""
import json, sqlite3, sys, types
from pathlib import Path

repo, db, labels, policy_path, out = sys.argv[1:6]
sys.path.insert(0, repo)
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy  # noqa: E402
from telegram_autopilot.v2.editorial import EditorialEngine  # noqa: E402


class NeedsAI(Exception):
    pass


class Gateway:
    def run(self, *a, **k):
        raise NeedsAI()


pol = json.load(open(policy_path, encoding="utf-8"))
fields = {k: v for k, v in pol.items() if k in ChannelPolicy.__dataclass_fields__}
fields.setdefault("monitoring_source_policy", "connected_original")
policy = ChannelPolicy(channel_id=3, **{k: v for k, v in fields.items() if k != "channel_id"})
channel = ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1", mode=ChannelMode.MONITORING, policy=policy)

engine = object.__new__(EditorialEngine)
engine.gateway = Gateway()
engine.store = None

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True); con.row_factory = sqlite3.Row
L = {a["id"]: a["label"] for a in json.load(open(labels, encoding="utf-8"))["articles"] if a["channel"] == 3}
rows = con.execute(
    """select a.*, s.name as source_name from articles a join sources s on s.id=a.source_id
       where a.channel_id=3 and (a.discovered_at>='2026-11-10T09:20' or a.id in (%s))"""
    % ",".join(str(i) for i in L) if L else "0").fetchall()
result = {}
for r in rows:
    art = dict(r)
    forwarded = str(r["reject_reason"] or "").startswith("MONITORING_NOT_ORIGINAL_FORWARD")
    art["article_layout_json"] = json.dumps({"source_kind": "telegram", "telegram": {"forwarded": forwarded}})
    try:
        o = engine.select(channel, art)
        verdict = "REJECT:" + str(o.reason).split(":")[0].strip() if str(o.decision).endswith("REJECT") else "PASS:" + str(o.reason)[:30]
    except NeedsAI:
        verdict = "AI"
    except Exception as exc:  # report, do not hide
        verdict = "ERROR:" + type(exc).__name__ + ":" + str(exc)[:80]
    result[r["id"]] = {"verdict": verdict, "label": L.get(r["id"]), "live_stage": r["stage"],
                       "live_reason": str(r["reject_reason"] or "")[:60], "msg": r["telegram_message_id"],
                       "after_boot": str(r["discovered_at"]) >= "2026-11-10T09:20"}
json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("replayed", len(result))
