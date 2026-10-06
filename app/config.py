"""运行配置（docs/12 §2）。

骨架阶段不强制 .env：缺失时使用开发默认值；未配置任何 LLM Key 时自动进入桩模式。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录

_PROVIDER_KEYS = ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def _load_dotenv(path: Path) -> None:
    """极简 .env 加载（不覆盖已存在的环境变量）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    env: str
    app_token: str
    database_url: str
    stub_llm: bool
    cost_limit_cny: float
    log_level: str
    artifacts_dir: Path
    corpus_dir: Path
    prompts_dir: Path


def _resolve_stub_mode() -> bool:
    explicit = os.getenv("STUB_LLM", "").strip()
    if explicit in ("0", "1"):
        return explicit == "1"
    # 未显式设置：没有任何供应商 Key 时自动桩模式（骨架阶段默认体验）
    return not any(os.getenv(k, "").strip() for k in _PROVIDER_KEYS)


settings = Settings(
    env=os.getenv("APP_ENV", "dev"),
    app_token=os.getenv("APP_TOKEN", "dev-token-change-me"),
    database_url=os.getenv("DATABASE_URL", "sqlite+pysqlite:///./dev.db"),
    stub_llm=_resolve_stub_mode(),
    cost_limit_cny=float(os.getenv("COST_LIMIT_CNY", "3")),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    artifacts_dir=Path(os.getenv("ARTIFACTS_DIR", str(BASE_DIR / "artifacts"))),
    corpus_dir=Path(os.getenv("CORPUS_DIR", str(BASE_DIR / "corpus"))),
    prompts_dir=BASE_DIR / "prompts",
)
