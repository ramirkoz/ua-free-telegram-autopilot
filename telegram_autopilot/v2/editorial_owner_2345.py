"""2.3.45 owner's absolute editorial ban on culinary recipes and cooking tips.

Evaluate the original title + source body, NEVER an AI-written post. This
is a deterministic, zero-token gate shared by selection and prepublication.
Food-product inventions, restaurant architecture and genuine ad campaigns are
not cooking instructions and must remain eligible for normal editorial QA.
"""
from __future__ import annotations

import re
from typing import Any


def _field(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


# A title must describe an actual culinary how-to, tip, ingredient swap or
# preparation procedure. A random occurrence of "recipe" in a technology
# story (or a figurative "recipe for success") is not sufficient.
_RECIPE_TITLE = re.compile(
    r"(?iu)\b(?:recipes?|marinad(?:e|es|ing)|marinate|"
    r"(?:how|ways?)\s+to\s+(?:cook|bake|roast|fry|grill|season|prepare|make|tenderi[sz]e)\b|"
    r"(?:best|better|easy|simple|perfect|secret|ultimate|delicious)\s+"
    r"(?:way|ways|method|trick|tip|tips|ingredient|ingredients)\b|"
    r"(?:ingredient|ingredients)\s+(?:to|for|that|in|makes?|keeps?)\b|"
    r"(?:cooking|kitchen|chef|baking|grilling)\s+(?:tips?|tricks?|hacks?|methods?)\b|"
    r"рецепт\w*|маринад\w*|як\s+приготува\w*|"
    r"(?:секретн\w*|прост\w*|головн\w*)\s+інгредієнт\w*)\b"
)
_CULINARY_CONTEXT = re.compile(
    r"(?iu)\b(?:steaks?|beef|turkey|chicken|meat|pork|salmon|fish|shrimp|"
    r"sandwich(?:es)?|hoagie|pasta|noodles?|ramen|soup|salad|rice|"
    r"potatoes?|vegetables?|bread|muffins?|cookies?|cakes?|desserts?|"
    r"chocolate|coffee|tea|cocktails?|smoothies?|pancakes?|sushi|bacon|"
    r"dough|flour|cheese|eggs?|milk|ice[ -]cream|"
    r"tacos?|burgers?|pizza|dinners?|breakfast|lunch|meals?|dishes?|"
    r"marinad(?:e|es)|sauces?|gravy|baking|roast(?:ing)?|grilling|"
    r"стейк\w*|м.яс\w*|курк\w*|риб\w*|маринад\w*|"
    r"суп\w*|салат\w*|тіст\w*|соус\w*|страв\w*|випічк\w*)\b"
)
_EXPLICIT_HOWTO = re.compile(
    r"(?iu)\b(?:how\s+to\s+(?:cook|bake|marinate|roast|fry|grill|season|prepare)|"
    r"(?:tips?|tricks?|hacks?)\s+(?:for|to)\s+(?:cook|bake|marinat|roast|fry|grill)|"
    r"як\s+(?:приготува\w*|замаринува\w*|запекти\w*|посмажити))\b"
)
_COOKING_STEPS = (
    re.compile(r"(?iu)\b(?:ingredients?|mix|stir|whisk|add|toss|season|marinate|baste)\b"),
    re.compile(r"(?iu)\b(?:cook|bake|roast|fry|grill|simmer|preheat|sear)\b"),
    re.compile(r"(?iu)\b(?:cup|cups|tablespoons?|teaspoons?|tbsp|tsp|ounces?|pounds?|minutes?|hours?)\b"),
    re.compile(r"(?iu)\b(?:garlic|ginger|lime|milk|soy\s+sauce|vinegar|butter|salt|pepper|oil)\b"),
    re.compile(r"(?iu)\b(?:інгредієнт\w*|додай\w*|змішай\w*|"
               r"склянк\w*|ложк\w*|смаж\w*|запік\w*|молок\w*|ол\w*)\b"),
)
# This is a positive food-tech / design *classification*, not a bypass for a
# genuine recipe. An article with actual preparation directions is still banned.
_PRODUCT_NOT_RECIPE = re.compile(
    r"(?iu)\b(?:robot(?:ic)?\s+(?:chef|cooking|kitchen)|prototype|"
    r"new\s+(?:product|device|material|packaging|invention)|"
    r"advertising\s+campaign|brand\s+campaign|architecture|"
    r"package\s+design|new\s+restaurant\s+concept|"
    r"нов\w*\s+(?:пристр\w*|пакуван\w*|винах\w*)|"
    r"рекламн\w*\s+кампані\w*)\b"
)


def absolute_recipe_reason_2345(article: Any) -> str:
    """Ban recipes, ingredient tricks and culinary advice, including old READY.

    Source-first: original headline is a strong signal, source body must
    confirm a food preparation subject. Do not block a food-tech innovation
    based on the word 'recipe' appearing as incidental background.
    """
    title = _field(article, "title")[:1000]
    body = _field(article, "raw_text")[:6000]
    if not title.strip() or not body.strip():
        return ""
    # Indirect food advice, e.g. "Gordon Ramsay's Turkey Is More Flavorful
    # Thanks To One Ingredient", is still a cooking tip, not product news.
    food_tip_title = bool(
        _CULINARY_CONTEXT.search(title)
        and re.search(r"(?iu)\b(?:ingredients?|flavou?rful|tastier|juicier|"
                      r"tender(?:er)?|secret\s+trick|cooking\s+tips?|"
                      r"інгредієнт\w*|смачніш\w*|соковитіш\w*)\b", title)
    )
    # The headline may conceal the recipe as a "flavour trick" or "the
    # easiest way". Require a food subject in the original headline plus
    # three *different* preparation cues in its opening source paragraphs.
    cooking_signals_early = sum(bool(p.search(body[:2400])) for p in _COOKING_STEPS)
    cooking_instruction_story = bool(
        _CULINARY_CONTEXT.search(title) and cooking_signals_early >= 3
    )
    if not (_RECIPE_TITLE.search(title) or _EXPLICIT_HOWTO.search(title)
            or food_tip_title or cooking_instruction_story):
        return ""
    src = title + "\n" + body[:2400]
    if not _CULINARY_CONTEXT.search(src):
        return ""
    step_signals = sum(bool(p.search(body[:3000])) for p in _COOKING_STEPS)
    # Clearly instructive food headlines don't have to expose a numeric recipe
    # in a short RSS excerpt. The whole genre is disallowed, not just lists.
    explicit_recipe = bool(_EXPLICIT_HOWTO.search(title))
    ingredient_advice = bool(re.search(
        r"(?iu)\b(?:marinad(?:e|es|ing)|marinate|"
        r"ingredients?|secret\s+(?:ingredient|trick)|"
        r"маринад\w*|інгредієнт\w*)\b", title))
    if _PRODUCT_NOT_RECIPE.search(title) and step_signals < 3 and not explicit_recipe:
        return ""
    if explicit_recipe or ingredient_advice or (food_tip_title and step_signals >= 2) or step_signals >= 2:
        return "EDITORIAL_NO_RECIPES_OR_COOKING_TIPS_2345"
    return ""


# Independent last-mile veto: a writer may hallucinate a recipe even where
# its original source headline looked innocent. Only clear directions with
# at least two distinct cooking signals count; food-tech descriptions do not.
_OUTPUT_DISH = re.compile(
    r"(?iu)\b(?:рецепт\w*|маринад\w*|стейк\w*|соус\w*|"
    r"м.яс\w*|курк\w*|індичк\w*|риб\w*|суп(?:у|ом|ів|и)?|"
    r"салат\w*|картопл\w*|пиріг\w*|кава\w*|"
    r"страв\w*|десерт\w*|випічк\w*|рис\w*|паст\w*)\b"
)
_OUTPUT_STEPS = (
    re.compile(r"(?iu)\b(?:додати|додають|додайте|додає|змішати|змішайте|"
               r"змішують|замаринувати|маринуйте|маринувати|запікати|"
               r"запікайте|запікають|смажити|смажте|варити|варіть)\b"),
    re.compile(r"(?iu)\b(?:склянк\w*|ложк\w*|\d+\s*(?:грам\w*|хвилин\w*|годин\w*))\b"),
    re.compile(r"(?iu)\b(?:часник\w*|імбир\w*|оцет|оцту|олія|"
               r"молок\w*|вершк\w*|сіль|цукор|мед|соєв\w*\s+соус)\b"),
    re.compile(r"(?iu)\b(?:інгредієнт\w*|пропорці\w*|марину\w*|"
               r"залишит\w*\s+(?:на\s+ніч|у\s+холодильник\w*))\b"),
)


def final_recipe_reason_2345(text: str) -> str:
    """Block obvious Ukrainian cooking instructions at the actual send gate."""
    value = str(text or "").strip()[:2500]
    if not value or not _OUTPUT_DISH.search(value):
        return ""
    # Demand an actual preparation VERB. Ingredient/amount mentions alone
    # also occur in science, product news, and retailer price reports.
    if _OUTPUT_STEPS[0].search(value) and sum(bool(pattern.search(value)) for pattern in _OUTPUT_STEPS) >= 2:
        return "EDITORIAL_NO_RECIPES_FINAL_TEXT_2345"
    return ""


__all__ = ["absolute_recipe_reason_2345", "final_recipe_reason_2345"]
