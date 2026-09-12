from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parameters that identify attribution/tracking, not the underlying article.
# Keep content-defining keys such as id=, p=, v=, page=, article=, etc.
_TRACKING_EXACT = {
    "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "ttclid", "twclid",
    "igshid", "mkt_tok", "ref", "ref_src", "ref_url", "referrer", "referer", "src", "source",
    "campaign", "campaign_id", "cmp", "cmpid", "ncid", "ocid", "s_cid", "spm", "vero_conv",
    "vero_id", "wickedid", "rb_clickid", "oly_anon_id", "oly_enc_id", "__twitter_impression",
}
_TRACKING_PREFIXES = (
    "utm_", "itm_", "mc_", "pk_", "hsa_", "ga_", "vero_", "oly_", "mkt_", "sc_",
)


def _is_tracking_key(key: str) -> bool:
    low = str(key or "").strip().casefold()
    return low in _TRACKING_EXACT or any(low.startswith(prefix) for prefix in _TRACKING_PREFIXES)


def normalize_url(value: str) -> str:
    """Return a stable article identity URL while preserving content-defining query parameters.

    The normalization is deliberately conservative: it removes known tracking parameters,
    lowercases scheme/host, drops fragments, removes default ports, and sorts the remaining
    query pairs. It does not remove arbitrary query parameters because many publishers use
    ?id= / ?p= / ?v= as part of the article identity.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except Exception:
        return raw
    scheme = parts.scheme.casefold()
    if scheme not in {"http", "https"} or not parts.netloc:
        return raw

    host = (parts.hostname or "").casefold()
    if not host:
        return raw
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    if parts.username:
        auth = parts.username
        if parts.password:
            auth += f":{parts.password}"
        netloc = f"{auth}@{netloc}"

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_key(k)
    ]
    query_pairs.sort(key=lambda item: (item[0].casefold(), item[0], item[1]))
    query = urlencode(query_pairs, doseq=True)
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def same_url(a: str, b: str) -> bool:
    na, nb = normalize_url(a), normalize_url(b)
    return bool(na and nb and na == nb)
