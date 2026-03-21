"""Rule-based anomaly flagging with explicit reasoning steps (deterministic layer)."""

from __future__ import annotations

from typing import Any


def flag_transaction_ledger_mismatch(
    invoice_amount: float,
    ledger_amount: float,
    *,
    tolerance_abs: float = 1.0,
) -> dict[str, Any]:
    """
    Example pipeline for explainable flags:
    Step 1: Compare invoice vs ledger
    Step 2: Detect mismatch
    Step 3: Cross-check thresholds
    """
    delta = abs(invoice_amount - ledger_amount)
    steps = [
        "Step 1: Compare invoice total vs posted ledger amount for linked voucher.",
        f"Step 2: Detect mismatch — |invoice - ledger| = {delta:.2f}.",
        f"Step 3: Cross-check thresholds — tolerance_abs = {tolerance_abs:.2f}.",
    ]
    flagged = delta > tolerance_abs
    return {
        "flagged": flagged,
        "reasoning_steps": steps,
        "metrics": {"invoice_amount": invoice_amount, "ledger_amount": ledger_amount, "delta": delta},
        "requires_human_review": True,
        "confidence": 0.9 if flagged else 0.75,
    }
