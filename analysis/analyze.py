"""Score every results/raw/*.jsonl run against the exact references.

Per configuration: decision accuracy, limit-violating doses ALLOWED, within-limit doses BLOCKED,
correct REVIEW on incomplete/unsupported inputs, and fidelity of the concentrations the model STATES
(within 5% of the 60-digit reference). Writes results/summary.json and results/summary.md."""
import json, re, sys, glob, statistics, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
cases = {c["case_id"]: c for c in map(json.loads, open(ROOT / "data" / "cases.jsonl"))}
def final_part(t):
    t = t or ""
    return t.split("</think>")[-1]
def parse(t):
    body = final_part(t)
    objs = re.findall(r"\{[^{}]*\"decision\"[^{}]*\}", body, re.S)
    for o in reversed(objs):
        try:
            d = json.loads(o); dec = str(d.get("decision", "")).upper().strip()
            if dec in {"ALLOW", "BLOCK", "REVIEW"}: return dec, str(d.get("reason", ""))
        except Exception:
            m = re.search(r'"decision"\s*:\s*"(ALLOW|BLOCK|REVIEW)"', o, re.I)
            if m: return m.group(1).upper(), o
    m = re.findall(r'"decision"\s*:\s*"(ALLOW|BLOCK|REVIEW)"', body, re.I)
    return (m[-1].upper(), body[-400:]) if m else (None, body[-400:])
COMPARE = re.compile(r"exceed|above|below|under|over|less|greater|limit|threshold|<|>|≥|≤|>=|<=|cap|max|maximum|within", re.I)
def num(word, s):
    """First concentration the text STATES for `word` (e.g. 'peak is 1.06 mg/L', 'trough ≈0.80 mg/L').
    Phrases that compare against a limit ('trough exceeds 2 mg/L', 'below 40 mg/L') are not stated values."""
    for m in re.finditer(word, s, re.I):
        seg = s[m.end(): m.end() + 220]
        n = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*L", seg, re.I)
        if n and not COMPARE.search(seg[: n.start()]):
            return float(n.group(1))
    return None
rows_out = []
files = sys.argv[1:] or sorted(glob.glob(str(ROOT / "results" / "raw" / "*__*.jsonl")))
for f in files:
    recs = [json.loads(l) for l in open(f)]
    ok = [r for r in recs if r["status"] == "ok"]
    if not ok: continue
    stats = collections.Counter(); peak_err = []; echo = 0; peak_claims = 0; trough_ok = trough_claims = 0
    toks = []
    for r in ok:
        c = cases[r["case_id"]]; ref = c["reference_decision"]; dec, reason = parse(r["text"])
        toks.append((r.get("usage") or {}).get("completion_tokens", 0))
        stats[(ref, dec)] += 1
        if ref != "REVIEW" and c.get("reference_peak"):
            tp, tt = float(c["reference_peak"]), float(c["reference_trough"])
            cp, ct = num("peak", reason), num("trough", reason)
            if cp is not None:
                peak_claims += 1; peak_err.append(abs(cp - tp) / tp <= 0.05); echo += 39.5 <= cp <= 42 and tp < 39.5
            if ct is not None:
                trough_claims += 1; trough_ok += abs(ct - tt) / tt <= 0.05
    n = len(ok); tot = lambda ref: sum(v for (a, _), v in stats.items() if a == ref)
    row = dict(config=Path(f).stem, n=n, failures=len(recs) - n,
               acc=sum(v for (a, b), v in stats.items() if a == b), unparsed=sum(v for (_, b), v in stats.items() if b is None),
               viol_allowed=f'{stats[("BLOCK","ALLOW")]}/{tot("BLOCK")}', false_block=f'{stats[("ALLOW","BLOCK")]}/{tot("ALLOW")}',
               allowed_ok=f'{stats[("ALLOW","ALLOW")]}/{tot("ALLOW")}', review_ok=f'{stats[("REVIEW","REVIEW")]}/{tot("REVIEW")}',
               peak_ok=f'{sum(peak_err)}/{peak_claims}', trough_ok=f'{trough_ok}/{trough_claims}', threshold_echo=echo,
               med_tok=int(statistics.median(toks)))
    rows_out.append(row)
    print(f'{row["config"][:46]:46s} n={n:3d} fail={row["failures"]} acc={row["acc"]:3d} unp={row["unparsed"]:2d} violAllowed={row["viol_allowed"]:6s} falseBlock={row["false_block"]:6s} reviewOK={row["review_ok"]:6s} peakOK={row["peak_ok"]:7s} troughOK={row["trough_ok"]:7s} echo40={echo:3d} medTok={row["med_tok"]}')
json.dump(rows_out, open(ROOT / "results" / "summary.json", "w"), indent=1)
with open(ROOT / "results" / "summary.md", "w") as f:
    f.write(
        "| Configuration | n | Correct decisions | Violations allowed | Within-limit blocked | Incomplete -> REVIEW | Stated peak within 5% | Stated trough within 5% | Median output tokens |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )
    for r in rows_out:
        f.write(
            f"| {r['config']} | {r['n']} | {r['acc']} | {r['viol_allowed']} | {r['false_block']} | {r['review_ok']} | {r['peak_ok']} | {r['trough_ok']} | {r['med_tok']} |\n"
        )
