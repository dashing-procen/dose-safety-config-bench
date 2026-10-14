"""Validated clinical calculator library for the Procen CNS harness.

Each calculator is deterministic, converts units itself, and returns a ``CalcResult`` with the
value plus a step-by-step derivation, every assumption/default applied, and every missing
required input (value is ``None`` when something required is missing; nothing is invented).

    from calculators import get_calculator, find_calculators
    calc = get_calculator("creatinine_clearance_cockcroft_gault")
    r = calc.compute({"age": [16, "years"], "sex": "female", "weight": {"value": 55, "unit": "kg"},
                      "height": "162.8 cm", "creatinine": [50.4, "µmol/L"]})
    r.value, r.unit, r.steps, r.assumptions, r.missing

Conventions:
  * Numeric inputs: bare number (canonical unit), [v, unit], {"value": v, "unit": u}, Quantity, or "v unit".
  * Dates: "YYYY-MM-DD" (or US "MM/DD/YYYY"); date outputs are "MM/DD/YYYY" strings.
  * Gestational age output is a (weeks, days) tuple of ints.
  * Score criteria not supplied are scored absent/normal and listed in ``assumptions``.
  * Validated against MedCalc-Bench (train split): prompt-evals/medcalc/validate_calculators.py.
"""

from .base import CalcInputError, CalcResult, Calculator, Quantity
from .registry import CALCULATORS, MEDCALC_ID_MAP, by_medcalc_id, find_calculators, get_calculator
from . import units

__all__ = ["Calculator", "CalcResult", "Quantity", "CalcInputError", "CALCULATORS", "get_calculator",
           "find_calculators", "by_medcalc_id", "MEDCALC_ID_MAP", "units"]
