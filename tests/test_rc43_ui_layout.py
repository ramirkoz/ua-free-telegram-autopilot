from __future__ import annotations

from telegram_autopilot.rc43_ui import _target_dialog_size


def test_rc43_uses_more_vertical_room_when_screen_allows_it():
    width, height = _target_dialog_size(1920, 1080, 880, 900)
    assert width >= 900
    assert height >= 924
    assert height <= 980


def test_rc43_never_places_dialog_beyond_available_screen_height():
    _width, height = _target_dialog_size(1366, 768, 900, 900)
    assert height <= 668


def test_rc43_keeps_small_requested_form_at_practical_default_size():
    width, height = _target_dialog_size(1920, 1080, 700, 600)
    assert width == 900
    assert height == 820
