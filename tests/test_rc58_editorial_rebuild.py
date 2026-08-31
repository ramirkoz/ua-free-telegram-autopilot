from __future__ import annotations

from types import SimpleNamespace


def _ch(name: str, profile: str = ""):
    return SimpleNamespace(id=1, name=name, editorial_profile=profile)


def test_ctrl_selector_rejects_consumer_howto_and_keeps_science():
    from telegram_autopilot.rc58_editorial_rebuild import editorial_reject_reason
    howto = {"title": "How to improve Android Auto audio quality", "raw_text": "Tips for settings, cable and streaming quality."}
    science = {"title": "CERN creates quark-gluon plasma in oxygen collisions", "raw_text": "Scientists report research into matter from the early universe."}
    assert editorial_reject_reason(_ch("CTRL+UA"), howto)
    assert editorial_reject_reason(_ch("CTRL+UA"), science) == ""


def test_prodano_requires_marketing_mechanic():
    from telegram_autopilot.rc58_editorial_rebuild import editorial_reject_reason
    login = {"title": "Meta updates Login with Facebook", "raw_text": "One-tap sign-on arrives in the SDK for developers."}
    activation = {"title": "Snipes turns stores into Knicks watch parties", "raw_text": "The brand activation brought influencers and community members into stores for watch parties and social-first content."}
    gem = {"title": "Threads tests a gem award for high-engagement posts", "raw_text": "A virtual gem badge would recognize creators whose posts drive engagement, adding gamification to the platform."}
    assert editorial_reject_reason(_ch("ПРОДАНО!"), login)
    assert editorial_reject_reason(_ch("ПРОДАНО!"), activation) == ""
    assert editorial_reject_reason(_ch("ПРОДАНО!"), gem) == ""


def test_dual_reactions_stay_independent_topic_vs_style():
    from telegram_autopilot.rc58_editorial_rebuild import semantic_editor_adjustment
    from telegram_autopilot.rc52_feedback import style_feedback_signal, topic_feedback_signal
    row = {"title": "CERN plasma research", "raw_text": "Scientists at CERN study quark gluon plasma and physics.", "published_at": "2099-01-01T00:00:00+00:00", "likes": 0, "dislikes": 1, "fires": 1}
    candidate = {"title": "New CERN plasma experiment", "raw_text": "Scientists report physics research at CERN."}
    assert topic_feedback_signal(row) == -2.0
    assert style_feedback_signal(row) == 1.0
    score, positive, negative = semantic_editor_adjustment(candidate, [row], "ctrlua")
    assert score < 0
    assert positive == 0
    assert negative > 0


def test_fire_alone_does_not_raise_topic_semantic_score():
    from telegram_autopilot.rc58_editorial_rebuild import semantic_editor_adjustment
    row = {"title": "Robot prototype", "raw_text": "Engineers built a robot prototype.", "published_at": "2099-01-01T00:00:00+00:00", "likes": 0, "dislikes": 0, "fires": 2}
    candidate = {"title": "Another robot", "raw_text": "Engineers test a robot."}
    assert semantic_editor_adjustment(candidate, [row], "ctrlua") == (0.0, 0.0, 0.0)


def test_writer_prompt_is_channel_specific_and_contains_profile():
    from telegram_autopilot.rc58_editorial_rebuild import build_ua_writer_prompt_rc58
    from telegram_autopilot import rc52_feedback
    old = rc52_feedback.style_memory_block
    rc52_feedback.style_memory_block = lambda *a, **k: ""
    try:
        article = {"title": "Test", "raw_text": "A sufficiently long source text about a brand campaign and creators." * 20}
        ctrl = build_ua_writer_prompt_rc58(_ch("CTRL+UA", "Мій профіль CTRL"), article, "", hard_limit=900)
        prod = build_ua_writer_prompt_rc58(_ch("ПРОДАНО!", "Мій профіль PROD"), article, "", hard_limit=900)
    finally:
        rc52_feedback.style_memory_block = old
    assert "розумної людини" in ctrl
    assert "16-річний" in ctrl
    assert "Мій профіль CTRL" in ctrl
    assert "МЕХАНІКА" in prod
    assert "вірусного маркетингу" in prod
    assert "Мій профіль PROD" in prod


def test_audio_player_is_not_video_media(monkeypatch):
    import telegram_autopilot.media as media
    import telegram_autopilot.media_pipeline as pipeline
    import telegram_autopilot.rc58_editorial_rebuild as rc58
    monkeypatch.setattr(rc58, "_PREVIOUS_MEDIA_VALIDATOR", media.valid_public_media)
    rc58._install_media_filter()
    assert pipeline.valid_public_media("video|https://example.com/tts/story.wav") is None
    assert pipeline.valid_public_media("video|https://example.com/video/story.mp4") == ("video", "https://example.com/video/story.mp4")


def test_learned_summary_exposes_topic_direction_and_fire():
    from telegram_autopilot.rc58_editorial_rebuild import learned_summary
    rows = [
        {"title": "CERN plasma research", "raw_text": "CERN scientists physics research", "published_at": "2099-01-01T00:00:00+00:00", "likes": 2, "dislikes": 0, "fires": 1, "views": 100, "audience_positive": 8, "audience_negative": 0, "audience_fires": 1, "audience_other": 0, "forwards": 2, "replies": 0},
        {"title": "How to improve Android Auto audio", "raw_text": "tips settings how to", "published_at": "2099-01-01T00:00:00+00:00", "likes": 0, "dislikes": 2, "fires": 0, "views": 100, "audience_positive": 1, "audience_negative": 1, "audience_fires": 0, "audience_other": 0, "forwards": 0, "replies": 0},
    ]
    text = learned_summary(rows, "ctrlua")
    assert "Адміни хочуть більше" in text
    assert "наука / дослідження" in text
    assert "Адміни хочуть менше" in text
    assert "побутові інструкції" in text
    assert "🔥 стильових голосів: 1" in text


def test_prodano_corpus_examples_filter_platform_churn():
    from telegram_autopilot.rc58_editorial_rebuild import editorial_reject_reason
    ch = _ch("ПРОДАНО!")
    instagram_metrics = {"title": "Instagram growth continues to outpace Facebook in EU", "raw_text": "Instagram had 297 million active users in the EU and Facebook 264 million in DSA reporting. User growth continues year over year."}
    pinterest_event = {"title": "Pinterest announces 2026 Pinterest Presents event", "raw_text": "The virtual event on September 17 will include speakers, sessions, product announcements and advertiser updates."}
    grok_api = {"title": "X offers free API credits for its Grok Bot", "raw_text": "Paid users can connect a developer account, use API credits and analytics tooling."}
    snipes = {"title": "Snipes uses Knicks run for in-store watch parties", "raw_text": "The brand activation turned stores into watch parties with community members and influencers, targeting Gen Z and Gen Alpha."}
    assert editorial_reject_reason(ch, instagram_metrics)
    assert editorial_reject_reason(ch, pinterest_event)
    assert editorial_reject_reason(ch, grok_api)
    assert editorial_reject_reason(ch, snipes) == ""
