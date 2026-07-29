"""공용 모델 캐시와 OpenAI 호출 호환성 회귀 테스트."""

from __future__ import annotations

import ast
import inspect

from app.services import gpt_service, kontext_service


def test_read_hf_token_from_file(monkeypatch, tmp_path):
    token_file = tmp_path / "hf_token"
    token_file.write_text("test-token\n", encoding="utf-8")
    monkeypatch.setenv("HF_TOKEN_PATH", str(token_file))

    assert kontext_service._read_hf_token() == "test-token"


def test_read_hf_token_without_path(monkeypatch):
    monkeypatch.delenv("HF_TOKEN_PATH", raising=False)

    assert kontext_service._read_hf_token() is None


def test_chat_completions_do_not_use_nonstandard_name_argument():
    tree = ast.parse(inspect.getsource(gpt_service))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create"
        and ast.unparse(node.func).endswith("chat.completions.create")
    ]

    assert calls
    assert all("name" not in {kw.arg for kw in call.keywords} for call in calls)
