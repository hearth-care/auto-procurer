"""Tests for the model fallback chain in _AnthropicStructuredGateway."""

from __future__ import annotations

import pytest


def _make_gateway(model_chain, side_effects):
    """Build a gateway with mocked _call_model side effects."""
    from xsource.cli.cockpit import _AnthropicStructuredGateway

    gw = object.__new__(_AnthropicStructuredGateway)
    gw.model_chain = list(model_chain)
    call_log = []

    def _call_model(model, messages, schema):
        call_log.append(model)
        exc = side_effects.get(model)
        if exc is not None:
            raise exc
        return {"result": f"ok-from-{model}"}

    gw._call_model = _call_model  # type: ignore[method-assign]

    return gw, call_log


class _OverloadedError(Exception):
    pass


class _AuthError(Exception):
    pass


def _patch_retriable(monkeypatch, err_type):
    monkeypatch.setattr(
        "xsource.cli.cockpit._is_retriable_anthropic_error",
        lambda exc: isinstance(exc, err_type),
    )


def test_primary_succeeds_no_fallback(monkeypatch):
    _patch_retriable(monkeypatch, _OverloadedError)
    monkeypatch.setattr("xsource.obs.event", lambda *a, **kw: None)

    gw, calls = _make_gateway(
        ["model-a", "model-b"],
        {},  # no errors
    )
    result = gw.complete_structured([], {})
    assert result == {"result": "ok-from-model-a"}
    assert calls == ["model-a"]


def test_primary_fails_fallback_succeeds(monkeypatch):
    _patch_retriable(monkeypatch, _OverloadedError)
    events = []
    monkeypatch.setattr("xsource.obs.event", lambda name, **kw: events.append(name))

    gw, calls = _make_gateway(
        ["model-a", "model-b"],
        {"model-a": _OverloadedError("overloaded")},
    )
    result = gw.complete_structured([], {})
    assert result == {"result": "ok-from-model-b"}
    assert calls == ["model-a", "model-b"]
    assert "gateway.model_fallback" in events


def test_chain_exhausted_raises(monkeypatch):
    _patch_retriable(monkeypatch, _OverloadedError)
    monkeypatch.setattr("xsource.obs.event", lambda *a, **kw: None)

    gw, calls = _make_gateway(
        ["model-a", "model-b"],
        {
            "model-a": _OverloadedError("overloaded"),
            "model-b": _OverloadedError("also overloaded"),
        },
    )
    with pytest.raises(_OverloadedError):
        gw.complete_structured([], {})
    assert calls == ["model-a", "model-b"]


def test_auth_error_does_not_fall_back(monkeypatch):
    """Non-retriable (auth) errors must fail fast without trying fallback models."""
    _patch_retriable(monkeypatch, _OverloadedError)
    events = []
    monkeypatch.setattr("xsource.obs.event", lambda name, **kw: events.append(name))

    gw, calls = _make_gateway(
        ["model-a", "model-b"],
        {"model-a": _AuthError("invalid api key")},
    )
    with pytest.raises(_AuthError):
        gw.complete_structured([], {})
    # Auth error is not retriable — must stop at model-a
    assert calls == ["model-a"]
    assert "gateway.model_fallback" not in events
