"""2.3.25 operator LIVE regression tests, no internet calls."""
from __future__ import annotations
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from telegram_autopilot.v2.numeric_grounding import unsupported_numbers
from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322
from telegram_autopilot.v2.editorial_feedback_2312 import source_only_promotion_veto_2312
from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2.domain import ProviderState, ProviderHealth, AIModelHealth
from telegram_autopilot.v2.freshness_fence_241 import restart_source_rejection

class Test2325(unittest.TestCase):
    def test_english_comma_thousands(self):
        self.assertEqual(unsupported_numbers("3,500 laser armed AI robots protect salmon farms", "3500 роботів"), [])
        self.assertIn("3501", unsupported_numbers("3,500 laser armed robots", "3501 роботів"))
        self.assertIn("3500", unsupported_numbers("Витрати склали 3,500 млн гривень.", "Витрати 3500 млн гривень."))

    def test_lost_animal_owner_notice(self):
        notice = "У Запоріжжі до кав’ярні зайшла коза. Волонтери шукають власників незвичайної гості."
        self.assertNotEqual(no_announcement_reason_2322({"title":notice,"raw_text":notice}), "")
        self.assertEqual(no_announcement_reason_2322({"title":"Рятувальники врятували козу","raw_text":"Ветеринари допомогли козі після пожежі."}), "")

    def test_creative_buying_guide_not_editorial_invention(self):
        row={"source_url":"https://www.creativebloq.com/buying-guides/the-best-cnc-machines-the-crafting-revolution-starts-here","title":"The best CNC machines"}
        self.assertEqual(source_only_promotion_veto_2312("creative",row), "EDITORIAL_OPERATOR_BUYING_GUIDE_2325")
        row["source_url"]="https://www.creativebloq.com/design/artist-makes-new-cnc-art"
        self.assertEqual(source_only_promotion_veto_2312("creative",row), "")

    def test_known_json_failure_is_demoted_not_disabled(self):
        gateway=AIGateway(MagicMock())
        self.assertTrue(gateway._contract_unreliable("editorial_selector","inclusionai/ling-3.0-tiny"))
        self.assertFalse(gateway._contract_unreliable("writer","inclusionai/ling-3.0-tiny"))

    def test_bounded_restart_checkpoint(self):
        now=datetime(2026,11,11,12,0,tzinfo=timezone.utc)
        started=(now-timedelta(minutes=5)).isoformat()
        checkpoint=(now-timedelta(minutes=20)).isoformat()
        published=(now-timedelta(minutes=12)).isoformat()
        discovered=(now-timedelta(minutes=1)).isoformat()
        self.assertEqual(restart_source_rejection(published,started,checkpoint,discovered_at=discovered,now=now,rolling_window_hours=24), "")
        self.assertEqual(restart_source_rejection(published,started,(now-timedelta(hours=4)).isoformat(),discovered_at=discovered,now=now,rolling_window_hours=24), "SOURCE_PREDATES_RUNTIME_START")

    def test_stale_health_preserves_model_rows(self):
        old="2026-11-09T10:41:54+02:00"
        provider=ProviderHealth(provider="gemini",state=ProviderState.NETWORK_DOWN,updated_at=old)
        model=AIModelHealth(provider="gemini",model="gemini-3.5-flash",state=ProviderState.NETWORK_DOWN,updated_at=old)
        store=MagicMock()
        store.provider_health.return_value=[provider]
        store.ai_model_health.return_value=[model]
        self.assertEqual(AIGateway(store).mark_stale_provider_health_on_start("2026-11-11T11:55:48+02:00"),1)
        self.assertEqual(provider.state,ProviderState.UNKNOWN)
        self.assertEqual(model.state,ProviderState.NETWORK_DOWN)
        store.set_ai_model_health.assert_not_called()

if __name__ == "__main__": unittest.main()
