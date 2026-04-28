from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as Date
from typing import Any

from app.data.calendar import last_trading_day_on_or_before
from app.data.service import DataService
from app.errors import AppError
from app.schemas import (
    AnalyticsPerformanceRequest,
    ChatContext,
    ChatCitation,
    ChatOptimizationInputs,
    ErrorCode,
    HistoricalResponse,
    LoadedPanelData,
    OptimizationRequest,
    OptimizationResult,
    PortfolioSnapshot,
    Quote,
    ReturnFrequency,
    RiskFreeRateResponse,
    TopHolding,
    ValuationRequest,
)
from app.services.analytics_service import AnalyticsService
from app.services.optimize_service import OptimizeService
from app.services.valuation_service import ValuationService


@dataclass(slots=True)
class ToolExecutionResult:
    name: str
    payload: dict[str, Any]
    citations: list[ChatCitation]


def build_portfolio_snapshot(context: OptimizationResult | None) -> PortfolioSnapshot | None:
    if context is None:
        return None
    top = sorted(
        context.orp.weights.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:5]
    return PortfolioSnapshot(
        request_id=context.request_id,
        as_of=context.as_of,
        risk_free_rate=context.risk_free_rate,
        orp_expected_return=context.orp.expected_return,
        orp_std_dev=context.orp.std_dev,
        orp_sharpe=context.orp.sharpe,
        complete_expected_return=context.complete.expected_return,
        complete_std_dev=context.complete.std_dev,
        y_star=context.complete.y_star,
        leverage_used=context.complete.leverage_used,
        top_holdings=[TopHolding(ticker=ticker, weight=weight) for ticker, weight in top],
        warnings=list(context.warnings),
    )


