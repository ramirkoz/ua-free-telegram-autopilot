# UA FREE Telegram Autopilot v0.1.0-rc29

Stability hotfix over RC28.

- Worker/service threads never call Tkinter directly.
- Service/UI events are transferred through a thread-safe queue and drained only by the main Tk thread.
- UI refresh bursts are coalesced instead of rebuilding views on every event.
- UI/observability callback failures cannot terminate the autopilot collection/processing cycle.
- Close path stops accepting UI work before shutting down LanguageTool and Tk.
- AI Router, LanguageTool policy, database, source logic, Telegram publisher, media pipeline and QA behavior are unchanged from RC28.
