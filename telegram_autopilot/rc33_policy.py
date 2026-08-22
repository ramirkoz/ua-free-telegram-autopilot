from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Mapping

from .models import Decision, Source

PRIORITY_MIN = 1
PRIORITY_MAX = 100
PRIORITY_DEFAULT = 50
POST_FORMAT_PREFIX_RC33 = "telegram-post-v19:"

CTRL_UA_PROFILE = """Аудиторія CTRL+UA: українські зумери, IT/розробники/product/tech-фахівці та корпоративна/бізнес-аудиторія.
Пріоритет: AI, software/cloud, кібербезпека й приватність, чипи та обчислення, enterprise/startups/Big Tech, робототехніка, енергетика та інфраструктура, космос і справді сильний научпоп.
Научпоп проходить, коли має щонайменше кілька з ознак: wow-фактор, наслідок для людини, технологічний перетин, масштаб, високу цінність для обговорення.
Не публікувати: cute/lifestyle filler, випадкові історії про тварин без наукової/технологічної новизни, звичайні pet/home gadgets, купони/знижки/buying guides, квитки/вебінари/промо, переказ CAPTCHA/службових сторінок, entertainment без суттєвого tech-angle.
Reddit не є достатнім фінальним доказом сам по собі: прямі Reddit-сторінки не публікувати без канонічного зовнішнього джерела."""

_INSTALLED = False

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "at", "by", "with", "from",
    "as", "is", "are", "was", "were", "be", "been", "this", "that", "these", "those", "its", "their",
    "new", "more", "over", "after", "before", "how", "why", "what", "your", "you", "we", "our",
}

_EVENT_ACTIONS = {
    "recall": {"recall", "recalls", "recalled", "fix", "fixes"},
    "settlement": {"settlement", "settle", "settles", "settled", "pay", "pays", "fine", "fined"},
    "lawsuit": {"lawsuit", "sues", "sued", "court", "trial"},
    "launch": {"launch", "launches", "launched", "unveil", "unveils", "unveiled", "release", "releases", "released"},
    "layoff": {"layoff", "layoffs", "cuts", "cut", "jobs", "roles"},
    "breach": {"breach", "breached", "hack", "hacked", "cyberattack", "leak", "leaked"},
    "funding": {"raises", "raised", "funding", "fund", "series", "valuation"},
    "acquisition": {"acquires", "acquired", "acquisition", "buys", "bought", "merger"},
    "regulation": {"ban", "bans", "banned", "regulator", "regulators", "rule", "rules", "policy", "probe", "investigation"},
    "research": {"study", "research", "researchers", "scientists", "finds", "found", "discovered", "discovery"},
}

_BAD_ACCESS = (
    "prove your humanity", "verify you are human", "are you a robot", "captcha", "blocked by network security",
    "log in to continue", "sign in to continue", "enable javascript to continue", "access denied",
    "checking your browser", "security verification", "human verification",
)

_LOW_VALUE = (
    "buying guide", "gift guide", "best deals", "deal of the day", "coupon", "discount", "price drop",
    "save $", "save up to", "on sale", "preorder now", "pre-order now", "buy now", "affiliate commission",
    "ticket today", "tickets today", "last chance save", "webinar", "register now", "premium for free",
    "free premium", "how to buy", "should you buy", "can you use", "how to use",
)

_ENTERTAINMENT = (
    "season ", "episode ", "star trek", "dungeons & dragons", "world of warcraft", "movie", "tv show",
    "streaming now", "paramount+", "netflix", "disney+", "trailer",
)

_PET_FLUFF = (
    "raccoon", "raccoons", "kitten", "kittens", "cat feeder", "pet feeder", "dog feeder",
    "baby animal", "baby animals", "cute animals", "wildlife camera",
)

_RESEARCH_OR_TECH = (
    "study", "research", "scientist", "researcher", "nature communications", "peer-reviewed",
    "artificial intelligence", " ai ", "machine learning", "computer vision", "sensor", "robot",
    "biotech", "genome", "microbiome", "medical", "nasa", "microgravity", "algorithm",
)

