"""Paired comparison of each model alone versus inside the CNS harness, from medcalc/records/.

Only cases where both arms returned a model answer are compared (API errors are excluded from both
arms and counted). Writes medcalc/summary.md and medcalc/summary.json.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "records"

# family, alone arm (best reasoning setting), CNS arm (reasoning off or low)
PAIRS = [
    ("Qwen3.8 27B", "alone__qwen3.8-27b__thinking-on", "cns__qwen3.8-27b__thinking-off"),
    ("DeepSeek-V4-Pro", "alone__deepseek-v4-pro__thinking-on", "cns__deepseek-v4-pro__thinking-off"),
    ("GPT-OSS-120B", "alone__gpt-oss-120b__effort-high", "cns__gpt-oss-120b__effort-low"),
    ("Gemma-4 26B", "alone__gemma-4-26b__thinking-off", "cns__gemma-4-26b__thinking-off"),
    ("Llama-3.3 70B", "alone__llama-3.3-70b__default", "cns__llama-3.3-70b__default"),
]
EXTRA = [  # other configurations reported for context
    ("Qwen3.8 27B, alone thinking off", "alone__qwen3.8-27b__thinking-off", "cns__qwen3.8-27b__thinking-off"),
    ("Qwen3.8 27B, CNS thinking on", "alone__qwen3.8-27b__thinking-on", "cns__qwen3.8-27b__thinking-on"),
    ("Gemma-4 26B, alone thinking on", "alone__gemma-4-26b__thinking-on", "cns__gemma-4-26b__thinking-off"),
]


def load(name: str) -> dict[str, dict]:
    return {r["row"]: r for r in map(json.loads, (REC / f"{name}.jsonl").open())}


def mcnemar(b: int, c: int) -> float:
    n, k = b + c, min(b, c)
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float("nan")


def compare(label: str, a_name: str, b_name: str) -> dict:
    A, B = load(a_name), load(b_name)
    errors_a = sum(r["status"] == "model_error" for r in A.values())
    errors_b = sum(r["status"] == "model_error" for r in B.values())
    rows = sorted(r for r in A if r in B and A[r]["status"] != "model_error" and B[r]["status"] != "model_error")
    ca = sum(A[r]["correct"] for r in rows)
    cb = sum(B[r]["correct"] for r in rows)
    gained = sum(B[r]["correct"] and not A[r]["correct"] for r in rows)
    lost = sum(A[r]["correct"] and not B[r]["correct"] for r in rows)
    rng = random.Random(42)
    diffs = sorted(sum(B[r]["correct"] - A[r]["correct"] for r in (rng.choice(rows) for _ in rows)) / len(rows) * 100
                   for _ in range(10000))
    tok = lambda R: median([(R[r].get("usage") or {}).get("completion_tokens", 0) for r in rows])  # noqa: E731
    return {"family": label, "alone": a_name, "cns": b_name, "n": len(rows),
            "api_errors_excluded": {"alone": errors_a, "cns": errors_b},
            "alone_pct": round(100 * ca / len(rows), 1), "cns_pct": round(100 * cb / len(rows), 1),
            "gained": gained, "lost": lost, "mcnemar_p": mcnemar(gained, lost),
            "diff_ci95_pp": [round(diffs[250], 1), round(diffs[9750], 1)],
            "median_output_tokens": {"alone": tok(A), "cns": tok(B)}}


def main() -> None:
    main_rows = [compare(*p) for p in PAIRS]
    extra_rows = [compare(*p) for p in EXTRA if all((REC / f"{n}.jsonl").exists() for n in p[1:])]
    lines = ["| Model | n | Alone | In CNS | Gained / lost | McNemar p | 95% CI (pp) | Median output tokens |",
             "|---|---|---|---|---|---|---|---|"]
    for r in main_rows + extra_rows:
        lines.append(f"| {r['family']} | {r['n']} | {r['alone_pct']}% | {r['cns_pct']}% | {r['gained']} / {r['lost']} | "
                     f"{r['mcnemar_p']:.1g} | [{r['diff_ci95_pp'][0]}, {r['diff_ci95_pp'][1]}] | "
                     f"{r['median_output_tokens']['alone']:.0f} → {r['median_output_tokens']['cns']:.0f} |")
    alone = [r["alone_pct"] for r in main_rows]
    cns = [r["cns_pct"] for r in main_rows]
    spread = (f"\nRange across the five families: alone {min(alone)}–{max(alone)}% "
              f"(spread {max(alone) - min(alone):.1f} points); in CNS {min(cns)}–{max(cns)}% "
              f"(spread {max(cns) - min(cns):.1f} points).\n")
    (HERE / "summary.md").write_text("\n".join(lines) + "\n" + spread)
    (HERE / "summary.json").write_text(json.dumps({"pairs": main_rows, "context": extra_rows}, indent=1))
    print("\n".join(lines) + spread)


if __name__ == "__main__":
    main()
