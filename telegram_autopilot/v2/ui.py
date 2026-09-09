from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..codex_engine import inspect_codex, login_chatgpt, test_codex
from .domain import ChannelConfig, ChannelMode, ChannelPolicy
from .migration_service import MigrationManager
from .runtime import RuntimeEngine
from .storage import V2Store


STAGE_UA = {
    "COLLECTED": "Зібрано",
    "EXTRACTED": "Витягнуто",
    "DEDUPED": "Перевірено дубль",
    "SELECTED": "Відібрано",
    "WRITTEN": "Написано",
    "QA_PASSED": "QA пройдено",
    "READY": "Готово",
    "PUBLISHED": "Опубліковано",
    "ARCHIVED": "Архів",
}
DECISION_UA = {
    "PENDING": "Очікує",
    "PUBLISH": "До публікації",
    "REJECT": "Відхилено",
    "DUPLICATE": "Дубль",
}
BLOCK_UA = {
    "NONE": "—",
    "AI": "AI",
    "SOURCE": "Джерело",
    "MEDIA": "Медіа",
    "TELEGRAM": "Telegram",
    "CONFIG": "Налаштування",
    "QUALITY": "Якість",
}
PROVIDER_UA = {
    "UNKNOWN": "Невідомо",
    "HEALTHY": "Працює",
    "RATE_LIMIT": "Обмеження частоти",
    "QUOTA": "Вичерпано квоту",
    "NETWORK_DOWN": "Немає мережі",
    "TIMEOUT": "Тайм-аут",
    "AUTH_ERROR": "Помилка доступу",
    "MODEL_UNSUPPORTED": "Модель недоступна",
    "CONFIG_ERROR": "Не налаштовано",
}


