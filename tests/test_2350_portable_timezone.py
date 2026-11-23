"""2.3.50: a portable runtime must not starve channels on missing tzdata.

Production symptom: v2.3.49 packaged 23 Nov had no Europe/Kyiv IANA
database. Its normal CI installed tzdata but release --target pip did not.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from zoneinfo import ZoneInfoNotFoundError

from telegram_autopilot.v2 import editorial_admission_2349 as admission


def test_commercial_channel_and_civic_non_schedule_do_not_require_tzdata():
    """A timezone failure in service scheduling must not block unrelated news."""
    admission._kyiv_tz.cache_clear()
    with patch.object(admission, "ZoneInfo", side_effect=ZoneInfoNotFoundError):
        assert admission.commercial_catalog_reason_2349(
            {"title": "New bespoke cultural collaboration", "raw_text": "Unique art"}
        ) == ""
        assert admission.commercial_catalog_reason_2349(
            {"title": "5 Best Cabin Accessories That Add Comfort"}
        ) == "CREATIVE_ROUTINE_BEST_N_CATALOG_2349"
        assert admission.regional_no_result_reason_2349(
            {"title": "A confirmed citizen rescue", "raw_text": "A victim rescued"}
        ) == ""
        assert admission.expired_service_reason_2349(
            {"title": "Art exhibition opens", "raw_text": "Date and address inside"}
        ) == ""
        with pytest.raises(ZoneInfoNotFoundError):
            admission._kyiv_tz()
    admission._kyiv_tz.cache_clear()


def test_windows_portable_really_installs_and_smokes_timezone():
    """Do not permit a future source-only green CI with a timezone-less ZIP."""
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")
    assert "'tzdata>=2025.2' pip" in workflow
    assert "Validate IANA Kyiv timezone in isolated portable runtime" in workflow
    assert "V2_PORTABLE_KYIV_ZONEINFO_AND_EDITORIAL_PASS" in workflow
    assert r"ZoneInfo('Europe/Kyiv')" in workflow
    assert r"2026,7,23" in workflow  # DST transition behavior is validated too
