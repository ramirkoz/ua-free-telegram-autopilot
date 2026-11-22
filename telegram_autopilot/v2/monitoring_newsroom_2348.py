"""2.3.48: original-source regional-newsworthiness and independent journalist voice.

Conservative ceremonial/protocol veto; tangible outcomes and service facts win.
Writing guidance changes only existing prompts, not source facts or delivery.
"""
from __future__ import annotations
import re
from typing import Any

def _v(a: Any,k: str)->str:
    try: return str(a[k] or "")
    except (KeyError,IndexError,TypeError): return str(getattr(a,k,"") or "")

_GREETING=re.compile(r"(?iu)\b(?:віта(?:ю|ємо|є|ють|ли)|привітал\w*|щиро\s+віта\w*|бажаємо|побажал\w*|нехай|хай\s+кожен)\b")
_HOLIDAY=re.compile(r"(?iu)\b(?:д(?:ень|ня|нем|ні|ню)\s+(?:територіальн\w*\s+)?громад\w*|д(?:ень|ня|нем|ні|ню)\s+(?:гідност\w*\s+та\s+свобод\w*|соборност\w*|незалежност\w*|вишиванк\w*|міста|села)|з\s+(?:професійн\w*|державн\w*)\s+свят\w*)\b")
_RESULT=re.compile(r"(?iu)\b(?:евакуювал\w*|евакуйован\w*|поранен\w*|загинул\w*|загибл\w*|постраждал\w*|пошкоджен\w*|відключил\w*|відновил\w*|перекрил\w*|відкрили|відкрито|запустили|запровадили|ухвалил\w*|затвердил\w*|рішенн\w*\s+про\s+виділенн\w*|спрямували\s+\d|виділили\s+\d|передали\s+(?:\d|автомобіл\w*|генератор\w*|обладнанн\w*|допомог\w*)|видали\s+(?:\d|мешканц\w*|родин\w*|допомог\w*)|отримали\s+(?:\d|допомог\w*)|здійснил\w*\s+(?:виплат\w*|ремонт\w*)|розпочал\w*\s+(?:ремонт\w*|реєстраці\w*)|завершил\w*\s+(?:ремонт\w*|будівництв\w*)|\d+\s+(?:людей|осіб|родин|дітей|укрит\w*|домів\w*)\s+(?:отримал\w*|евакуювал\w*|забезпечил\w*|відремонтувал\w*))\b")
_SERVICE=re.compile(r"(?iu)(?:\b(?:телефон\w*|звертайтеся|реєстраці\w*|графік\w*|адрес\w*|прийом\s+заявок|гаряч\w*\s+ліні\w*)\b.{0,120}\b(?:\d{2,}|о\s+\d{1,2}[:.]\d{2})\b|\b(?:вул\.?|вулиц\w*|пров\.?|просп\.?|проспект\w*)\s+[А-ЯІЇЄҐ][^\n,.;]{2,65}(?:\d{1,3}|до\s+\d{1,2}[:.]\d{2}))")
_PROTOCOL=re.compile(r"(?iu)\b(?:взяв\w*\s+участь|взял\w*\s+участь|долучил\w*\s+до\s+(?:засіданн\w*|зустріч\w*|форум\w*)|відбу\w*\s+(?:зустріч\w*|засіданн\w*|кругл\w*\s+стіл)|провел\w*\s+(?:засіданн\w*|зустріч\w*|кругл\w*\s+стіл))\b")
_MEETING=re.compile(r"(?iu)\b(?:засіданн\w*|нарад\w*|кругл\w*\s+стол\w*|кругл\w*\s+стіл|форум\w*|зустріч\w*\s+(?:з|із|зі)\s+(?:представник\w*|керівник\w*|партнер\w*))\b")
_DISCUSS=re.compile(r"(?iu)\b(?:обговорил\w*|дискутувал\w*|ознайомил\w*|поділ\w*\s+досвід\w*|розповіл\w*|висловил\w*|підкреслил\w*\s+важлив\w*|наголосил\w*\s+на\s+важлив\w*)\b")
_ATTACK=re.compile(r"(?iu)\b(?:загинул\w*|загибл\w*|поранен\w*|постраждал\w*|атак\w*|влуч\w*|обстріл\w*|пожеж\w*)\b")
_CIVIC_SERVICE=re.compile(r"(?iu)\b(?:евакуац\w*|водопостачанн\w*|електропостачанн\w*|відключенн\w*|рух\s+транспорт\w*|розклад\w*|графік\w*|укрит\w*|реєстраці\w*|виплат\w*)\b")
_AID=re.compile(r"(?iu)\b(?:передал\w*\s+допомог\w*|видал\w*\s+допомог\w*|отримал\w*\s+допомог\w*|підтрима\w*\s+родин\w*)\b")
_ROBOTIC=re.compile(r"(?iu)^\s*(?:у\s+межах\s+(?:виконанн\w*|реалізаці\w*|проєкт\w*)|з\s+метою\s+(?:покращенн\w*|забезпеченн\w*|реалізаці\w*)|було\s+(?:проведено|здійснено|організовано)|(?:представник\w*|керівник\w*|начальник\w*|фахівц\w*|спеціаліст\w*)\b[^.!?\n]{0,140}\b(?:взял\w*\s+участь|долучил\w*|обговорил\w*))")