_PET_TECH = (
    "study", "research", "peer-reviewed", "artificial intelligence", " ai ", "machine learning",
    "computer vision", "sensor", "robot", "algorithm", "biometric",
)

_TOPIC_GROUPS = (
    ("ai", ("artificial intelligence", " ai ", "chatgpt", "claude", "gemini", "grok", "llm", "agentic", "machine learning")),
    ("software", ("software", "cloud", "developer", "programming", "database", "platform", "open source", "linux", "windows", "macos")),
    ("cyber", ("cybersecurity", "security flaw", "vulnerability", "ransomware", "malware", "data breach", "privacy", "zero-day", "zero day")),
    ("chips", ("semiconductor", "chip", "gpu", "cpu", "dram", "hbm", "foundry", "lithography", "tsmc", "intel", "nvidia", "amd")),
    ("enterprise", ("startup", "funding", "valuation", "enterprise", "antitrust", "regulator", "lawsuit", "acquisition", "marketplace")),
    ("space", ("space", "nasa", "spacex", "starship", "satellite", "orbit", "astronom", "telescope", "black hole", "galaxy", "microgravity")),
    ("science", ("research", "study", "scientists", "physics", "biology", "medicine", "medical", "nature communications", "quantum", "geology")),
    ("industry", ("robot", "autonomous", "lidar", "factory", "manufacturing", "energy", "data center", "datacenter", "battery", "grid", "infrastructure")),
)

_STRONG_EVENT = (
    "announced", "launch", "launched", "released", "introduced", "unveiled", "published", "study",
    "researchers", "scientists", "discovered", "found", "raises", "raised", "acquired", "acquisition",
    "lawsuit", "court", "regulator", "recall", "breach", "hack", "vulnerability", "ban", "investigation",
    "contract", "deal", "partnership", "funding", "layoffs", "cuts", "test", "tested",
)


def _row_value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else value


def normalize_priority(value: Any) -> int:
    try:
        priority = int(str(value).strip())
    except Exception as exc:
        raise ValueError("Пріоритет має бути цілим числом від 1 до 100.") from exc
    if not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise ValueError("Пріоритет має бути від 1 до 100, де 100 — найвищий.")
    return priority


def editorial_gate_reason(article: Mapping[str, Any] | Any) -> str:
    title = " ".join(str(_row_value(article, "title", "") or "").split())
    raw = " ".join(str(_row_value(article, "raw_text", "") or "").split())
    url = str(_row_value(article, "url", "") or "").casefold()
    text = f" {title}\n{raw[:10000]} ".casefold()

    if "reddit.com/" in url:
        return "Reddit у CTRL+UA використовується лише для discovery: потрібне канонічне зовнішнє джерело."
    if any(signal in text for signal in _BAD_ACCESS):
        return "Джерело повернуло CAPTCHA/службову сторінку замість перевіреної новини."
    if len(raw) < 220:
        return "У джерелі замало змістовного тексту для безпечної новинної публікації."
    if any(signal in text for signal in _LOW_VALUE):
        return "Матеріал має низьку редакційну цінність для CTRL+UA: промо, знижка, квитки, вебінар або how-to."

    has_research_or_tech = any(signal in text for signal in _RESEARCH_OR_TECH)
    if any(signal in text for signal in _PET_FLUFF) and not any(signal in text for signal in _PET_TECH):
        return "Cute/pet/wildlife filler без достатньої наукової або технологічної новизни."
    if any(signal in text for signal in _ENTERTAINMENT) and not has_research_or_tech:
        return "Entertainment-матеріал без достатнього технологічного або наукового кута."

    topic_hits = sum(1 for _, terms in _TOPIC_GROUPS if any(term in text for term in terms))
    event_hit = any(term in text for term in _STRONG_EVENT)
    priority = int(_row_value(article, "source_priority", PRIORITY_DEFAULT) or PRIORITY_DEFAULT)

    if topic_hits == 0:
        return "Матеріал не потрапляє в редакційне ядро CTRL+UA для зумерів, IT і корпоративної аудиторії."
    if not event_hit and topic_hits < 2 and priority < 85:
        return "Є тематичний збіг, але немає достатньо виразної нової події або дослідження."
    return ""


