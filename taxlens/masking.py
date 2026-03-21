"""PII / financial identifier masking before any LLM or external-adjacent processing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class MaskingResult:
    """Text with sensitive fields replaced and a reversible token map (do not log raw secrets)."""

    masked_text: str
    token_map: dict[str, str] = field(default_factory=dict)


_VN_TAX_ID = re.compile(r"\b\d{10}(-\d{3})?\b")
# Loose bank account patterns (VN: often 8–16 digits; adjust per deployment)
_BANK_ACCOUNT = re.compile(r"\b\d{8,16}\b")
# Names: heuristic placeholder replacement when labeled
_NAME_LIKE = re.compile(r"(?i)(customer|khách hàng|ten|họ tên)\s*[:=]\s*([^\n,;]+)")


def mask_sensitive_text(
    text: str,
    *,
    extra_names: list[str] | None = None,
) -> MaskingResult:
    """
    Mask customer names, tax IDs, and bank account numbers.
    Order: specific names → tax IDs → long digit runs (accounts).
    """
    token_map: dict[str, str] = {}
    counter = [0]

    def _tok(label: str, original: str) -> str:
        counter[0] += 1
        t = f"<<{label}_{counter[0]}>>"
        token_map[t] = original
        return t

    out = text
    if extra_names:
        for name in sorted(extra_names, key=len, reverse=True):
            if name and name.strip():
                safe = re.escape(name.strip())
                out = re.sub(safe, lambda m, n=name: _tok("NAME", n), out)

    def _sub_tax(m: re.Match[str]) -> str:
        return _tok("TAX_ID", m.group(0))

    out = _VN_TAX_ID.sub(_sub_tax, out)

    def _sub_bank(m: re.Match[str]) -> str:
        raw = m.group(0)
        # Avoid masking short tax IDs already tokenized
        if raw.startswith("<") and raw.endswith(">"):
            return raw
        return _tok("BANK_ACCT", raw)

    out = _BANK_ACCOUNT.sub(_sub_bank, out)

    def _sub_name_label(m: re.Match[str]) -> str:
        label, value = m.group(1), m.group(2).strip()
        return f"{label}: {_tok('NAME', value)}"

    out = _NAME_LIKE.sub(_sub_name_label, out)
    return MaskingResult(masked_text=out, token_map=token_map)


def mask_mapping(data: Mapping[str, Any], keys_to_mask: frozenset[str]) -> dict[str, Any]:
    """Recursively mask values for given keys in nested dict/list structures."""

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _tok_val(k, v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        return obj

    def _tok_val(key: str, val: Any) -> Any:
        if key in keys_to_mask and isinstance(val, str):
            return mask_sensitive_text(val).masked_text
        return _walk(val)

    return dict(_walk(dict(data)))


DEFAULT_KEYS_TO_MASK = frozenset(
    {"customer_name", "tax_id", "bank_account", "mst", "so_tai_khoan", "ten_khach_hang"}
)
