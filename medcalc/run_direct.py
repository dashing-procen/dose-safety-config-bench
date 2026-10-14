"""Model-alone arm: one request per case, MedCalc-Bench zero-shot chain-of-thought format.

Reproduces the "alone" records in medcalc/records/. The CNS arm runs the same cases through
Procen's harness (see medcalc/README.md for its protocol); that code is not part of this release.

  export CF_ACCOUNT_ID=... CF_API_TOKEN=...
  python medcalc/run_direct.py --test path/to/test_data.csv --model @cf/qwen/qwen3.8-27b --thinking on

Cases: all 1,100 test rows by default (--per-calc 0); --per-calc 4 picks the seeded 220-case subset (seed 42).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import os
import random
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score import direct_answer, score  # noqa: E402

SYSTEM = (
    "You are a helpful assistant for calculating a score for a given patient note. Please think step-by-step to solve "
    'the question and then generate the required score. Your output should only contain a JSON dict formatted as '
    '{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
    '"answer": str(short_and_direct_answer_of_the_question)}.'
)


def load_cases(path: Path, per_calc: int, seed: int = 42) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not per_calc:
        return rows
    by_calc: dict[str, list[dict]] = {}
    for r in rows:
        by_calc.setdefault(r["Calculator ID"], []).append(r)
    rng = random.Random(seed)
    picked = [r for cid in sorted(by_calc, key=int) for r in rng.sample(by_calc[cid], min(per_calc, len(by_calc[cid])))]
    return sorted(picked, key=lambda r: int(r["Row Number"]))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--test", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", help="OpenAI-compatible /v1 URL; default Cloudflare Workers AI")
    p.add_argument("--thinking", choices=["on", "off", "default"], default="default")
    p.add_argument("--reasoning-effort", choices=["low", "medium", "high"])
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--per-calc", type=int, default=0, help="cases per calculator; 0 = all 20")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    if a.base_url:
        url, token = a.base_url.rstrip("/") + "/chat/completions", os.environ.get("OPENAI_API_KEY")
    else:
        url = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID']}/ai/v1/chat/completions"
        token = os.environ["CF_API_TOKEN"]
    try:
        import certifi
        tls = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        tls = ssl.create_default_context()

    cases = load_cases(a.test, a.per_calc)
    done = {json.loads(l)["row"] for l in a.out.open()} if a.out.exists() else set()
    lock = threading.Lock()

    def one(r: dict) -> None:
        body = {"model": a.model, "temperature": 0.0, "max_tokens": a.max_tokens, "seed": 42, "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Here is the patient note:\n{r['Patient Note']}\n\nHere is the task:\n{r['Question']}"
             '\n\nPlease directly output the JSON dict formatted as {"step_by_step_thinking": str(...), "answer": str(...)}:'}]}
        if a.thinking != "default":
            on = a.thinking == "on"
            body |= {"chat_template_kwargs": {"enable_thinking": on}, "reasoning": {"enabled": on}}
        if a.reasoning_effort:
            body["reasoning_effort"] = a.reasoning_effort
        headers = {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {token}"} if token else {})
        rec = {"row": r["Row Number"], "calc_id": r["Calculator ID"], "calc": r["Calculator Name"],
               "output_type": r["Output Type"], "gold": r["Ground Truth Answer"], "arm": "alone", "model": a.model}
        t0, err = time.monotonic(), None
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
                with urllib.request.urlopen(req, timeout=900, context=tls) as resp:
                    out = json.load(resp)
                choice = out["choices"][0]
                content = (choice.get("message") or {}).get("content") or ""
                answer = direct_answer(content)
                rec |= {"status": "ok", "answer": answer, "correct": score(r, answer), "finish": choice.get("finish_reason"),
                        "usage": out.get("usage", {}), "latency_s": round(time.monotonic() - t0, 2), "content": content}
                break
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as e:
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(min(60, 3 * 2 ** attempt))
        else:
            rec |= {"status": "model_error", "error": err, "answer": None, "correct": False}
        with lock, a.out.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with cf.ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, [r for r in cases if r["Row Number"] not in done]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
