from __future__ import annotations

import logging

from .rc57_feedback_db import install_database_patch
from .rc57_scoring import install_scoring_patch
from .rc57_telegram_feedback import refresh_feedback_metrics_rc57
from .rc57_ui import (
    analytics_dialog_rc57,
    build_memory_rc57,
    install_fault_tolerant_ui_queue,
    refresh_memory_rc57,
    refresh_metrics_now_rc57,
)

LOG = logging.getLogger("telegram_autopilot.rc57")
_INSTALLED = False


def install_rc57_admin_audience_feedback() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    install_database_patch()
    install_scoring_patch()
    install_fault_tolerant_ui_queue()

    from . import rc48_learning, rc48_ui, rc51_feedback, rc51_ui, rc52_ui, rc53_ui, rc54_mtproto, rc56_reaction_runtime
    from .ui import MainWindow

    rc48_learning.refresh_channel_metrics = refresh_feedback_metrics_rc57
    rc51_feedback.refresh_feedback_metrics = refresh_feedback_metrics_rc57
    rc48_ui.refresh_channel_metrics = refresh_feedback_metrics_rc57
    rc51_ui.refresh_feedback_metrics = refresh_feedback_metrics_rc57
    rc54_mtproto.refresh_feedback_metrics_rc54 = refresh_feedback_metrics_rc57
    rc56_reaction_runtime.refresh_feedback_metrics_rc56 = refresh_feedback_metrics_rc57
    MainWindow._rc48_refresh_metrics_now = refresh_metrics_now_rc57

    old_build = MainWindow._build

    def build_rc57(self):
        old_build(self)
        build_memory_rc57(self)

    MainWindow._build = build_rc57
    MainWindow._rc48_refresh_memory = refresh_memory_rc57

    rc48_ui._analytics_dialog = analytics_dialog_rc57
    rc51_ui._analytics_dialog = analytics_dialog_rc57
    rc52_ui._analytics_dialog = analytics_dialog_rc57
    rc53_ui._analytics_dialog_rc53 = analytics_dialog_rc57

    _INSTALLED = True
    LOG.info(
        "RC57 installed: all-admin editor signals, normalized audience performance, fault-tolerant UI queue, bounded feedback runtime"
    )
