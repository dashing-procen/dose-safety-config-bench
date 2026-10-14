"""QT correction, dose conversion and obstetric date calculators."""

from __future__ import annotations

import datetime as _dt

from .base import Calculator, CalcInputError, Ctx, dparam, fmt, parse_quantity, qparam, schema
from . import units as _units

# ----------------------------------------------------------------------------------------
# QTc
# ----------------------------------------------------------------------------------------

_QT_PARAMS = dict(qt_interval=qparam("Measured QT interval.", "duration_ms"),
                  heart_rate=qparam("Heart rate.", "rate_per_min"))


class _QTc(Calculator):
    category = "physical"
    output_unit = "msec"
    parameters = schema(["qt_interval", "heart_rate"], **_QT_PARAMS)

    def formula(self, c: Ctx, qt: float, hr: float, rr: float) -> float:  # pragma: no cover
        raise NotImplementedError

    def run(self, c: Ctx):
        qt = c.qty("qt_interval", positive=True)
        hr = c.qty("heart_rate", positive=True)
        if qt is None or hr is None:
            return None
        rr = 60.0 / hr
        c.step(f"RR interval = 60 / {fmt(hr)} = {fmt(rr)} s")
        return self.formula(c, qt, hr, rr)


class QTcBazett(_QTc):
    id = "qtc_bazett"
    name = "QTc (Bazett)"
    medcalc_ids = (11,)
    aliases = ("qtc", "qtc bazett", "bazett", "corrected qt")
    description = "Heart-rate corrected QT by Bazett: QT / sqrt(RR seconds)."

    def formula(self, c, qt, hr, rr):
        v = qt / rr ** 0.5
        c.step(f"QTc = {fmt(qt)} / sqrt({fmt(rr)}) = {fmt(v)} msec")
        return v


class QTcFridericia(_QTc):
    id = "qtc_fridericia"
    name = "QTc (Fridericia)"
    medcalc_ids = (56,)
    aliases = ("qtc fridericia", "fridericia", "qtcf")
    description = "Heart-rate corrected QT by Fridericia: QT / RR^(1/3)."

    def formula(self, c, qt, hr, rr):
        v = qt / rr ** (1 / 3)
        c.step(f"QTc = {fmt(qt)} / {fmt(rr)}^(1/3) = {fmt(v)} msec")
        return v


class QTcFramingham(_QTc):
    id = "qtc_framingham"
    name = "QTc (Framingham / Sagie)"
    medcalc_ids = (57,)
    aliases = ("qtc framingham", "sagie", "framingham qtc")
    description = "Heart-rate corrected QT by the Framingham linear formula: QT + 154 x (1 - RR seconds)."

    def formula(self, c, qt, hr, rr):
        v = qt + 154 * (1 - rr)
        c.step(f"QTc = {fmt(qt)} + 154 x (1 - {fmt(rr)}) = {fmt(v)} msec")
        return v


class QTcHodges(_QTc):
    id = "qtc_hodges"
    name = "QTc (Hodges)"
    medcalc_ids = (58,)
    aliases = ("qtc hodges", "hodges")
    description = "Heart-rate corrected QT by Hodges: QT + 1.75 x (HR - 60)."

    def formula(self, c, qt, hr, rr):
        v = qt + 1.75 * (hr - 60)
        c.step(f"QTc = {fmt(qt)} + 1.75 x ({fmt(hr)} - 60) = {fmt(v)} msec")
        return v


class QTcRautaharju(_QTc):
    id = "qtc_rautaharju"
    name = "QTc (Rautaharju)"
    medcalc_ids = (59,)
    aliases = ("qtc rautaharju", "rautaharju")
    description = "Heart-rate corrected QT by Rautaharju: QT x (120 + HR) / 180."

    def formula(self, c, qt, hr, rr):
        v = qt * (120 + hr) / 180
        c.step(f"QTc = {fmt(qt)} x (120 + {fmt(hr)}) / 180 = {fmt(v)} msec")
        return v


# ----------------------------------------------------------------------------------------
# steroid conversion
# ----------------------------------------------------------------------------------------

