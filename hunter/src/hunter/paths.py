from pathlib import Path

# 项目根目录（含 config/、prompts/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
FEEDBACK_DIR = PROJECT_ROOT / "feedback"
FEEDBACK_PROCESSED_DIR = FEEDBACK_DIR / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
