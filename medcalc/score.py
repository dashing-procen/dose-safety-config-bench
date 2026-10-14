"""MedCalc-Bench scoring rules and answer extraction, shared by every arm.

decimal  correct if Lower Limit <= answer <= Upper Limit
integer  correct if the rounded answer equals the gold integer
date     exact MM/DD/YYYY; gestational age exact (weeks, days)
"""

from __future__ import annotations

import json
import re

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


def first_number(x) -> float | None:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    m = _NUM.search(str(x).replace(",", ""))
    return float(m.group()) if m else None


def as_date(x) -> str | None:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(x))
    return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}" if m else None


def weeks_days(x) -> tuple[int, int] | None:
    s = str(x)
    w, d = re.search(r"(\d+)\s*weeks?", s), re.search(r"(\d+)\s*days?", s)
    if w and d:
        return int(w.group(1)), int(d.group(1))
    nums = [int(n) for n in re.findall(r"\d+", s)]
    return (nums[0], nums[1]) if len(nums) >= 2 else None


def score(row: dict, answer) -> bool:
    """row: a MedCalc-Bench test row (Output Type, Ground Truth Answer, Lower Limit, Upper Limit)."""
    kind, gold = row["Output Type"], row["Ground Truth Answer"]
    if answer is None:
        return False
    if "weeks" in gold:
        return weeks_days(answer) == weeks_days(gold)
    if kind == "date":
        return as_date(answer) is not None and as_date(answer) == as_date(gold)
    a = first_number(answer)
    if a is None:
        return False
    if kind == "integer":
        return round(a) == round(float(gold))
    return float(row["Lower Limit"]) <= a <= float(row["Upper Limit"])


def direct_answer(content: str):
    """The "answer" field of the model's final JSON, after removing any reasoning block."""
    text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).split("</think>")[-1]
    for blob in reversed(re.findall(r"\{.*\}", text, re.S)):
        try:
            return json.loads(blob).get("answer")
        except (json.JSONDecodeError, AttributeError):
            continue
    m = re.findall(r'"answer"\s*:\s*"?([^"\n}]+)', text)
    return m[-1].strip() if m else None
