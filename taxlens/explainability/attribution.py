"""
Explainability: lightweight feature attribution (SHAP-like linear proxy).

For each flagged transaction, decompose risk_score into weighted contributions
from normalized features (amount z-score, VAT mismatch, ledger match, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FeatureAttribution:
    feature: str
    value: float
    weight: float
    contribution: float


def explain_risk_linear(
    features: dict[str, float],
    weights: dict[str, float],
) -> tuple[float, list[FeatureAttribution]]:
    """
    risk_score = sum(weight_i * feature_i), clipped to [0, 1] at call site.
    Returns total and per-feature contributions (SHAP-like for linear models).
    """
    contributions: list[FeatureAttribution] = []
    total = 0.0
    for name, val in features.items():
        w = weights.get(name, 0.0)
        c = w * val
        contributions.append(FeatureAttribution(feature=name, value=val, weight=w, contribution=c))
        total += c
    contributions.sort(key=lambda x: abs(x.contribution), reverse=True)
    return total, contributions


def summarize_drivers(attrs: list[FeatureAttribution], top_k: int = 5) -> list[str]:
    lines: list[str] = []
    for a in attrs[:top_k]:
        lines.append(
            f"{a.feature}: value={a.value:.4f}, weight={a.weight:.4f}, "
            f"contribution={a.contribution:.4f}"
        )
    return lines