# Glucocorticoid-equivalent doses (mg) — standard anti-inflammatory equivalence tables.
STEROID_EQUIV_MG = {
    "betamethasone": 0.75, "cortisone": 25.0, "dexamethasone": 0.75, "hydrocortisone": 20.0,
    "methylprednisolone": 4.0, "prednisolone": 5.0, "prednisone": 5.0, "triamcinolone": 4.0,
}
_ROUTES = ("PO", "IV", "IM")


def _steroid(name: str, field: str) -> str:
    s = name.lower().replace("-", "").replace(" ", "")
    for r in _ROUTES:
        if s.endswith(r.lower()):
            s = s[: -len(r)]
    s = s.replace("(decadron)", "").replace("decadron", "dexamethasone")
    if s not in STEROID_EQUIV_MG:
        raise CalcInputError(f"{field}: unknown corticosteroid {name!r}; known: {sorted(STEROID_EQUIV_MG)}")
    return s


class SteroidConversion(Calculator):
    id = "steroid_conversion"
    name = "Corticosteroid Dose Conversion"
    medcalc_ids = (24,)
    category = "dosage"
    output_unit = "mg"
    aliases = ("steroid conversion", "corticosteroid equivalence", "prednisone equivalent", "glucocorticoid conversion")
    description = ("Equivalent dose of a target corticosteroid. Equivalent doses (mg): betamethasone 0.75, cortisone 25, "
                   "dexamethasone 0.75, hydrocortisone 20, methylprednisolone 4, prednisolone 5, prednisone 5, "
                   "triamcinolone 4. Route (PO/IV) suffixes are accepted and do not change the equivalence.")
    parameters = schema(["input_steroid", "dose", "target_steroid"],
                        input_steroid={"type": "string", "description": "Source steroid, e.g. 'Prednisone PO'."},
                        dose=qparam("Dose of the source steroid.", "drug_mass"),
                        target_steroid={"type": "string", "description": "Target steroid, e.g. 'Dexamethasone IV'."})

    def run(self, c: Ctx):
        src = c.inputs.get("input_steroid")
        tgt = c.inputs.get("target_steroid")
        dose = c.qty("dose", lo=0)
        if src is None:
            c._need("input_steroid")
        if tgt is None:
            c._need("target_steroid")
        if None in (src, tgt, dose):
            return None
        a, b = _steroid(str(src), "input_steroid"), _steroid(str(tgt), "target_steroid")
        ea, eb = STEROID_EQUIV_MG[a], STEROID_EQUIV_MG[b]
        v = dose / ea * eb
        c.step(f"{src} {fmt(ea)} mg ~ {tgt} {fmt(eb)} mg; {fmt(dose)} mg / {fmt(ea)} x {fmt(eb)} = {fmt(v)} mg")
        return v


# ----------------------------------------------------------------------------------------
# morphine milligram equivalents
# ----------------------------------------------------------------------------------------

# CDC Clinical Practice Guideline for Prescribing Opioids (2022) conversion factors (MME per mg);
# fentanyl buccal/sublingual per µg (CDC 2016 table), transdermal fentanyl per µg/hr.
MME_FACTORS = {
    "codeine": (0.15, "mg"), "fentanyl_buccal": (0.13, "ug"), "fentanyl_transdermal": (2.4, "ug/hr"),
    "hydrocodone": (1.0, "mg"), "hydromorphone": (5.0, "mg"), "methadone": (4.7, "mg"),
    "morphine": (1.0, "mg"), "oxycodone": (1.5, "mg"), "oxymorphone": (3.0, "mg"),
    "tapentadol": (0.4, "mg"), "tramadol": (0.2, "mg"), "buprenorphine": (10.0, "mg"),
}
_DRUG_ALIASES = {"fentanylbuccal": "fentanyl_buccal", "fentanyl buccal": "fentanyl_buccal",
                 "fentanylpatch": "fentanyl_transdermal", "fentanyltransdermal": "fentanyl_transdermal",
                 "fentanyl": "fentanyl_buccal"}


