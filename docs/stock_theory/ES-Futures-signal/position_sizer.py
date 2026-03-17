"""
ES Futures Signal Bot — position_sizer.py
Kelly Criterion: contracts = (Equity × 1.5%) / (|Entry-SL| × $50)
Supports E-mini ($50/pt) and Micro ($5/pt).
"""
from dataclasses import dataclass
import config as C


@dataclass
class PositionSize:
    contracts:       int
    risk_dollars:    float
    risk_pct:        float
    contract_type:   str
    notional:        float
    note:            str = ""


def calculate_size(entry_price: float,
                   stop_loss:   float,
                   equity:      float = C.EQUITY,
                   risk_pct:    float = C.RISK_PCT,
                   contract_type: str = C.CONTRACT_TYPE) -> PositionSize:
    """
    contracts = (equity × risk_pct) / (|entry - sl| × multiplier)
    Minimum 1, capped at 10 for safety.
    """
    mult = C.EMINI_MULT if contract_type == "emini" else C.MICRO_MULT
    risk_per_pt = abs(entry_price - stop_loss)

    if risk_per_pt < 0.01:
        return PositionSize(
            contracts=0, risk_dollars=0.0, risk_pct=0.0,
            contract_type=contract_type, notional=0.0,
            note="SL too close to entry"
        )

    raw = (equity * risk_pct) / (risk_per_pt * mult)
    contracts = max(1, min(10, int(raw)))               # 1–10 safety cap

    risk_dollars = contracts * risk_per_pt * mult
    notional     = contracts * entry_price * mult

    return PositionSize(
        contracts=contracts,
        risk_dollars=round(risk_dollars, 2),
        risk_pct=round(risk_dollars / equity * 100, 3),
        contract_type=contract_type,
        notional=round(notional, 2),
        note=f"raw={raw:.2f} → capped={contracts}"
    )
