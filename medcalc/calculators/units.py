"""Unit conversion for the clinical calculator library.

Every physical input is converted to one *canonical* unit per kind before a formula runs.
A "kind" is either a physical dimension (mass, length, temperature, ...) or an analyte
(creatinine, glucose, sodium, ...). Analyte concentrations are converted generically: the
unit is parsed as ``<amount>/<volume>`` where the amount is a mass (g, mg, µg ...), a molar
amount (mol, mmol, µmol ...) or an equivalent (Eq, mEq), and the molar mass / valence of the
analyte bridges mass <-> mol <-> Eq. So ``mg/dL``, ``µmol/L``, ``mmol/L``, ``g/L``, ``mEq/L``,
``mmol/dL`` and even odd forms like ``mEq/mL`` all convert correctly.

Public API:
    to_canonical(kind, value, unit) -> (value_in_canonical_unit, canonical_unit)
    convert(value, from_unit, to_unit, kind) -> float
    canonical_unit(kind) -> str
    accepted_units(kind) -> list[str]   (human-readable list for tool descriptions)
    UnitError
"""

from __future__ import annotations

import re

__all__ = [
    "UnitError", "to_canonical", "convert", "canonical_unit", "accepted_units",
    "normalize_unit", "ANALYTES", "KINDS",
]


class UnitError(ValueError):
    """Raised for an unknown or incompatible unit."""


# --------------------------------------------------------------------------------------
# unit-string normalisation
# --------------------------------------------------------------------------------------

def normalize_unit(unit: str | None) -> str:
    """Lower-case, ASCII-fy and de-space a unit string ('µmol/L' -> 'umol/l')."""
    if unit is None:
        return ""
    u = str(unit).strip().lower()
    for micro in ("µ", "μ", "µ"):
        u = u.replace(micro, "u")
    u = u.replace("mcg", "ug").replace("³", "3").replace("²", "2").replace("°", "")
    u = u.replace("per ", "/").replace(" per", "/")
    u = re.sub(r"\s+", "", u)
    u = u.replace("**", "^")
    return u


# --------------------------------------------------------------------------------------
# simple dimensional kinds: table of (aliases -> factor to canonical) or callables
# --------------------------------------------------------------------------------------

def _lin(factor: float, offset: float = 0.0):
    return lambda v: v * factor + offset


_MASS = {  # canonical kg
    "kg": 1.0, "kgs": 1.0, "kilogram": 1.0, "kilograms": 1.0,
    "g": 1e-3, "gram": 1e-3, "grams": 1e-3, "mg": 1e-6, "ug": 1e-9,
    "lb": 0.453592, "lbs": 0.453592, "pound": 0.453592, "pounds": 0.453592,
    "oz": 0.0283495, "ounce": 0.0283495, "ounces": 0.0283495,
}
_LENGTH = {  # canonical cm
    "cm": 1.0, "centimeter": 1.0, "centimeters": 1.0, "centimetre": 1.0, "centimetres": 1.0,
    "m": 100.0, "meter": 100.0, "meters": 100.0, "metre": 100.0, "metres": 100.0,
    "mm": 0.1, "in": 2.54, "inch": 2.54, "inches": 2.54, '"': 2.54,
    "ft": 30.48, "foot": 30.48, "feet": 30.48, "'": 30.48,
}
_AGE = {  # canonical years
    "y": 1.0, "yr": 1.0, "yrs": 1.0, "year": 1.0, "years": 1.0, "yearsold": 1.0,
    "mo": 1 / 12, "month": 1 / 12, "months": 1 / 12,
    "wk": 7 / 365.25, "week": 7 / 365.25, "weeks": 7 / 365.25,
    "d": 1 / 365.25, "day": 1 / 365.25, "days": 1 / 365.25,
    "h": 1 / 8766, "hr": 1 / 8766, "hour": 1 / 8766, "hours": 1 / 8766,
}
_DURATION = {  # canonical msec (ECG intervals)
    "ms": 1.0, "msec": 1.0, "millisecond": 1.0, "milliseconds": 1.0,
    "s": 1000.0, "sec": 1000.0, "second": 1000.0, "seconds": 1000.0,
}
_TIME_DAYS = {  # canonical days (cycle length etc.)
    "d": 1.0, "day": 1.0, "days": 1.0, "wk": 7.0, "week": 7.0, "weeks": 7.0,
}
_PRESSURE = {  # canonical mmHg
    "mmhg": 1.0, "mm": 1.0, "torr": 1.0, "smmhg": 1.0,
    "kpa": 7.50062, "cmh2o": 0.735559, "atm": 760.0,
}
_PERCENT = {"%": 1.0, "percent": 1.0, "pct": 1.0, "fraction": 100.0}
_ENZYME = {"u/l": 1.0, "iu/l": 1.0, "units/l": 1.0, "ukat/l": 60.0, "nkat/l": 0.06}
_INSULIN = {  # canonical µIU/mL; 1 µIU/mL = 6.0 pmol/L (WHO IRP 66/304 convention used by MDCalc)
    "uiu/ml": 1.0, "uu/ml": 1.0, "miu/l": 1.0, "mu/l": 1.0, "uiu/l": 1e-3,
    "pmol/l": 1 / 6.0,
}
_HEMOGLOBIN = {"g/dl": 1.0, "g/l": 0.1, "mg/dl": 1e-3, "mmol/l": 1.61135}
_BMI = {"kg/m2": 1.0, "kg/m^2": 1.0, "kgm2": 1.0, "kgm^2": 1.0}
_VOLUME = {"ml": 1.0, "l": 1000.0, "dl": 100.0, "cc": 1.0}
_URINE_RATE = {  # canonical mL/day
    "ml/day": 1.0, "ml/d": 1.0, "ml/24h": 1.0, "ml/24hr": 1.0, "ml/24hours": 1.0,
    "l/day": 1000.0, "l/d": 1000.0, "ml/h": 24.0, "ml/hr": 24.0, "ml/hour": 24.0,
}
_DOSE_RATE = {"ug/kg/min": 1.0, "mg/kg/min": 1000.0, "ug/kg/h": 1 / 60, "ug/kg/hr": 1 / 60}
_DRUG_MASS = {"mg": 1.0, "g": 1000.0, "ug": 1e-3}  # canonical mg
_FLUID_RATE = {"ml/hr": 1.0, "ml/h": 1.0, "ml/day": 1 / 24, "l/day": 1000 / 24}


