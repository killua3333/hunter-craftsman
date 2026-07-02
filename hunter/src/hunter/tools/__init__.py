from hunter.tools.builtin import echo, word_count
from hunter.tools.play_category_scan import play_category_scan
from hunter.tools.play_earnings import play_get_earnings
from hunter.tools.play_scraper import play_analyze_reviews, play_competitive_analysis, play_get_app_detail, play_get_reviews, play_search_apps
from hunter.tools.play_search import play_search
from hunter.tools.tavily_search import web_search


def get_research_tools():
    """市场调研 Agent 工具集：Play 真实数据优先。"""
    return [play_search_apps, play_competitive_analysis, play_get_reviews, play_analyze_reviews, play_get_app_detail, web_search, play_search]


def get_discovery_tools():
    """Autopilot 发现模式：Play scraper 优先 + 竞品分析 + 差评分析 + 通用搜索兜底。"""
    return [play_competitive_analysis, play_analyze_reviews, play_search_apps, play_get_reviews, play_get_app_detail, play_category_scan, web_search]


def get_accounting_tools():
    """Agent D 会计工具集：财务报表读取。"""
    return [play_get_earnings]


def get_default_tools():
    """默认：Play scraper + Tavily 搜索。"""
    return get_research_tools()


__all__ = [
    "echo",
    "word_count",
    "web_search",
    "play_search",
    "play_category_scan",
    "play_search_apps",
    "play_get_reviews",
    "play_get_app_detail",
    "play_competitive_analysis",
    "play_analyze_reviews",
    "play_get_earnings",
    "get_research_tools",
    "get_discovery_tools",
    "get_accounting_tools",
    "get_default_tools",
]
