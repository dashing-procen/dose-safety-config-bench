"""Paired comparison on the same 200 MedQA questions, all scored by the same strict parser.

Rows: historical 1,024-token baseline (1 sample, temperature 0); historical multi-sample pipeline
(3 samples at 2,048 tokens, temperature 0.7, vote, rescue, evidence arbitration) and its first sample;
new single samples at temperature 0 with 2,048 and 4,096 tokens.
Writes medqa_budget/summary.md."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "records"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (REC / name).open() if line.strip()]


def mcnemar(b: int, c: int) -> float:
    n, k = b + c, min(b, c)
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


hist = load("qwq-32b__historical_base1024_and_harness_20260927.jsonl")
gold = {r["id"]: r["correct_verdict"] for r in hist}
truthy = lambda v: str(v) == "True"  # noqa: E731
pipe = {r["id"]: r for r in hist if r["arm"] == "procen_cns"}
arms = {
    "1 sample, 1,024 tokens, temp 0 (historical baseline)":
        {r["id"]: truthy(r["match"]) for r in hist if r["arm"] == "base_direct"},
    "Pipeline: first of 3 samples, 2,048 tokens, temp 0.7":
        {i: ((r.get("votes") or [""])[0] == gold[i]) for i, r in pipe.items()},
    "Pipeline: 3 samples x 2,048 tokens, vote, rescue, retrieval arbitration":
        {i: truthy(r["match"]) for i, r in pipe.items()},
}
for budget in (2048, 4096):
    recs = [r for r in load(f"qwq-32b__t0_{budget}.jsonl") if r["status"] == "ok"]
    arms[f"1 sample, {budget:,} tokens, temp 0"] = {r["id"]: r["match_strict"] for r in recs}

ids = sorted(set.intersection(*(set(a) for a in arms.values())), key=lambda s: int(s.split("-")[1]))
base = arms["1 sample, 1,024 tokens, temp 0 (historical baseline)"]
rng = random.Random(42)
lines = [f"Matched questions: {len(ids)}\n",
         "| Condition | Accuracy | Gained / lost vs baseline | Exact McNemar p | Paired bootstrap 95% CI (pp) |",
         "|---|---|---|---|---|"]
for name, arm in arms.items():
    acc = sum(arm[i] for i in ids) / len(ids) * 100
    gained = sum(arm[i] and not base[i] for i in ids)
    lost = sum(base[i] and not arm[i] for i in ids)
    diffs = sorted(sum(arm[i] - base[i] for i in (rng.choice(ids) for _ in ids)) / len(ids) * 100
                   for _ in range(10000))
    ci = "—" if arm is base else f"[{diffs[250]:.1f}, {diffs[9750]:.1f}]"
    p = "—" if arm is base else f"{mcnemar(gained, lost):.2g}"
    lines.append(f"| {name} | {acc:.1f}% | {gained} / {lost} | {p} | {ci} |")
(HERE / "summary.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