class ChannelDialog(tk.Toplevel):
    def __init__(self, master, store: V2Store, channel_id: int, on_saved):
        super().__init__(master)
        self.store = store
        self.channel_id = channel_id
        self.on_saved = on_saved
        self.title("Налаштування каналу · V2")
        self.geometry("900x760")
        self.transient(master)
        self.grab_set()
        cfg = store.get_channel(channel_id)
        if cfg is None:
            self.destroy()
            return
        self.cfg = cfg
        self.vars: dict[str, object] = {}
        book = ttk.Notebook(self)
        book.pack(fill="both", expand=True, padx=10, pady=10)
        basic, policy, editorial = ttk.Frame(book), ttk.Frame(book), ttk.Frame(book)
        book.add(basic, text="Основне")
        book.add(policy, text="Політика")
        book.add(editorial, text="Редакційне")
        self._build_basic(basic, cfg)
        self._build_policy(policy, cfg)
        self._build_editorial(editorial, cfg)
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(footer, text="Зберегти канал", command=self._save).pack(side="right")
        ttk.Button(footer, text="Скасувати", command=self.destroy).pack(side="right", padx=8)

    def _entry(self, parent, row, label, value, width=42):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=5)
        var = tk.StringVar(value=str(value))
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="ew", padx=6, pady=5)
        self.vars[label] = var
        parent.columnconfigure(1, weight=1)
        return var

    def _check(self, parent, row, label, value):
        var = tk.BooleanVar(value=bool(value))
        ttk.Checkbutton(parent, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=5)
        self.vars[label] = var
        return var

    def _combo(self, parent, row, label, value, values):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=5)
        var = tk.StringVar(value=str(value))
        ttk.Combobox(parent, textvariable=var, values=values, state="readonly").grid(row=row, column=1, sticky="ew", padx=6, pady=5)
        self.vars[label] = var
        return var

    def _build_basic(self, p, cfg):
        self._entry(p, 0, "Назва", cfg.name)
        self._entry(p, 1, "Telegram Chat ID / @username", cfg.telegram_chat_id)
        self._check(p, 2, "Канал увімкнено", cfg.enabled)
        self._combo(p, 3, "Режим", str(cfg.mode), ["editorial", "monitoring"])
        self._entry(p, 4, "Опитування, хв", cfg.poll_interval_minutes)
        self._entry(p, 5, "Мін. інтервал публікацій, хв", cfg.min_publish_interval_minutes)
        self._entry(p, 6, "Вікно дедуплікації, год", cfg.dedupe_window_hours)
        self._entry(p, 7, "Макс. вік матеріалу, год", cfg.max_age_hours)
        self._entry(p, 8, "Макс. постів за цикл", cfg.max_posts_per_cycle)
        self._check(p, 9, "Публікація 24/7", cfg.publish_24h)
        self._entry(p, 10, "Початок публікацій", cfg.publish_start)
        self._entry(p, 11, "Кінець публікацій", cfg.publish_end)
        self._check(p, 12, "Публікувати готове одразу (але не обходити мінімальний інтервал)", cfg.publish_immediately)
        self._combo(p, 13, "Мова", cfg.language_mode, ["ukru_to_uk", "uk_to_uk", "ru_to_uk", "en_to_uk", "ukru_to_en"])
        self._combo(p, 14, "Медіа-збагачення", cfg.media_enrichment_mode, ["auto", "off"])
        self._check(p, 15, "Дозволити media-first", cfg.media_first_allowed)
        self._entry(p, 16, "Media-first поріг тексту", cfg.media_min_text_chars)
        ttk.Label(p, text="Джерело є обов'язковим для READY/PUBLISH і не може бути вимкнене.").grid(row=17, column=0, columnspan=2, sticky="w", padx=6, pady=10)

    def _text(self, parent, row, label, value, height=6):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", padx=6, pady=5)
        box = tk.Text(parent, height=height, wrap="word")
        box.insert("1.0", str(value or ""))
        box.grid(row=row, column=1, sticky="nsew", padx=6, pady=5)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(row, weight=1)
        self.vars[label] = box
        return box

    def _get(self, label):
        obj = self.vars[label]
        return obj.get("1.0", "end").strip() if isinstance(obj, tk.Text) else obj.get()

    def _build_policy(self, p, cfg):
        q = cfg.policy
        self._text(p, 0, "Мета каналу", q.purpose, 4)
        self._text(p, 1, "Аудиторія", q.audience, 3)
        self._text(p, 2, "Що включати", q.selection_rules, 7)
        self._text(p, 3, "Що виключати", q.rejection_rules, 7)
        self._text(p, 4, "Додатковий prompt selector", q.selector_extra_prompt, 4)

    def _build_editorial(self, p, cfg):
        q = cfg.policy
        self._text(p, 0, "Правила написання", q.writing_rules, 7)
        self._text(p, 1, "Стиль", q.style_rules, 6)
        self._text(p, 2, "Позитивні приклади", q.positive_examples, 5)
        self._text(p, 3, "Негативні приклади", q.negative_examples, 5)
        self._text(p, 4, "Додаткові інструкції", q.extra_instructions, 4)
        self._text(p, 5, "Додатковий prompt writer", q.writer_extra_prompt, 4)
        self._combo(p, 6, "Політика медіа", q.media_policy, ["required", "preferred", "optional"])
        self._entry(p, 7, "Мін. символів", q.target_min_chars)
        self._entry(p, 8, "Макс. символів", q.target_max_chars)
        self._text(p, 9, "Редакційні ваги JSON", cfg.editorial_weights_json, 4)

    def _save(self):
        try:
            old = self.cfg
            policy = ChannelPolicy(
                channel_id=old.id,
                enabled=True,
                purpose=self._get("Мета каналу"),
                audience=self._get("Аудиторія"),
                selection_rules=self._get("Що включати"),
                rejection_rules=self._get("Що виключати"),
                writing_rules=self._get("Правила написання"),
                style_rules=self._get("Стиль"),
                positive_examples=self._get("Позитивні приклади"),
                negative_examples=self._get("Негативні приклади"),
                extra_instructions=self._get("Додаткові інструкції"),
                selector_extra_prompt=self._get("Додатковий prompt selector"),
                writer_extra_prompt=self._get("Додатковий prompt writer"),
                media_policy=self._get("Політика медіа"),
                target_min_chars=int(self._get("Мін. символів")),
                target_max_chars=int(self._get("Макс. символів")),
            )
            cfg = ChannelConfig(
                id=old.id,
                name=self._get("Назва"),
                telegram_chat_id=self._get("Telegram Chat ID / @username"),
                enabled=bool(self._get("Канал увімкнено")),
                mode=ChannelMode(self._get("Режим")),
                editorial_profile=old.editorial_profile,
                include_source_link=True,
                source_link_required=True,
                poll_interval_minutes=int(self._get("Опитування, хв")),
                poll_immediate=old.poll_immediate,
                min_publish_interval_minutes=int(self._get("Мін. інтервал публікацій, хв")),
                dedupe_window_hours=int(self._get("Вікно дедуплікації, год")),
                max_age_hours=int(self._get("Макс. вік матеріалу, год")),
                max_posts_per_cycle=int(self._get("Макс. постів за цикл")),
                publish_24h=bool(self._get("Публікація 24/7")),
                publish_start=self._get("Початок публікацій"),
                publish_end=self._get("Кінець публікацій"),
                publish_immediately=bool(self._get("Публікувати готове одразу (але не обходити мінімальний інтервал)")),
                topic_balance_enabled=old.topic_balance_enabled,
                topic_daily_limit=old.topic_daily_limit,
                related_spacing_posts=old.related_spacing_posts,
                editorial_weights_json=self._get("Редакційні ваги JSON") or "[]",
                language_mode=self._get("Мова"),
                media_enrichment_mode=self._get("Медіа-збагачення"),
                media_first_allowed=bool(self._get("Дозволити media-first")),
                media_min_text_chars=int(self._get("Media-first поріг тексту")),
                policy=policy,
            )
            json.loads(cfg.editorial_weights_json)
            self.store.save_channel(cfg)
            self.on_saved()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Не збережено", str(exc), parent=self)