def _temperature(v: float, u: str) -> float:
    if u in ("c", "degc", "celsius", "degreescelsius", "degreecelsius", "centigrade"):
        return v
    if u in ("f", "degf", "fahrenheit", "degreesfahrenheit", "degreefahrenheit"):
        return (v - 32.0) * 5.0 / 9.0
    if u in ("k", "kelvin"):
        return v - 273.15
    raise UnitError(f"unknown temperature unit {u!r} (use °C, °F or K)")


def _per_minute(v: float, u: str) -> float:
    if u in ("", "bpm", "/min", "/minute", "min^-1", "min-1") or "min" in u:
        return v
    if u in ("hz", "/s", "/sec", "/second"):
        return v * 60.0
    raise UnitError(f"unknown rate unit {u!r} (use per minute)")


_COUNT_PER_VOL = {  # canonical 10^9/L (== 10^3/µL)
    "10^9/l": 1.0, "x10^9/l": 1.0, "10e9/l": 1.0, "giga/l": 1.0, "10^3/ul": 1.0,
    "x10^3/ul": 1.0, "k/ul": 1.0, "thou/ul": 1.0, "10^3/mm3": 1.0, "10^3/mm^3": 1.0,
    "x10^3/mm3": 1.0, "10^3/l": 1e-6,
    # bare per-volume counts (MedCalc style: [277000, 'µL'] means 277000 per µL)
    "ul": 1e-3, "/ul": 1e-3, "cells/ul": 1e-3, "count/ul": 1e-3, "mm3": 1e-3, "/mm3": 1e-3,
    "mm^3": 1e-3, "/mm^3": 1e-3, "cells/mm3": 1e-3, "count/mm3": 1e-3,
    "ml": 1e-6, "/ml": 1e-6, "dl": 1e-8, "/dl": 1e-8, "l": 1e-9, "/l": 1e-9, "count/l": 1e-9,
}

