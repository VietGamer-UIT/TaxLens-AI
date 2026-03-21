"""Transaction risk scoring and top-percentile selection (audit efficiency)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from taxlens.config import RISK_PERCENTILE_HIGH
from taxlens.explainability.attribution import explain_risk_linear, summarize_drivers


@dataclass
class ScoredTransaction:
    transaction_id: str
    risk_score: float
    features: dict[str, float]
    attribution_summary: list[str]


DEFAULT_WEIGHTS: dict[str, float] = {
    "amount_z": 0.25,
    "vat_gap_pct": 0.25,
    "ledger_amount_match": 0.2,
    "invoice_duplicate_signal": 0.15,
    "round_number_flag": 0.15,
}


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def compute_features(row: dict[str, Any], gl_stats: dict[str, float]) -> dict[str, float]:
    """Derive normalized features; extend per deployment."""
    amt = float(row.get("amount") or row.get("so_tien") or 0.0)
    mean_amt = gl_stats.get("amount_mean", 0.0) or 1.0
    std_amt = gl_stats.get("amount_std", 1.0) or 1.0
    amount_z = abs(amt - mean_amt) / std_amt
    amount_z = min(amount_z / 5.0, 1.0)

    vat_expected = float(row.get("vat_expected") or 0.0)
    vat_actual = float(row.get("vat_actual") or 0.0)
    vat_gap_pct = abs(vat_expected - vat_actual) / max(abs(vat_expected), 1.0)
    vat_gap_pct = min(vat_gap_pct, 1.0)

    ledger_amount_match = float(row.get("ledger_amount_match", 1.0))
    invoice_duplicate_signal = float(row.get("invoice_duplicate_signal", 0.0))
    round_number_flag = 1.0 if amt > 0 and amt % 1_000_000 == 0 else 0.0

    return {
        "amount_z": amount_z,
        "vat_gap_pct": vat_gap_pct,
        "ledger_amount_match": 1.0 - ledger_amount_match,
        "invoice_duplicate_signal": invoice_duplicate_signal,
        "round_number_flag": round_number_flag,
    }


def score_transactions(
    rows: list[dict[str, Any]],
    gl_stats: dict[str, float],
    weights: dict[str, float] | None = None,
) -> list[ScoredTransaction]:
    w = weights or DEFAULT_WEIGHTS
    out: list[ScoredTransaction] = []
    for i, row in enumerate(rows):
        tid = str(row.get("id") or row.get("so_chung_tu") or f"row-{i}")
        feats = compute_features(row, gl_stats)
        raw, attrs = explain_risk_linear(feats, w)
        risk = _clip01(raw / 2.0)
        out.append(
            ScoredTransaction(
                transaction_id=tid,
                risk_score=risk,
                features=feats,
                attribution_summary=summarize_drivers(attrs),
            )
        )
    return out


def top_risk_percentile(
    scored: list[ScoredTransaction],
    percentile: float = RISK_PERCENTILE_HIGH,
) -> list[ScoredTransaction]:
    """Flag top (1 - percentile) risk by score, e.g. top 5% when percentile=0.95."""
    if not scored:
        return []
    scores = np.array([s.risk_score for s in scored], dtype=float)
    thr = float(np.quantile(scores, percentile))
    return [s for s in scored if s.risk_score >= thr]