def output_refusal_blockers(body: str) -> tuple[str, ...]:
    low = " ".join(str(body or "").casefold().split())
    signals = (
        "не придатний для новинної публікації",
        "непридатний для новинної публікації",
        "немає достатньо перевірених фактів",
        "немає достатньо підтверджених фактів",
        "неможливо підготувати коректну",
        "у наданому фрагменті",
        "у наданому пакеті",
        "пакеті доказів",
        "інших підтверджених деталей",
        "не можна підготувати корект",
        "не містить перевіреної технологічної новини",
    )
    return ("AI повернув редакційну відмову/мета-коментар замість поста.",) if any(s in low for s in signals) else ()


def _title_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+_-]{2,}", str(value or ""))
        if token.casefold() not in _STOPWORDS
    }


def _title_actions(value: str) -> set[str]:
    tokens = _title_tokens(value)
    return {name for name, words in _EVENT_ACTIONS.items() if tokens & words}


def _title_numbers(value: str) -> set[str]:
    return {x.replace(",", ".") for x in re.findall(r"\b\d+(?:[.,]\d+)?\b", str(value or ""))}


def _named_title_anchors(value: str) -> set[str]:
    anchors = set()
    for token in re.findall(r"\b[A-Z][A-Za-z0-9.+_-]{2,}\b", str(value or "")):
        low = token.casefold()
        if low not in _STOPWORDS:
            anchors.add(low)
    return anchors


def title_event_duplicate(current_title: str, recent: list[Any]) -> tuple[int, str] | None:
    cur_tokens = _title_tokens(current_title)
    cur_actions = _title_actions(current_title)
    cur_numbers = _title_numbers(current_title)
    cur_anchors = _named_title_anchors(current_title)
    if not cur_tokens or not cur_actions:
        return None
    for row in recent:
        old_title = str(_row_value(row, "title", "") or "")
        old_tokens = _title_tokens(old_title)
        old_actions = _title_actions(old_title)
        if not (cur_actions & old_actions):
            continue
        shared = cur_tokens & old_tokens
        anchors = cur_anchors & _named_title_anchors(old_title)
        number_shared = bool(cur_numbers & _title_numbers(old_title))
        union = cur_tokens | old_tokens
        jaccard = len(shared) / max(1, len(union))
        if anchors and number_shared and len(shared) >= 2:
            return int(_row_value(row, "id", 0) or 0), "та сама подія: збігаються дія, сутність і числовий факт"
        if anchors and len(shared) >= 5 and jaccard >= 0.30:
            return int(_row_value(row, "id", 0) or 0), "та сама подія: сильний збіг дії, сутності та заголовка"
    return None


_VIDEO_LINE_RE = re.compile(r"(?:\n\n|\A)🎬\s*Відео:\s*(https?://\S+)\s*", re.I)


def split_video_footer(text: str) -> tuple[str, str]:
    value = str(text or "")
    matches = list(_VIDEO_LINE_RE.finditer(value))
    if not matches:
        return value, ""
    match = matches[-1]
    url = match.group(1)
    cleaned = (value[:match.start()] + value[match.end():]).strip()
    return cleaned, url


