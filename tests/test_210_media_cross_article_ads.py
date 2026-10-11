from telegram_autopilot.media_pipeline import PreparedMedia, _semantic_media_match

CASES = (
    ("3D printed jet Kingchaser takes flight", "kingchaser-jet.jpg", "Kingchaser jet prototype"),
    ("Yandex data center affected by drone attack", "yandex-data-center.jpg", "Yandex data center"),
    ("AnyPS5 shader instruction coverage RDNA", "anyps5-rdna.jpg", "AnyPS5 RDNA shader code"),
    ("AI game demo costs developers thousand dollars", "ai-game-demo.jpg", "AI game demo"),
    ("PS5SX2 PS2 games on jailbroken PlayStation", "ps5sx2-screen.jpg", "PS5SX2 emulator"),
)

def test_210_five_articles_do_not_accept_shared_sitewide_ad_as_verified_hero():
    for title, image_path, alt in CASES:
        common_ad = PreparedMedia(
            index=0, kind="image", url="https://example.org/sponsored/motherboard-cpu-socket.jpg",
            alt="generic motherboard cpu socket advertisement",
            context="verified_article_hero", featured=True,
        )
        assert not _semantic_media_match(common_ad, title=title, article_text=title), title
        article_hero = PreparedMedia(
            index=0, kind="image", url="https://example.org/images/" + image_path,
            alt=alt, context="verified_article_hero", featured=True,
        )
        assert _semantic_media_match(article_hero, title=title, article_text=title), title
