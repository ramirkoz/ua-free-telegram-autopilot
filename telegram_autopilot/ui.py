from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import APP_NAME, __version__
from .ai_router import clear_router_cooldowns, test_all, test_production_route
from .local_ai_runtime import discover_local_models, test_local_runtime
from .codex_engine import inspect_codex, install_codex, login_chatgpt
from .collector import detect_source
from .database import Database
from .models import Channel, Source
from .secrets_store import SecretConfig, load_secrets, save_secrets
from .service import AutopilotService
from .language_tool_local import apply_local_languagetool_detailed, ensure_languagetool, languagetool_status, shutdown_languagetool
from .telegram import normalize_chat_target, test_bot


_LOG = logging.getLogger("telegram_autopilot.ui")


DEFAULT_PROFILE = """Тематика: технології, AI, наука, космос, кібербезпека, чипи, робототехніка, енергетика, транспорт та важливі цифрові зміни у США й Європі.
Публікувати: реальні технологічні або наукові новації, дослідження, інженерні прориви, значущі впровадження, безпекові події та рішення, цікаві широкій українській аудиторії.
Не публікувати: маркетингові запуски товарів без технологічної новизни, продажі/передзамовлення/ціни/рестайлінг, рекламу, buying guides, opinion-only, чутки, клікбейт, крипто-ціни та геймінг-релізи.
Стиль: максимально природний український научпоп/техножурналістика для розумного неспеціаліста; складне пояснювати просто, без машинного перекладу й канцеляриту."""


