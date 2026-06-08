from hunter.tools.builtin import echo, word_count
from hunter.tools.agent_reach_search import agent_reach_search
from hunter.tools.play_category_scan import play_category_scan
from hunter.tools.play_search import play_search
from hunter.tools.tavily_search import web_search


def get_research_tools():
    """市场调研 Agent 工具集。"""
    return [agent_reach_search, web_search, play_search]


def get_discovery_tools():
    """Autopilot 发现模式：仅 play_search，避免多工具 + 类目扫描耗尽 LangGraph 步数。"""
    return [agent_reach_search, play_search]


def get_default_tools():
    """默认：Tavily 搜索（调研主工具）。"""
    return get_research_tools()


__all__ = [
    "echo",
    "word_count",
    "agent_reach_search",
    "web_search",
    "play_search",
    "play_category_scan",
    "get_research_tools",
    "get_discovery_tools",
    "get_default_tools",
]