def source_non_news_reason_2348(article: Any)->str:
    """Narrow source-only gate; protect real outcomes, numbers and services."""
    original=(_v(article,"title")+"\n"+_v(article,"raw_text")[:10000]).strip()
    if len(original)<50 or _RESULT.search(original) or _SERVICE.search(original):return ""
    if _GREETING.search(original) and _HOLIDAY.search(original):return "MONITORING_CEREMONIAL_GREETING_NO_EVENT_2348"
    if _PROTOCOL.search(original) and _MEETING.search(original) and _DISCUSS.search(original):return "MONITORING_PROTOCOL_MEETING_NO_RESULT_2348"
    return ""

def monitoring_newsroom_instruction_2348(article: Any, *, final: bool=False)->str:
    """Late-stage independent newsroom voice, no source assertions."""
    s=_v(article,"title")+" "+_v(article,"raw_text")[:2800]
    if _ATTACK.search(s):
        direction="НАСЛІДКИ АТАКИ: почни з підтверджених наслідків для людей і місця; далі обсяг атаки й попередні дані з атрибуцією."
    elif _CIVIC_SERVICE.search(s):
        direction="СЕРВІС: спочатку що змінилось, кому, де і коли; збережи точні адреси, строки, контакти, умови."
    elif _AID.search(s):
        direction="ДОПОМОГА: спочатку кому і що передали/видали, де і в якій кількості; не вигадуй одержувачів."
    elif _MEETING.search(s):
        direction="НАРАДА: лише доведене SOURCE рішення/наслідок у першому реченні; якщо є тільки обговорення, не вигадуй рішення."
    else:
        direction="МІСЦЕВА ПОДІЯ: конкретна дія, наслідок, місце чи людина в першому реченні."
    return ("\nРЕДАКТОРСЬКИЙ СТАНДАРТ 2.3.48: Ти журналіст незалежної української "
            "регіональної редакції, не речник організатора. "+direction+" "
            "Не переказуй джерело абзац за абзацом. Перше речення відповідає "
            "на питання, що сталося й чого це стосується читача, без сенсаційності. "
            "Не починай з «у межах реалізації», «взяли участь», «відбулося засідання», "
            "«обговорили питання». Пиши короткими природними реченнями, називай "
            "того, хто діє, використай прості дієслова замість офіціозу. "
            "Не приписуй коментарю посадовця статус перевіреного факту. "
            "Не додавай вигаданих цитат, фактів, рішень, адрес, причин, наслідків "
            "або морального висновку. Невелика новина може мати два речення. "
            "Для постраждалих і загиблих лише стриманий тон. "
            + ("Як старший редактор, перероби казенний DRAFT по суті, не тільки коми." if final else "")
            + "\n")

def robotic_lead_reason_2348(draft: str)->str:
    """Soft diagnostic: requests existing trusted editor, never vetoes delivery."""
    return "MONITORING_BUREAUCRATIC_LEAD_2348" if _ROBOTIC.search(str(draft or "").strip()[:260]) else ""
