"""Frozen configuration of the validated Retest RS-first paper strategy (Task 10).

These values mirror the validated research setup (Task 6 engine, Task 9 baseline without a
sector limit). Do not tune them here — changing a value is a strategy change and needs a
new validation cycle.
"""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PaperConfig:
    # signal (same rules as backtest.retest_at + simulate filters)
    mode: str = "retest"
    lookback: int = 3
    min_rs: int = 85
    stop_buf_pct: float = 3.0
    max_risk_pct: float = 0.0          # 0 = no filter
    market_filter: str = "ma50"        # SPY close > MA50 on the signal day
    # execution (next-session open, pre-open sizing — Task 6 P1)
    entry_at: str = "open"
    hold_days: int = 20
    # portfolio (portfolio_bt.replay defaults used in the research)
    initial_cash: float = 10000.0
    risk_fraction: float = 0.01
    max_position_fraction: float = 0.20
    max_positions: int = 5
    max_new_per_day: int = 3
    cost_bps: float = 10.0
    # ranking: RS descending, ties by ticker (research "RS-first")
    ranking: str = "rs_first"
    # sector limits are research-only (Task 9) and stay OFF
    max_per_sector: object = None

    def as_dict(self):
        return asdict(self)


DEFAULT = PaperConfig()
