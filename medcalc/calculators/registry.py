"""Calculator registry: lookup by id, by MedCalc-Bench calculator id, and keyword/alias search."""

from __future__ import annotations

import re

from . import calcs_body_renal, calcs_labs, calcs_misc, scores_acute, scores_cardio
from .base import Calculator

__all__ = ["CALCULATORS", "get_calculator", "find_calculators", "by_medcalc_id", "MEDCALC_ID_MAP"]

_CLASSES = (calcs_body_renal.CALCS + calcs_labs.CALCS + calcs_misc.CALCS + scores_cardio.CALCS
            + scores_acute.CALCS)

CALCULATORS: dict[str, Calculator] = {}
for _cls in _CLASSES:
    _inst = _cls()
    if _inst.id in CALCULATORS:
        raise RuntimeError(f"duplicate calculator id {_inst.id}")
    CALCULATORS[_inst.id] = _inst

_BY_MEDCALC: dict[int, Calculator] = {}
for _c in CALCULATORS.values():
    for _m in _c.medcalc_ids:
        if _m in _BY_MEDCALC:
            raise RuntimeError(f"MedCalc id {_m} mapped twice")
        _BY_MEDCALC[_m] = _c

#: MedCalc-Bench "Calculator ID" -> our calculator id
MEDCALC_ID_MAP: dict[int, str] = {k: v.id for k, v in sorted(_BY_MEDCALC.items())}


def get_calculator(key: str | int) -> Calculator:
    """By our id (exact), MedCalc id (int or digit string), exact name, or alias (case-insensitive)."""
    if isinstance(key, int) or (isinstance(key, str) and key.strip().isdigit()):
        return by_medcalc_id(int(key))
    if key in CALCULATORS:
        return CALCULATORS[key]
    k = _norm(key)
    for c in CALCULATORS.values():
        if k == _norm(c.id) or k == _norm(c.name) or k in (_norm(a) for a in c.aliases):
            return c
    raise KeyError(f"no calculator {key!r}")


def by_medcalc_id(medcalc_id: int) -> Calculator:
    try:
        return _BY_MEDCALC[int(medcalc_id)]
    except KeyError:
        raise KeyError(f"no calculator for MedCalc id {medcalc_id}") from None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t]


_STOP = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "what", "is", "patient", "patients", "s",
         "score", "calculator", "using", "based", "on", "with", "their", "value", "compute", "calculate"}


def find_calculators(query: str, k: int = 5) -> list[Calculator]:
    """Keyword/alias search. Exact alias/abbreviation matches rank first, then token overlap."""
    qn = _norm(query)
    qt = [t for t in _tokens(query) if t not in _STOP]
    scored: list[tuple[float, int, Calculator]] = []
    for order, c in enumerate(CALCULATORS.values()):
        s = 0.0
        alias_norms = [_norm(a) for a in c.aliases] + [_norm(c.id), _norm(c.name)]
        for a in alias_norms:
            if not a:
                continue
            if qn == a:
                s += 100
            elif len(a) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", _spaced(query)):
                s += 20 + len(a) / 4
        name_t = set(_tokens(c.name)) | set(_tokens(" ".join(c.aliases)))
        desc_t = set(_tokens(c.description))
        for t in qt:
            if t in name_t:
                s += 3
            elif t in desc_t:
                s += 1
        if s > 0:
            scored.append((s, -order, c))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [c for _, _, c in scored[:k]]


def _spaced(q: str) -> str:
    """Query normalised so that alias matching works on squashed tokens ('CHA2DS2-VASc' -> 'cha2ds2vasc')."""
    toks = _tokens(q)
    # include squashed n-grams so multi-token aliases ('curb 65') match
    grams = set()
    for n in range(1, 5):
        for i in range(len(toks) - n + 1):
            grams.add("".join(toks[i:i + n]))
    return " " + " ".join(sorted(grams)) + " "