class ChatToolbox:
    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service
        self._optimize = OptimizeService()
        self._analytics = AnalyticsService()
        self._valuation = ValuationService()

    def definitions(self) -> list[dict[str, Any]]:
        return [
            _fn(
                "get_portfolio_snapshot",
                "Read the compact canonical summary of the currently viewed portfolio.",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
            _fn(
                "get_loaded_panel_data",
                "Read analytics, valuation, or technical panel data already loaded in the UI.",
                {
                    "type": "object",
                    "properties": {
                        "panel": {
                            "type": "string",
                            "enum": ["analytics", "valuation", "technical", "all"],
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            _fn(
                "run_optimization",
                "Recompute optimize results for the current portfolio or a hypothetical input change.",
                {
                    "type": "object",
                    "properties": {
                        "tickers": {"type": "array", "items": {"type": "string"}},
                        "risk_aversion": {"type": "number"},
                        "target_return": {"type": "number"},
                        "return_frequency": {
                            "type": "string",
                            "enum": ["daily", "weekly", "monthly"],
                        },
                        "lookback_years": {"type": "integer", "minimum": 1, "maximum": 20},
                        "allow_short": {"type": "boolean"},
                        "allow_leverage": {"type": "boolean"},
                        "as_of": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
            _fn(
                "get_quote",
                "Fetch the latest quote for a ticker.",
                {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
            ),
            _fn(
                "get_historical",
                "Fetch historical price bars for a ticker and window.",
                {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "frequency": {
                            "type": "string",
                            "enum": ["daily", "weekly", "monthly"],
                        },
                        "years": {"type": "integer", "minimum": 1, "maximum": 20},
                        "as_of": {"type": "string"},
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
            ),
            _fn(
                "get_risk_free_rate",
                "Fetch the current or anchored risk-free rate.",
                {
                    "type": "object",
                    "properties": {"as_of": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
            _fn(
                "get_analytics_performance",
                "Run analytics performance metrics for the current or hypothetical ORP.",
                {
                    "type": "object",
                    "properties": {
                        "tickers": {"type": "array", "items": {"type": "string"}},
                        "orp_weights": {
                            "type": "object",
                            "additionalProperties": {"type": "number"},
                        },
                        "return_frequency": {
                            "type": "string",
                            "enum": ["daily", "weekly", "monthly"],
                        },
                        "lookback_years": {"type": "integer", "minimum": 1, "maximum": 20},
                        "y_star": {"type": "number"},
                        "weight_risk_free": {"type": "number"},
                        "as_of": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
            _fn(
                "get_valuation",
                "Run valuation for one or more tickers.",
                {
                    "type": "object",
                    "properties": {
                        "tickers": {"type": "array", "items": {"type": "string"}},
                        "as_of": {"type": "string"},
                        "wacc": {"type": "number"},
                        "fcff_growth": {"type": "number"},
                        "fcff_terminal_growth": {"type": "number"},
                        "cost_of_equity_override": {"type": "number"},
                        "ddm_gordon_g": {"type": "number"},
                        "ddm_two_stage": {
                            "type": "object",
                            "properties": {
                                "g1": {"type": "number"},
                                "g2": {"type": "number"},
                                "n_periods": {"type": "integer"},
                            },
                            "required": ["g1", "g2", "n_periods"],
                            "additionalProperties": False,
                        },
                    },
                    "additionalProperties": False,
                },
            ),
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        chat_context: ChatContext | None,
        context: OptimizationResult | None,
    ) -> ToolExecutionResult:
        if name == "get_portfolio_snapshot":
            snapshot = chat_context.portfolio_snapshot if chat_context else None
            if snapshot is None:
                snapshot = build_portfolio_snapshot(context)
            return ToolExecutionResult(
                name=name,
                payload={"portfolio_snapshot": _dump(snapshot)},
                citations=_snapshot_citations(snapshot),
            )
        if name == "get_loaded_panel_data":
            panel = str(arguments.get("panel") or "all")
            payload = _loaded_panel_payload(chat_context.loaded_panel_data if chat_context else None, panel)
            return ToolExecutionResult(
                name=name,
                payload=payload,
                citations=[
                    ChatCitation(
                        label="loaded panel",
                        value=panel,
                        source_type="tool",
                        tool_name=name,
                    )
                ],
            )
        if name == "run_optimization":
            inputs = _require_inputs(chat_context)
            req = _build_optimization_request(inputs, arguments)
            result = await self._optimize.run(req, data_service=self._data_service)
            return ToolExecutionResult(
                name=name,
                payload={"optimization_result": result.result.model_dump(mode="json", by_alias=True)},
                citations=_snapshot_citations(build_portfolio_snapshot(result.result), tool_name=name),
            )
        if name == "get_quote":
            ticker = str(arguments["ticker"]).upper().strip()
            result = await self._data_service.get_quote(ticker)
            quote = Quote(ticker=result.quote.ticker, price=result.quote.price, as_of=result.quote.as_of)
            return ToolExecutionResult(
                name=name,
                payload={"quote": quote.model_dump(mode="json", by_alias=True)},
                citations=[
                    ChatCitation(
                        label=f"quote · {quote.ticker}",
                        value=f"{quote.price:.4f}",
                        source_type="tool",
                        tool_name=name,
                        scope=quote.ticker,
                        as_of=quote.as_of.isoformat(),
                    )
                ],
            )
        if name == "get_historical":
            ticker = str(arguments["ticker"]).upper().strip()
            frequency = ReturnFrequency(str(arguments.get("frequency") or "daily"))
            years = int(arguments.get("years") or _require_inputs(chat_context).lookback_years)
            as_of = _parse_date_opt(arguments.get("as_of")) or _default_as_of(chat_context)
            result = await self._data_service.get_historical(
                ticker,
                frequency=frequency,
                lookback_years=years,
                as_of=as_of,
            )
            payload = HistoricalResponse(
                ticker=result.ticker,
                frequency=result.frequency,
                bars=result.bars,
            )
            return ToolExecutionResult(
                name=name,
                payload={"historical": payload.model_dump(mode="json", by_alias=True)},
                citations=[
                    ChatCitation(
                        label=f"history · {ticker}",
                        value=f"{len(payload.bars)} bars",
                        source_type="tool",
                        tool_name=name,
                        scope=f"{ticker}:{frequency.value}",
                        as_of=(payload.bars[-1].date.isoformat() if payload.bars else None),
                    )
                ],
            )
        if name == "get_risk_free_rate":
            as_of = _parse_date_opt(arguments.get("as_of")) or _default_as_of(chat_context)
            window_end = last_trading_day_on_or_before(as_of) if as_of is not None else None
            result = await self._data_service.get_risk_free_rate(window_end=window_end)
            payload = RiskFreeRateResponse(rate=result.rate, as_of=result.as_of, source=result.source)
            return ToolExecutionResult(
                name=name,
                payload={"risk_free_rate": payload.model_dump(mode="json", by_alias=True)},
                citations=[
                    ChatCitation(
                        label="risk-free rate",
                        value=f"{payload.rate:.4f}",
                        source_type="tool",
                        tool_name=name,
                        as_of=payload.as_of.isoformat(),
                    )
                ],
            )
        if name == "get_analytics_performance":
            req = _build_analytics_request(arguments, chat_context, context)
            result, src = await self._analytics.run(req, data_service=self._data_service)
            return ToolExecutionResult(
                name=name,
                payload={
                    "analytics_performance": result.model_dump(mode="json", by_alias=True),
                    "data_source": src,
                },
                citations=[
                    ChatCitation(
                        label="analytics as of",
                        value=result.as_of.isoformat(),
                        source_type="tool",
                        tool_name=name,
                    ),
                    ChatCitation(
                        label="ORP Treynor",
                        value=f"{result.orp.treynor:.4f}",
                        source_type="tool",
                        tool_name=name,
                    ),
                ],
            )
        if name == "get_valuation":
            req = _build_valuation_request(arguments, chat_context)
            window_end = last_trading_day_on_or_before(req.as_of) if req.as_of is not None else None
            risk_free = await self._data_service.get_risk_free_rate(window_end=window_end)
            result, src = await self._valuation.run(
                req,
                data_service=self._data_service,
                risk_free_rate=risk_free.rate,
            )
            return ToolExecutionResult(
                name=name,
                payload={
                    "valuation": result.model_dump(mode="json", by_alias=True),
                    "data_source": src,
                },
                citations=[
                    ChatCitation(
                        label="valuation tickers",
                        value=", ".join(block.ticker for block in result.per_ticker),
                        source_type="tool",
                        tool_name=name,
                        as_of=result.as_of.isoformat(),
                    )
                ],
            )
        raise AppError(
            ErrorCode.INTERNAL,
            f"Unknown chat tool: {name}",
        )


def _fn(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _dump(model: Any) -> Any:
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", by_alias=True, exclude_none=True)
    return model


def _snapshot_citations(
    snapshot: PortfolioSnapshot | None,
    *,
    tool_name: str | None = None,
) -> list[ChatCitation]:
    if snapshot is None:
        return []
    citations: list[ChatCitation] = []
    if snapshot.orp_sharpe is not None:
        citations.append(
            ChatCitation(
                label="ORP Sharpe",
                value=f"{snapshot.orp_sharpe:.4f}",
                source_type="tool" if tool_name else "context",
                tool_name=tool_name,
                as_of=snapshot.as_of.isoformat() if snapshot.as_of else None,
            )
        )
    for holding in snapshot.top_holdings[:3]:
        citations.append(
            ChatCitation(
                label=f"top holding · {holding.ticker}",
                value=f"{holding.weight:.4f}",
                source_type="tool" if tool_name else "context",
                tool_name=tool_name,
                scope=holding.ticker,
                as_of=snapshot.as_of.isoformat() if snapshot.as_of else None,
            )
        )
    return citations


def _require_inputs(chat_context: ChatContext | None) -> ChatOptimizationInputs:
    if chat_context is None:
        raise AppError(ErrorCode.INTERNAL, "Chat tool requires optimization inputs.")
    return chat_context.optimization_inputs


def _build_optimization_request(
    inputs: ChatOptimizationInputs,
    overrides: dict[str, Any],
) -> OptimizationRequest:
    target_return = overrides.get("target_return")
    risk_profile = inputs.risk_profile.model_copy(
        update={
            "risk_aversion": int(overrides.get("risk_aversion") or inputs.risk_profile.risk_aversion),
            "target_return": target_return if target_return is not None else inputs.risk_profile.target_return,
        }
    )
    return OptimizationRequest(
        tickers=[str(t).upper().strip() for t in overrides.get("tickers") or inputs.tickers],
        risk_profile=risk_profile,
        return_frequency=ReturnFrequency(
            str(overrides.get("return_frequency") or inputs.return_frequency.value)
        ),
        lookback_years=int(overrides.get("lookback_years") or inputs.lookback_years),
        allow_short=bool(
            overrides["allow_short"] if "allow_short" in overrides else inputs.allow_short
        ),
        allow_leverage=bool(
            overrides["allow_leverage"] if "allow_leverage" in overrides else inputs.allow_leverage
        ),
        as_of=_parse_date_opt(overrides.get("as_of")) or inputs.as_of,
    )


def _build_analytics_request(
    overrides: dict[str, Any],
    chat_context: ChatContext | None,
    context: OptimizationResult | None,
) -> AnalyticsPerformanceRequest:
    inputs = _require_inputs(chat_context)
    tickers = [str(t).upper().strip() for t in overrides.get("tickers") or inputs.tickers]
    if "orp_weights" in overrides:
        weights = {str(k).upper().strip(): float(v) for k, v in overrides["orp_weights"].items()}
    elif context is not None:
        weights = {str(k).upper().strip(): float(v) for k, v in context.orp.weights.items()}
    else:
        raise AppError(ErrorCode.INTERNAL, "Analytics tool requires ORP weights.")
    y_star = float(
        overrides.get("y_star")
        if "y_star" in overrides
        else (context.complete.y_star if context is not None else 1.0)
    )
    weight_risk_free = float(
        overrides.get("weight_risk_free")
        if "weight_risk_free" in overrides
        else (context.complete.weight_risk_free if context is not None else 0.0)
    )
    return AnalyticsPerformanceRequest(
        tickers=tickers,
        orp_weights=weights,
        return_frequency=ReturnFrequency(
            str(overrides.get("return_frequency") or inputs.return_frequency.value)
        ),
        lookback_years=int(overrides.get("lookback_years") or inputs.lookback_years),
        y_star=y_star,
        weight_risk_free=weight_risk_free,
        as_of=_parse_date_opt(overrides.get("as_of")) or inputs.as_of,
    )


def _build_valuation_request(
    overrides: dict[str, Any],
    chat_context: ChatContext | None,
) -> ValuationRequest:
    inputs = _require_inputs(chat_context)
    return ValuationRequest(
        tickers=[str(t).upper().strip() for t in overrides.get("tickers") or inputs.tickers],
        as_of=_parse_date_opt(overrides.get("as_of")) or inputs.as_of,
        wacc=_float_opt(overrides.get("wacc")),
        fcff_growth=_float_opt(overrides.get("fcff_growth")),
        fcff_terminal_growth=_float_opt(overrides.get("fcff_terminal_growth")),
        cost_of_equity_override=_float_opt(overrides.get("cost_of_equity_override")),
        ddm_gordon_g=_float_opt(overrides.get("ddm_gordon_g")),
        ddm_two_stage=overrides.get("ddm_two_stage"),
    )


def _default_as_of(chat_context: ChatContext | None) -> Date | None:
    if chat_context is None:
        return None
    return chat_context.optimization_inputs.as_of


def _parse_date_opt(value: Any) -> Date | None:
    if value is None or value == "":
        return None
    return Date.fromisoformat(str(value)[:10])


def _float_opt(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _loaded_panel_payload(loaded: LoadedPanelData | None, panel: str) -> dict[str, Any]:
    if loaded is None:
        return {"loaded_panel_data": None}
    data = loaded.model_dump(mode="json", by_alias=True, exclude_none=True)
    if panel == "all":
        return {"loaded_panel_data": data}
    key_map = {
        "analytics": "analytics",
        "valuation": "valuation",
        "technical": "technicalHistory",
    }
    selected_key = key_map.get(panel)
    return {
        "loaded_panel_data": {
            "availability": data.get("availability", {}),
            panel: data.get(selected_key) if selected_key else None,
            "technicalSelectedTicker": data.get("technicalSelectedTicker"),
            "technicalBenchmark": data.get("technicalBenchmark"),
        }
    }


__all__ = ["ChatToolbox", "ToolExecutionResult", "build_portfolio_snapshot"]
