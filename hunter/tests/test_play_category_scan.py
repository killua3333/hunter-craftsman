import json
from unittest.mock import MagicMock, patch

import pytest

from hunter.tools.play_category_scan import play_category_scan


def test_play_category_scan_invoke(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    payload = {
        "play_search_query": "site:play.google.com 工具 app",
        "result_count": 1,
        "results": [{"title": "Tool", "url": "https://play.google.com/x", "snippet": "s"}],
    }

    with patch("hunter.tools.play_category_scan.play_search") as mock_search:
        mock_search.invoke.return_value = json.dumps(payload)
        out = play_category_scan.invoke({"max_per_category": 1})
    data = json.loads(out)
    assert data["result_count"] >= 1
    assert mock_search.invoke.call_count == 3
