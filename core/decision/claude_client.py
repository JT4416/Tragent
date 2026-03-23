import json
from dataclasses import dataclass
from pathlib import Path

import anthropic

from config import settings
from core.decision.prompt_builder import DECISION_SYSTEM, SELF_IMPROVE_SYSTEM
from core.logger import get_logger

# Claude Sonnet pricing (per 1M tokens) — update if pricing changes
_INPUT_COST_PER_1M = 3.00
_OUTPUT_COST_PER_1M = 15.00


@dataclass
class TradeDecision:
    action: str            # buy | sell | short | cover | hold
    symbol: str | None
    confidence: float
    position_size_pct: float
    reasoning: str
    signals_used: list[str]
    skip_reason: str | None


class ClaudeClient:
    def __init__(self, daily_limit_usd: float = 10.0,
                 log_dir: Path | None = None,
                 agent_id: str = "system"):
        self._client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY())
        self._limit = daily_limit_usd
        self.daily_spend_usd: float = 0.0
        self._logger = get_logger(agent_id, "decisions", log_dir) \
            if log_dir else None

    def decide(self, system_context: str, user_prompt: str) -> TradeDecision:
        if self.daily_spend_usd >= self._limit:
            raise RuntimeError(
                f"Daily Claude spend limit ${self._limit} reached. Pausing.")

        response = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=DECISION_SYSTEM + "\n\n" + system_context,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._track_cost(response.usage)
        raw = response.content[0].text

        if self._logger:
            self._logger.log({"prompt": user_prompt[:500],
                               "response": raw, "spend": self.daily_spend_usd})

        return self._parse_response(raw)

    def self_improve(self, user_prompt: str) -> str:
        response = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SELF_IMPROVE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._track_cost(response.usage)
        return response.content[0].text

    @staticmethod
    def _parse_response(raw: str) -> TradeDecision:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        return TradeDecision(
            action=data["action"],
            symbol=data.get("symbol"),
            confidence=float(data["confidence"]),
            position_size_pct=float(data.get("position_size_pct", 0)),
            reasoning=data.get("reasoning", ""),
            signals_used=data.get("signals_used", []),
            skip_reason=data.get("skip_reason"),
        )

    def _track_cost(self, usage) -> None:
        cost = (usage.input_tokens / 1_000_000 * _INPUT_COST_PER_1M +
                usage.output_tokens / 1_000_000 * _OUTPUT_COST_PER_1M)
        self.daily_spend_usd += cost
