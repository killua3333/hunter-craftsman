import json
from unittest.mock import MagicMock, patch

import pytest

from hunter.tools.play_search import play_search


def test_play_search_requires_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        play_search.invoke({"query": "番茄钟"})


def test_play_search_invoke(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "query": "site:play.google.com 番茄钟 app",
        "answer": "竞品广告多",
        "results": [
            {
                "title": "Focus Timer",
                "url": "https://play.google.com/store/apps/details?id=com.example",
                "content": "用户抱怨广告",
            }
        ],
    }
    with patch("hunter.tools.play_search._get_client", return_value=mock_client):
        out = play_search.invoke({"query": "番茄钟", "max_results": 3})
    data = json.loads(out)
    assert "site:play.google.com" in data["play_search_query"]
    assert data["result_count"] == 1
    mock_client.search.assert_called_once()