class MainWindow:
    def __init__(self, root: tk.Tk, db: Database):
        self.root=root; self.db=db
        self.root.title(f"{APP_NAME} {__version__}")
        self.root.geometry("1180x760"); self.root.minsize(980,650)
        self.channel_map:dict[str,int]={}; self.current_channel_id:int|None=None
        # Tkinter is main-thread only. Worker/service threads may only enqueue callables;
        # the main Tk loop drains them below. This prevents "main thread is not in main loop"
        # from killing the autopilot cycle.
        self._ui_queue: queue.Queue = queue.Queue()
        self._closing=False
        self._refresh_after_id=None
        self._view_dirty={"sources":False,"history":False,"stats":False}
        self._event_refresh_delay_ms=1500
        self._log_event_count=0
        self._lt_status_busy=False
        self._next_lt_status_at=0.0
        self.service=AutopilotService(db,self._service_event)
        self._install_editing_support()
        self._build(); self.refresh_all()
        self._drain_ui_queue()
        if self.db.get_state("auto_start","1") == "1": self.service.start()
        self._tick()

    def _install_editing_support(self) -> None:
        """Make editing behave like a normal Windows application in every text field.

        Tk's default Ctrl+V can depend on the active keyboard layout. On Windows we
        also recognize physical VK keycodes, so Ctrl+V keeps working with Ukrainian
        layout enabled. Right-click always exposes the familiar edit menu.
        """
        for widget_class in ("Entry", "TEntry", "TCombobox", "Text"):
            self.root.bind_class(widget_class, "<Control-KeyPress>", self._control_edit_shortcut, add="+")
            self.root.bind_class(widget_class, "<Shift-Insert>", self._paste_shortcut, add="+")
            self.root.bind_class(widget_class, "<Button-3>", self._show_edit_menu, add="+")

    @staticmethod
    def _edit_action(event: tk.Event) -> str:
        keysym = str(getattr(event, "keysym", "") or "").casefold()
        keycode = int(getattr(event, "keycode", 0) or 0)
        by_symbol = {"v": "paste", "c": "copy", "x": "cut", "a": "select_all"}
        if keysym in by_symbol:
            return by_symbol[keysym]
        # Win32 virtual-key codes remain V/C/X/A even when the layout is Ukrainian.
        return {86: "paste", 67: "copy", 88: "cut", 65: "select_all"}.get(keycode, "")

    def _control_edit_shortcut(self, event: tk.Event):
        action = self._edit_action(event)
        if not action:
            return None
        if action == "select_all":
            self._select_all_widget(event.widget)
        elif action == "paste":
            self._paste_widget(event.widget)
        else:
            event.widget.event_generate({"copy": "<<Copy>>", "cut": "<<Cut>>"}[action])
        return "break"

    def _paste_shortcut(self, event: tk.Event):
        self._paste_widget(event.widget)
        return "break"

    def _paste_widget(self, widget: tk.Widget) -> None:
        try:
            value = self.root.clipboard_get()
        except tk.TclError:
            return
        try:
            if isinstance(widget, tk.Text):
                try:
                    widget.delete("sel.first", "sel.last")
                except tk.TclError:
                    pass
                widget.insert("insert", value)
            else:
                try:
                    first = widget.index("sel.first")
                    last = widget.index("sel.last")
                    widget.delete(first, last)
                except tk.TclError:
                    pass
                widget.insert("insert", value)
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _select_all_widget(widget: tk.Widget) -> None:
        try:
            if isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "1.0")
                widget.see("insert")
            else:
                widget.selection_range(0, "end")
                widget.icursor("end")
        except tk.TclError:
            pass

    def _show_edit_menu(self, event: tk.Event):
        widget = event.widget
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Вирізати", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Копіювати", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставити", command=lambda: self._paste_widget(widget))
        menu.add_separator()
        menu.add_command(label="Виділити все", command=lambda: self._select_all_widget(widget))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _build(self):
        top=ttk.Frame(self.root,padding=(10,8)); top.pack(fill="x")
        ttk.Label(top,text="Канал:").pack(side="left")
        self.channel_var=tk.StringVar(); self.channel_combo=ttk.Combobox(top,textvariable=self.channel_var,state="readonly",width=32)
        self.channel_combo.pack(side="left",padx=(6,12)); self.channel_combo.bind("<<ComboboxSelected>>",lambda _e:self._channel_changed())
        self.status_var=tk.StringVar(value="Автопілот: зупинено"); ttk.Label(top,textvariable=self.status_var).pack(side="left",padx=10)
        ttk.Button(top,text="▶ Автопілот",command=self.start_auto).pack(side="right",padx=4)
        ttk.Button(top,text="■ Стоп",command=self.stop_auto).pack(side="right",padx=4)
        ttk.Button(top,text="Запустити цикл зараз",command=self.run_once).pack(side="right",padx=4)

        self.tabs=ttk.Notebook(self.root); self.tabs.pack(fill="both",expand=True,padx=10,pady=(0,10))
        self.dashboard=ttk.Frame(self.tabs,padding=12); self.channels_tab=ttk.Frame(self.tabs,padding=12); self.sources_tab=ttk.Frame(self.tabs,padding=12); self.history_tab=ttk.Frame(self.tabs,padding=12); self.ai_tab=ttk.Frame(self.tabs,padding=12); self.log_tab=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(self.dashboard,text="Головна"); self.tabs.add(self.channels_tab,text="Канали"); self.tabs.add(self.sources_tab,text="Джерела"); self.tabs.add(self.history_tab,text="Історія"); self.tabs.add(self.ai_tab,text="AI та токени"); self.tabs.add(self.log_tab,text="Журнал")
        self.tabs.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._build_dashboard(); self._build_channels(); self._build_sources(); self._build_history(); self._build_ai(); self._build_log()

    def _build_dashboard(self):
        self.stats_vars={}
        labels=[("published","Опубліковано"),("duplicate","Дублі"),("rejected","Відхилено"),("new","Нові"),("retry","На повтор"),("error","Помилки"),("unknown","Невідомий результат")]
        row=ttk.Frame(self.dashboard); row.pack(fill="x")
        for key,label in labels:
            box=ttk.LabelFrame(row,text=label,padding=12); box.pack(side="left",fill="x",expand=True,padx=4)
            v=tk.StringVar(value="0"); self.stats_vars[key]=v; ttk.Label(box,textvariable=v,font=("Segoe UI",18,"bold")).pack()
        info=ttk.LabelFrame(self.dashboard,text="Як працює автопілот",padding=12); info.pack(fill="both",expand=True,pady=14)
        ttk.Label(info,justify="left",wraplength=1000,text=(
            "Кожен Telegram-канал має власний список джерел. Нове джерело спочатку проходить baseline: поточні матеріали запам'ятовуються, але не публікуються. "
            "Нові англомовні матеріали проходять перевірку віку, мови й дублів. Для довгих статей програма локально формує Evidence Pack: зберігає лід і відбирає речення з цифрами, назвами, одиницями та атрибуцією замість простого обрізання тексту. "
            "AI створює один український Telegram-пост без окремого заголовка. Fact Guard блокує вигадані назви/моделі та непідтверджені твердження на кшталт «перший», «найбільший» або «рекорд». "
            "З надійним медіа діє ліміт до 900 символів, без медіа — до 4096. Після успішної перевірки публікація йде безпосередньо в Telegram; робота джерел та ключові етапи зберігаються в локальному журналі."
        )).pack(anchor="w")
        self.last_event=tk.StringVar(value="Ще немає подій."); ttk.Label(info,textvariable=self.last_event,wraplength=1000).pack(anchor="w",pady=(20,0))

    def _build_channels(self):
        bar=ttk.Frame(self.channels_tab); bar.pack(fill="x",pady=(0,8))
        ttk.Button(bar,text="+ Додати канал",command=self.add_channel).pack(side="left",padx=3)
        ttk.Button(bar,text="Редагувати",command=self.edit_channel).pack(side="left",padx=3)
        ttk.Button(bar,text="Видалити",command=self.delete_channel).pack(side="left",padx=3)
        cols=("name","chat","enabled","poll","gap","dedupe","sources")
        self.channels_tree=ttk.Treeview(self.channels_tab,columns=cols,show="headings")
        heads=("Назва","Telegram Chat ID","Активний","Перевірка, хв","Мін. пауза, хв","Дедуп, год","Джерел")
        widths=(220,180,80,100,110,100,80)
        for c,h,w in zip(cols,heads,widths): self.channels_tree.heading(c,text=h); self.channels_tree.column(c,width=w,anchor="w")
        self.channels_tree.pack(fill="both",expand=True); self.channels_tree.bind("<Double-1>",lambda _e:self.edit_channel())

    def _build_sources(self):
        bar=ttk.Frame(self.sources_tab); bar.pack(fill="x",pady=(0,8))
        ttk.Button(bar,text="+ Додати джерело",command=self.add_source).pack(side="left",padx=3)
        ttk.Button(bar,text="Редагувати",command=self.edit_source).pack(side="left",padx=3)
        ttk.Button(bar,text="Видалити",command=self.delete_source).pack(side="left",padx=3)
        ttk.Label(bar,text="Просто вставте адресу. Програма сама визначить Telegram, RSS/Atom або вебсторінку.").pack(side="left",padx=18)
        cols=("name","kind","url","enabled","initialized","health","last_new","yield","errors","checked","error")
        self.sources_tree=ttk.Treeview(self.sources_tab,columns=cols,show="headings")
        heads=("Назва","Тип","URL","Активне","Baseline","Стан","Остання нова","+ за раз","Помилок","Остання перевірка","Остання помилка")
        widths=(150,75,260,65,65,105,135,70,70,135,220)
        for c,h,w in zip(cols,heads,widths): self.sources_tree.heading(c,text=h); self.sources_tree.column(c,width=w,anchor="w")
        self.sources_tree.pack(fill="both",expand=True); self.sources_tree.bind("<Double-1>",lambda _e:self.edit_source())

    def _build_history(self):
        bar=ttk.Frame(self.history_tab); bar.pack(fill="x",pady=(0,8))
        ttk.Label(bar,text="Статус:").pack(side="left")
        self.history_status=tk.StringVar(value="усі"); combo=ttk.Combobox(bar,textvariable=self.history_status,state="readonly",values=["усі","published","duplicate","rejected","new","retry","error","unknown","baseline","telegram_writing"],width=18); combo.pack(side="left",padx=6); combo.bind("<<ComboboxSelected>>",lambda _e:self.refresh_history())
        ttk.Button(bar,text="Оновити",command=self.refresh_history).pack(side="left")
        cols=("id","channel","source","title","status","reason","published","ai","media","msg")
        self.history_tree=ttk.Treeview(self.history_tab,columns=cols,show="headings")
        heads=("ID","Канал","Джерело","Заголовок","Статус","Причина / помилка","Опубліковано","AI","Медіа","Telegram ID")
        widths=(55,120,120,280,95,330,135,120,60,90)
        for c,h,w in zip(cols,heads,widths): self.history_tree.heading(c,text=h); self.history_tree.column(c,width=w,anchor="w")
        self.history_tree.pack(fill="both",expand=True)

    def _build_ai(self):
        form=ttk.Frame(self.ai_tab); form.pack(fill="x")
        self.secret_entries={}
        fields=[("default_telegram_bot_token","Глобальний Telegram Bot Token"),("gemini_api_key","Google Gemini API Key"),("nvidia_api_key","NVIDIA NIM API Key"),("groq_api_key","Groq API Key"),("cloudflare_account_id","Cloudflare Account ID"),("cloudflare_api_token","Cloudflare API Token")]
        for r,(key,label) in enumerate(fields):
            ttk.Label(form,text=label,width=28).grid(row=r,column=0,sticky="w",pady=4)
            e=ttk.Entry(form,width=70,show="" if key=="cloudflare_account_id" else "•"); e.grid(row=r,column=1,sticky="ew",pady=4); self.secret_entries[key]=e
        form.columnconfigure(1,weight=1)
        self.local_enabled=tk.BooleanVar(); ttk.Checkbutton(form,text="Локальний fallback: Ollama автоматично → llama.cpp",variable=self.local_enabled).grid(row=6,column=0,sticky="w",pady=4)
        self.local_url=ttk.Entry(form,width=40); self.local_url.grid(row=6,column=1,sticky="w")
        self.local_model=ttk.Combobox(form,width=28,state="normal"); self.local_model.grid(row=6,column=1,sticky="e")
        local_tools=ttk.Frame(form); local_tools.grid(row=7,column=0,columnspan=2,sticky="w",pady=(0,6))
        ttk.Button(local_tools,text="Знайти локальні моделі",command=self.find_local_models_ui).pack(side="left")
        ttk.Label(local_tools,text="  Ollama: показує реально встановлені моделі; нічого не завантажує. URL праворуч використовується лише як запасний llama.cpp.",wraplength=850).pack(side="left")
        ltbar=ttk.Frame(self.ai_tab); ltbar.pack(fill="x",pady=(4,0))
        ttk.Label(ltbar,text="LanguageTool:").pack(side="left")
        self.lt_status_var=tk.StringVar(value="перевіряється…")
        ttk.Label(ltbar,textvariable=self.lt_status_var).pack(side="left",padx=(6,10))
        ttk.Button(ltbar,text="Перевірити / встановити LanguageTool",command=self.test_languagetool_ui).pack(side="left")
        btn=ttk.Frame(self.ai_tab); btn.pack(fill="x",pady=12)
        ttk.Button(btn,text="Зберегти токени",command=self.save_secret_ui).pack(side="left",padx=3)
        ttk.Button(btn,text="Знайти / тестувати AI моделі",command=self.test_ai_ui).pack(side="left",padx=3)
        ttk.Button(btn,text="Перевірити локальний AI",command=self.test_local_ai_ui).pack(side="left",padx=3)
        ttk.Button(btn,text="Встановити / оновити Codex",command=self.install_codex_ui).pack(side="left",padx=3)
        ttk.Button(btn,text="Увійти ChatGPT",command=self.login_codex_ui).pack(side="left",padx=3)
        self.ai_result=tk.Text(self.ai_tab,height=18,wrap="word"); self.ai_result.pack(fill="both",expand=True)

    def _build_log(self):
        bar=ttk.Frame(self.log_tab); bar.pack(fill="x",pady=(0,8))
        ttk.Label(bar,text="Стійкий локальний audit trail. Токени та повні тексти джерел сюди не записуються.").pack(side="left")
        ttk.Button(bar,text="Оновити журнал",command=self.refresh_audit_log).pack(side="right")
        self.log_text=tk.Text(self.log_tab,wrap="word",state="disabled"); self.log_text.pack(fill="both",expand=True)

    def _selected_id(self,tree:ttk.Treeview)->int|None:
        sel=tree.selection();
        if not sel: return None
        try: return int(sel[0])
        except ValueError: return None

    def refresh_all(self):
        channels=self.db.list_channels(); self.channel_map={c.name:c.id for c in channels}; names=list(self.channel_map)
        self.channel_combo["values"]=names
        if self.current_channel_id not in {c.id for c in channels}: self.current_channel_id=channels[0].id if channels else None
        if self.current_channel_id:
            ch=next((c for c in channels if c.id==self.current_channel_id),None)
            if ch: self.channel_var.set(ch.name)
        else: self.channel_var.set("")
        self.refresh_channels(); self.refresh_sources(); self.refresh_history(); self.refresh_stats(); self.refresh_audit_log(); self.load_secret_ui()

    def _channel_changed(self):
        self.current_channel_id=self.channel_map.get(self.channel_var.get()); self.refresh_sources(); self.refresh_history(); self.refresh_stats(); self.refresh_audit_log()

    def refresh_channels(self):
        for i in self.channels_tree.get_children(): self.channels_tree.delete(i)
        for c in self.db.list_channels():
            self.channels_tree.insert("", "end", iid=str(c.id), values=(c.name,c.telegram_chat_id,"так" if c.enabled else "ні",c.poll_interval_minutes,c.min_publish_interval_minutes,c.dedupe_window_hours,len(self.db.list_sources(c.id))))

    def refresh_sources(self):
        for i in self.sources_tree.get_children(): self.sources_tree.delete(i)
        if not self.current_channel_id:return
        kind_names={"telegram":"Telegram","rss":"RSS/Atom","page":"Веб"}
        for s,health in self.db.list_sources_with_health(self.current_channel_id):
            if not s.enabled:
                state="⚪ вимкнено"
            elif s.last_error:
                state="🔴 помилка"
            elif health.get("last_success_at"):
                state="🟢 працює"
            elif s.initialized:
                state="🟡 очікує"
            else:
                state="⚪ не перевірено"
            self.sources_tree.insert("","end",iid=str(s.id),values=(
                s.name,kind_names.get(s.kind,s.kind),s.url,"так" if s.enabled else "ні","так" if s.initialized else "ні",
                state,health.get("last_new_at") or "",health.get("last_inserted_count") or 0,health.get("total_errors") or 0,
                s.last_checked_at or "",s.last_error or ""
            ))

    def refresh_audit_log(self):
        if not hasattr(self,"log_text"):
            return
        rows=self.db.recent_audit(self.current_channel_id,limit=400)
        lines=[]
        for r in reversed(rows):
            refs=[]
            if r["source_id"]: refs.append(f"source={r['source_id']}")
            if r["article_id"]: refs.append(f"article={r['article_id']}")
            ref_text=(" · "+", ".join(refs)) if refs else ""
            detail=(" · "+str(r["detail"])) if r["detail"] else ""
            lines.append(f"{r['created_at']} [{r['stage']}/{r['outcome']}]{ref_text}{detail}")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0","end")
        self.log_text.insert("1.0","\n".join(lines) if lines else "Журнал ще порожній.")
        self.log_text.configure(state="disabled")

    def refresh_history(self):
        for i in self.history_tree.get_children(): self.history_tree.delete(i)
        status=self.history_status.get() if hasattr(self,"history_status") else "усі"; status=None if status=="усі" else status
        for r in self.db.history(self.current_channel_id,status,limit=200):
            row_status=str(r["status"] or "")
            if row_status in {"retry","error","unknown","processing","telegram_writing"}:
                reason=r["last_error"] or r["reject_reason"] or ""
            elif row_status in {"rejected","duplicate"}:
                reason=r["reject_reason"] or r["last_error"] or ""
            else:
                reason=r["last_error"] or r["reject_reason"] or ""
            self.history_tree.insert("","end",iid=f"h{r['id']}",values=(r["id"],r["channel_name"],r["source_name"],r["headline_uk"] or r["title"],r["status"],reason,r["published_at"] or "",r["ai_provider"] or "",r["telegram_media_count"] or 0,r["telegram_message_id"] or ""))

    def refresh_stats(self):
        stats=self.db.stats(self.current_channel_id)
        for k,v in self.stats_vars.items(): v.set(str(stats.get(k,0)))

    def add_channel(self): self._channel_dialog(None)
    def edit_channel(self):
        cid=self._selected_id(self.channels_tree) or self.current_channel_id
        if cid: self._channel_dialog(self.db.get_channel(cid))
    def delete_channel(self):
        cid=self._selected_id(self.channels_tree)
        if cid and messagebox.askyesno(APP_NAME,"Видалити канал разом з його джерелами та локальною історією?"):
            self.db.delete_channel(cid); self.current_channel_id=None; self.refresh_all()

    def _channel_dialog(self,ch:Channel|None):
        win=tk.Toplevel(self.root); win.title("Канал"); win.transient(self.root); win.grab_set(); win.geometry("720x430")
        fields={}
        def entry(label,value="",show=""):
            frame=ttk.Frame(win); frame.pack(fill="x",padx=12,pady=5); ttk.Label(frame,text=label,width=30).pack(side="left"); e=ttk.Entry(frame,show=show); e.pack(side="left",fill="x",expand=True); e.insert(0,str(value))
            e.bind("<Control-KeyPress>", self._control_edit_shortcut, add="+"); e.bind("<Shift-Insert>", self._paste_shortcut, add="+"); e.bind("<Button-3>", self._show_edit_menu, add="+")
            return e
        fields["name"]=entry("Назва каналу",ch.name if ch else "")
        fields["chat"]=entry("Telegram: посилання / @username / Chat ID",ch.telegram_chat_id if ch else "")
        secret=load_secrets(); existing=secret.channel_bot_tokens.get(str(ch.id),"") if ch else ""
        fields["token"]=entry("Bot Token (необов'язково)",existing,show="•")
        nums=ttk.LabelFrame(win,text="Автоматизація",padding=8); nums.pack(fill="x",padx=12,pady=8)
        vals=[("poll","Перевірка джерел, хв",ch.poll_interval_minutes if ch else 5),("gap","Мін. пауза між постами, хв",ch.min_publish_interval_minutes if ch else 10),("dedupe","Вікно дедуплікації, год",ch.dedupe_window_hours if ch else 72),("age","Макс. вік матеріалу, год",ch.max_age_hours if ch else 24),("maxcycle","Макс. постів за цикл",ch.max_posts_per_cycle if ch else 3)]
        for r,(key,label,val) in enumerate(vals):
            ttk.Label(nums,text=label).grid(row=r,column=0,sticky="w",pady=3); e=ttk.Entry(nums,width=12); e.insert(0,str(val)); e.grid(row=r,column=1,sticky="w",padx=8); fields[key]=e
            e.bind("<Control-KeyPress>", self._control_edit_shortcut, add="+"); e.bind("<Shift-Insert>", self._paste_shortcut, add="+"); e.bind("<Button-3>", self._show_edit_menu, add="+")
        enabled=tk.BooleanVar(value=ch.enabled if ch else True)
        ttk.Checkbutton(nums,text="Канал активний",variable=enabled).grid(row=0,column=2,sticky="w",padx=20)
        ttk.Label(nums,text="Формат: 1 медіа + ≤900 / без медіа ≤4096",foreground="#555").grid(row=1,column=2,sticky="w",padx=20)
        def save():
            try:
                name=fields["name"].get().strip()
                if not name:
                    raise ValueError("Вкажіть назву каналу.")
                chat=normalize_chat_target(fields["chat"].get())
                profile=ch.editorial_profile if ch and ch.editorial_profile.strip() else DEFAULT_PROFILE
                cid=self.db.save_channel(channel_id=ch.id if ch else None,name=name,telegram_chat_id=chat,editorial_profile=profile,enabled=enabled.get(),include_source_link=False,poll_interval_minutes=int(fields["poll"].get()),min_publish_interval_minutes=int(fields["gap"].get()),dedupe_window_hours=int(fields["dedupe"].get()),max_age_hours=int(fields["age"].get()),max_posts_per_cycle=int(fields["maxcycle"].get()))
                sec=load_secrets(); tok=fields["token"].get().strip()
                if tok: sec.channel_bot_tokens[str(cid)]=tok
                else: sec.channel_bot_tokens.pop(str(cid),None)
                save_secrets(sec); self.current_channel_id=cid; win.destroy(); self.refresh_all()
            except Exception as exc: messagebox.showerror(APP_NAME,str(exc),parent=win)
        bottom=ttk.Frame(win); bottom.pack(fill="x",padx=12,pady=10); ttk.Button(bottom,text="Зберегти",command=save).pack(side="right")
        if ch:
            def test():
                try:
                    tok=fields["token"].get().strip() or load_secrets().default_telegram_bot_token
                    name=test_bot(tok,fields["chat"].get()); messagebox.showinfo(APP_NAME,f"Telegram канал доступний: {name}",parent=win)
                except Exception as exc: messagebox.showerror(APP_NAME,str(exc),parent=win)
            ttk.Button(bottom,text="Перевірити Telegram",command=test).pack(side="left")


    def add_source(self):
        if not self.current_channel_id: messagebox.showwarning(APP_NAME,"Спочатку створіть канал."); return
        self._source_dialog(None)
    def edit_source(self):
        sid=self._selected_id(self.sources_tree)
        if not sid or not self.current_channel_id:return
        src=next((s for s in self.db.list_sources(self.current_channel_id) if s.id==sid),None)
        if src:self._source_dialog(src)
    def delete_source(self):
        sid=self._selected_id(self.sources_tree)
        if sid and messagebox.askyesno(APP_NAME,"Видалити джерело?"): self.db.delete_source(sid); self.refresh_sources()

    def _source_dialog(self,src:Source|None):
        win=tk.Toplevel(self.root); win.title("Джерело"); win.transient(self.root); win.grab_set(); win.geometry("680x250")
        ttk.Label(win,text="URL джерела").pack(anchor="w",padx=12,pady=(12,2))
        url=ttk.Entry(win); url.pack(fill="x",padx=12); url.insert(0,src.url if src else "")
        ttk.Label(win,text="Вставте сайт, прямий RSS/Atom або публічний Telegram-канал (t.me/username). Тип визначається автоматично.",wraplength=640,foreground="#555").pack(anchor="w",padx=12,pady=(4,8))
        ttk.Label(win,text="Назва (необов'язково)").pack(anchor="w",padx=12,pady=(2,2))
        name=ttk.Entry(win); name.pack(fill="x",padx=12); name.insert(0,src.name if src else "")
        enabled=tk.BooleanVar(value=src.enabled if src else True); ttk.Checkbutton(win,text="Активне",variable=enabled).pack(anchor="w",padx=12,pady=8)
        status=tk.StringVar(value=("Поточний тип: " + {"telegram":"Telegram","rss":"RSS/Atom","page":"вебсторінка"}.get(src.kind,src.kind)) if src else "")
        ttk.Label(win,textvariable=status,foreground="#555").pack(anchor="w",padx=12)
        bottom=ttk.Frame(win); bottom.pack(fill="x",padx=12,pady=10)
        save_button=ttk.Button(bottom,text="Зберегти"); save_button.pack(side="right")
        ttk.Button(bottom,text="Скасувати",command=win.destroy).pack(side="right",padx=6)

        def save():
            raw_url=url.get().strip()
            if not raw_url:
                messagebox.showerror(APP_NAME,"Вставте адресу джерела.",parent=win); return
            requested_name=name.get().strip()
            save_button.configure(state="disabled")
            status.set("Визначаю тип джерела…")

            def work():
                try:
                    detected=detect_source(raw_url)
                except Exception as exc:
                    self._post_ui(self._source_detection_failed,win,save_button,status,exc)
                    return
                def finish():
                    try:
                        final_name=requested_name or detected.suggested_name
                        self.db.save_source(
                            source_id=src.id if src else None,
                            channel_id=self.current_channel_id,
                            kind=detected.kind,
                            name=final_name,
                            url=detected.url,
                            enabled=enabled.get(),
                        )
                        win.destroy(); self.refresh_sources()
                    except Exception as exc:
                        save_button.configure(state="normal"); status.set("")
                        messagebox.showerror(APP_NAME,str(exc),parent=win)
                self._post_ui(finish)
            threading.Thread(target=work,daemon=True).start()
        save_button.configure(command=save)
        url.focus_set()

    @staticmethod
    def _source_detection_failed(win,button,status,error):
        if not win.winfo_exists():
            return
        button.configure(state="normal")
        text = str(error)
        if "HTTP 403" in text:
            status.set("Сервер відхилив автоматичний запит (HTTP 403).")
        else:
            status.set("Не вдалося перевірити джерело.")
        messagebox.showerror(APP_NAME,text,parent=win)

    def load_secret_ui(self):
        try: sec=load_secrets()
        except Exception:return
        for k,e in self.secret_entries.items(): e.delete(0,"end"); e.insert(0,str(getattr(sec,k)))
        self.local_enabled.set(sec.local_enabled); self.local_url.delete(0,"end"); self.local_url.insert(0,sec.local_base_url); self.local_model.delete(0,"end"); self.local_model.insert(0,sec.local_model)

    def save_secret_ui(self,quiet=False):
        try:
            old=load_secrets(); data={k:e.get().strip() for k,e in self.secret_entries.items()}; sec=SecretConfig(**data,channel_bot_tokens=old.channel_bot_tokens,local_enabled=self.local_enabled.get(),local_base_url=self.local_url.get(),local_model=self.local_model.get()); save_secrets(sec)
            clear_router_cooldowns()
            if not quiet: messagebox.showinfo(APP_NAME,"Токени збережено. AI cooldown скинуто, провайдери перевірятимуться заново.")
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def test_ai_ui(self):
        self.save_secret_ui(quiet=True)
        def work():
            try:
                rows=test_all()
                lines=[f"{mark} {provider}: {detail}" for provider,mark,detail in rows]
                try:
                    prod=test_production_route()
                    lines.append(f"✓ production-route: реальний rewrite prompt пройшов · {prod.label}")
                except Exception as exc:
                    lines.append(f"⚠ production-route: {exc}")
                lines.append(str(languagetool_status().get("text") or "LanguageTool: невідомий стан"))
                text="\n".join(lines)
            except Exception as exc:text=str(exc)
            self._post_ui(self._set_ai_result,text)
        threading.Thread(target=work,daemon=True).start(); self._set_ai_result("Оновлення каталогів моделей + перевірка API + production-route...")
    def _set_ai_result(self,text): self.ai_result.delete("1.0","end"); self.ai_result.insert("1.0",text)

    def test_languagetool_ui(self):
        def work():
            try:
                ready=ensure_languagetool(self._service_event)
                status=languagetool_status()
                text=str(status.get("text") or "LanguageTool: невідомий стан")
                if ready or status.get("ready"):
                    sample="Цей система працюють неправильно, а Swift згоріть у атмосфері."
                    result=apply_local_languagetool_detailed(sample,timeout=2.5,max_changes=12,require_ready=False)
                    text += f"\n\nКонтрольна перевірка: {result.changes} правок\nБуло: {sample}\nСтало: {result.text}"
                    if result.details:
                        text += "\nПравки: " + "; ".join(result.details)
                else:
                    text += "\nLanguageTool не готовий; автопілот продовжує роботу через вбудований UA-gate."
            except Exception as exc:
                text=f"✗ LanguageTool: {exc}"
            self._post_ui(self._set_lt_result,text)
        threading.Thread(target=work,daemon=True).start()
        self.lt_status_var.set("перевірка/встановлення…")

    def _set_lt_result(self, text):
        self.lt_status_var.set(str(text).splitlines()[0])
        self._set_ai_result(str(text))

    def find_local_models_ui(self):
        def work():
            try:
                models=discover_local_models(auto_start=True)
                if models:
                    text="Знайдено локальні Ollama-моделі:\n" + "\n".join(f"  • {m}" for m in models)
                else:
                    text="Ollama відповідає, але локальних моделей немає."
            except Exception as exc:
                models=[]; text=f"✗ Пошук локальних моделей: {exc}"
            def finish():
                self.local_model.configure(values=models)
                current=self.local_model.get().strip()
                if models and (not current or current == "local-model"):
                    self.local_model.set(models[0])
                self._set_ai_result(text)
            self._post_ui(finish)
        threading.Thread(target=work,daemon=True).start(); self._set_ai_result("Пошук локальних Ollama-моделей...")

    def test_local_ai_ui(self):
        self.save_secret_ui(quiet=True)
        def work():
            try:
                sec=load_secrets()
                if not sec.local_enabled:
                    text="Локальний fallback вимкнений. Увімкніть його та збережіть налаштування."
                else:
                    target=test_local_runtime(preferred_model=sec.local_model,manual_base_url=sec.local_base_url,manual_model=sec.local_model)
                    text=f"✓ Локальний AI працює: {target.label}"
            except Exception as exc:
                text=f"✗ Локальний AI: {exc}"
            self._post_ui(self._set_ai_result,text)
        threading.Thread(target=work,daemon=True).start(); self._set_ai_result("Перевірка локального AI...")


    def install_codex_ui(self):
        def work():
            try: install_codex(); clear_router_cooldowns("codex"); text="Codex встановлено/оновлено."
            except Exception as exc:text=f"Помилка Codex: {exc}"
            self._post_ui(self._set_ai_result,text)
        threading.Thread(target=work,daemon=True).start(); self._set_ai_result("Встановлення Codex...")
    def login_codex_ui(self):
        def work():
            try: login_chatgpt(); clear_router_cooldowns("codex"); s=inspect_codex(); text=f"Codex: {'✓' if s.authenticated else '⚠'} {s.detail}"
            except Exception as exc:text=f"Помилка входу: {exc}"
            self._post_ui(self._set_ai_result,text)
        threading.Thread(target=work,daemon=True).start(); self._set_ai_result("Вхід ChatGPT...")

    def start_auto(self): self.db.set_state("auto_start","1"); self.service.start(); self.status_var.set("Автопілот: працює")
    def stop_auto(self): self.db.set_state("auto_start","0"); self.service.stop(); self.status_var.set("Автопілот: зупинено")
    def run_once(self):
        threading.Thread(target=self.service.run_once,daemon=True).start(); self.last_event.set("Ручний цикл запущено...")

    def _post_ui(self, callback, *args, **kwargs):
        """Queue a UI callable without touching Tcl/Tk from a worker thread."""
        if self._closing:
            return
        self._ui_queue.put((callback,args,kwargs))

    def _drain_ui_queue(self):
        if self._closing:
            return
        # Keep every pass short. A burst of service events must never monopolize
        # Tk's message pump and make the window look hung.
        started=time.perf_counter(); processed=0
        while processed < 60 and (time.perf_counter()-started) < 0.010:
            try:
                callback,args,kwargs=self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args,**kwargs)
            except tk.TclError:
                if not self._closing:
                    pass
            except Exception:
                _LOG.debug("UI callback failed", exc_info=True)
            processed += 1
        if not self._closing:
            self.root.after(50 if not self._ui_queue.empty() else 100,self._drain_ui_queue)

    def _service_event(self,kind,text):
        self._post_ui(self._record_event,kind,text)

    def _active_view(self) -> str:
        try:
            selected=self.tabs.select()
        except tk.TclError:
            return ""
        if selected == str(self.dashboard): return "stats"
        if selected == str(self.sources_tab): return "sources"
        if selected == str(self.history_tab): return "history"
        return ""

    def _run_view_refresh(self, view: str) -> None:
        if self._closing or not view:
            return
        refresh={"sources":self.refresh_sources,"history":self.refresh_history,"stats":self.refresh_stats}.get(view)
        if refresh is None:
            return
        started=time.perf_counter()
        try:
            refresh()
            self._view_dirty[view]=False
        except Exception:
            _LOG.debug("UI %s refresh failed", view, exc_info=True)
        finally:
            elapsed=(time.perf_counter()-started)*1000.0
            if elapsed >= 500:
                _LOG.warning("UI slow refresh view=%s elapsed_ms=%.0f", view, elapsed)

    def _tab_changed(self, _event=None):
        if self._closing:
            return
        view=self._active_view()
        if view and self._view_dirty.get(view):
            self.root.after_idle(lambda v=view:self._run_view_refresh(v))

    def _refresh_event_views(self):
        self._refresh_after_id=None
        if self._closing:
            return
        # Service events dirty all live views, but only the visible one is rebuilt.
        # Hidden 200-row trees are refreshed lazily when the operator opens them.
        view=self._active_view()
        if view and self._view_dirty.get(view):
            self._run_view_refresh(view)

    def _record_event(self,kind,text):
        if self._closing:
            return
        self.last_event.set(text)
        if hasattr(self,"lt_status_var") and kind in {"languagetool","warning","error"} and "LanguageTool" in str(text):
            self.lt_status_var.set(str(text))
        self.log_text.configure(state="normal")
        self.log_text.insert("end",f"[{kind}] {text}\n")
        self._log_event_count += 1
        # The visible Text widget is only a live console. Keep it bounded; the
        # durable audit trail remains in SQLite and is never truncated here.
        if self._log_event_count % 50 == 0:
            try:
                line_count=int(self.log_text.index("end-1c").split(".")[0])
                if line_count > 800:
                    self.log_text.delete("1.0",f"{line_count-600}.0")
            except (tk.TclError,ValueError):
                pass
        if self.tabs.select() == str(self.log_tab):
            self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self._view_dirty.update({"sources":True,"history":True,"stats":True})
        # Coalesce event bursts into a slow, visible-view-only refresh.
        if self._refresh_after_id is None:
            self._refresh_after_id=self.root.after(self._event_refresh_delay_ms,self._refresh_event_views)

    def _refresh_lt_status_async(self):
        if self._closing or self._lt_status_busy:
            return
        self._lt_status_busy=True
        def worker():
            try:
                text=str(languagetool_status().get("text") or "LanguageTool: невідомий стан")
            except Exception as exc:
                text=f"LanguageTool: стан недоступний ({type(exc).__name__})"
            self._post_ui(self._apply_lt_status,text)
        threading.Thread(target=worker,daemon=True,name="ui-languagetool-status").start()

    def _apply_lt_status(self,text):
        self._lt_status_busy=False
        if not self._closing and hasattr(self,"lt_status_var"):
            self.lt_status_var.set(str(text))

    def _tick(self):
        if self._closing:
            return
        self.status_var.set("Автопілот: працює" if self.service.running else "Автопілот: зупинено")
        now=time.monotonic()
        if hasattr(self,"lt_status_var") and now >= self._next_lt_status_at:
            self._next_lt_status_at=now+15.0
            self._refresh_lt_status_async()
        self.root.after(2000,self._tick)

    def close(self):
        if self._closing:
            return
        self._closing=True
        self.service.stop()
        try:
            shutdown_languagetool()
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
