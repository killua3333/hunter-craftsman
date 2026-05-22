import json
from unittest.mock import MagicMock, patch

import pytest

from hunter.tools.tavily_search import _format_search_response, web_search


def test_format_search_response():
    raw = {
        "query": "计算器 app 痛点",
        "answer": "用户反感广告",
        "results": [{"title": "T1", "url": "https://a.com", "content": "x" * 900}],
    }
    data = json.loads(_format_search_response(raw))
    assert data["result_count"] == 1


def test_web_search_requires_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        web_search.invoke({"query": "test"})


def test_web_search_invoke(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "query": "护肤 痛点",
        "answer": "成分安全",
        "results": [{"title": "R1", "url": "https://b.com", "content": "snippet"}],
    }
    with patch("hunter.tools.tavily_search._get_client", return_value=mock_client):
        out = web_search.invoke({"query": "护肤 痛点", "topic": "news", "time_range": "week"})
    data = json.loads(out)
    assert data["answer"] == "成分安全"
    mock_client.search.assert_called_once()
