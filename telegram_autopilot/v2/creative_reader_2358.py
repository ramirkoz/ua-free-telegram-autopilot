"""Narrow source-only portfolio veto and shared creative selector guidance."""
import re

CREATIVE_READER_GUIDANCE = (
    'ПРОДАНО! 2.3.58: обов’язкова конкретна причина, чому історія цікава '
    'людині поза професійною галуззю. Самі портфоліо, добірки робіт автора, '
    'нагороди, презентації звичайного товару, типографічні вправи або '
    'професійні похвали не є новиною. Потрібна підтверджена SOURCE незвичайна '
    'ідея, механізм, людська історія, культурний поворот або практична користь, '
    'яку можна пояснити без професійного жаргону. Не вимагай вірусності, '
    'продажів чи сенсації. Не відхиляй цілу категорію дизайну. Якщо такої '
    'причини немає, REJECT; не вигадуй її з рекламних прикметників.'
)

def _field(article, key):
    try:
        return str(article[key] or '')
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, '') or '')

_PORTFOLIO = re.compile(r'\b(?:portfolio|(?:five|six|seven|eight|ten|\d+)\s+(?:of\s+(?:his|her|their)\s+)?(?:favou?rite\s+|design\s+|creative\s+)?(?:works|projects)|career retrospective|selected works|body of work)\b', re.I)
_PROFILE = re.compile(r'\b(?:designer|creative director|graphic design|design studio|typographer|art director)\b', re.I)
_CAREER = re.compile(r'\b(?:portfolio|career|practice|client projects|commissioned|design process|creative journey|personal style|visual identity|selected works)\b', re.I)
_PUBLIC = re.compile(r'\b(?:public installation|accessible|accessibility|blind|disabled|wheelchair|recycl\w*|repair\w*|interactive|invent\w*|patent\w*|protest|community|charity|social impact|first[- ]ever|world record|unexpected|unusual|campaign stunt|optical illusion|working prototype)\b', re.I)

def creative_portfolio_reason(article):
    title = _field(article, 'title')[:700]
    body = _field(article, 'raw_text')[:12000]
    if (_PORTFOLIO.search(title) and _PROFILE.search(title + ' ' + body[:1200])
            and _CAREER.search(body) and not _PUBLIC.search(title + ' ' + body)):
        return 'CREATIVE_SPECIALIST_PORTFOLIO_2358'
    # Narrowly scoped to retail footwear/apparel listings, not all design.
    # Related-story cards must not provide the novelty for a routine product.
    main = re.split(r"(?i)Read Full Article|What to Read Next|Related Stories", body, maxsplit=1)[0]
    retail = bool(re.search(r"(?i)\b(?:colorway|colourway)\s*:", main) and
                  re.search(r"(?i)\b(?:SKU|MSRP|Release Date)\s*:", main))
    fashion = bool(re.search(r"(?i)\b(?:sneakers?|footwear|shoes?|vans|apparel|jacket)\b", title + ' ' + main[:700]))
    # A named unusual mechanism, accessibility, material reuse, public-interest
    # intervention or explicitly novel transformation remains eligible for AI.
    if retail and fashion and not _PUBLIC.search(title + ' ' + main) and not re.search(
        r"(?i)\b(?:solar.powered|self.lacing|3d.print\w*|biodegradable|prosthe\w*|made from waste|made from recycled|transform\w* into|built from|upcycl\w*)\b", title + ' ' + main):
        return 'CREATIVE_ROUTINE_RETAIL_LISTING_2362'
    return ''
