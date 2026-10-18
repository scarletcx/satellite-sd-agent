"""测试环境准备：必须在导入 app 之前设置环境变量。"""
import os
import pathlib
import tempfile

import pytest

_tmp = pathlib.Path(tempfile.mkdtemp(prefix="satellite-test-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_tmp / 'test.db'}"
os.environ["ARTIFACTS_DIR"] = str(_tmp / "artifacts")
os.environ["CORPUS_DIR"] = str(_tmp / "corpus")
os.environ["APP_TOKEN"] = "test-token"
os.environ["STUB_LLM"] = "1"


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    """统一建表：让每个测试文件都能独立运行（不再依赖用例执行顺序）。"""
    from app.db import init_db

    init_db()
    yield
