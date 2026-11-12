"""Focused v2.3.28 regressions: operator control, foreign media, truncated copy, restart."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from telegram_autopilot.article_extractor import extract_article_content
from telegram_autopilot.v2.terminal_text_guard_228 import incomplete_terminal_text_228
from telegram_autopilot.v2.carryover_ready_228 import safe_same_day_ready_228
from telegram_autopilot.media_pipeline import PreparedMedia, _in_story_gallery


class TestV2328(unittest.TestCase):
    def test_visible_controls_scrollable_tabs_in_actual_ui_source(self):
        import inspect
        from telegram_autopilot.v2.ui import ChannelDialog
        source = inspect.getsource(ChannelDialog)
        self.assertIn('footer.pack(side="bottom"', source)
        self.assertIn('self._scrollable_tab(', source)
        self.assertIn('text="Зберегти канал"', source)
        self.assertIn('self.protocol("WM_DELETE_WINDOW", self._cancel)', source)

    def test_gear_up_commerce_images_not_article_photos(self):
        html = """<html><head><meta property="og:title" content="Naruto art"></head><body>
        <article><h1>Naruto art</h1><p>Artist painted Kankuro.</p>
        <figure><img alt="Kankuro Naruto ninja puppet" src="/naruto-art.jpg"></figure>
        <h2>Gear up</h2><p>See below for today's best deals on drawing tablets.</p>
        <div class="gallery"><img alt="Drawing tablet tool kit" src="/tool-kit.jpg"></div>
        </article></body></html>"""
        value = extract_article_content(html, "https://www.creativebloq.com/how-to/naruto-art")
        self.assertIn("naruto-art.jpg", " ".join(value.media_urls))
        self.assertNotIn("tool-kit.jpg", " ".join(value.media_urls))

    def test_unverified_blank_css_gallery_never_overrides_story_media(self):
        unrelated = PreparedMedia(2, "image", "https://example.com/tool-kit.jpg", gallery=True, context="gallery")
        self.assertFalse(_in_story_gallery(unrelated, title="Naruto puppet", article_text="Kankuro anime"))
        verified = PreparedMedia(2, "image", "https://example.com/actual.jpg", gallery=True, schema_verified=True)
        self.assertTrue(_in_story_gallery(verified, title="Naruto puppet", article_text="Kankuro anime"))

    def test_repeated_zaporizhzhia_outage_with_older_restoration_details_is_duplicate(self):
        from telegram_autopilot.v2.incident_guard import same_confirmed_power_event_228
        prior = ("Вчора КАБи пошкодили дві високовольтні лінії у Запоріжжі. "
                 "Без світла залишилися понад 16 тисяч споживачів. "
                 "Знеструмлення зафіксували о 20:15; з 01:46 світло відновили.")
        echo = ("Через удари КАБів у Запоріжжі пошкоджено дві високовольтні лінії. "
                "Без світла залишилися понад 16 тисяч споживачів.")
        update = echo + " О 02:35 пошкоджено ще один об'єкт."
        restored_update = echo + " Пізніше електропостачання відновлено."
        self.assertTrue(same_confirmed_power_event_228(echo, prior))
        self.assertFalse(same_confirmed_power_event_228(update, prior))
        self.assertFalse(same_confirmed_power_event_228(restored_update, echo))

    def test_truncated_sentence_hard_gate(self):
        self.assertEqual(incomplete_terminal_text_228("Батарея працює за інших умов:"), "TRUNCATED_TERMINAL_PUNCTUATION_228")
        self.assertEqual(incomplete_terminal_text_228("Виявили новий пристрій, але"), "TRUNCATED_TERMINAL_CONNECTOR_228")
        self.assertEqual(incomplete_terminal_text_228("Батарея пройшла 1000 циклів."), "")

    def test_preboot_prepared_same_day_passes_only_within_short_restart(self):
        now = datetime(2026, 11, 11, 16, 6, tzinfo=timezone.utc)
        self.assertTrue(safe_same_day_ready_228(
            "2026-11-11T14:00:00+00:00", "2026-11-11T14:02:00+00:00",
            "2026-11-11T14:15:00+00:00", "2026-11-11T14:55:00+00:00", now=now))
        self.assertFalse(safe_same_day_ready_228(
            "2026-11-10T14:00:00+00:00", "2026-11-10T14:02:00+00:00",
            "2026-11-10T14:15:00+00:00", "2026-11-11T14:55:00+00:00", now=now))
        self.assertFalse(safe_same_day_ready_228(
            "2026-11-11T14:00:00+00:00", "2026-11-11T15:02:00+00:00",
            "2026-11-11T15:15:00+00:00", "2026-11-11T14:55:00+00:00", now=now))


if __name__ == "__main__":
    unittest.main()