def _opioid(name: str) -> str:
    s = str(name).lower().strip()
    key = s.replace(" ", "_")
    if key in MME_FACTORS:
        return key
    k2 = s.replace(" ", "").replace("_", "")
    if k2 in _DRUG_ALIASES:
        return _DRUG_ALIASES[k2]
    raise CalcInputError(f"opioids: unknown drug {name!r}; known: {sorted(MME_FACTORS)}")


class MME(Calculator):
    id = "morphine_milligram_equivalents"
    name = "Morphine Milligram Equivalents (MME/day)"
    medcalc_ids = (49,)
    category = "dosage"
    output_unit = "MME/day"
    aliases = ("mme", "morphine equivalents", "morphine milligram equivalent", "opioid conversion", "omed")
    description = ("Total daily MME = sum over opioids of dose x doses/day x CDC conversion factor (codeine 0.15, "
                   "fentanyl buccal 0.13/µg, fentanyl patch 2.4 per µg/hr, hydrocodone 1, hydromorphone 5, methadone 4.7, "
                   "morphine 1, oxycodone 1.5, oxymorphone 3, tapentadol 0.4, tramadol 0.2, buprenorphine 10).")
    parameters = schema(["opioids"], opioids={
        "type": "array",
        "description": "One entry per opioid. dose in mg (fentanyl buccal in µg; fentanyl patch in µg/hr).",
        "items": {"type": "object", "properties": {
            "drug": {"type": "string", "enum": sorted(MME_FACTORS)},
            "dose": {"type": "object", "properties": {"value": {"type": "number"}, "unit": {"type": "string"}}},
            "doses_per_day": {"type": "number"}},
            "required": ["drug", "dose", "doses_per_day"]}})

    def run(self, c: Ctx):
        items = c.inputs.get("opioids")
        if not items:
            c._need("opioids")
            return None
        if not isinstance(items, list):
            raise CalcInputError("opioids: expected a list of {drug, dose, doses_per_day}")
        total = 0.0
        for i, it in enumerate(items):
            if not isinstance(it, dict) or "drug" not in it:
                raise CalcInputError(f"opioids[{i}]: expected an object with drug, dose, doses_per_day")
            drug = _opioid(it["drug"])
            factor, unit = MME_FACTORS[drug]
            if it.get("dose") is None:
                c._need(f"opioids[{i}].dose")
                continue
            if it.get("doses_per_day") is None:
                c._need(f"opioids[{i}].doses_per_day")
                continue
            v, u = parse_quantity(it["dose"], f"opioids[{i}].dose")
            nu = _units.normalize_unit(u)
            if unit == "mg":
                if nu in ("", "mg"):
                    dose = v
                elif nu == "ug":
                    dose = v / 1000
                elif nu == "g":
                    dose = v * 1000
                else:
                    raise CalcInputError(f"opioids[{i}].dose: unit {u!r} not accepted (mg, mcg, g)")
            elif unit == "ug":
                if nu in ("", "ug"):
                    dose = v
                elif nu == "mg":
                    dose = v * 1000
                else:
                    raise CalcInputError(f"opioids[{i}].dose: unit {u!r} not accepted (µg, mg)")
            else:
                if nu not in ("", "ug/hr", "ug/h"):
                    raise CalcInputError(f"opioids[{i}].dose: fentanyl patch dose must be in µg/hr")
                dose = v
            try:
                n = float(it["doses_per_day"][0] if isinstance(it["doses_per_day"], (list, tuple)) else it["doses_per_day"])
            except (TypeError, ValueError):
                raise CalcInputError(f"opioids[{i}].doses_per_day: expected a number") from None
            if dose < 0 or n < 0:
                raise CalcInputError(f"opioids[{i}]: negative dose or frequency")
            mme = dose * n * factor
            if unit == "ug/hr":
                mme = dose * factor
                c.step(f"{drug}: {fmt(dose)} µg/hr x {factor} = {fmt(mme)} MME/day")
            else:
                c.step(f"{drug}: {fmt(dose)} {unit} x {fmt(n)}/day x {factor} = {fmt(mme)} MME/day")
            total += mme
        c.step(f"Total = {fmt(total)} MME/day")
        if any(_opioid(it.get('drug')) == "methadone" for it in items if isinstance(it, dict)):
            c.assume("methadone uses the CDC 2022 single factor 4.7; true equianalgesia is dose-dependent")
        return total


