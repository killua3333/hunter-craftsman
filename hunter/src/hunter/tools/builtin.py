"""内置示例工具：可替换为业务工具或接入 langchain-community 现成工具。"""

try:
    from langchain_core.tools import tool
except ModuleNotFoundError:
    class _LocalTool:
        def __init__(self, fn):
            self.fn = fn
            self.__name__ = getattr(fn, "__name__", "local_tool")
            self.__doc__ = getattr(fn, "__doc__", None)

        def __call__(self, *args, **kwargs):
            return self.fn(*args, **kwargs)

        def invoke(self, payload):
            if isinstance(payload, dict):
                return self.fn(**payload)
            return self.fn(payload)

    def tool(fn):
        return _LocalTool(fn)


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
