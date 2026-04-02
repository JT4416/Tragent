import yaml
from core.decision.prompt_builder import build_self_improve_prompt, build_peer_learning_prompt
from agents.expertise_manager import ExpertiseManager

_SIGNAL_TO_EXPERTISE = {
    "volume_spike": "market",
    "vwap_cross": "market",
    "range_breakout": "market",
    "52w_high": "market",
    "earnings_beat": "news",
    "fda_approval": "news",
    "sector_catalyst": "news",
    "form4_insider_cluster": "institutional",
    "13f_new_position": "institutional",
    "congressional_buy": "institutional",
}


class SelfImproveOrchestrator:
    def __init__(self, expertise_mgr: ExpertiseManager, claude_client):
        self._mgr = expertise_mgr
        self._claude = claude_client

    def run(self, trade_record: dict, original_reasoning: str,
            outcome: str, pnl_pct: float, duration: str) -> None:
        files_to_update = self._determine_files(trade_record)
        files_to_update.add("trade")

        for file_name in files_to_update:
            current_data = self._mgr.load(file_name)
            current_yaml = yaml.dump(current_data, default_flow_style=False)
            prompt = build_self_improve_prompt(
                trade_record=trade_record,
                original_reasoning=original_reasoning,
                outcome=outcome,
                pnl_pct=pnl_pct,
                duration=duration,
                current_yaml=current_yaml,
                max_lines=1000,
            )
            updated_yaml = self._claude.self_improve(prompt)
            try:
                updated_data = yaml.safe_load(updated_yaml)
                if updated_data:
                    self._mgr.save(file_name, updated_data)
            except yaml.YAMLError:
                pass  # keep existing file if Claude returns invalid YAML

    def run_peer_learning(self, insight: dict) -> None:
        """Update expertise based on a trade insight from the competing agent."""
        files_to_update = self._determine_files(insight["trade_record"])
        files_to_update.add("trade")

        for file_name in files_to_update:
            current_data = self._mgr.load(file_name)
            current_yaml = yaml.dump(current_data, default_flow_style=False)
            prompt = build_peer_learning_prompt(insight, current_yaml)
            updated_yaml = self._claude.self_improve(prompt)
            try:
                updated_data = yaml.safe_load(updated_yaml)
                if updated_data:
                    self._mgr.save(file_name, updated_data)
            except yaml.YAMLError:
                pass

    def _determine_files(self, trade_record: dict) -> set[str]:
        files = set()
        for signal in trade_record.get("signals_used", []):
            if signal in _SIGNAL_TO_EXPERTISE:
                files.add(_SIGNAL_TO_EXPERTISE[signal])
        return files
