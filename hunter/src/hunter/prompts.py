from hunter.config import get_agent_settings, load_settings
from hunter.paths import PROMPTS_DIR


def _read_prompt_file(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"提示词文件不存在: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_learnings_prompt(name: str | None = None) -> str:
    """加载 specialist_learnings（Agent B 反馈归纳，每周批更新）。"""
    learn_cfg = load_settings().get("learning", {})
    prompt_name = name or learn_cfg.get("learnings_prompt", "specialist_learnings")
    return _read_prompt_file(prompt_name)


def load_system_prompt(name: str | None = None) -> str:
    """
    加载完整系统提示词 = specialist_system（核心护栏）
    + specialist_learnings（每周从反馈迭代）。
    """
    prompt_name = name or get_agent_settings().get("system_prompt", "specialist_system")
    core = _read_prompt_file(prompt_name)
    try:
        learnings = load_learnings_prompt()
    except FileNotFoundError:
        learnings = ""
    if not learnings:
        return core
    return f"{core}\n\n---\n\n{learnings}"
