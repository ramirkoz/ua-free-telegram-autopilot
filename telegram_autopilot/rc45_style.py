from __future__ import annotations

_INSTALLED = False

_STYLE_ADDENDUM = """RC45 HUMAN EDITORIAL STYLE OVERRIDE.
These rules refine style only; all factual/Fact Guard rules below remain mandatory.
- Build the post around ONE dominant news idea. Do not retell every useful-looking detail from SOURCE.
- Prefer an ordinary strong fact to a manufactured hook. A post does not need to sound clever to sound human.
- Usually use 2-3 short paragraphs. Keep only the details needed to understand the event.
- Do not force a witty turn, dramatic reveal, obligatory 'why it matters' sentence or closing kicker.
- Avoid recurring scaffolding such as «найцікавіше тут», «але є нюанс», «іронія в тому», «ставка проста», «найгірша деталь», «це не ще один», «головна деталь» unless that exact construction is genuinely the clearest wording for this one story.
- Do not make every paragraph end with an editorial flourish. Some paragraphs should simply state the verified fact.
- Vary openings naturally across the feed: fact, number, person, result or short source-supported quote are all valid. Never invent an angle just to make the opening distinctive.
- Never refer to the Telegram channel itself as a source or narrator.
- End on the last useful verified fact. Do not add a mini-summary of what the reader has just read.
"""


def install_rc45_style() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production

    original = production.build_rewrite_prompt

    def build_rewrite_prompt_rc45(channel, article, *, local=False, hard_limit=production.MEDIA_POST_HARD_LIMIT):
        return _STYLE_ADDENDUM + "\n\n" + original(
            channel, article, local=local, hard_limit=hard_limit
        )

    production.build_rewrite_prompt = build_rewrite_prompt_rc45
    _INSTALLED = True