# ----------------------------------------------------------------------------------------
# obstetric dates
# ----------------------------------------------------------------------------------------

def _mdy(d: _dt.date) -> str:
    return d.strftime("%m/%d/%Y")


class DueDate(Calculator):
    id = "estimated_due_date"
    name = "Estimated Due Date (Naegele's rule, cycle-adjusted)"
    medcalc_ids = (13,)
    category = "date"
    output_unit = "date (MM/DD/YYYY)"
    decimals = None
    aliases = ("edd", "due date", "naegele", "estimated date of delivery", "edc")
    description = "EDD = LMP + 280 days + (cycle length - 28) days. Returns 'MM/DD/YYYY'."
    parameters = schema(["last_menstrual_period"], last_menstrual_period=dparam("First day of last menstrual period."),
                        cycle_length=qparam("Menstrual cycle length (default 28 days).", "days"))

    def run(self, c: Ctx):
        lmp = c.date("last_menstrual_period")
        cyc = c.qty("cycle_length", required=False, default=28.0, lo=10, hi=90,
                    default_note="cycle length not provided: assumed 28 days")
        if lmp is None:
            return None
        base = lmp + _dt.timedelta(days=280)
        adj = int(round(cyc - 28))
        edd = base + _dt.timedelta(days=adj)
        c.step(f"LMP {_mdy(lmp)} + 280 days = {_mdy(base)}; cycle adjustment {adj:+d} days -> {_mdy(edd)}")
        return _mdy(edd)


class ConceptionDate(Calculator):
    id = "estimated_conception_date"
    name = "Estimated Date of Conception"
    medcalc_ids = (68,)
    category = "date"
    output_unit = "date (MM/DD/YYYY)"
    decimals = None
    aliases = ("conception date", "date of conception", "estimated conception")
    description = "Estimated conception = LMP + 14 days (assumes 28-day cycle). Returns 'MM/DD/YYYY'."
    parameters = schema(["last_menstrual_period"], last_menstrual_period=dparam("First day of last menstrual period."))

    def run(self, c: Ctx):
        lmp = c.date("last_menstrual_period")
        if lmp is None:
            return None
        d = lmp + _dt.timedelta(days=14)
        c.step(f"LMP {_mdy(lmp)} + 14 days = {_mdy(d)}")
        c.assume("ovulation assumed on day 14 (28-day cycle)")
        return _mdy(d)


class GestationalAge(Calculator):
    id = "gestational_age_lmp"
    name = "Estimated Gestational Age (by LMP)"
    medcalc_ids = (69,)
    category = "date"
    output_unit = "(weeks, days)"
    decimals = None
    aliases = ("gestational age", "ga", "weeks pregnant", "pregnancy dating")
    description = "Gestational age = current date - LMP, returned as a (weeks, days) tuple of ints."
    parameters = schema(["last_menstrual_period", "current_date"],
                        last_menstrual_period=dparam("First day of last menstrual period."),
                        current_date=dparam("Date of assessment."))

    def run(self, c: Ctx):
        lmp = c.date("last_menstrual_period")
        cur = c.date("current_date")
        if lmp is None or cur is None:
            return None
        days = (cur - lmp).days
        if days < 0:
            raise CalcInputError("current_date is before last_menstrual_period")
        w, d = divmod(days, 7)
        c.step(f"{_mdy(cur)} - {_mdy(lmp)} = {days} days = {w} weeks {d} days")
        return (w, d)


CALCS = [QTcBazett, QTcFridericia, QTcFramingham, QTcHodges, QTcRautaharju, SteroidConversion, MME,
         DueDate, ConceptionDate, GestationalAge]

