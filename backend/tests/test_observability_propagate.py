"""propagate_attributes 예외 전파 회귀 — 담당: 한의정.

본문 예외가 원형 그대로 전파돼야 한다(감싸서 500으로 변질 금지). P4D 게이트 실행 중
입력 게이트 ValueError가 `generator didn't stop after throw()`로 마스킹된 사고의 회귀 방지.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.core import observability


def test_body_valueerror_propagates_unchanged(monkeypatch):
    """langfuse 있을 때: 본문 ValueError가 그대로 나와야 한다(RuntimeError로 변질 금지)."""
    from contextlib import contextmanager

    @contextmanager
    def _fake_propagate(**_kw):
        yield

    monkeypatch.setitem(sys.modules, "langfuse",
                        SimpleNamespace(propagate_attributes=_fake_propagate))

    with pytest.raises(ValueError, match="user error"):
        with observability.propagate_attributes(session_id="x"):
            raise ValueError("user error")


def test_body_valueerror_propagates_when_langfuse_absent(monkeypatch):
    """langfuse 없을 때(no-op 경로): 본문 예외 역시 원형 전파."""
    monkeypatch.setitem(sys.modules, "langfuse", None)  # import 시 TypeError → 폴백

    with pytest.raises(ValueError, match="user error"):
        with observability.propagate_attributes(session_id="x"):
            raise ValueError("user error")


def test_noop_yields_once_and_runs_body(monkeypatch):
    monkeypatch.setitem(sys.modules, "langfuse", None)
    ran = []
    with observability.propagate_attributes(session_id="x"):
        ran.append(True)
    assert ran == [True]
