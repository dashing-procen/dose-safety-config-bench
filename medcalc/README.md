# MedCalc-Bench: the same models, alone and inside the Procen CNS harness

Five open model families answered all 1,100 test questions of MedCalc-Bench Verified twice: once alone, at their best measured reasoning setting, and once inside Procen's Clinical Nervous System (CNS) harness with reasoning off or low. Every family scored higher inside the harness (Qwen3.8 78.8% → 95.0%, DeepSeek-V4-Pro 80.8% → 90.6%, GPT-OSS-120B 71.5% → 88.2%, Gemma-4 62.3% → 87.8%, Llama-3.3 42.9% → 82.8%; paired McNemar p ≤ 3e-12 for each), and the spread between the best and worst model narrowed from 37.9 to 12.2 points. For Qwen3.8, Gemma-4 and Llama-3.3 both arms use the same reasoning setting, so the gain is not a change of reasoning mode.

**Results:** [summary.md](summary.md) (paired table), [summary.json](summary.json), and every model response in [records/](records/).

## The cases

The full [MedCalc-Bench Verified](https://huggingface.co/datasets/nsk7153/MedCalc-Bench-Verified) test split: 1,100 cases, 20 per calculator for all 55 calculators (`run_direct.py --per-calc 0`). The benchmark's gold inputs and answers never enter a prompt. Scoring follows the benchmark's rules ([score.py](score.py)): decimals must fall inside the reference's lower and upper limits, integers must match, dates and gestational ages must match exactly.

Every arm completed all 1,100 cases; replies were streamed so long reasoning was not cut off by the provider's request timeout, and the few rate-limited requests were retried. An earlier unstreamed run on a 220-case subset lost 32 Qwen thinking-on cases to timeouts; those were the harder cases, which is why that subset overstated Qwen's alone score (85.1%) relative to the full split (75.9% with thinking on).

## The two arms

**Alone.** One request per case in the benchmark's zero-shot chain-of-thought format, asking for JSON with an answer ([run_direct.py](run_direct.py)). Each family's alone arm is its best measured setting on these cases, chosen after the fact (which can only favour the baseline): Qwen3.8 thinking off (78.8%, above 75.9% with thinking on), DeepSeek-V4-Pro thinking on, GPT-OSS-120B high reasoning effort, Gemma-4 thinking off (with thinking on it exhausted its 8,192-token budget before answering on most of the 101 cases tried), Llama-3.3 default. The other settings are reported in summary.md.

**Inside the CNS.** The same model, temperature 0, with reasoning off (GPT-OSS: low effort). The harness gives the model two tools and one rule:

- `find_calculator(query)` searches a library of 55 calculators and returns each match's inputs as a JSON schema.
- `calculate(calculator_id, inputs)` runs the calculator on values the model read from the note, with the units written in the note. It returns the value, each step of the derivation, every assumption (for example, a score criterion not mentioned in the note is counted absent and listed) and any missing input.
- A gate at the end of the turn rejects any final answer that does not equal a value `calculate` returned with no missing inputs. A rejected answer goes back to the model with the reason, at most twice.

The model never does arithmetic. Its job is to pick the calculator and read the note. Every model call, tool result and gate verdict is written to a hash-chained session log. The harness itself is not part of this release; the calculator library is.

## The calculator library

[calculators/](calculators/) implements all 55 MedCalc-Bench calculators from the published formulas and score definitions, in plain Python with no dependencies. Inputs are unit-aware (`[55, "kg"]`, `{"value": 0.57, "unit": "mg/dL"}`, `"162.8 cm"`), impossible values raise an error that names the likely unit mistake, and every default is reported.

```python
import sys; sys.path.insert(0, "medcalc")
from calculators import find_calculators
calc = find_calculators("CrCl")[0]
r = calc.compute({"age": [16, "years"], "sex": "female", "weight": [55, "kg"],
                  "height": [162.8, "cm"], "creatinine": [0.57, "mg/dL"]})
r.value, r.unit, r.assumptions   # 141.04, 'mL/min', ['used min(IBW, actual weight) because BMI 18.5-24.9 ...']
```

**Validation on the training split** ([calculator_validation.md](calculator_validation.md)): the library agrees with the gold answer on 10,489 of 10,538 training cases (99.5%). Each of the other 49 is a documented suspected label error. For example, gold HOMA-IR values with insulin in pmol/L multiply by 6 instead of dividing, and several creatinine values are physically impossible in the stated unit. The test split was never used to build or tune the library. `python medcalc/validate_calculators.py --train path/to/train_data.csv` reproduces the report.

Where the test split contains the same kind of label error, the harness can be marked wrong for the clinically correct value; we did not add a compatibility mode that reproduces the errors.

## Reproduce

```bash
python medcalc/analyze.py   # paired table from records/
export CF_ACCOUNT_ID=... CF_API_TOKEN=...
python medcalc/run_direct.py --test path/to/test_data.csv --model @cf/qwen/qwen3.8-27b --thinking on \
  --out medcalc/records/alone__qwen3.8-27b__thinking-on.jsonl
```

Models ran on Cloudflare Workers AI between 13 and 15 October 2026. Model responses in `records/` are derived from MedCalc-Bench Verified and are released under CC BY-SA 4.0, like the benchmark; the code in this folder is MIT.