class SourceDialog(tk.Toplevel):
    def __init__(self, master, store: V2Store, channel_id: int, on_saved):
        super().__init__(master)
        self.store = store
        self.channel_id = channel_id
        self.on_saved = on_saved
        self.title("Джерела каналу")
        self.geometry("820x460")
        self.transient(master)
        self.grab_set()
        self.tree = ttk.Treeview(self, columns=("id", "kind", "name", "url", "enabled", "error"), show="headings")
        for col, label, width in (("id", "ID", 55), ("kind", "Тип", 90), ("name", "Назва", 170), ("url", "URL", 300), ("enabled", "Увімк.", 65), ("error", "Остання помилка", 220)):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="Додати", command=self._add).pack(side="left")
        ttk.Button(bar, text="Редагувати", command=self._edit).pack(side="left", padx=6)
        ttk.Button(bar, text="Увімк./вимк.", command=self._toggle).pack(side="left")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in self.store.sources_for_channel(self.channel_id, enabled_only=False):
            self.tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["kind"], row["name"], row["url"], "так" if row["enabled"] else "ні", str(row["last_error"] or "")[:160]))

    def _prompt(self, row=None):
        win = tk.Toplevel(self)
        win.title("Джерело")
        win.transient(self)
        win.grab_set()
        vars: dict[str, tk.StringVar] = {}
        values = (("Тип", row["kind"] if row else "rss"), ("Назва", row["name"] if row else ""), ("URL", row["url"] if row else ""), ("Пріоритет", row["priority"] if row else 100))
        for i, (label, value) in enumerate(values):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=6)
            var = tk.StringVar(value=str(value))
            vars[label] = var
            widget = ttk.Combobox(win, textvariable=var, values=["rss", "page", "telegram"], state="readonly") if label == "Тип" else ttk.Entry(win, textvariable=var, width=60)
            widget.grid(row=i, column=1, sticky="ew", padx=8, pady=6)
        saved = {"ok": False}

        def save():
            try:
                with self.store.connect() as con:
                    if row:
                        con.execute("UPDATE sources SET kind=?,name=?,url=?,priority=? WHERE id=?", (vars["Тип"].get(), vars["Назва"].get().strip(), vars["URL"].get().strip(), int(vars["Пріоритет"].get()), int(row["id"])))
                    else:
                        con.execute("INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(?,?,?,?,1,?)", (self.channel_id, vars["Тип"].get(), vars["Назва"].get().strip(), vars["URL"].get().strip(), int(vars["Пріоритет"].get())))
                saved["ok"] = True
                win.destroy()
            except Exception as exc:
                messagebox.showerror("Помилка", str(exc), parent=win)

        ttk.Button(win, text="Зберегти", command=save).grid(row=5, column=1, sticky="e", padx=8, pady=8)
        self.wait_window(win)
        return saved["ok"]

    def _selected(self):
        ids = self.tree.selection()
        return int(ids[0]) if ids else None

    def _add(self):
        if self._prompt():
            self.refresh()
            self.on_saved()

    def _edit(self):
        sid = self._selected()
        if sid is None:
            return
        with self.store.connect() as con:
            row = con.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        if row and self._prompt(row):
            self.refresh()
            self.on_saved()

    def _toggle(self):
        sid = self._selected()
        if sid is None:
            return
        with self.store.connect() as con:
            con.execute("UPDATE sources SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (sid,))
        self.refresh()
        self.on_saved()


class MainWindow(tk.Tk):
    def __init__(self, store: V2Store, runtime: RuntimeEngine, logs_dir: Path):
        super().__init__()
        self.store = store
        self.runtime = runtime
        self.logs_dir = Path(logs_dir)
        self.title("UA FREE Telegram Autopilot V2")
        self.geometry("1320x820")
        self.migration = MigrationManager(store.path)
        self._running = False
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        self.status = tk.StringVar(value="Автопілот зупинено")
        ttk.Label(top, textvariable=self.status).pack(side="left")
        ttk.Button(top, text="Старт", command=self.start_runtime).pack(side="right")
        ttk.Button(top, text="Стоп", command=self.stop_runtime).pack(side="right", padx=5)
        ttk.Button(top, text="Тест усіх AI", command=self.test_ai).pack(side="right", padx=5)
        self.book = ttk.Notebook(self)
        self.book.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tabs = {}
        for key, title in (("home", "Головна"), ("channels", "Канали"), ("queue", "Черга"), ("history", "Історія"), ("ai", "AI"), ("migration", "Міграція"), ("logs", "Журнали")):
            frame = ttk.Frame(self.book)
            self.book.add(frame, text=title)
            self.tabs[key] = frame
        self._build_home()
        self._build_channels()
        self._build_queue()
        self._build_history()
        self._build_ai()
        self._build_migration()
        self._build_logs()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(800, self.refresh_all)

    def _build_home(self):
        self.home_text = tk.Text(self.tabs["home"], wrap="word", state="disabled", font=("TkDefaultFont", 11))
        self.home_text.pack(fill="both", expand=True, padx=10, pady=10)

    def _tree(self, parent, columns):
        tree = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings")
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        return tree

    def _build_channels(self):
        self.channel_tree = self._tree(self.tabs["channels"], [("id", "ID", 55), ("name", "Канал", 270), ("mode", "Режим", 110), ("enabled", "Увімк.", 70), ("sources", "Джерел", 70), ("policy", "Політика", 400)])
        bar = ttk.Frame(self.tabs["channels"])
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text="Редагувати канал", command=self.edit_channel).pack(side="left")
        ttk.Button(bar, text="Джерела", command=self.edit_sources).pack(side="left", padx=6)

    def _build_queue(self):
        filterbar = ttk.Frame(self.tabs["queue"])
        filterbar.pack(fill="x", padx=8, pady=6)
        ttk.Label(filterbar, text="Статус:").pack(side="left")
        self.queue_filter = tk.StringVar(value="Усі")
        ttk.Combobox(filterbar, textvariable=self.queue_filter, state="readonly", values=["Усі", "Очікує", "Готово", "Заблоковано AI", "Заблоковано джерелом", "Заблоковано медіа", "Проблема якості"], width=28).pack(side="left", padx=6)
        self.queue_filter.trace_add("write", lambda *_: self.refresh_queue())
        self.queue_tree = self._tree(self.tabs["queue"], [("id", "ID", 60), ("channel", "Канал", 180), ("stage", "Етап", 125), ("decision", "Рішення", 120), ("blocked", "Блокер", 125), ("title", "Матеріал", 420), ("detail", "Деталі", 420)])

    def _build_history(self):
        self.history_tree = self._tree(self.tabs["history"], [("id", "ID", 60), ("channel", "Канал", 180), ("status", "Статус", 120), ("title", "Матеріал", 430), ("published", "Опубліковано", 170), ("source", "Джерело", 320)])

    def _build_ai(self):
        panel = self.tabs["ai"]
        bar = ttk.Frame(panel)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        self.codex_status = tk.StringVar(value="Codex: перевіряється…")
        ttk.Label(bar, textvariable=self.codex_status).pack(side="left")
        ttk.Button(bar, text="Перевірити Codex", command=self.check_codex).pack(side="right")
        ttk.Button(bar, text="Увійти через ChatGPT", command=self.login_codex).pack(side="right", padx=6)
        self.ai_tree = self._tree(panel, [("provider", "Провайдер", 120), ("state", "Стан", 180), ("model", "Модель", 280), ("success", "Успіхів", 80), ("fail", "Помилок", 80), ("cooldown", "Пауза до", 180), ("detail", "Деталі", 420)])
        self.after(400, self.refresh_codex_status)

    def _build_migration(self):
        p = self.tabs["migration"]
        text = "Імпорт читає стару Data ТІЛЬКИ read-only. Перед заміною V2 БД створюється backup. Переносяться канали, правила, ваги, джерела, published history, dedupe/feedback та зашифровані credentials. Не переносяться cooldown, retry, worker state, RC markers та transient errors. Codex SDK у RC4 входить до самого portable і не залежить від старої Data."
        ttk.Label(p, text=text, wraplength=980, justify="left").pack(anchor="w", padx=12, pady=12)
        self.migration_status = tk.StringVar(value="")
        ttk.Button(p, text="Імпортувати стару Data", command=self.import_legacy).pack(anchor="w", padx=12, pady=5)
        ttk.Button(p, text="Створити export-bundle старої Data", command=self.export_legacy).pack(anchor="w", padx=12, pady=5)
        ttk.Label(p, textvariable=self.migration_status, wraplength=1050, justify="left").pack(anchor="w", padx=12, pady=12)

    def _build_logs(self):
        p = self.tabs["logs"]
        ttk.Label(p, text=f"Окремі ротаційні журнали: {self.logs_dir}", wraplength=1000).pack(anchor="w", padx=12, pady=12)
        ttk.Button(p, text="Відкрити папку журналів", command=self.open_logs).pack(anchor="w", padx=12)

    def start_runtime(self):
        if self._running:
            return
        self.runtime.start()
        self._running = True
        self.status.set("Автопілот запускається")
        self.refresh_all()

    def stop_runtime(self):
        if not self._running:
            return
        self.runtime.stop()
        self._running = False
        self.status.set("Автопілот зупинено")
        self.refresh_all()

    def test_ai(self):
        self.status.set("Перевіряю AI…")

        def work():
            try:
                self.runtime.gateway.probe_all()
                msg = "Перевірку AI завершено"
            except Exception as exc:
                msg = f"Помилка тесту AI: {exc}"
            self.after(0, lambda: (self.status.set(msg), self.refresh_ai(), self.refresh_codex_status(), self.refresh_home()))

        threading.Thread(target=work, daemon=True, name="V2-AI-Probe").start()

    def refresh_codex_status(self):
        def work():
            status = inspect_codex()
            if not status.installed:
                text = "Codex: SDK відсутній або пошкоджений"
            elif status.authenticated:
                account = f" · {status.account_label}" if status.account_label else ""
                text = f"Codex {status.version or '0.147.0'}: готовий{account}"
            else:
                text = f"Codex {status.version or '0.147.0'}: потрібен вхід через ChatGPT"
            self.after(0, lambda: self.codex_status.set(text))

        threading.Thread(target=work, daemon=True, name="V2-Codex-Status").start()

    def login_codex(self):
        self.codex_status.set("Codex: відкриваю вхід через ChatGPT…")

        def work():
            try:
                login_chatgpt()
                msg = "Codex: вхід через ChatGPT завершено"
                try:
                    self.runtime.gateway.probe_all()
                except Exception:
                    pass
            except Exception as exc:
                msg = f"Codex: помилка входу: {exc}"
            self.after(0, lambda: (self.codex_status.set(msg), self.refresh_codex_status(), self.refresh_ai(), self.refresh_home()))

        threading.Thread(target=work, daemon=True, name="V2-Codex-Login").start()

    def check_codex(self):
        self.codex_status.set("Codex: виконую живий тест…")

        def work():
            try:
                msg = test_codex()
                try:
                    self.runtime.gateway.probe_all()
                except Exception:
                    pass
            except Exception as exc:
                msg = f"Codex: тест не пройдено: {exc}"
            self.after(0, lambda: (self.codex_status.set(msg), self.refresh_ai(), self.refresh_home()))

        threading.Thread(target=work, daemon=True, name="V2-Codex-Test").start()

    def refresh_all(self):
        try:
            self.refresh_home()
            self.refresh_channels()
            self.refresh_queue()
            self.refresh_history()
            self.refresh_ai()
        finally:
            self.after(2500, self.refresh_all)

    def refresh_home(self):
        snap = self.runtime.health_snapshot()
        alive = sum(1 for value in snap["channels"].values() if value["alive"])
        healthy = sum(1 for value in snap["providers"] if value["state"] == "HEALTHY")
        configured = sum(1 for value in snap["providers"] if not (value["state"] == "CONFIG_ERROR" and str(value.get("detail", "")).casefold().startswith("не налаштовано")))
        with self.store.connect() as con:
            counts = {row[0]: row[1] for row in con.execute("SELECT stage,COUNT(*) FROM articles GROUP BY stage")}
            rejected = con.execute("SELECT COUNT(*) FROM articles WHERE decision='REJECT'").fetchone()[0]
            waiting = con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','WAITING','LEASED')").fetchone()[0]
            blocked = {
                row[0]: row[1]
                for row in con.execute(
                    """
                    SELECT a.blocked_by, COUNT(DISTINCT j.article_id)
                    FROM jobs j
                    JOIN articles a ON a.id=j.article_id
                    WHERE j.state IN ('QUEUED','WAITING','LEASED')
                      AND a.blocked_by IS NOT NULL
                      AND a.blocked_by <> 'NONE'
                    GROUP BY a.blocked_by
                    """
                )
            }
        ai_blocked = int(blocked.get("AI", 0) or 0)
        if self._running:
            if healthy == 0 and ai_blocked:
                self.status.set("Автопілот: AI пауза, workers активні")
            elif alive == 0:
                self.status.set("Автопілот: workers не працюють")
            else:
                self.status.set("Автопілот працює")
        provider_total = len(snap["providers"])
        configured_text = f"{configured} налаштовано" if provider_total else "стан ще не перевірено"
        blockers_text = ", ".join(f"{BLOCK_UA.get(key, key)}={value}" for key, value in blocked.items()) or "немає активних"
        text = (
            "UA FREE Telegram Autopilot V2\n\n"
            f"Канали: {alive}/{len(snap['channels'])} workers активні\n"
            f"AI: {healthy}/{provider_total} healthy · {configured_text}\n"
            f"Черга: {waiting}\n"
            f"Опубліковано: {counts.get('PUBLISHED', 0)}\n"
            f"Готово: {counts.get('READY', 0)}\n"
            f"Відхилено: {rejected}\n\n"
            f"Активні блокери: {blockers_text}"
        )
        self.home_text.configure(state="normal")
        self.home_text.delete("1.0", "end")
        self.home_text.insert("1.0", text)
        self.home_text.configure(state="disabled")

    def refresh_channels(self):
        self.channel_tree.delete(*self.channel_tree.get_children())
        for row in self.store.list_channels():
            cfg = self.store.get_channel(int(row["id"]))
            sources = len(self.store.sources_for_channel(int(row["id"]), enabled_only=False))
            policy = (cfg.policy.selection_rules[:180] + "…") if cfg and len(cfg.policy.selection_rules) > 180 else (cfg.policy.selection_rules if cfg else "")
            self.channel_tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["name"], "Моніторинг" if str(row["channel_mode"]) == "monitoring" else "Редакційний", "так" if row["enabled"] else "ні", sources, policy))

    def refresh_queue(self):
        self.queue_tree.delete(*self.queue_tree.get_children())
        where = "a.stage NOT IN ('PUBLISHED','ARCHIVED') AND a.decision NOT IN ('REJECT','DUPLICATE')"
        args: list[object] = []
        selected = self.queue_filter.get()
        if selected == "Готово":
            where += " AND a.stage='READY'"
        elif selected == "Заблоковано AI":
            where += " AND a.blocked_by='AI'"
        elif selected == "Заблоковано джерелом":
            where += " AND a.blocked_by='SOURCE'"
        elif selected == "Заблоковано медіа":
            where += " AND a.blocked_by='MEDIA'"
        elif selected == "Проблема якості":
            where += " AND a.blocked_by='QUALITY'"
        elif selected == "Очікує":
            where += " AND a.decision='PENDING'"
        with self.store.connect() as con:
            rows = con.execute(f"SELECT a.*,c.name channel_name FROM articles a JOIN channels c ON c.id=a.channel_id WHERE {where} ORDER BY a.id DESC LIMIT 500", args).fetchall()
        for row in rows:
            self.queue_tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["channel_name"], STAGE_UA.get(row["stage"], row["stage"]), DECISION_UA.get(row["decision"], row["decision"]), BLOCK_UA.get(row["blocked_by"], row["blocked_by"]), str(row["title"] or "")[:240], str(row["last_error_detail"] or row["status_detail"] or "")[:260]))

    def refresh_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        with self.store.connect() as con:
            rows = con.execute("SELECT a.*,c.name channel_name FROM articles a JOIN channels c ON c.id=a.channel_id WHERE a.stage='PUBLISHED' OR a.decision IN ('REJECT','DUPLICATE') ORDER BY a.id DESC LIMIT 600").fetchall()
        for row in rows:
            status = "Опубліковано" if row["stage"] == "PUBLISHED" else DECISION_UA.get(row["decision"], row["decision"])
            self.history_tree.insert("", "end", values=(row["id"], row["channel_name"], status, str(row["title"] or "")[:260], row["published_at"], row["canonical_source_url"]))

    def refresh_ai(self):
        self.ai_tree.delete(*self.ai_tree.get_children())
        for health in self.store.provider_health():
            self.ai_tree.insert("", "end", iid=health.provider, values=(health.provider, PROVIDER_UA.get(str(health.state), str(health.state)), health.model, health.success_count, health.failure_count, health.cooldown_until, health.detail[:300]))

    def _selected_channel(self):
        ids = self.channel_tree.selection()
        return int(ids[0]) if ids else None

    def edit_channel(self):
        cid = self._selected_channel()
        if cid is not None:
            ChannelDialog(self, self.store, cid, lambda: (self.refresh_channels(), self.runtime.refresh_channels()))

    def edit_sources(self):
        cid = self._selected_channel()
        if cid is not None:
            SourceDialog(self, self.store, cid, self.refresh_channels)

    def import_legacy(self):
        path = filedialog.askdirectory(title="Оберіть стару папку Data або portable-папку")
        if not path:
            return
        if not messagebox.askyesno("Імпорт V2", "Автопілот буде зупинено. Поточна V2 БД, якщо є, буде збережена в backup. Стару Data програма відкриє тільки read-only. Продовжити?"):
            return
        self.stop_runtime()
        self.migration_status.set("Імпортую…")

        def work():
            try:
                report, backup, cred = self.migration.import_legacy_atomic(path, import_credentials=True, overwrite_credentials=False)
                msg = f"Готово. Канали {report.channels_imported}/{report.channels_total}; джерела {report.sources_imported}/{report.sources_total}; матеріали {report.articles_imported}/{report.articles_total}; published {report.published_imported}; re-evaluate {report.pending_reevaluation}; archive {report.archived_unpublished}. {cred}. Warnings: {'; '.join(report.warnings) or 'немає'}. Backup: {backup or 'не потрібен'}"
            except Exception as exc:
                msg = "ПОМИЛКА ІМПОРТУ: " + str(exc)
            self.after(0, lambda: (self.migration_status.set(msg), self.refresh_all()))

        threading.Thread(target=work, daemon=True, name="V2-Migration").start()

    def export_legacy(self):
        path = filedialog.askdirectory(title="Оберіть стару Data")
        if not path:
            return
        out = filedialog.asksaveasfilename(title="Зберегти export bundle", defaultextension=".zip", filetypes=[("ZIP", "*.zip")], initialfile="UA_FREE_Autopilot_Legacy_Export.zip")
        if not out:
            return
        try:
            self.migration.export_legacy(path, out)
            self.migration_status.set(f"Export bundle створено: {out}")
        except Exception as exc:
            messagebox.showerror("Помилка export", str(exc))

    def open_logs(self):
        try:
            if os.name == "nt":
                os.startfile(self.logs_dir)  # type: ignore[attr-defined]
            else:
                messagebox.showinfo("Журнали", str(self.logs_dir))
        except Exception as exc:
            messagebox.showerror("Помилка", str(exc))

    def _close(self):
        try:
            self.stop_runtime()
        finally:
            self.destroy()
