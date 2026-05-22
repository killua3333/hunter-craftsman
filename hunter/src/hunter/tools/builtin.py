"""内置示例工具：可替换为业务工具或接入 langchain-community 现成工具。"""

from langchain_core.tools import tool


@tool
def echo(text: str) -> str:
    """回显输入文本，用于验证 agent 工具调用链路是否正常。"""
    return text


@tool
def word_count(text: str) -> int:
    """统计文本中的字符数（含空格）。"""
    return len(text)

@tool
def addition(a: int, b: int) -> int:
    """计算两个整数的和。"""
    return a + b


def get_default_tools():
    return [echo, word_count,addition]
