import pytest


def test_ashare_context_only_runner_passes_safe_context_input():
    """Native wrapper should pass context-only payloads with the worker prompt."""
    from vnpy_tradingagents.native_context_runner import AShareContextOnlyRunner

    native = RecordingNative()
    runner = AShareContextOnlyRunner(native_runner=native)

    result = runner.run(
        {
            "symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "context": {"market": {"bars": [{"close": 10}]}},
        }
    )

    assert result["rating"] == "Buy"
    assert native.input["context"]["market"]["bars"][0]["close"] == 10
    assert "system_prompt" in native.input
    assert "gateway" not in native.input


def test_ashare_context_only_runner_rejects_missing_required_context():
    """Native wrapper should fail before a runner can use external default tools."""
    from vnpy_tradingagents.native_context_runner import (
        AShareContextOnlyRunner,
        ContextRunnerError,
    )

    with pytest.raises(ContextRunnerError, match="missing required context"):
        AShareContextOnlyRunner(RecordingNative()).run(
            {
                "symbol": "600519.SSE",
                "trade_date": "2024-01-03",
                "context": {},
            }
        )


def test_ashare_context_only_runner_rejects_trading_handles():
    """Native wrapper should keep Gateway/MainEngine handles out of the runner."""
    from vnpy_tradingagents.native_context_runner import (
        AShareContextOnlyRunner,
        ContextRunnerError,
    )

    with pytest.raises(ContextRunnerError, match="forbidden"):
        AShareContextOnlyRunner(RecordingNative()).run(
            {
                "symbol": "600519.SSE",
                "gateway": object(),
                "context": {"market": {"bars": [{"close": 10}]}},
            }
        )


class RecordingNative:
    """Native runner fake."""

    def __init__(self) -> None:
        self.input = {}

    def run(self, native_input):
        self.input = native_input
        return {"rating": "Buy", "action": "buy", "confidence": 0.8}

