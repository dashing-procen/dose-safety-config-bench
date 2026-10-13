"""Run the 150-case dose-check task against any OpenAI-compatible chat endpoint.

The prompt gives the model the regimen, the kinetics, the closed-form formula and the limits,
and asks for ALLOW / BLOCK / REVIEW. Only the inference configuration (--mode) varies between runs.

Examples
  # Cloudflare Workers AI (credentials from the environment)
  export CF_ACCOUNT_ID=... CF_API_TOKEN=...
  python run/run_dose_check.py --provider cloudflare --model @cf/qwen/qwen3.8-27b --mode think_off

  # Local llama.cpp server
  python run/run_dose_check.py --base-url http://localhost:8080/v1 --model qwen --mode think_on

Output: results/raw/<model>__<mode>.jsonl, one record per case, resumable.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = (
    '\nReturn only JSON: {"decision":"ALLOW|BLOCK|REVIEW","reason":"brief explanation"}. '
    "ALLOW means within the encoded rules; REVIEW means missing, conflicting or unsupported inputs."
)
# Extra request fields per inference configuration. Providers ignore fields they do not support,
# so check that a toggle takes effect (reasoning tokens present or absent) before comparing modes.
MODES = {
    "think_off": {"chat_template_kwargs": {"enable_thinking": False}, "reasoning": {"enabled": False}},
    "think_on": {"chat_template_kwargs": {"enable_thinking": True}, "reasoning": {"enabled": True}},
    "effort_low": {"reasoning_effort": "low"},
    "effort_high": {"reasoning_effort": "high"},
    "default": {},
}


def prompt_for(case: dict) -> str:
    return (
        case["generation_input"]
        + "\nExecutable rule documentation:\n"
        + case["rule_documentation"]
        + SUFFIX
    )


def post(url: str, payload: dict, token: str | None, timeout: float) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", choices=["cloudflare", "openai-compatible"], default="openai-compatible")
    p.add_argument("--base-url", help="OpenAI-compatible base URL ending in /v1")
    p.add_argument("--model", required=True)
    p.add_argument("--mode", choices=sorted(MODES), default="default")
    p.add_argument("--cases", type=Path, default=ROOT / "data" / "cases.jsonl")
    p.add_argument("--out-dir", type=Path, default=ROOT / "results" / "raw")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    if a.provider == "cloudflare":
        base = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID']}/ai/v1"
        token = os.environ["CF_API_TOKEN"]
    else:
        if not a.base_url:
            p.error("--base-url is required for openai-compatible endpoints")
        base, token = a.base_url, os.environ.get("OPENAI_API_KEY")
    url = base.rstrip("/") + "/chat/completions"

    cases = [json.loads(line) for line in a.cases.open() if line.strip()]
    if a.limit:
        cases = cases[: a.limit]
    a.out_dir.mkdir(parents=True, exist_ok=True)
    out = a.out_dir / f"{a.model.split('/')[-1]}__{a.mode}.jsonl"
    done = {json.loads(line)["case_id"] for line in out.open()} if out.exists() else set()
    lock = threading.Lock()

    def run(case: dict) -> None:
        payload = {
            "model": a.model,
            "messages": [{"role": "user", "content": prompt_for(case)}],
            "temperature": 0.0,
            "max_tokens": a.max_tokens,
            "seed": 42,
            **MODES[a.mode],
        }
        t0, body, err = time.time(), None, None
        for attempt in range(8):
            try:
                body = post(url, payload, token, a.timeout)
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                time.sleep(5 + 3 * attempt if e.code == 429 else 3)
            except Exception as e:  # noqa: BLE001 - record and retry transport failures
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(3)
        rec = {"case_id": case["case_id"], "model": a.model, "mode": a.mode,
               "latency_s": round(time.time() - t0, 2)}
        if body is None:
            rec.update(status="backend_failure", error=err)
        else:
            choice = body["choices"][0]
            msg = choice.get("message") or {}
            rec.update(status="ok", text=msg.get("content") or "",
                       reasoning=msg.get("reasoning_content") or msg.get("reasoning") or "",
                       finish=choice.get("finish_reason"), usage=body.get("usage", {}))
        with lock, out.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    todo = [c for c in cases if c["case_id"] not in done]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, todo))
    print(f"{out}: {len(todo)} new records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