_SIMPLE: dict[str, tuple[str, dict[str, float]]] = {
    "mass": ("kg", _MASS),
    "length": ("cm", _LENGTH),
    "age": ("years", _AGE),
    "duration_ms": ("msec", _DURATION),
    "days": ("days", _TIME_DAYS),
    "pressure": ("mmHg", _PRESSURE),
    "percent": ("%", _PERCENT),
    "enzyme": ("U/L", _ENZYME),
    "insulin": ("µIU/mL", _INSULIN),
    "hemoglobin": ("g/dL", _HEMOGLOBIN),
    "bmi": ("kg/m^2", _BMI),
    "volume": ("mL", _VOLUME),
    "urine_output": ("mL/day", _URINE_RATE),
    "dose_rate": ("mcg/kg/min", _DOSE_RATE),
    "drug_mass": ("mg", _DRUG_MASS),
    "cell_count": ("10^9/L", _COUNT_PER_VOL),
    "fluid_rate": ("mL/hr", _FLUID_RATE),
}

_FUNCTIONAL: dict[str, tuple[str, object, list[str]]] = {
    "temperature": ("°C", _temperature, ["°C", "°F", "K"]),
    "rate_per_min": ("/min", _per_minute, ["beats/min", "breaths/min", "bpm", "/min", "Hz"]),
}


# --------------------------------------------------------------------------------------
# analytes: molar mass (g/mol), valence, canonical unit
# --------------------------------------------------------------------------------------

ANALYTES: dict[str, dict] = {
    "creatinine": {"mw": 113.12, "valence": None, "canonical": "mg/dL"},
    "glucose": {"mw": 180.156, "valence": None, "canonical": "mg/dL"},
    # BUN is reported as mass of urea *nitrogen*; 1 mmol urea carries 28.0134 mg N.
    "bun": {"mw": 28.0134, "valence": None, "canonical": "mg/dL"},
    "calcium": {"mw": 40.078, "valence": 2, "canonical": "mg/dL"},
    "albumin": {"mw": 66500.0, "valence": None, "canonical": "g/dL"},
    "bilirubin": {"mw": 584.66, "valence": None, "canonical": "mg/dL"},
    "cholesterol": {"mw": 386.65, "valence": None, "canonical": "mg/dL"},
    "triglycerides": {"mw": 885.7, "valence": None, "canonical": "mg/dL"},
    "sodium": {"mw": 22.98977, "valence": 1, "canonical": "mEq/L"},
    "potassium": {"mw": 39.0983, "valence": 1, "canonical": "mEq/L"},
    "chloride": {"mw": 35.453, "valence": 1, "canonical": "mEq/L"},
    "bicarbonate": {"mw": 61.0168, "valence": 1, "canonical": "mEq/L"},
    "magnesium": {"mw": 24.305, "valence": 2, "canonical": "mg/dL"},
}

_MASS_G = {"kg": 1e3, "g": 1.0, "mg": 1e-3, "ug": 1e-6, "ng": 1e-9, "pg": 1e-12}
_MOL = {"mol": 1.0, "mmol": 1e-3, "umol": 1e-6, "nmol": 1e-9, "pmol": 1e-12}
_EQ = {"eq": 1.0, "meq": 1e-3, "ueq": 1e-6}
_VOL_L = {"l": 1.0, "dl": 0.1, "cl": 0.01, "ml": 1e-3, "ul": 1e-6, "100ml": 0.1, "cc": 1e-3}


def _parse_conc(u: str) -> tuple[str, float, float]:
    """'mg/dl' -> ('mass', g-per-unit-amount, L-per-unit-volume)."""
    if u.endswith("%") and u[:-1] in _MASS_G:  # mg% == mg/dL
        u = u[:-1] + "/dl"
    if "/" not in u:
        raise UnitError(f"not a concentration unit: {u!r}")
    num, den = u.split("/", 1)
    if den not in _VOL_L:
        raise UnitError(f"unknown volume in concentration unit {u!r}")
    if num in _MASS_G:
        return "mass", _MASS_G[num], _VOL_L[den]
    if num in _MOL:
        return "mol", _MOL[num], _VOL_L[den]
    if num in _EQ:
        return "eq", _EQ[num], _VOL_L[den]
    raise UnitError(f"unknown amount in concentration unit {u!r}")


def _conc_to_canonical(analyte: str, v: float, u: str) -> float:
    spec = ANALYTES[analyte]
    mw, val = spec["mw"], spec["valence"]
    kind, amt_f, vol_f = _parse_conc(u)
    per_l = v * amt_f / vol_f  # g/L, mol/L or Eq/L
    # -> mol/L
    if kind == "mass":
        mol_l = per_l / mw
    elif kind == "mol":
        mol_l = per_l
    else:
        if not val:
            raise UnitError(f"{analyte} has no valence; cannot use equivalents ({u!r})")
        mol_l = per_l / val
    ckind, camt, cvol = _parse_conc(normalize_unit(spec["canonical"]))
    if ckind == "mass":
        return mol_l * mw / camt * cvol
    if ckind == "mol":
        return mol_l / camt * cvol
    return mol_l * val / camt * cvol


