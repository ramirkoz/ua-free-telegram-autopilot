"""Owner 20 Nov 2026: ZERO culinary recipes; reader-first three-channel voice.

Original-source replay without operator Data or network calls.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_owner_2345 import absolute_recipe_reason_2345
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.editorial_voice_2337 import newsroom_voice_2337


CREATIVE = SimpleNamespace(
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    policy=SimpleNamespace(selection_rules=MARKER),
)
SCIENCE = SimpleNamespace(
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True,
    dedupe_compound_events=True,
    policy=SimpleNamespace(selection_rules=MARKER),
)
MONITORING = SimpleNamespace(mode=ChannelMode.MONITORING, policy=SimpleNamespace())
EXPECTED = "EDITORIAL_NO_RECIPES_OR_COOKING_TIPS_2345"


@pytest.mark.parametrize("title,source", [
    (
        "Add A Splash Of This Creamy Ingredient To Your Marinade For A Steak That's Anything But Rubbery",
        "A good marinade can make steak taste better. Start with half a cup to a cup "
        "of coconut milk for 1 to 2 pounds of steak. Add soy sauce and lime juice "
        "then leave the meat in the fridge overnight.",
    ),
    (
        "Steak Marinade Gets Extra Smoky And Flavorful With 3 Underappreciated Ingredients",
        "Marinade can transform a good steak into a great dish, using three "
        "underappreciated ingredients.",
    ),
    (
        "Gordon Ramsay's Thanksgiving Turkey Is 10X More Flavorful Than Yours Thanks To One Savory Ingredient",
        "The chef keeps turkey moist with bacon. He roasts it for 15 minutes "
        "then he bastes the bird before it goes back into the oven.",
    ),
    (
        "Ultimate Thanksgiving Leftovers Hoagie Sandwich Recipe",
        "Ingredients: turkey, ham, cheese and mayo. Step 1: Mix and bake for ten minutes.",
    ),
    (
        "Як приготувати маринад для стейка",
        "Додайте склянку молока, часник і ложку оцту, щоб замаринувати м'ясо.",
    ),
])
def test_real_owner_red_cooking_advice_blocked_before_ai_and_at_ready(title,source):
    row={"title":title,"raw_text":source}
    assert absolute_recipe_reason_2345(row)==EXPECTED
    assert editorial_source_topic_reason_2319(CREATIVE,row) in {
        EXPECTED,"CREATIVE_ORDINARY_COOKING_RECIPE_NOT_NEWS_2341"
    }
    assert hard_editorial_reject(CREATIVE,row,"AI-made beautiful cooking tip") in {
        EXPECTED,"CREATIVE_ORDINARY_COOKING_RECIPE_NOT_NEWS_2341"
    }


@pytest.mark.parametrize("row", [
    {"title":"This Cactus-Inspired Coffee Machine Looks More Like a Sculpture Than a Kitchen Appliance",
     "raw_text":"The redesigned coffee machine is a distinctive sculptural device with a new form."},
    {"title":"Easy Cooking Stove Concept Folds Its Burner and Pot Supports Into One Case",
     "raw_text":"The innovative stove prototype is compact and folds into its carrying case."},
    {"title":"This Madrid restaurant built a greenhouse to sell the vegetables it cooks with",
     "raw_text":"Architects designed a greenhouse that doubles as a farm shop."},
    {"title":"Yesterday's cooking oil powers 410,000 pink lights along Tokyo's river",
     "raw_text":"A lighting installation uses recycled cooking oil as biofuel."},
    {"title":"Innovative robot chef recipe campaign",
     "raw_text":"New robotic chef cooks ramen using novel sensors. Step 1 demonstrates the design."},
    {"title":"This recipe for successful packaging design is deceptively simple",
     "raw_text":"A brand design study of consumer packaging and marketing, not culinary preparation."},
])
def test_actual_design_foodtech_and_non_recipe_background_not_rejected(row):
    assert absolute_recipe_reason_2345(row)==""
    assert hard_editorial_reject(CREATIVE,row, "Справжня новина про дизайн") != EXPECTED


def test_no_recipe_any_channel_including_monitoring_and_old_ready():
    row={"title":"How to roast turkey for dinner","raw_text":"Cook the turkey for 30 minutes with salt and oil."}
    for channel in (SCIENCE,CREATIVE,MONITORING):
        assert hard_editorial_reject(channel,row,"Ready since yesterday") == EXPECTED


def test_no_guessed_source_and_no_data_dependency():
    row={"title":"Secret ingredient for steak", "raw_text":""}
    assert absolute_recipe_reason_2345(row)==""  # fail source-closed; no guessed claims


@pytest.mark.parametrize("role,mandatory,forbidden",[
    ({"science":True},"напругу від електричної","кулінарні інструкції"),
    ({"commercial":True},"АБСОЛЮТНО ЗАБОРОНЕНО рецепти","привітання до дати"),
    ({"monitoring":True},"повідомляють\nчитачі","маринади, секретні інгредієнти"),
])
def test_owner_reader_voice_calibration_is_channel_scoped(role,mandatory,forbidden):
    writer = newsroom_voice_2337(**role)
    final = newsroom_voice_2337(**role, final=True)
    assert "РЕДАКЦІЙНИЙ ЕТАЛОН 2.3.45" in writer
    assert mandatory in writer and forbidden not in writer
    assert "ПОВТОРНЕ РЕДАКТОРСЬКЕ ЧИТАННЯ" in final
    assert "ніяких нових дат" in writer
