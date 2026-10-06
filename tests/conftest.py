"""测试环境准备：必须在导入 app 之前设置环境变量。"""
import os
import pathlib
import tempfile

_tmp = pathlib.Path(tempfile.mkdtemp(prefix="satellite-test-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_tmp / 'test.db'}"
os.environ["ARTIFACTS_DIR"] = str(_tmp / "artifacts")
os.environ["CORPUS_DIR"] = str(_tmp / "corpus")
os.environ["APP_TOKEN"] = "test-token"
os.environ["STUB_LLM"] = "1"
