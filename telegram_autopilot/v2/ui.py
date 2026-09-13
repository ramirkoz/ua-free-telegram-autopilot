from __future__ import annotations

import json
import os
import statistics
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..codex_engine import inspect_codex, login_chatgpt, test_codex
from ..secrets_store import load_secrets
from .domain import ChannelConfig, ChannelMode, ChannelPolicy
from .feedback import FeedbackRuntime, FeedbackService, analytics_configured, authorize_telegram_analytics, save_analytics_credentials
from .learning import LearningEngine, audience_performance_score, audience_raw_rate, topic_feedback_signal
from .migration_service import MigrationManager
from .runtime import RuntimeEngine
from .storage import V2Store
from .supervisor import SupervisorConfig, SupervisorService


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
        ttk.Label(p, text="RC18: required/preferred/optional задаєте ви. Telegram-аватари/логотипи та video thumbnails не вважаються медіа поста. 1 реальне медіа публікується з caption до 900 символів; кілька різних реальних медіа — як Telegram-альбом з тим самим caption.", wraplength=760, foreground="#444").grid(row=9, column=0, columnspan=2, sticky="w", padx=6, pady=8)
        self._text(p, 10, "Редакційні ваги JSON", cfg.editorial_weights_json, 4)

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
        self.tree.bind("<Double-1>", lambda _e: self._edit())
        self.tree.bind("<Return>", lambda _e: self._edit())
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="Додати", command=self._add).pack(side="left")
        ttk.Button(bar, text="Редагувати", command=self._edit).pack(side="left", padx=6)
        ttk.Button(bar, text="Увімк./вимк.", command=self._toggle).pack(side="left")
        self.refresh()

    def refresh(self):
        selected = self.tree.selection()
        wanted = selected[0] if selected else ""
        self.tree.delete(*self.tree.get_children())
        for row in self.store.sources_for_channel(self.channel_id, enabled_only=False):
            self.tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["kind"], row["name"], row["url"], "так" if row["enabled"] else "ні", str(row["last_error"] or "")[:160]))
        children = self.tree.get_children()
        target = wanted if wanted in children else (children[0] if children else "")
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)

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
        if ids:
            return int(ids[0])
        children = self.tree.get_children()
        if not children:
            return None
        self.tree.selection_set(children[0])
        self.tree.focus(children[0])
        return int(children[0])

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
        self.supervisor = SupervisorService(store, runtime, logs_dir)
        self.feedback = FeedbackService(store)
        self.feedback_runtime = FeedbackRuntime(self.feedback, store)
        self.learning = LearningEngine(store)
        self._running = False
        self._startup_ready = True
        self._feedback_ready = False
        self._learning_refresh_inflight = False
        self._refresh_after_id = None
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        self.status = tk.StringVar(value="Автопілот зупинено")
        ttk.Label(top, textvariable=self.status).pack(side="left")
        self.start_button = ttk.Button(top, text="Старт", command=self.start_runtime)
        self.start_button.pack(side="right")
        ttk.Button(top, text="Стоп", command=self.stop_runtime).pack(side="right", padx=5)
        ttk.Button(top, text="Тест усіх AI", command=self.test_ai).pack(side="right", padx=5)
        self.book = ttk.Notebook(self)
        self.book.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tabs = {}
        for key, title in (("home", "Головна"), ("channels", "Канали"), ("queue", "Черга"), ("history", "Історія"), ("ai", "AI"), ("learning", "Статистика / навчання"), ("supervisor", "Нагляд"), ("migration", "Міграція"), ("logs", "Журнали")):
            frame = ttk.Frame(self.book)
            self.book.add(frame, text=title)
            self.tabs[key] = frame
        self._build_home()
        self._build_channels()
        self._build_queue()
        self._build_history()
        self._build_ai()
        self._build_learning()
        self._build_supervisor()
        self._build_migration()
        self._build_logs()
        self.supervisor.start()
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
        self.channel_tree.bind("<Double-1>", lambda _e: self.edit_channel())
        self.channel_tree.bind("<Return>", lambda _e: self.edit_channel())
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

    def _build_learning(self):
        p = self.tabs["learning"]
        top = ttk.Frame(p)
        top.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(top, text="Канал:").pack(side="left")
        self.learning_channel_var = tk.StringVar(value="")
        self.learning_channel_combo = ttk.Combobox(top, textvariable=self.learning_channel_var, state="readonly", width=34)
        self.learning_channel_combo.pack(side="left", padx=6)
        self.learning_channel_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_learning())
        self.learning_setup_button = ttk.Button(top, text="Налаштувати Telegram Analytics", command=self.learning_setup_analytics)
        self.learning_setup_button.pack(side="right", padx=4)
        self.learning_refresh_all_button = ttk.Button(top, text="Оновити всю історію (7 днів)", command=lambda: self.learning_refresh_metrics(force=True))
        self.learning_refresh_all_button.pack(side="right", padx=4)
        self.learning_refresh_button = ttk.Button(top, text="Оновити статистику", command=lambda: self.learning_refresh_metrics(force=False))
        self.learning_refresh_button.pack(side="right", padx=4)

        self.learning_status = tk.StringVar(value="Модуль статистики готується…")
        ttk.Label(p, textvariable=self.learning_status, wraplength=1220, justify="left", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=10, pady=(4, 4))
        ttk.Label(
            p,
            text=(
                "МОДУЛЬ ОЦІНЮВАННЯ: MTProto читає перегляди, пересилання, відповіді та реакції. "
                "Реакції адміністраторів відокремлюються від реакцій аудиторії. "
                "МОДУЛЬ НАВЧАННЯ: 👍/👎 адміністраторів навчають відбору тем, 🔥 навчає стилю написання. "
                "Аудиторія впливає на теми м'яко після нормалізації на перегляди і ніколи напряму не навчає стиль."
            ),
            wraplength=1220, justify="left", foreground="#444",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.learning_summary = tk.StringVar(value="")
        ttk.Label(p, textvariable=self.learning_summary, wraplength=1220, justify="left", foreground="#555").pack(anchor="w", padx=10, pady=(0, 5))
        self.learning_tree = self._tree(p, [
            ("id", "ID", 55), ("post", "Пост", 390), ("age", "Опубліковано", 145),
            ("alike", "Адм 👍", 60), ("adis", "Адм 👎", 60), ("afire", "Адм 🔥", 60),
            ("audience", "Audience", 80), ("views", "Перегл.", 75), ("react", "Реакції", 75),
            ("fwd", "Пересл.", 65), ("reply", "Відп.", 60), ("coverage", "Покриття", 120),
        ])
        bar = ttk.Frame(p)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        self.learning_refresh_one_button = ttk.Button(bar, text="Оновити вибрану публікацію", command=self.learning_refresh_selected)
        self.learning_refresh_one_button.pack(side="left")
        ttk.Label(bar, text="Навчальне вікно: 7 днів · автооновлення: кожні 15 хв, окремим фоновим модулем").pack(side="right")
        self._set_learning_buttons(False)

    def _set_learning_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for name in ("learning_refresh_button", "learning_refresh_all_button", "learning_refresh_one_button", "learning_setup_button"):
            button = getattr(self, name, None)
            if button is not None:
                try:
                    button.configure(state=state)
                except Exception:
                    pass

    def set_feedback_ready(self, ready: bool, message: str = "") -> None:
        self._feedback_ready = bool(ready)
        self._set_learning_buttons(self._feedback_ready)
        if message and hasattr(self, "learning_status"):
            self.learning_status.set(message)
        if ready:
            self.feedback_runtime.start()
            self.refresh_learning()

    def _learning_channel_map(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in self.store.list_channels():
            result[f"{int(row['id'])} · {str(row['name'])}"] = int(row["id"])
        return result

    def _learning_channel_id(self) -> int | None:
        mapping = self._learning_channel_map()
        value = self.learning_channel_var.get().strip()
        if value in mapping:
            return mapping[value]
        if mapping:
            first = next(iter(mapping))
            self.learning_channel_var.set(first)
            return mapping[first]
        return None

    def refresh_learning_channels(self) -> None:
        if not hasattr(self, "learning_channel_combo"):
            return
        mapping = self._learning_channel_map()
        values = list(mapping)
        current = self.learning_channel_var.get().strip()
        self.learning_channel_combo["values"] = values
        if current not in mapping:
            self.learning_channel_var.set(values[0] if values else "")

    @staticmethod
    def _coverage_ua(value: str) -> str:
        return {
            "all_admins": "всі адміни", "partial_reactor_scan": "частково",
            "operator_only_fallback": "лише акаунт", "legacy": "старі дані",
        }.get(str(value or ""), str(value or "—"))

    def refresh_learning(self):
        if not hasattr(self, "learning_tree"):
            return
        self.refresh_learning_channels()
        if not self._feedback_ready:
            return
        cid = self._learning_channel_id()
        if cid is None:
            self.learning_status.set("Немає каналів")
            return
        try:
            rows = self.feedback.feedback_rows(cid, limit=180)
            stats = self.feedback.stats(cid)
            profile = self.learning.summary(cid)
        except Exception as exc:
            self.learning_status.set(f"Статистика недоступна: {exc}")
            return
        rates = [audience_raw_rate(row) for row in rows if int(row.get("views") or 0) >= 25]
        baseline = statistics.median(rates) if rates else 0.0
        self.learning_tree.delete(*self.learning_tree.get_children())
        for row in rows:
            perf = audience_performance_score(row, baseline)
            audience = "—" if int(row.get("views") or 0) <= 0 else ("сильно +" if perf >= .75 else "+" if perf >= .2 else "слабо" if perf <= -.65 else "−" if perf <= -.2 else "норма")
            title = " ".join(str(row.get("title") or "").split())
            if len(title) > 95:
                title = title[:92].rstrip() + "…"
            self.learning_tree.insert("", "end", iid=str(row.get("article_id")), values=(
                row.get("article_id"), title, str(row.get("published_at") or "")[:16].replace("T", " "),
                int(row.get("likes") or 0), int(row.get("dislikes") or 0), int(row.get("fires") or 0),
                audience, int(row.get("views") or 0), int(row.get("audience_total") or 0),
                int(row.get("forwards") or 0), int(row.get("replies") or 0), self._coverage_ua(str(row.get("editor_coverage") or "")),
            ))
        configured, config_text = analytics_configured()
        self.learning_status.set(
            f"{'✅' if configured else '⚠'} {config_text} · відстежено {int(stats.get('tracked') or 0)} · "
            f"адмін-постів {int(stats.get('editor_rated_posts') or 0)} · audience-постів {int(stats.get('audience_rated_posts') or 0)} · "
            f"👍 {int(stats.get('likes') or 0)} · 👎 {int(stats.get('dislikes') or 0)} · 🔥 {int(stats.get('fires') or 0)}"
        )
        self.learning_summary.set(
            f"Навчання тем: +{int(profile.get('topic_positive') or 0)} / −{int(profile.get('topic_negative') or 0)} прикладів · "
            f"Навчання стилю: {int(profile.get('style_examples') or 0)} 🔥-прикладів · "
            f"Audience: {int(profile.get('audience_examples') or 0)} нормалізованих прикладів · "
            f"останнє оновлення: {profile.get('last_checked') or 'ще не було'}"
        )

    def learning_refresh_metrics(self, *, force: bool = False, article_id: int | None = None) -> None:
        if not self._feedback_ready or self._learning_refresh_inflight:
            return
        cid = self._learning_channel_id()
        if cid is None:
            return
        self._learning_refresh_inflight = True
        self._set_learning_buttons(False)
        channel = self.store.get_channel(cid)
        name = channel.name if channel else str(cid)
        self.learning_status.set(f"{name}: читаю Telegram Analytics…")

        def progress(text: str) -> None:
            try:
                self.after(0, lambda: self.learning_status.set(f"{name}: {text}"))
            except Exception:
                pass

        def worker() -> None:
            summary = self.feedback.refresh_channel(cid, force=force, article_id=article_id, progress=progress)
            def done() -> None:
                self._learning_refresh_inflight = False
                self._set_learning_buttons(True)
                self.refresh_learning()
                if summary.get("error"):
                    self.learning_status.set(f"{name}: ❌ {summary.get('error')}")
                else:
                    warning = str(summary.get("warning") or "")
                    suffix = f" · ⚠ {warning}" if warning else ""
                    self.learning_status.set(
                        f"{name}: ✅ перевірено {int(summary.get('checked') or 0)} постів · "
                        f"адмінів {int(summary.get('admin_count') or 0)} · {float(summary.get('elapsed') or 0):.1f} с{suffix}"
                    )
            self.after(0, done)
        threading.Thread(target=worker, daemon=True, name="V2-Feedback-Manual").start()

    def learning_refresh_selected(self) -> None:
        selected = self.learning_tree.selection()
        if not selected:
            messagebox.showinfo("Статистика / навчання", "Оберіть публікацію в таблиці")
            return
        try:
            article_id = int(selected[0])
        except Exception:
            return
        self.learning_refresh_metrics(force=True, article_id=article_id)

    def learning_setup_analytics(self) -> None:
        win = tk.Toplevel(self)
        win.title("Telegram Analytics")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)
        secret = load_secrets()
        ttk.Label(frame, text="Telegram API ID").grid(row=0, column=0, sticky="w", pady=4)
        api_id = ttk.Entry(frame, width=42); api_id.grid(row=0, column=1, padx=(10,0), pady=4)
        if int(getattr(secret, "telegram_api_id", 0) or 0): api_id.insert(0, str(secret.telegram_api_id))
        ttk.Label(frame, text="Telegram API Hash").grid(row=1, column=0, sticky="w", pady=4)
        api_hash = ttk.Entry(frame, width=42, show="•"); api_hash.grid(row=1, column=1, padx=(10,0), pady=4); api_hash.insert(0, str(getattr(secret, "telegram_api_hash", "") or ""))
        ttk.Label(frame, text="Телефон акаунта").grid(row=2, column=0, sticky="w", pady=4)
        phone = ttk.Entry(frame, width=42); phone.grid(row=2, column=1, padx=(10,0), pady=4); phone.insert(0, str(getattr(secret, "telegram_phone", "") or ""))
        configured, detail = analytics_configured()
        status = tk.StringVar(value=("✅ " if configured else "⚠ ") + detail)
        ttk.Label(frame, textvariable=status, wraplength=650, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8,6))
        ttk.Label(frame, text="User-session потрібна для читання переглядів, аудиторних реакцій і окремих реакцій адміністраторів. Дані залишаються локально у V2 БД.", wraplength=650, justify="left", foreground="#555").grid(row=4, column=0, columnspan=2, sticky="w", pady=(0,10))
        buttons = ttk.Frame(frame); buttons.grid(row=5, column=0, columnspan=2, sticky="e")

        def values() -> tuple[int, str, str]:
            try: aid = int(api_id.get().strip() or "0")
            except ValueError: raise ValueError("Telegram API ID має бути цілим числом")
            return aid, api_hash.get().strip(), phone.get().strip()

        def save_only() -> None:
            try:
                aid, ahash, ph = values(); save_analytics_credentials(api_id=aid, api_hash=ahash, phone=ph)
                ok, text = analytics_configured(); status.set(("✅ " if ok else "⚠ ") + text)
            except Exception as exc:
                messagebox.showerror("Telegram Analytics", str(exc), parent=win)

        def prompt_worker(text: str, password: bool = False) -> str:
            gate = threading.Event(); result = {"value": ""}
            def ask() -> None:
                try:
                    kwargs = {"parent": win}
                    if password:
                        kwargs["show"] = "•"
                    result["value"] = simpledialog.askstring("Telegram Analytics", text, **kwargs) or ""
                finally:
                    gate.set()
            win.after(0, ask)
            gate.wait(timeout=300)
            return str(result["value"] or "")

        def authorize() -> None:
            try:
                aid, ahash, ph = values()
                if aid <= 0 or not ahash or not ph:
                    raise ValueError("Заповніть API ID, API Hash і телефон")
            except Exception as exc:
                messagebox.showerror("Telegram Analytics", str(exc), parent=win); return
            status.set("⏳ Підключаюсь до Telegram…")
            auth_btn.configure(state="disabled")
            def worker() -> None:
                try:
                    current = load_secrets()
                    session, display = authorize_telegram_analytics(
                        api_id=aid, api_hash=ahash, phone=ph,
                        existing_session=str(getattr(current, "telegram_user_session", "") or ""),
                        code_callback=lambda: prompt_worker("Введіть код, який Telegram надіслав цьому акаунту:"),
                        password_callback=lambda: prompt_worker("Увімкнено 2FA. Введіть пароль Telegram:", True),
                    )
                    save_analytics_credentials(api_id=aid, api_hash=ahash, phone=ph, session=session)
                    self.after(0, lambda: (status.set(f"✅ Авторизовано: {display}"), auth_btn.configure(state="normal"), self.refresh_learning()))
                except Exception as exc:
                    self.after(0, lambda: (status.set(f"❌ {exc}"), auth_btn.configure(state="normal")))
            threading.Thread(target=worker, daemon=True, name="V2-Telegram-Analytics-Auth").start()

        ttk.Button(buttons, text="Закрити", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Зберегти", command=save_only).pack(side="right", padx=6)
        auth_btn = ttk.Button(buttons, text="Авторизувати Telegram", command=authorize); auth_btn.pack(side="right")

    def _build_supervisor(self):
        p = self.tabs["supervisor"]
        cfg = self.supervisor.config
        info = (
            "Нагляд працює окремим фоновим потоком усередині V2: формує status.json, incident.json "
            "та recent_events.json, ловить AI/worker/queue/SQLite/disk/media аварії й дзеркалить telemetry "
            "у локальну папку Google Drive Desktop. Telegram-оповіщення та окремий агент прибрані: "
            "діагностика читається напряму з файлового feed."
        )
        ttk.Label(p, text=info, wraplength=1120, justify="left").grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 8))
        self.sup_enabled = tk.BooleanVar(value=cfg.enabled)
        self.sup_mirror_dir = tk.StringVar(value=cfg.mirror_dir)
        self.sup_interval = tk.StringVar(value=str(cfg.interval_seconds))
        self.sup_ai_grace = tk.StringVar(value=str(cfg.ai_grace_seconds))
        self.sup_worker_stale = tk.StringVar(value=str(cfg.worker_stale_seconds))
        self.sup_queue_stall = tk.StringVar(value=str(cfg.queue_stall_seconds))
        self.sup_disk_mb = tk.StringVar(value=str(cfg.disk_min_free_mb))
        ttk.Checkbutton(p, text="Увімкнути нагляд", variable=self.sup_enabled).grid(row=1, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(p, text="Google Drive / telemetry папка").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        ttk.Entry(p, textvariable=self.sup_mirror_dir, width=80).grid(row=2, column=1, columnspan=2, sticky="ew", padx=12, pady=4)
        ttk.Button(p, text="Обрати папку", command=self.supervisor_choose_mirror).grid(row=2, column=3, sticky="w", padx=4, pady=4)
        fields = (
            ("Період перевірки, с", self.sup_interval, 3, 0),
            ("AI grace, с", self.sup_ai_grace, 3, 2),
            ("Worker stale, с", self.sup_worker_stale, 4, 0),
            ("Queue stall, с", self.sup_queue_stall, 4, 2),
            ("Мін. вільного диска, МБ", self.sup_disk_mb, 5, 0),
        )
        for label, var, row, col in fields:
            ttk.Label(p, text=label).grid(row=row, column=col, sticky="w", padx=12, pady=4)
            ttk.Entry(p, textvariable=var, width=14).grid(row=row, column=col + 1, sticky="w", padx=12, pady=4)
        bar = ttk.Frame(p)
        bar.grid(row=6, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 6))
        ttk.Button(bar, text="Зберегти нагляд", command=self.supervisor_save).pack(side="left")
        ttk.Button(bar, text="Оновити feed зараз", command=self.supervisor_write_status).pack(side="left", padx=6)
        ttk.Button(bar, text="Створити diagnostic ZIP", command=self.supervisor_diagnostic).pack(side="left", padx=6)
        self.supervisor_status = tk.StringVar(value="Supervisor запускається…")
        ttk.Label(p, textvariable=self.supervisor_status, wraplength=1120, justify="left").grid(row=7, column=0, columnspan=4, sticky="w", padx=12, pady=12)
        for col in (1, 2):
            p.columnconfigure(col, weight=1)

    def _supervisor_config_from_ui(self):
        return SupervisorConfig(
            enabled=bool(self.sup_enabled.get()),
            mirror_dir=self.sup_mirror_dir.get().strip(),
            interval_seconds=int(self.sup_interval.get()),
            ai_grace_seconds=int(self.sup_ai_grace.get()),
            worker_stale_seconds=int(self.sup_worker_stale.get()),
            queue_stall_seconds=int(self.sup_queue_stall.get()),
            disk_min_free_mb=int(self.sup_disk_mb.get()),
        )

    def supervisor_save(self):
        try:
            cfg = self.supervisor.save_config(self._supervisor_config_from_ui())
            self.supervisor_status.set(f"Налаштування збережено. file feed={cfg.mirror_dir or 'не задано'}")
            self.supervisor.write_snapshot()
        except Exception as exc:
            messagebox.showerror("Нагляд", str(exc))

    def supervisor_choose_mirror(self):
        path = filedialog.askdirectory(title="Оберіть локальну синхронізовану папку Supervisor Feed")
        if path:
            self.sup_mirror_dir.set(path)
            self.supervisor_save()

    def supervisor_write_status(self):
        try:
            self.supervisor.save_config(self._supervisor_config_from_ui())
            snap = self.supervisor.write_snapshot()
            self.supervisor_status.set(f"status.json оновлено: {snap.get('generated_at')}")
        except Exception as exc:
            messagebox.showerror("Нагляд", str(exc))

    def supervisor_diagnostic(self):
        self.supervisor_status.set("Збираю diagnostic ZIP…")
        def work():
            try:
                out = self.supervisor.create_diagnostic_bundle()
                msg = f"Diagnostic ZIP: {out}"
            except Exception as exc:
                msg = f"Diagnostic FAILED: {exc}"
            self.after(0, lambda: self.supervisor_status.set(msg))
        threading.Thread(target=work, daemon=True, name="V2-Supervisor-Diagnostic").start()

    def refresh_supervisor(self):
        if not hasattr(self, "supervisor_status"):
            return
        summary = self.supervisor.summary()
        snap = summary.get("snapshot") or {}
        incidents = summary.get("incidents") or []
        cfg = summary.get("config") or {}
        ai = snap.get("ai") or {}
        q = snap.get("queue") or {}
        incident_text = "; ".join(f"{i.get('severity')} {i.get('code')}: {i.get('title')}" for i in incidents) or "немає"
        self.supervisor_status.set(
            f"Supervisor thread: {'працює' if summary.get('thread_alive') else 'не працює'} · "
            f"AI {ai.get('healthy', 0)}/{ai.get('total', 0)} · active jobs {q.get('active', 0)} · "
            f"last publish {q.get('last_publish') or 'немає'} · incidents: {incident_text} · "
            f"mirror: {cfg.get('mirror_dir') or 'не задано'}"
        )

    def _build_migration(self):
        p = self.tabs["migration"]
        text = "Імпорт читає стару Data ТІЛЬКИ read-only. Перед заміною V2 БД створюється backup. Переносяться канали, правила, ваги, джерела, published history, dedupe/feedback та зашифровані credentials. Не переносяться cooldown, retry, worker state, RC markers та transient errors. Codex SDK входить до самого portable і не залежить від старої Data."
        ttk.Label(p, text=text, wraplength=980, justify="left").pack(anchor="w", padx=12, pady=12)
        self.migration_status = tk.StringVar(value="")
        ttk.Button(p, text="Імпортувати стару Data", command=self.import_legacy).pack(anchor="w", padx=12, pady=5)
        ttk.Button(p, text="Створити export-bundle старої Data", command=self.export_legacy).pack(anchor="w", padx=12, pady=5)
        ttk.Label(p, textvariable=self.migration_status, wraplength=1050, justify="left").pack(anchor="w", padx=12, pady=12)

    def _build_logs(self):
        p = self.tabs["logs"]
        ttk.Label(p, text=f"Окремі ротаційні журнали: {self.logs_dir}", wraplength=1000).pack(anchor="w", padx=12, pady=12)
        ttk.Button(p, text="Відкрити папку журналів", command=self.open_logs).pack(anchor="w", padx=12)

    def set_startup_ready(self, ready: bool, message: str = "") -> None:
        self._startup_ready = bool(ready)
        try:
            self.start_button.configure(state=("normal" if self._startup_ready else "disabled"))
        except Exception:
            pass
        if message:
            self.status.set(message)

    def start_runtime(self):
        if not self._startup_ready:
            self.status.set("Підготовка бази ще триває…")
            return
        if self._running:
            return
        self.runtime.start()
        self._running = True
        self.supervisor.set_expected_running(True)
        self.status.set("Автопілот запускається")
        self.refresh_all()

    def stop_runtime(self):
        if not self._running:
            return
        self.supervisor.set_expected_running(False)
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
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None
        try:
            self.refresh_home()
            self.refresh_channels()
            self.refresh_queue()
            self.refresh_history()
            self.refresh_ai()
            self.refresh_learning()
            self.refresh_supervisor()
        finally:
            if self.winfo_exists():
                self._refresh_after_id = self.after(2500, self.refresh_all)

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
        selected = self.channel_tree.selection()
        wanted = selected[0] if selected else ""
        self.channel_tree.delete(*self.channel_tree.get_children())
        for row in self.store.list_channels():
            cfg = self.store.get_channel(int(row["id"]))
            sources = len(self.store.sources_for_channel(int(row["id"]), enabled_only=False))
            policy = (cfg.policy.selection_rules[:180] + "…") if cfg and len(cfg.policy.selection_rules) > 180 else (cfg.policy.selection_rules if cfg else "")
            self.channel_tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["name"], "Моніторинг" if str(row["channel_mode"]) == "monitoring" else "Редакційний", "так" if row["enabled"] else "ні", sources, policy))
        children = self.channel_tree.get_children()
        target = wanted if wanted in children else (children[0] if children else "")
        if target:
            self.channel_tree.selection_set(target)
            self.channel_tree.focus(target)

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
        if ids:
            return int(ids[0])
        children = self.channel_tree.get_children()
        if not children:
            return None
        self.channel_tree.selection_set(children[0])
        self.channel_tree.focus(children[0])
        return int(children[0])

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
            if self._refresh_after_id is not None:
                try:
                    self.after_cancel(self._refresh_after_id)
                except Exception:
                    pass
                self._refresh_after_id = None
            self.stop_runtime()
            self.feedback_runtime.stop()
            self.supervisor.stop()
        finally:
            self.destroy()
