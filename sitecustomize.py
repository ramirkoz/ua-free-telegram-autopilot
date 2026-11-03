import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

def _codex_present():
    try:
        from telegram_autopilot.codex_engine import inspect_codex
        return bool(inspect_codex().installed)
    except Exception:
        return False

def _data_root():
    raw = os.environ.get('UA_FREE_TELEGRAM_AUTOPILOT_DATA', '').strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / 'Data'

def _bootstrap_codex():
    if _codex_present():
        return True, ''
    root = Path(__file__).resolve().parent / 'Tools' / 'Codex'
    versions = root / 'codex_versions'
    versions.mkdir(parents=True, exist_ok=True)
    unique = f"codex-0.156.1-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    staging = versions / ('.' + unique + '.tmp')
    target = versions / unique
    staging.mkdir(parents=True, exist_ok=False)
    runtime = Path(__file__).resolve().parent / '_runtime_console.exe'
    command = [str(runtime), '-I', '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--target', str(staging), 'openai-codex==0.156.1']
    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'
    env['UA_FREE_CODEX_BOOTSTRAP'] = '0'
    try:
        done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=600, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if done.returncode != 0 or not (staging / 'openai_codex').exists():
            tail='\n'.join(done.stdout.splitlines()[-12:])
            raise RuntimeError(tail or f'pip exit {done.returncode}')
        staging.rename(target)
        pointer = root / 'codex_active.json'
        temp = root / 'codex_active.tmp'
        temp.write_text(json.dumps({'directory': target.relative_to(root).as_posix(), 'package': 'openai-codex==0.156.1', 'updated_at': int(time.time())}, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, pointer)
        return True, ''
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return False, str(exc)

def _first_run_setup():
    if os.environ.get('UA_FREE_CODEX_BOOTSTRAP', '1') == '0' or _codex_present():
        return True
    if os.environ.get('UA_FREE_CODEX_BOOTSTRAP_ONLY', '') == '1':
        ok, error = _bootstrap_codex()
        os._exit(0 if ok else 2)
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
        root = tk.Tk()
        root.title('UA FREE Telegram Autopilot · AI runtime')
        root.geometry('520x175')
        root.resizable(False, False)
        ttk.Label(root, text='Перший запуск: встановлюю Codex AI runtime', font=('Segoe UI', 11, 'bold')).pack(pady=(22, 8))
        ttk.Label(root, text='Це одноразове завантаження. Основна програма залишається компактною.').pack(pady=(0, 12))
        bar = ttk.Progressbar(root, mode='indeterminate', length=430)
        bar.pack(pady=4)
        bar.start(10)
        result = {'done': False, 'ok': False, 'error': ''}
        def work():
            ok, error = _bootstrap_codex()
            result.update(done=True, ok=ok, error=error)
        threading.Thread(target=work, daemon=True, name='Codex-FirstRun-Bootstrap').start()
        def poll():
            if not result['done']:
                root.after(250, poll)
                return
            bar.stop()
            if not result['ok']:
                messagebox.showwarning('Codex не встановлено', 'Не вдалося завантажити AI runtime. Програма відкриється без Codex; повторіть запуск при стабільному інтернеті.\n\n' + result['error'][-1200:], parent=root)
            root.destroy()
        root.after(250, poll)
        root.mainloop()
        return bool(result['ok'])
    except Exception:
        return False

if os.path.basename(sys.executable).casefold() == 'ua_free_telegram_autopilot.exe':
    # Optional Codex provisioning must NEVER gate UI/import/runtime.
    # Explicit bootstrap-only mode remains available to release QA;
    # operator may configure Codex later without delaying startup.
    if os.environ.get('UA_FREE_CODEX_BOOTSTRAP_ONLY', '') == '1':
        _first_run_setup()
        os._exit(0)
    from telegram_autopilot.v2.main import main
    os._exit(int(main() or 0))
