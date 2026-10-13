"""QwQ-32B on the first 200 MedQA (US) test questions: one sample, temperature 0, a given token budget.

The only change from the historical 1,024-token baseline is --budget. Prompt, model, temperature and
answer parser are identical. MedQA is not redistributed here; download it from
https://github.com/jind11/MedQA and pass the US test.jsonl path.

  export CF_ACCOUNT_ID=... CF_API_TOKEN=...
  python medqa_budget/run_medqa_budget.py --medqa path/to/US/test.jsonl --budget 4096
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Prompt and strict parser exactly as in the historical run, including the parser's known flaw:
# _letters() collects every A-E character in the matched span, so "answer is about" reads as "AB".
# Kept unchanged so the budget comparison uses the same scoring as the historical baseline.
BOXED_RE = re.compile(r"\\boxed\{([^}]*)\}")
ANS_RE = re.compile(
    r"(?i)(?:final\s+answer|answer|correct(?: option| choice)?|choice|option|最终答案)"
    r"\s*(?:is|:|：)?\s*\(?([A-E]{1,5})\)?"
)
TRAIL_RE = re.compile(r"\b([A-E])\b[.\s]*$")


def _letters(blob: str) -> str:
    found = re.findall(r"[A-E]", (blob or "").upper())
    if not found:
        return ""
    return found[0] if len(found) == 1 else "".join(sorted(set(found)))


def parse_strict_letters(text: str) -> str:
    t = (text or "").strip()
    boxed = BOXED_RE.search(t)
    if boxed and _letters(boxed.group(1)):
        return _letters(boxed.group(1))
    m = ANS_RE.search(t)
    if m:
        return _letters(m.group(1))
    m = TRAIL_RE.search(t)
    return m.group(1).upper() if m else ""


def mcq_prompt(question: str, options: dict[str, str]) -> str:
    lines = [question.strip(), ""] + [f"{k}. {options[k]}" for k in sorted(options)]
    lines += ["", "Reason step by step, then give your final answer as \\boxed{X} "
              "where X is the option letter. Output the boxed answer only once, at the very end."]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--medqa", type=Path, required=True, help="MedQA US test.jsonl")
    p.add_argument("--budget", type=int, required=True)
    p.add_argument("--model", default="@cf/qwen/qwq-32b")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--workers", type=int, default=6)
    a = p.parse_args()

    url = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID']}/ai/v1/chat/completions"
    token = os.environ["CF_API_TOKEN"]
    rows = [json.loads(line) for line in a.medqa.open() if line.strip()][: a.limit]
    items = [{"id": f"medqa-{i}", "gold": str(r["answer_idx"]).strip().upper(),
              "prompt": mcq_prompt(r["question"], dict(r["options"]))} for i, r in enumerate(rows)]
    out = HERE / "records" / f"{a.model.split('/')[-1]}__t0_{a.budget}.jsonl"
    done = {json.loads(line)["id"] for line in out.open()} if out.exists() else set()
    lock = threading.Lock()

    def run(item: dict) -> None:
        payload = {"model": a.model, "messages": [{"role": "user", "content": item["prompt"]}],
                   "temperature": 0.0, "max_tokens": a.budget, "reasoning": {"enabled": True}}
        t0, body, err = time.time(), None, None
        for attempt in range(8):
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=600) as r:
                    body = json.load(r)
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                time.sleep(5 + 3 * attempt if e.code == 429 else 3)
            except Exception as e:  # noqa: BLE001 - record and retry transport failures
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(3)
        rec = {"id": item["id"], "gold": item["gold"]}
        if body is None:
            rec.update(status="backend_failure", error=err)
        else:
            choice = body["choices"][0]
            msg = choice.get("message") or {}
            content = msg.get("content") or ""
            pred = parse_strict_letters(content)
            rec.update(status="ok", budget=a.budget, temperature=0.0, finish=choice.get("finish_reason"),
                       usage=body.get("usage"), latency_s=round(time.time() - t0, 2),
                       pred_strict=pred or None, match_strict=pred == item["gold"], content=content,
                       reasoning=msg.get("reasoning") or msg.get("reasoning_content") or "")
        with lock, out.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    todo = [i for i in items if i["id"] not in done]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, todo))
    print(f"{out}: {len(todo)} new records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
