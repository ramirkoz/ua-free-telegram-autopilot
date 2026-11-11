"""Before/after evidence on the operator's label corpus (read-only, no AI calls).

Usage: python compare_editorial.py <repo> <op.sqlite3> <labels.json> <gr_before.json> <gr_after.json>

Monitoring channel: deterministic gates are replayed by replay_monitoring.py.
Editorial channels (CTRL+UA, ПРОДАНО!): the selector is an AI call that cannot be
replayed offline, so this script uses the RECORDED live outcome of each article
and applies the new deterministic rules to it:

* EDITOR_2321_* review losses -> the primary selector had already said PUBLISH;
  they are released unless the title matches a reviewed risk pattern.
* LEARNING_ADMIN_DISLIKE -> released when the recorded similarity is below the
  new near-identical threshold.
* RC107 cluster duplicates -> re-evaluated with the headline guard.
Released means "no longer lost at this gate"; fact, media, freshness, duplicate
and writer QA gates downstream still apply and are NOT assumed to pass.
"""
import collections, json, re, sqlite3, sys

repo, db, labels, gr_before, gr_after = sys.argv[1:6]
sys.path.insert(0, repo)
from telegram_autopilot.v2.editorial_operator_2321 import verify_low_confidence_publish  # noqa: E402
from telegram_autopilot.v2.event_dedupe_guard import _fingerprint_stats, _validated_cluster_same_event  # noqa: E402

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True); con.row_factory = sqlite3.Row
A = json.load(open(labels, encoding="utf-8"))["articles"]
NAMES = {1: "CTRL+UA", 2: "ПРОДАНО!", 3: "ГРОМАДИ"}
ROLE = {1: "science", 2: "creative"}


def live(row):
    """(selected_before, reason) from the recorded live outcome."""
    reason = str(row["reject_reason"] or row["status_detail"] or "")
    decision = str(row["decision"] or "")
    selected = decision == "PUBLISH" or str(row["stage"]) in {"PUBLISHED", "READY", "QA_PASSED"}
    return selected, reason


def editorial_after(row, channel):
    selected, reason = live(row)
    if selected:
        return True, "selected"
    if reason.startswith("EDITOR_2321_"):
        if verify_low_confidence_publish(ROLE[channel], 70, {"title": row["title"]}):
            return False, "still reviewed (risk title)"
        return True, "released: review veto removed"
    if reason.startswith("LEARNING_ADMIN_DISLIKE"):
        m = re.search(r"similarity=([0-9.]+)", reason)
        if m and float(m.group(1)) < 0.60:
            return None, "to selector: weak-similarity dislike no longer vetoes"
        return False, "near-identical dislike"
    if str(row["decision"]) == "DUPLICATE" and "RC107 validated cluster" in reason and row["duplicate_of"]:
        other = con.execute("select * from articles where id=?", (row["duplicate_of"],)).fetchone()
        if other is not None:
            ok, _ = _validated_cluster_same_event(_fingerprint_stats(row, other), commercial_profile=channel == 2)
            if not ok:
                return None, "to selector: boilerplate cluster duplicate released"
    return False, re.match(r"[A-Z][A-Z0-9_]{3,}(?::[A-Z0-9_]+)?", reason).group(0) if re.match(r"[A-Z][A-Z0-9_]{3,}", reason) else "selector/other"


def matrix(pairs):
    tp = sum(1 for sel, lab in pairs if sel and lab); fp = sum(1 for sel, lab in pairs if sel and not lab)
    fn = sum(1 for sel, lab in pairs if not sel and lab); tn = sum(1 for sel, lab in pairs if not sel and not lab)
    prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
    return tp, fp, fn, tn, prec, rec


def line(name, m):
    return f"| {name} | {m[0]} | {m[1]} | {m[2]} | {m[3]} | {m[4]:.0%} | {m[5]:.0%} |"


print("## Thematic selection on the label corpus (selected = reaches writing; later gates not assumed)\n")
print("| Канал / версія | TP | FP | FN | TN | precision | recall |\n|---|---:|---:|---:|---:|---:|---:|")
released = collections.Counter()
for ch in (1, 2):
    before, after = [], []
    for a in (x for x in A if x["channel"] == ch):
        row = con.execute("select * from articles where id=?", (a["id"],)).fetchone()
        if row is None:
            continue
        b_sel, reason = live(row)
        # undecided rows (still queued when the snapshot was taken) are not counted
        if str(row["decision"] or "") in {"", "PENDING"} and not b_sel:
            continue
        a_sel, why = editorial_after(row, ch)
        if a_sel is None:
            # now reaches the AI selector; its verdict cannot be known offline
            released[(ch, why, a["label"])] += 1
            a_sel = False
        elif a_sel and not b_sel:
            released[(ch, why, a["label"])] += 1
        before.append((b_sel, a["label"])); after.append((a_sel, a["label"]))
    print(line(f"{NAMES[ch]} 2.3.22 (n={len(before)})", matrix(before)))
    print(line(f"{NAMES[ch]} 2.3.23", matrix(after)))

gb, ga = json.load(open(gr_before, encoding="utf-8")), json.load(open(gr_after, encoding="utf-8"))
reach = lambda v: v == "AI" or v.startswith("PASS")
ids = [k for k in ga if ga[k]["label"] is not None]
print(line(f"ГРОМАДИ 2.3.22, детерміновані ворота (n={len(ids)})", matrix([(reach(gb[k]["verdict"]), ga[k]["label"]) for k in ids])))
print(line("ГРОМАДИ 2.3.23, детерміновані ворота", matrix([(reach(ga[k]["verdict"]), ga[k]["label"]) for k in ids])))

print("\n## What was released, by reason and human label (1 = wanted)\n")
for (ch, why, lab), n in sorted(released.items()):
    print(f"- {NAMES[ch]}: {why}: label={lab}: {n}")
ann = collections.Counter(ga[k]["verdict"] for k in ids if reach(gb[k]["verdict"]) and not reach(ga[k]["verdict"]) and ga[k]["label"] == 1)
print("\n## ГРОМАДИ: wanted-by-label rows now blocked by the no-announcement policy\n")
for v, n in ann.items():
    print(f"- {v}: {n}")
