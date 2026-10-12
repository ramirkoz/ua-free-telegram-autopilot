"""2.1.2 source owned YouTube video and Shorts regression cases."""
import json
from telegram_autopilot.video_links import canonical_video_url, scoped_video_links
from telegram_autopilot.article_extractor import extract_article_content


def test_three_distinct_robitussin_style_youtube_embeds():
    ids = ["aBcdEFg1234", "aBcdEFg1235", "aBcdEFg1236"]
    html = "<html><head><title>Robitussin hires a hitman to take out your cough</title></head><body><article><h1>Robitussin hires a hitman</h1><p>Three campaign spots produced for the medicine launch and its storytelling.</p>" + "".join(
        f'<iframe src="https://www.youtube-nocookie.com/embed/{key}?feature=oembed"></iframe>' for key in ids
    ) + "</article></body></html>"
    result = extract_article_content(html, "https://www.thedrum.com/news/robitussin-hires-a-hitman-to-take-out-your-cough")
    layout = json.loads(result.layout_json)
    assert layout["video_embed_count"] == 3
    assert layout["video_links"] == [f"https://www.youtube.com/watch?v={v}" for v in ids]
    assert len(scoped_video_links(layout)) == 3


def test_shortcode_and_lazy_src_video():
    html = '<html><body><article><h1>Campaign story</h1><p>New brand creativity is launched this week.</p><iframe data-lazy-src="https://www.youtube.com/shorts/aBcdEFg1234"></iframe></article></body></html>'
    result = extract_article_content(html, "https://example.org/article")
    assert "https://www.youtube.com/watch?v=aBcdEFg1234" in json.loads(result.layout_json)["video_links"]


def test_unrelated_youtube_in_page_recommendations_is_not_bound():
    html = '<html><body><article><h1>Campaign story</h1><p>New brand creativity is launched this week.</p></article><aside><iframe src="https://www.youtube.com/embed/aBcdEFg1234"></iframe></aside></body></html>'
    result = extract_article_content(html, "https://example.org/article")
    assert not json.loads(result.layout_json)["video_links"]


def test_invalid_and_cross_origin_video_url_rejected():
    assert not canonical_video_url("https://evil.example/?v=aBcdEFg1234")
    assert not canonical_video_url("http://127.0.0.1/watch?v=aBcdEFg1234")
    assert canonical_video_url("https://youtu.be/aBcdEFg1234?t=5") == "https://www.youtube.com/watch?v=aBcdEFg1234"
