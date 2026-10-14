"""Core types for the validated clinical calculator library.

A calculator is a deterministic function from structured inputs to a ``CalcResult`` that
carries, besides the value, the full derivation (``steps``), every convention or default
that was applied (``assumptions``) and every required input that was not supplied
(``missing``). Nothing is ever invented: a required input that is absent yields
``value=None`` and an entry in ``missing``; an optional criterion that is absent is scored
per the documented convention (almost always "absent / normal") and that choice is listed
in ``assumptions``.

Input value formats accepted for numeric (physical) parameters:
    55                      bare number = canonical unit of the parameter
    [55.0, 'kg']            MedCalc style
    [5, 'ft', 7, 'in']      compound quantities are summed
    {"value": 55, "unit": "kg"}
    Quantity(55, "kg")
    "55 kg"                 string with value and unit
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import units as _units

__all__ = ["Calculator", "CalcResult", "Quantity", "CalcInputError", "Ctx"]


class CalcInputError(ValueError):
    """Unusable input: unknown parameter, bad unit, impossible value, wrong type."""


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str | None = None


@dataclass(frozen=True)
class CalcResult:
    value: float | int | str | tuple | None
    unit: str | None
    steps: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.value is not None and not self.missing

    def to_dict(self) -> dict:
        return {"value": self.value, "unit": self.unit, "steps": list(self.steps),
                "assumptions": list(self.assumptions), "missing": list(self.missing)}


# ------------------------------------------------------------------------------------------
# JSON-schema helpers used by calculator definitions
# ------------------------------------------------------------------------------------------

def qparam(description: str, kind: str) -> dict:
    """Schema for a numeric physical quantity; accepted units are appended to the description."""
    canon = _units.canonical_unit(kind)
    units = ", ".join(_units.accepted_units(kind))
    return {
        "type": "object",
        "properties": {"value": {"type": "number"}, "unit": {"type": "string"}},
        "required": ["value"],
        "description": f"{description} Units: {units}. A bare number is read as {canon}.",
        "x-kind": kind,
    }


def bparam(description: str) -> dict:
    return {"type": "boolean", "description": description}


def eparam(description: str, choices: Iterable[str]) -> dict:
    return {"type": "string", "enum": list(choices), "description": description}


def nparam(description: str, minimum: float | None = None, maximum: float | None = None) -> dict:
    d: dict = {"type": "number", "description": description}
    if minimum is not None:
        d["minimum"] = minimum
    if maximum is not None:
        d["maximum"] = maximum
    return d


def dparam(description: str) -> dict:
    return {"type": "string", "format": "date",
            "description": f"{description} Format YYYY-MM-DD (MM/DD/YYYY also accepted)."}


SEX = eparam("Biological sex.", ["male", "female"])


def fmt(x: float, nd: int = 5) -> str:
    """Compact number formatting for derivation steps."""
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer() and abs(x) < 1e15):
        return str(int(x))
    return f"{x:.{nd}g}" if abs(x) >= 1e5 or abs(x) < 1e-3 else str(round(x, nd))


# ------------------------------------------------------------------------------------------
# input context
# ------------------------------------------------------------------------------------------

_TRUE = {"true", "yes", "y", "present", "positive", "1", "t"}
_FALSE = {"false", "no", "n", "absent", "negative", "0", "f", "none"}


class _Missing(Exception):
    pass


class Ctx:
    """Per-call helper: parses inputs, converts units, and records steps/assumptions/missing."""

    def __init__(self, calc: "Calculator", inputs: dict):
        self.calc = calc
        self.inputs = inputs
        self.steps: list[str] = []
        self.assumptions: list[str] = []
        self.missing: list[str] = []

    # -- bookkeeping -----------------------------------------------------------------------
    def step(self, text: str) -> None:
        self.steps.append(text)

    def assume(self, text: str) -> None:
        if text not in self.assumptions:
            self.assumptions.append(text)

    def _label(self, name: str) -> str:
        spec = self.calc.parameters["properties"].get(name, {})
        return spec.get("title") or name.replace("_", " ")

    def has(self, name: str) -> bool:
        return self.inputs.get(name) is not None

    def _raw(self, name: str):
        if name not in self.calc.parameters["properties"]:
            raise RuntimeError(f"{self.calc.id}: undeclared parameter {name!r}")
        return self.inputs.get(name)

    def _need(self, name: str, why: str | None = None) -> None:
        entry = name if not why else f"{name} ({why})"
        if entry not in self.missing:
            self.missing.append(entry)

    # -- quantities ------------------------------------------------------------------------
    def qty(self, name: str, required: bool = True, *, positive: bool = False,
            lo: float | None = None, hi: float | None = None, default: float | None = None,
            default_note: str | None = None, log: bool = True) -> float | None:
        """Numeric physical input converted to the parameter's canonical unit."""
        spec = self.calc.parameters["properties"][name]
        kind = spec.get("x-kind")
        raw = self._raw(name)
        if raw is None:
            if default is not None:
                self.assume(default_note or f"{self._label(name)} not provided: used {fmt(default)} {_units.canonical_unit(kind) if kind else ''}".rstrip())
                return default
            if required:
                self._need(name)
            return None
        value, unit = parse_quantity(raw, name)
        if kind is None:
            if unit:
                raise CalcInputError(f"{name}: unitless parameter given unit {unit!r}")
            out, canon = value, ""
        else:
            try:
                if isinstance(value, list):  # compound e.g. [5,'ft',7,'in']
                    out = 0.0
                    for v, u in value:
                        out += _units.to_canonical(kind, v, u)[0]
                    canon = _units.canonical_unit(kind)
                    unit = " + ".join(f"{fmt(v)} {u}" for v, u in value)
                    value = None
                else:
                    out, canon = _units.to_canonical(kind, value, unit)
            except _units.UnitError as exc:
                raise CalcInputError(f"{name}: {exc}") from None
        if not math.isfinite(out):
            raise CalcInputError(f"{name}: value is not finite")
        if positive and out <= 0:
            raise CalcInputError(f"{name}: must be > 0 (got {fmt(out)} {canon})")
        if lo is not None and out < lo:
            raise CalcInputError(f"{name}: {fmt(out)} {canon} is below the plausible range (>= {fmt(lo)})")
        if hi is not None and out > hi:
            raise CalcInputError(f"{name}: {fmt(out)} {canon} is above the plausible range (<= {fmt(hi)}); check the unit")
        if log:
            src = f"{fmt(value)} {unit}" if value is not None else str(unit)
            if unit and _units.normalize_unit(unit) != _units.normalize_unit(canon):
                self.step(f"{self._label(name)} = {src} = {fmt(out)} {canon}")
            else:
                self.step(f"{self._label(name)} = {fmt(out)} {canon}".rstrip())
        return out

    def num(self, name: str, required: bool = True, *, lo: float | None = None, hi: float | None = None,
            default: float | None = None, default_note: str | None = None, log: bool = True) -> float | None:
        """Dimensionless number (INR, pH, GCS, counts...)."""
        raw = self._raw(name)
        if raw is None:
            if default is not None:
                self.assume(default_note or f"{self._label(name)} not provided: used {fmt(default)}")
                return default
            if required:
                self._need(name)
            return None
        if isinstance(raw, (list, tuple)) and len(raw) >= 1:
            raw = raw[0]
        if isinstance(raw, dict):
            raw = raw.get("value")
        try:
            out = float(raw)
        except (TypeError, ValueError):
            raise CalcInputError(f"{name}: expected a number, got {raw!r}") from None
        if not math.isfinite(out):
            raise CalcInputError(f"{name}: value is not finite")
        if lo is not None and out < lo:
            raise CalcInputError(f"{name}: {fmt(out)} is below the valid range (>= {fmt(lo)})")
        if hi is not None and out > hi:
            raise CalcInputError(f"{name}: {fmt(out)} is above the valid range (<= {fmt(hi)})")
        if log:
            self.step(f"{self._label(name)} = {fmt(out)}")
        return out

    # -- booleans / enums -----------------------------------------------------------------
    def flag(self, name: str, default: bool | None = False, *, note: str | None = None) -> bool | None:
        """Boolean criterion. Absent -> ``default`` (listed in assumptions). default=None -> required."""
        raw = self._raw(name)
        if raw is None:
            if default is None:
                self._need(name)
                return None
            self.assume(note or f"{'absent' if not default else 'present'}: {self._label(name)} (not provided)")
            return default
        return parse_bool(raw, name)

    def enum(self, name: str, default: str | None = None, *, note: str | None = None,
             aliases: dict[str, str] | None = None) -> str | None:
        spec = self.calc.parameters["properties"][name]
        choices = spec["enum"]
        raw = self._raw(name)
        if raw is None:
            if default is None:
                self._need(name)
                return None
            self.assume(note or f"{self._label(name)} not provided: assumed '{default}'")
            return default
        key = _norm_choice(str(raw))
        for c in choices:
            if _norm_choice(c) == key:
                return c
        for a, c in (aliases or {}).items():
            if _norm_choice(a) == key:
                return c
        raise CalcInputError(f"{name}: {raw!r} is not one of {choices}")

    def sex(self, name: str = "sex", required: bool = True) -> str | None:
        raw = self._raw(name)
        if raw is None:
            if required:
                self._need(name)
            return None
        s = _norm_choice(str(raw))
        if s in ("male", "m", "man", "boy"):
            return "male"
        if s in ("female", "f", "woman", "girl"):
            return "female"
        raise CalcInputError(f"{name}: expected 'male' or 'female', got {raw!r}")

    def date(self, name: str, required: bool = True) -> _dt.date | None:
        raw = self._raw(name)
        if raw is None:
            if required:
                self._need(name)
            return None
        return parse_date(raw, name)