def media_first_fields(method: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    safe_fields = dict(fields)
    if method in {"sendPhoto", "sendVideo", "sendAnimation"}:
        safe_fields["show_caption_above_media"] = "false"
    return safe_fields


def install_rc33_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import database as database_module
    from . import event_dedupe as event_dedupe_module
    from . import production_pipeline as production_module
    from . import service as service_module
    from . import telegram as telegram_module
    from . import ui as ui_module

    Database = database_module.Database
    MainWindow = ui_module.MainWindow

    original_db_init = Database._init
    original_decide = production_module.decide
    original_hard_blockers = production_module.hard_editorial_blockers
    original_event_dedupe = event_dedupe_module.find_event_duplicate
    original_request = telegram_module._request
    original_request_file = telegram_module._request_file
    original_build_post_text = telegram_module.build_post_text
    original_send_video_url = telegram_module.send_video_url

    def db_init(self) -> None:
        original_db_init(self)
        with self.connect() as con:
            self._ensure_column(con, "sources", "priority", f"INTEGER NOT NULL DEFAULT {PRIORITY_DEFAULT}")
            con.execute(
                "UPDATE sources SET priority=? WHERE priority IS NULL OR priority<? OR priority>?",
                (PRIORITY_DEFAULT, PRIORITY_MIN, PRIORITY_MAX),
            )

    def list_sources(self, channel_id: int) -> list[Source]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM sources WHERE channel_id=? ORDER BY priority DESC, name COLLATE NOCASE",
                (channel_id,),
            ).fetchall()
        return [
            Source(
                id=int(r["id"]), channel_id=int(r["channel_id"]), kind=str(r["kind"]),
                name=str(r["name"]), url=str(r["url"]), enabled=bool(r["enabled"]),
                initialized=bool(r["initialized"]), last_checked_at=r["last_checked_at"],
                last_error=r["last_error"], priority=int(r["priority"] or PRIORITY_DEFAULT),
            )
            for r in rows
        ]

    def list_sources_with_health(self, channel_id: int):
        with self.connect() as con:
            rows = con.execute(
                """SELECT s.*,
                          h.last_success_at AS h_last_success_at,
                          h.last_new_at AS h_last_new_at,
                          h.last_error_at AS h_last_error_at,
                          h.last_error AS h_last_error,
                          h.last_inserted_count AS h_last_inserted_count,
                          h.total_checks AS h_total_checks,
                          h.total_errors AS h_total_errors,
                          h.total_inserted AS h_total_inserted
                   FROM sources s
                   LEFT JOIN source_health h ON h.source_id=s.id
                   WHERE s.channel_id=?
                   ORDER BY s.priority DESC, s.name COLLATE NOCASE""",
                (channel_id,),
            ).fetchall()
        result = []
        for r in rows:
            src = Source(
                id=int(r["id"]), channel_id=int(r["channel_id"]), kind=str(r["kind"]),
                name=str(r["name"]), url=str(r["url"]), enabled=bool(r["enabled"]),
                initialized=bool(r["initialized"]), last_checked_at=r["last_checked_at"],
                last_error=r["last_error"], priority=int(r["priority"] or PRIORITY_DEFAULT),
            )
            health = {
                "last_success_at": r["h_last_success_at"] or "",
                "last_new_at": r["h_last_new_at"] or "",
                "last_error_at": r["h_last_error_at"] or "",
                "last_error": r["h_last_error"] or "",
                "last_inserted_count": int(r["h_last_inserted_count"] or 0),
                "total_checks": int(r["h_total_checks"] or 0),
                "total_errors": int(r["h_total_errors"] or 0),
                "total_inserted": int(r["h_total_inserted"] or 0),
            }
            result.append((src, health))
        return result

    def save_source(
        self, *, source_id: int | None, channel_id: int, kind: str,
        name: str, url: str, enabled: bool, priority: int = PRIORITY_DEFAULT,
    ) -> int:
        clean_name = str(name or "").strip()
        clean_url = str(url or "").strip()
        if not clean_name:
            raise ValueError("Вкажіть назву джерела.")
        if not clean_url:
            raise ValueError("Вкажіть посилання на джерело.")
        clean_priority = normalize_priority(priority)
        with self.connect() as con:
            if source_id:
                old = con.execute(
                    "SELECT kind,url FROM sources WHERE id=? AND channel_id=?",
                    (source_id, channel_id),
                ).fetchone()
                reset = bool(old and (str(old["kind"]) != kind or str(old["url"]) != clean_url))
                con.execute(
                    """UPDATE sources
                       SET kind=?,name=?,url=?,priority=?,enabled=?,
                           initialized=CASE WHEN ? THEN 0 ELSE initialized END
                       WHERE id=? AND channel_id=?""",
                    (kind, clean_name, clean_url, clean_priority, int(enabled), int(reset), source_id, channel_id),
                )
                return source_id
            cur = con.execute(
                "INSERT INTO sources(channel_id,kind,name,url,priority,enabled) VALUES(?,?,?,?,?,?)",
                (channel_id, kind, clean_name, clean_url, clean_priority, int(enabled)),
            )
            return int(cur.lastrowid)

    def get_article(self, article_id: int):
        with self.connect() as con:
            return con.execute(
                """SELECT a.*,s.name AS source_name,s.priority AS source_priority
                   FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?""",
                (article_id,),
            ).fetchone()

    def pending_articles(self, channel_id: int, limit: int = 20):
        with self.connect() as con:
            return con.execute(
                """SELECT a.*,s.name AS source_name,s.priority AS source_priority
                   FROM articles a JOIN sources s ON s.id=a.source_id
                   WHERE a.channel_id=? AND (
                     a.status='new' OR (
                       a.status='retry' AND (
                         a.next_retry_at IS NULL OR a.next_retry_at='' OR datetime(a.next_retry_at) <= datetime('now')
                       )
                     )
                   )
                   ORDER BY
                     CASE WHEN a.status='new' THEN 0 ELSE 1 END,
                     CASE WHEN a.status='new' THEN s.priority END DESC,
                     CASE WHEN a.status='new' THEN a.id END DESC,
                     CASE WHEN a.status='retry' THEN s.priority END DESC,
                     CASE WHEN a.status='retry' THEN datetime(COALESCE(NULLIF(a.next_retry_at,''),a.discovered_at)) END ASC,
                     a.id DESC
                   LIMIT ?""",
                (channel_id, limit),
            ).fetchall()

    Database._init = db_init
    Database.list_sources = list_sources
    Database.list_sources_with_health = list_sources_with_health
    Database.save_source = save_source
    Database.get_article = get_article
    Database.pending_articles = pending_articles

    def build_sources(self) -> None:
        bar = ui_module.ttk.Frame(self.sources_tab)
        bar.pack(fill="x", pady=(0, 8))
        ui_module.ttk.Button(bar, text="+ Додати джерело", command=self.add_source).pack(side="left", padx=3)
        ui_module.ttk.Button(bar, text="Редагувати", command=self.edit_source).pack(side="left", padx=3)
        ui_module.ttk.Button(bar, text="Видалити", command=self.delete_source).pack(side="left", padx=3)
        ui_module.ttk.Label(
            bar,
            text="Назва, посилання і пріоритет 1–100 обов'язкові. 100 = найвищий.",
        ).pack(side="left", padx=18)
        cols = ("name", "priority", "kind", "url", "enabled", "initialized", "health", "last_new", "yield", "errors", "checked", "error")
        self.sources_tree = ui_module.ttk.Treeview(self.sources_tab, columns=cols, show="headings")
        heads = ("Назва", "Пріоритет", "Тип", "URL", "Активне", "Baseline", "Стан", "Остання нова", "+ за раз", "Помилок", "Остання перевірка", "Остання помилка")
        widths = (145, 75, 75, 240, 65, 65, 105, 135, 70, 70, 135, 220)
        for c, h, w in zip(cols, heads, widths):
            self.sources_tree.heading(c, text=h)
            self.sources_tree.column(c, width=w, anchor="w")
        self.sources_tree.pack(fill="both", expand=True)
        self.sources_tree.bind("<Double-1>", lambda _e: self.edit_source())

    def refresh_sources(self) -> None:
        for item in self.sources_tree.get_children():
            self.sources_tree.delete(item)
        if not self.current_channel_id:
            return
        kind_names = {"telegram": "Telegram", "rss": "RSS/Atom", "page": "Веб"}
        for source, health in self.db.list_sources_with_health(self.current_channel_id):
            if not source.enabled:
                state = "⚪ вимкнено"
            elif source.last_error:
                state = "🔴 помилка"
            elif health.get("last_success_at"):
                state = "🟢 працює"
            elif source.initialized:
                state = "🟡 очікує"
            else:
                state = "⚪ не перевірено"
            self.sources_tree.insert(
                "", "end", iid=str(source.id),
                values=(
                    source.name, source.priority, kind_names.get(source.kind, source.kind), source.url,
                    "так" if source.enabled else "ні", "так" if source.initialized else "ні",
                    state, health.get("last_new_at") or "", health.get("last_inserted_count") or 0,
                    health.get("total_errors") or 0, source.last_checked_at or "", source.last_error or "",
                ),
            )

    def source_dialog(self, src: Source | None) -> None:
        win = ui_module.tk.Toplevel(self.root)
        win.title("Джерело")
        win.transient(self.root)
        win.grab_set()
        win.geometry("720x330")

        ui_module.ttk.Label(win, text="Назва джерела *").pack(anchor="w", padx=12, pady=(12, 2))
        name = ui_module.ttk.Entry(win)
        name.pack(fill="x", padx=12)
        name.insert(0, src.name if src else "")

        ui_module.ttk.Label(win, text="Посилання / URL *").pack(anchor="w", padx=12, pady=(10, 2))
        url = ui_module.ttk.Entry(win)
        url.pack(fill="x", padx=12)
        url.insert(0, src.url if src else "")
        ui_module.ttk.Label(
            win,
            text="Сайт, прямий RSS/Atom або публічний Telegram-канал (t.me/username). Тип визначається автоматично.",
            wraplength=680, foreground="#555",
        ).pack(anchor="w", padx=12, pady=(4, 8))

        ui_module.ttk.Label(win, text="Пріоритет 1–100 * (100 = найвищий)").pack(anchor="w", padx=12, pady=(2, 2))
        priority = ui_module.ttk.Entry(win, width=12)
        priority.pack(anchor="w", padx=12)
        priority.insert(0, str(src.priority if src else PRIORITY_DEFAULT))

        enabled = ui_module.tk.BooleanVar(value=src.enabled if src else True)
        ui_module.ttk.Checkbutton(win, text="Активне", variable=enabled).pack(anchor="w", padx=12, pady=8)
        status = ui_module.tk.StringVar(
            value=("Поточний тип: " + {"telegram": "Telegram", "rss": "RSS/Atom", "page": "вебсторінка"}.get(src.kind, src.kind))
            if src else ""
        )
        ui_module.ttk.Label(win, textvariable=status, foreground="#555").pack(anchor="w", padx=12)

        bottom = ui_module.ttk.Frame(win)
        bottom.pack(fill="x", padx=12, pady=10)
        save_button = ui_module.ttk.Button(bottom, text="Зберегти")
        save_button.pack(side="right")
        ui_module.ttk.Button(bottom, text="Скасувати", command=win.destroy).pack(side="right", padx=6)

        def save() -> None:
            requested_name = name.get().strip()
            raw_url = url.get().strip()
            if not requested_name:
                ui_module.messagebox.showerror(ui_module.APP_NAME, "Вкажіть назву джерела.", parent=win)
                return
            if not raw_url:
                ui_module.messagebox.showerror(ui_module.APP_NAME, "Вставте адресу джерела.", parent=win)
                return
            try:
                requested_priority = normalize_priority(priority.get())
            except ValueError as exc:
                ui_module.messagebox.showerror(ui_module.APP_NAME, str(exc), parent=win)
                return

            save_button.configure(state="disabled")
            status.set("Визначаю тип джерела…")

            def work() -> None:
                try:
                    detected = ui_module.detect_source(raw_url)
                except Exception as exc:
                    self._post_ui(self._source_detection_failed, win, save_button, status, exc)
                    return

                def finish() -> None:
                    try:
                        self.db.save_source(
                            source_id=src.id if src else None,
                            channel_id=self.current_channel_id,
                            kind=detected.kind,
                            name=requested_name,
                            url=detected.url,
                            enabled=enabled.get(),
                            priority=requested_priority,
                        )
                        win.destroy()
                        self.refresh_sources()
                    except Exception as exc:
                        save_button.configure(state="normal")
                        status.set("")
                        ui_module.messagebox.showerror(ui_module.APP_NAME, str(exc), parent=win)

                self._post_ui(finish)

            ui_module.threading.Thread(target=work, daemon=True).start()

        save_button.configure(command=save)
        name.focus_set()

    MainWindow._build_sources = build_sources
    MainWindow.refresh_sources = refresh_sources
    MainWindow._source_dialog = source_dialog
    ui_module.DEFAULT_PROFILE = CTRL_UA_PROFILE

    def hard_blockers(body: str):
        return tuple(dict.fromkeys((*original_hard_blockers(body), *output_refusal_blockers(body))))

    production_module.hard_editorial_blockers = hard_blockers

    def decide(channel, article, recent, **kwargs):
        duplicate = title_event_duplicate(str(_row_value(article, "title", "") or ""), recent)
        if duplicate:
            duplicate_id, reason = duplicate
            return Decision(
                decision="duplicate", duplicate_of=duplicate_id,
                reason=f"Event-level dedupe RC33: {reason} (#{duplicate_id}).",
                event_key="event-title-duplicate-v3", event_summary=str(_row_value(article, "title", "") or "")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.97, provider="local-rule", model="event-dedupe-v3",
            )

        reason = editorial_gate_reason(article)
        if reason:
            return Decision(
                decision="reject", duplicate_of=None, reason=reason,
                event_key="ctrl-ua-audience-gate-v1", event_summary=str(_row_value(article, "title", "") or "")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.98, provider="local-rule", model="ctrl-ua-gate-v1",
            )

        profile = (channel.editorial_profile or "").strip()
        if CTRL_UA_PROFILE not in profile:
            channel = replace(channel, editorial_profile=(profile + "\n\n" + CTRL_UA_PROFILE).strip())
        return original_decide(channel, article, recent, **kwargs)

    production_module.decide = decide
    service_module.decide = decide

    def event_dedupe(current_title: str, current_body: str, recent):
        match = original_event_dedupe(current_title, current_body, recent)
        if match is not None:
            return match
        fallback = title_event_duplicate(current_title, list(recent))
        if not fallback:
            return None
        article_id, reason = fallback
        return event_dedupe_module.DuplicateMatch(article_id=article_id, score=0.88, reason=reason)

    event_dedupe_module.find_event_duplicate = event_dedupe
    service_module.find_event_duplicate = event_dedupe

    def source_link_entities(text: str, source_url: str) -> str:
        url = str(source_url or "").strip()
        value = str(text or "")
        if not url:
            return ""
        matches = list(re.finditer(r"(?m)^Джерело$", value))
        if not matches:
            return ""
        match = matches[-1]
        entity = [{
            "type": "text_link",
            "offset": telegram_module._utf16_units(value[:match.start()]),
            "length": telegram_module._utf16_units("Джерело"),
            "url": url,
        }]
        return json.dumps(entity, ensure_ascii=False, separators=(",", ":"))

    telegram_module._source_link_entities = source_link_entities

    def build_post_text(text_or_internal_headline: str, body: str | None = None, **kwargs) -> str:
        source_text = body if body is not None else text_or_internal_headline
        core, video_url = split_video_footer(str(source_text or ""))
        if body is not None:
            built = original_build_post_text(text_or_internal_headline, core, **kwargs)
        else:
            built = original_build_post_text(core, **kwargs)
        if video_url:
            built = built.rstrip() + f"\n\n🎬 Відео: {video_url}"
        hard_limit = int(kwargs.get("hard_limit", 900))
        if len(built) > hard_limit:
            raise telegram_module.TelegramError(
                f"Telegram-пост перевищує ліміт {hard_limit} символів.", retryable=False
            )
        return built

    telegram_module.build_post_text = build_post_text
    service_module.build_post_text = build_post_text

    def request(token: str, method: str, fields: dict[str, str], **kwargs):
        return original_request(token, method, media_first_fields(method, fields), **kwargs)

    def request_file(token: str, method: str, fields: dict[str, str], **kwargs):
        return original_request_file(token, method, media_first_fields(method, fields), **kwargs)

    telegram_module._request = request
    telegram_module._request_file = request_file

    def send_video_url(token: str, chat_id: str, caption: str, video_url: str, **kwargs):
        clean_caption, _ = split_video_footer(caption)
        return original_send_video_url(token, chat_id, clean_caption, video_url, **kwargs)

    telegram_module.send_video_url = send_video_url
    service_module.send_video_url = send_video_url

    production_module.POST_FORMAT_PREFIX = POST_FORMAT_PREFIX_RC33
    service_module.POST_FORMAT_PREFIX = POST_FORMAT_PREFIX_RC33

    _INSTALLED = True
