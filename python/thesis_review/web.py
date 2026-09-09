from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from urllib.parse import quote_plus

import httpx

from thesis_review.errors import ReviewError

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "ThesisReviewAgent/0.6 (+local-teacher-review)"
RESULT_RE = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.I | re.S,
)
SNIPPET_RE = re.compile(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""
    source_type: str = "web"
    query: str = ""
    checked_time: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class WebSearcher:
    """Provider-independent HTML search. Failures return errors, never fabricated hits."""

    def __init__(self, *, client: httpx.Client | None = None, timeout: float = 15.0) -> None:
        self._client = client
        self.timeout = timeout

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        needle = (query or "").strip()
        if not needle:
            raise ReviewError("invalid_params", "缺少检索词。")
        url = f"{SEARCH_ENDPOINT}?q={quote_plus(needle)}"
        html = self._get_text(url)
        hits = _parse_results(html, query=needle, limit=limit)
        return hits

    def fetch(self, url: str, *, max_chars: int = 4000) -> dict:
        target = (url or "").strip()
        if not target.startswith("http://") and not target.startswith("https://"):
            raise ReviewError("invalid_params", "外部来源地址无效。")
        text = self._get_text(target)
        plain = _strip_tags(text)
        return {
            "ok": True,
            "url": target,
            "title": _guess_title(text),
            "text": plain[:max_chars],
            "truncated": len(plain) > max_chars,
            "checked_time": _now(),
        }

    def _get_text(self, url: str) -> str:
        try:
            if self._client is not None:
                response = self._client.get(url, timeout=self.timeout, headers={"User-Agent": USER_AGENT})
            else:
                response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - network boundary
            raise ReviewError("search_failed", f"外部检索失败，未写入结果。{exc}") from exc
        return response.text or ""


def _parse_results(html: str, *, query: str, limit: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    snippets = [_strip_tags(item) for item in SNIPPET_RE.findall(html)]
    checked = _now()
    for index, (href, title_html) in enumerate(RESULT_RE.findall(html)):
        url = unescape(href).strip()
        if not url.startswith("http"):
            continue
        title = _strip_tags(title_html) or url
        snippet = snippets[index] if index < len(snippets) else ""
        hits.append(
            SearchHit(
                title=title,
                url=url,
                snippet=snippet,
                source_type="web",
                query=query,
                checked_time=checked,
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _strip_tags(html: str) -> str:
    text = unescape(TAG_RE.sub(" ", html or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _guess_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html or "", re.I | re.S)
    if not match:
        return ""
    return _strip_tags(match.group(1)).strip()[:180]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
