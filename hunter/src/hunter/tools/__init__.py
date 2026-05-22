from hunter.tools.builtin import echo, word_count
from hunter.tools.tavily_search import web_search


def get_research_tools():
    """市场调研 Agent 工具集。"""
    return [web_search]


def get_default_tools():
    """默认：Tavily 搜索（调研主工具）。"""
    return get_research_tools()


__all__ = [
    "echo",
    "word_count",
    "web_search",
    "get_research_tools",
    "get_default_tools",
]
