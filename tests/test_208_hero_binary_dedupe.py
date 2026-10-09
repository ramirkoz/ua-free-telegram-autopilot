from __future__ import annotations

from telegram_autopilot import media_pipeline as pipeline


def _image(url: str, digest: str, *, featured: bool = False):
    return pipeline.PreparedMedia(
        index=1, kind="image", url=url, featured=featured,
        digest=digest, position=0.1, alt="real article photo"
    )


def test_208_featured_image_binary_not_repeated_from_body(monkeypatch):
    featured = _image("https://cdn.example.test/hero.jpg", "same-binary", featured=True)
    alias = _image("https://cdn.example.test/hero-small.jpg", "same-binary")
    other = _image("https://cdn.example.test/other.jpg", "another-binary")
    monkeypatch.setattr(pipeline, "_layout_items", lambda *_: (featured, [alias, other]))
    monkeypatch.setattr(pipeline, "_probe_image", lambda item, **kwargs: item)
    monkeypatch.setattr(pipeline, "_score", lambda *args, **kwargs: 80.0)
    monkeypatch.setattr(pipeline, "_semantic_media_match", lambda *args, **kwargs: True)
    result = pipeline.prepare_article_media("{}", [], title="A", article_text="A")
    assert result.featured is featured
    assert [item.url for item in result.body] == ["https://cdn.example.test/other.jpg"]


def test_208_distinct_article_images_are_preserved(monkeypatch):
    featured = _image("https://cdn.example.test/hero.jpg", "hero-binary", featured=True)
    gallery = _image("https://cdn.example.test/second.jpg", "second-binary")
    monkeypatch.setattr(pipeline, "_layout_items", lambda *_: (featured, [gallery]))
    monkeypatch.setattr(pipeline, "_probe_image", lambda item, **kwargs: item)
    monkeypatch.setattr(pipeline, "_score", lambda *args, **kwargs: 80.0)
    monkeypatch.setattr(pipeline, "_semantic_media_match", lambda *args, **kwargs: True)
    result = pipeline.prepare_article_media("{}", [], title="A", article_text="A")
    assert result.featured is featured
    assert len(result.body) == 1