def _norm_choice(s: str) -> str:
    return re.sub(r"[^a-z0-9<>=+]+", "", s.lower())


def parse_bool(raw: Any, name: str = "value") -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    s = str(raw).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise CalcInputError(f"{name}: expected true/false, got {raw!r}")


_QSTR = re.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")


def parse_quantity(raw: Any, name: str = "value"):
    """Return (value, unit) or ([(v,u),...], None) for compound quantities."""
    if isinstance(raw, Quantity):
        return float(raw.value), raw.unit
    if isinstance(raw, bool):
        raise CalcInputError(f"{name}: expected a quantity, got a boolean")
    if isinstance(raw, (int, float)):
        return float(raw), None
    if isinstance(raw, dict):
        if "value" not in raw:
            raise CalcInputError(f"{name}: quantity object needs 'value'")
        try:
            return float(raw["value"]), raw.get("unit")
        except (TypeError, ValueError):
            raise CalcInputError(f"{name}: non-numeric value {raw['value']!r}") from None
    if isinstance(raw, (list, tuple)):
        if len(raw) == 1:
            return parse_quantity(raw[0], name)
        if len(raw) == 2:
            try:
                return float(raw[0]), (None if raw[1] is None else str(raw[1]))
            except (TypeError, ValueError):
                raise CalcInputError(f"{name}: cannot read quantity {raw!r}") from None
        if len(raw) % 2 == 0:
            try:
                pairs = [(float(raw[i]), str(raw[i + 1])) for i in range(0, len(raw), 2)]
            except (TypeError, ValueError):
                raise CalcInputError(f"{name}: cannot read quantity {raw!r}") from None
            return pairs, None
        raise CalcInputError(f"{name}: cannot read quantity {raw!r}")
    if isinstance(raw, str):
        m = _QSTR.match(raw)
        if m:
            return float(m.group(1)), (m.group(2) or None)
    raise CalcInputError(f"{name}: cannot read quantity {raw!r}")


