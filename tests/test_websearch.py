from __future__ import annotations

from pathlib import Path

import pytest

from thesis_review.errors import ReviewError
from thesis_review.web import SearchHit, WebSearcher
from thesis_review.worker import Worker
from tests.helpers import FULL_STATS, sample_full_thesis_draft, sample_overclaim_draft


class FakeSearcher(WebSearcher):
    def __init__(self, hits=None, fail: bool = False) -> None:
        super().__init__()
        self.hits = hits or [
            SearchHit(title="国家统计局公报", url="https://example.test/stats", snippet="产业规模", query="国家统计局", checked_time="2026-01-01T00:00:00+00:00")
        ]
        self.fail = fail
        self.queries: list[str] = []

    def search(self, query: str, *, limit: int = 5):
        self.queries.append(query)
        if self.fail:
            raise ReviewError("search_failed", "外部检索失败，未写入结果。")
        return self.hits[:limit]


def _open(worker: Worker, data: bytes) -> None:
    import base64

    worker.dispatch("open_draft", {"bytes_b64": base64.b64encode(data).decode("ascii")})


def test_web_search_persists_sources_and_does_not_fabricate_on_failure(tmp_path: Path):
    searcher = FakeSearcher()
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能", searcher=searcher)
    _open(worker, sample_full_thesis_draft())
    found = worker.dispatch("web_search", {"query": "国家统计局 2023 产业规模"})
    assert found["ok"] is True
    assert found["hits"][0]["url"] == "https://example.test/stats"
    recorded = worker.dispatch(
        "record_external_finding",
        {
            "quote": FULL_STATS,
            "problem": "对外引用的宏观数据需要老师核对来源。",
            "rationale": "已检索到候选来源，不能当作绝对真理。",
            "external_sources": found["hits"],
            "draft_id": "full",
        },
    )
    assert recorded["ok"] is True
    finding = worker.findings[-1]
    assert finding.kind == "external"
    assert finding.external_sources
    assert finding.external_sources[0].url.startswith("https://")

    failing = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能", searcher=FakeSearcher(fail=True))
    _open(failing, sample_full_thesis_draft())
    failed = failing.dispatch("web_search", {"query": "国家统计局"})
    assert failed["ok"] is False
    assert failed["hits"] == []
    assert failed["fabricated"] is False
    with pytest.raises(ReviewError) as caught:
        failing.dispatch(
            "record_external_finding",
            {
                "quote": FULL_STATS,
                "problem": "编造来源。",
                "rationale": "失败后仍要记录。",
                "external_sources": [],
                "draft_id": "full",
            },
        )
    assert caught.value.code == "missing_source"


def test_internal_data_mismatch_does_not_require_search(tmp_path: Path):
    searcher = FakeSearcher()
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能", searcher=searcher)
    _open(worker, sample_overclaim_draft())
    worker.dispatch("find_text", {"needle": "0.81"})
    assert searcher.queries == []
