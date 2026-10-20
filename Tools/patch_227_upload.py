from pathlib import Path
p = Path("telegram_autopilot/v2/publisher.py")
s = p.read_text(encoding="utf-8")
needle = '        if prepare_failures and policy == "required":'
assert needle in s
addition = '''        # Preserve source-owned media also when preferred/optional downloads fail.
        if bundle.source_kind == "telegram" and bundle.count and (prepare_failures or not prepared):
            self.store.publication_backoff(
                article_id, blocked_by=BlockedBy.MEDIA,
                error_code="TELEGRAM_MEDIA_DOWNLOAD_PENDING",
                detail="Telegram source media could not be fully downloaded",
                retry_seconds=1800, count_attempt=False)
            event("media", "Telegram media download incomplete", level=30,
                  channel_id=channel_id, article_id=article_id,
                  source_media=bundle.count, prepared=len(prepared),
                  failures=len(prepare_failures))
            return "TELEGRAM_MEDIA_DOWNLOAD_PENDING"

'''
if "TELEGRAM_MEDIA_DOWNLOAD_PENDING" not in s:
    p.write_text(s.replace(needle, addition + needle, 1), encoding="utf-8")
print("TELEGRAM_MEDIA_DOWNLOAD_GUARD_OK")