def parse_date(raw: Any, name: str = "date") -> _dt.date:
    if isinstance(raw, _dt.datetime):
        return raw.date()
    if isinstance(raw, _dt.date):
        return raw
    s = str(raw).strip()
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise CalcInputError(f"{name}: unrecognised date {raw!r} (use YYYY-MM-DD or MM/DD/YYYY)")


# ------------------------------------------------------------------------------------------
# calculator base class
# ------------------------------------------------------------------------------------------

class Calculator:
    """One clinical calculator. Subclasses set the class attributes and implement ``run``."""

    id: str = ""
    name: str = ""
    medcalc_ids: tuple[int, ...] = ()
    description: str = ""
    output_unit: str | None = None
    parameters: dict = {"type": "object", "properties": {}, "required": []}
    aliases: tuple[str, ...] = ()
    category: str = ""
    references: tuple[str, ...] = ()
    decimals: int | None = 5  # rounding applied to float outputs (None = no rounding)

    def run(self, c: Ctx):  # pragma: no cover - abstract
        raise NotImplementedError

    def compute(self, inputs: dict | None = None, **kwargs) -> CalcResult:
        data = dict(inputs or {})
        data.update(kwargs)
        props = self.parameters.get("properties", {})
        unknown = [k for k in data if k not in props]
        if unknown:
            raise CalcInputError(
                f"{self.id}: unknown parameter(s) {unknown}; valid parameters: {sorted(props)}")
        c = Ctx(self, {k: v for k, v in data.items()})
        value = self.run(c)
        if c.missing:
            value = None
        if isinstance(value, float) and self.decimals is not None and math.isfinite(value):
            # keep `decimals` places, but never round a small non-zero value to 0 (keep 6 significant digits)
            value = round(value, self.decimals) if abs(value) >= 10 ** -(self.decimals - 2) else float(f"{value:.6g}")
        return CalcResult(value=value, unit=self.output_unit if value is not None else self.output_unit,
                          steps=c.steps, assumptions=c.assumptions, missing=c.missing)

    def tool_spec(self) -> dict:
        """OpenAI/JSON-schema style function spec for an agent loop."""
        params = _strip_private(self.parameters)
        return {"name": self.id, "description": f"{self.name}. {self.description}", "parameters": params}

    def __repr__(self) -> str:
        return f"<Calculator {self.id} medcalc={self.medcalc_ids}>"


def _strip_private(obj):
    if isinstance(obj, dict):
        return {k: _strip_private(v) for k, v in obj.items() if not k.startswith("x-")}
    if isinstance(obj, list):
        return [_strip_private(v) for v in obj]
    return obj


def schema(required: list[str] | tuple[str, ...] = (), **props: dict) -> dict:
    """Build a JSON-schema object; parameter titles default to their names."""
    return {"type": "object", "properties": props, "required": list(required)}


def points(c: Ctx, total: list, pts: float, text: str) -> None:
    """Add points to a running score and log the step."""
    before = total[0]
    total[0] = before + pts
    if pts:
        c.step(f"{text}: {'+' if pts > 0 else ''}{fmt(pts)} (total {fmt(before)} -> {fmt(total[0])})")
    else:
        c.step(f"{text}: +0 (total {fmt(total[0])})")