def _conc_units(analyte: str) -> list[str]:
    spec = ANALYTES[analyte]
    out = ["mg/dL", "g/dL", "g/L", "mg/L", "mmol/L", "µmol/L"]
    if spec["valence"]:
        out.append("mEq/L")
    return out


KINDS = sorted(set(_SIMPLE) | set(_FUNCTIONAL) | set(ANALYTES))


def canonical_unit(kind: str) -> str:
    if kind in _SIMPLE:
        return _SIMPLE[kind][0]
    if kind in _FUNCTIONAL:
        return _FUNCTIONAL[kind][0]
    if kind in ANALYTES:
        return ANALYTES[kind]["canonical"]
    raise KeyError(kind)


def accepted_units(kind: str) -> list[str]:
    if kind in _SIMPLE:
        canon, table = _SIMPLE[kind]
        pretty = {
            "mass": ["kg", "g", "lb", "oz"], "length": ["cm", "m", "mm", "in", "ft"],
            "age": ["years", "months", "weeks", "days"], "duration_ms": ["msec", "s"],
            "days": ["days", "weeks"], "pressure": ["mmHg", "kPa", "cmH2O"],
            "percent": ["%", "fraction (0-1)"], "enzyme": ["U/L", "IU/L", "µkat/L"],
            "insulin": ["µIU/mL", "mIU/L", "pmol/L"], "hemoglobin": ["g/dL", "g/L", "mmol/L"],
            "bmi": ["kg/m^2"], "volume": ["mL", "L"], "urine_output": ["mL/day", "L/day", "mL/hr"],
            "dose_rate": ["mcg/kg/min", "mcg/kg/hr"], "drug_mass": ["mg", "g", "mcg"],
            "cell_count": ["10^9/L", "10^3/µL", "count per µL (e.g. [277000,'µL'])", "count per L"],
            "fluid_rate": ["mL/hr", "mL/day"],
        }
        return pretty.get(kind, [canon])
    if kind in _FUNCTIONAL:
        return list(_FUNCTIONAL[kind][2])
    if kind in ANALYTES:
        return _conc_units(kind)
    raise KeyError(kind)


def to_canonical(kind: str, value: float, unit: str | None) -> tuple[float, str]:
    """Convert ``value unit`` to the canonical unit of ``kind``.

    ``unit`` None/'' means the value is already canonical.
    Raises UnitError for an unknown/incompatible unit.
    """
    v = float(value)
    canon = canonical_unit(kind)
    u = normalize_unit(unit)
    if u == "" or u == normalize_unit(canon):
        return v, canon
    if kind in _SIMPLE:
        table = _SIMPLE[kind][1]
        if u in table:
            return v * table[u], canon
        # tolerate trailing words like 'mm hg' -> 'mmhg' already handled; try stripping 's'
        if u.endswith("s") and u[:-1] in table:
            return v * table[u[:-1]], canon
        raise UnitError(f"unknown unit {unit!r} for {kind}; accepted: {', '.join(accepted_units(kind))}")
    if kind in _FUNCTIONAL:
        fn = _FUNCTIONAL[kind][1]
        return fn(v, u), canon  # type: ignore[operator]
    if kind in ANALYTES:
        if u in ("meq/l", "mmol/l") and ANALYTES[kind]["valence"] == 1 and normalize_unit(canon) == "meq/l":
            return v, canon
        try:
            return _conc_to_canonical(kind, v, u), canon
        except UnitError as exc:
            raise UnitError(f"{exc}; accepted for {kind}: {', '.join(accepted_units(kind))}") from None
    raise UnitError(f"unknown quantity kind {kind!r}")


def convert(value: float, from_unit: str | None, to_unit: str, kind: str) -> float:
    """Convert between two units of the same kind (via the canonical unit)."""
    canon_v, canon = to_canonical(kind, value, from_unit)
    if normalize_unit(to_unit) == normalize_unit(canon):
        return canon_v
    one, _ = to_canonical(kind, 1.0, to_unit)
    if kind == "temperature":
        zero, _ = to_canonical(kind, 0.0, to_unit)
        return (canon_v - zero) / (one - zero)
    return canon_v / one
