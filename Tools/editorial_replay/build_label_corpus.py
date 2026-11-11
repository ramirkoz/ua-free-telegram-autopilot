"""Build one de-duplicated human-label corpus from the operator's returned XLSX files.

Usage: python build_label_corpus.py <out.json> <xlsx> [<xlsx> ...]   (oldest first)
Rules (ProductVault EDITORIAL_XLSX_STANDARD / policy 05.11): in a returned, rated
sheet only an explicit check mark is positive, everything else is negative; a sheet
with no explicit mark at all was never rated and is skipped. Later files win.
"""
import json, sys, os, collections
import openpyxl

ALIASES = {
    "label": ("ВИБІР РЕДАКТОРА",), "id": ("ARTICLE_ID",), "title_uk": ("ЗАГОЛОВОК УКРАЇНСЬКОЮ",),
    "title": ("ОРИГІНАЛЬНИЙ ЗАГОЛОВОК",), "source": ("ДЖЕРЕЛО",), "url": ("URL ОРИГІНАЛУ", "ПОСИЛАННЯ НА ПЕРШОДЖЕРЕЛО"),
    "excerpt": ("УРИВОК ДЖЕРЕЛА", "УРИВОК ПЕРШОДЖЕРЕЛА"), "decision": ("РІШЕННЯ AUTOPILOT", "РІШЕННЯ СИСТЕМИ"),
    "stage": ("СТАДІЯ БАЗИ", "СТАДІЯ"), "reason": ("ТОЧНА ПРИЧИНА СИСТЕМИ",), "final_text": ("ФІНАЛЬНИЙ ТЕКСТ",),
    "arrived": ("НАДІЙШЛО (КИЇВ)", "ДАТА НАДХОДЖЕННЯ"), "published": ("ОПУБЛІКОВАНО (КИЇВ)", "ОПУБЛІКОВАНО"),
    "post": ("ПОСИЛАННЯ НА ПОСТ",), "comment": ("КОМЕНТАР РЕДАКТОРА",),
}
CHANNELS = {"CTRL+UA": 1, "ПРОДАНО!": 2, "ПРОДАНО": 2, "ГРОМАДИ": 3}

out, files = sys.argv[1], sys.argv[2:]
corpus, conflicts, stats = {}, [], []
for path in files:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        if ws.title not in CHANNELS:
            continue
        rows = list(ws.iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows[:8]) if r and "ARTICLE_ID" in [str(c or "").strip() for c in r]), None)
        if hi is None:
            continue
        hdr = [str(c or "").strip() for c in rows[hi]]
        col = {k: next((hdr.index(a) for a in al if a in hdr), None) for k, al in ALIASES.items()}
        data = [r for r in rows[hi + 1:] if r and r[col["id"]] not in (None, "")]
        marks = [str(r[col["label"]] or "").strip() for r in data]
        if "☑" not in marks:
            stats.append((os.path.basename(path), ws.title, len(data), "UNRATED - skipped"))
            continue
        pos = 0
        for r, mark in zip(data, marks):
            aid = int(str(r[col["id"]]).strip().lstrip("#"))
            rec = {k: ("" if col[k] is None or r[col[k]] is None else str(r[col[k]]).strip()) for k in ALIASES}
            rec.update(id=aid, channel=CHANNELS[ws.title], label=1 if mark == "☑" else 0, file=os.path.basename(path))
            pos += rec["label"]
            old = corpus.get(aid)
            if old and old["label"] != rec["label"]:
                conflicts.append((aid, old["file"], old["label"], rec["file"], rec["label"]))
            if old:  # keep richer text from either snapshot
                for k in ("excerpt", "final_text", "title", "url"):
                    if len(old.get(k, "")) > len(rec.get(k, "")):
                        rec[k] = old[k]
            corpus[aid] = rec
        stats.append((os.path.basename(path), ws.title, len(data), f"+{pos} / -{len(data) - pos}"))
json.dump({"articles": sorted(corpus.values(), key=lambda r: r["id"]), "conflicts": conflicts}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
for s in stats: print(*s, sep=" | ")
by = collections.Counter((r["channel"], r["label"]) for r in corpus.values())
print("UNIQUE:", {f"ch{c}": (by[(c, 1)], by[(c, 0)]) for c in (1, 2, 3)}, "total", len(corpus))
print("label conflicts between files:", len(conflicts), conflicts[:12])
