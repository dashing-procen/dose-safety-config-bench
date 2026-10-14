"""Anthropometrics, haemodynamics and renal-function calculators."""

from __future__ import annotations

import math

from .base import SEX, Calculator, Ctx, bparam, eparam, fmt, qparam, schema

CM_PER_IN = 2.54
#: serum creatinine above this (mg/dL) is physically implausible -> CalcInputError (usually a unit error)
SCR_MAX = 40.0


def ideal_body_weight(sex: str, height_cm: float) -> float:
    """Devine (1974): 50 kg (male) / 45.5 kg (female) + 2.3 kg per inch over 60 in."""
    base = 50.0 if sex == "male" else 45.5
    return base + 2.3 * (height_cm / CM_PER_IN - 60.0)


def _ibw_steps(c: Ctx, sex: str, h_cm: float) -> float:
    ibw = ideal_body_weight(sex, h_cm)
    base = 50.0 if sex == "male" else 45.5
    c.step(f"Height {fmt(h_cm)} cm = {fmt(h_cm / CM_PER_IN)} in; IBW (Devine, {sex}) = {fmt(base)} + 2.3 x "
           f"({fmt(h_cm / CM_PER_IN)} - 60) = {fmt(ibw)} kg")
    if h_cm / CM_PER_IN < 60:
        c.assume("height < 60 in: Devine formula extrapolated below its validated range")
    return ibw


class BMI(Calculator):
    id = "bmi"
    name = "Body Mass Index (BMI)"
    medcalc_ids = (6,)
    category = "physical"
    output_unit = "kg/m^2"
    aliases = ("bmi", "body mass index", "quetelet")
    description = "Weight divided by height squared (kg/m^2); classifies under/normal/over-weight and obesity."
    parameters = schema(["weight", "height"],
                        weight=qparam("Body weight.", "mass"), height=qparam("Height.", "length"))

    def run(self, c: Ctx):
        w = c.qty("weight", positive=True)
        h = c.qty("height", positive=True)
        if w is None or h is None:
            return None
        bmi = w / (h / 100) ** 2
        c.step(f"BMI = {fmt(w)} kg / ({fmt(h / 100)} m)^2 = {fmt(bmi)} kg/m^2")
        return bmi


class BSA(Calculator):
    id = "body_surface_area_mosteller"
    name = "Body Surface Area (Mosteller)"
    medcalc_ids = (60,)
    category = "physical"
    output_unit = "m^2"
    aliases = ("bsa", "body surface area", "mosteller")
    description = "Body surface area by the Mosteller formula sqrt(height_cm x weight_kg / 3600); used for drug dosing and indexing."
    parameters = schema(["weight", "height"],
                        weight=qparam("Body weight.", "mass"), height=qparam("Height.", "length"))

    def run(self, c: Ctx):
        w = c.qty("weight", positive=True)
        h = c.qty("height", positive=True)
        if w is None or h is None:
            return None
        bsa = math.sqrt(w * h / 3600.0)
        c.step(f"BSA = sqrt({fmt(h)} cm x {fmt(w)} kg / 3600) = {fmt(bsa)} m^2")
        return bsa


class IdealBodyWeight(Calculator):
    id = "ideal_body_weight_devine"
    name = "Ideal Body Weight (Devine)"
    medcalc_ids = (10,)
    category = "physical"
    output_unit = "kg"
    aliases = ("ibw", "ideal body weight", "devine")
    description = "Ideal body weight by the Devine formula (50/45.5 kg + 2.3 kg per inch above 5 ft); used for dosing and ventilator settings."
    parameters = schema(["sex", "height"], sex=SEX, height=qparam("Height.", "length"))

    def run(self, c: Ctx):
        sex = c.sex()
        h = c.qty("height", positive=True)
        if sex is None or h is None:
            return None
        return _ibw_steps(c, sex, h)


class AdjustedBodyWeight(Calculator):
    id = "adjusted_body_weight"
    name = "Adjusted Body Weight"
    medcalc_ids = (62,)
    category = "physical"
    output_unit = "kg"
    aliases = ("abw", "adjbw", "adjusted body weight", "dosing weight")
    description = "Adjusted body weight = IBW + 0.4 x (actual weight - IBW), IBW by Devine; used for dosing in obesity."
    parameters = schema(["sex", "weight", "height"], sex=SEX,
                        weight=qparam("Actual body weight.", "mass"), height=qparam("Height.", "length"))

    def run(self, c: Ctx):
        sex = c.sex()
        w = c.qty("weight", positive=True)
        h = c.qty("height", positive=True)
        if None in (sex, w, h):
            return None
        ibw = _ibw_steps(c, sex, h)
        abw = ibw + 0.4 * (w - ibw)
        c.step(f"AdjBW = {fmt(ibw)} + 0.4 x ({fmt(w)} - {fmt(ibw)}) = {fmt(abw)} kg")
        return abw


class TargetWeight(Calculator):
    id = "target_weight"
    name = "Target Weight for a Target BMI"
    medcalc_ids = (61,)
    category = "physical"
    output_unit = "kg"
    aliases = ("target weight", "goal weight", "weight for target bmi")
    description = "Body weight that corresponds to a target BMI at the patient's height: target BMI x height(m)^2."
    parameters = schema(["target_bmi", "height"], target_bmi=qparam("Target BMI.", "bmi"),
                        height=qparam("Height.", "length"))

    def run(self, c: Ctx):
        bmi = c.qty("target_bmi", positive=True)
        h = c.qty("height", positive=True)
        if bmi is None or h is None:
            return None
        tw = bmi * (h / 100) ** 2
        c.step(f"Target weight = {fmt(bmi)} kg/m^2 x ({fmt(h / 100)} m)^2 = {fmt(tw)} kg")
        return tw


class MaintenanceFluids(Calculator):
    id = "maintenance_fluids_4_2_1"
    name = "Maintenance Fluids (Holliday-Segar 4-2-1 rule)"
    medcalc_ids = (22,)
    category = "physical"
    output_unit = "mL/hr"
    aliases = ("maintenance fluids", "4-2-1 rule", "holliday segar", "ivf rate", "maintenance iv fluid")
    description = "Hourly maintenance IV fluid rate by weight: 4 mL/kg/h for the first 10 kg, 2 mL/kg/h for the next 10 kg, 1 mL/kg/h above 20 kg."
    parameters = schema(["weight"], weight=qparam("Body weight.", "mass"))

    def run(self, c: Ctx):
        w = c.qty("weight", positive=True)
        if w is None:
            return None
        if w < 10:
            r = 4 * w
            c.step(f"Weight < 10 kg: 4 mL/kg/h x {fmt(w)} kg = {fmt(r)} mL/h")
        elif w <= 20:
            r = 40 + 2 * (w - 10)
            c.step(f"Weight 10-20 kg: 40 + 2 x ({fmt(w)} - 10) = {fmt(r)} mL/h")
        else:
            r = 60 + (w - 20)
            c.step(f"Weight > 20 kg: 60 + 1 x ({fmt(w)} - 20) = {fmt(r)} mL/h")
        return r


class MeanArterialPressure(Calculator):
    id = "mean_arterial_pressure"
    name = "Mean Arterial Pressure (MAP)"
    medcalc_ids = (5,)
    category = "physical"
    output_unit = "mmHg"
    aliases = ("map", "mean arterial pressure", "mean blood pressure")
    description = "MAP = (SBP + 2 x DBP) / 3."
    parameters = schema(["systolic_bp", "diastolic_bp"],
                        systolic_bp=qparam("Systolic blood pressure.", "pressure"),
                        diastolic_bp=qparam("Diastolic blood pressure.", "pressure"))

    def run(self, c: Ctx):
        s = c.qty("systolic_bp", positive=True)
        d = c.qty("diastolic_bp", positive=True)
        if s is None or d is None:
            return None
        m = (s + 2 * d) / 3
        c.step(f"MAP = ({fmt(s)} + 2 x {fmt(d)}) / 3 = {fmt(m)} mmHg")
        return m


def mean_arterial_pressure(sbp: float, dbp: float) -> float:
    return (sbp + 2 * dbp) / 3


class CockcroftGault(Calculator):
    id = "creatinine_clearance_cockcroft_gault"
    name = "Creatinine Clearance (Cockcroft-Gault)"
    medcalc_ids = (2,)
    category = "lab test"
    output_unit = "mL/min"
    aliases = ("crcl", "creatinine clearance", "cockcroft-gault", "cockcroft gault", "cg", "renal dosing")
    description = (
        "Estimated creatinine clearance ((140-age) x weight x [0.85 if female]) / (72 x SCr mg/dL), used for "
        "renal drug dosing. weight_basis='auto' (default, MedCalc convention) picks the weight from BMI: "
        "BMI<18.5 actual weight; 18.5-24.9 min(IBW, actual); >=25 adjusted body weight (IBW+0.4x(actual-IBW)).")
    parameters = schema(
        ["age", "sex", "weight", "creatinine"],
        age=qparam("Age.", "age"), sex=SEX, weight=qparam("Actual body weight.", "mass"),
        height=qparam("Height (needed for IBW/BMI-based weight selection).", "length"),
        creatinine=qparam("Serum creatinine.", "creatinine"),
        weight_basis=eparam("Which weight to use; 'auto' = BMI-based MedCalc convention.",
                            ["auto", "actual", "ideal", "adjusted"]),
    )

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        w = c.qty("weight", positive=True)
        h = c.qty("height", required=False, positive=True)
        scr = c.qty("creatinine", positive=True, hi=SCR_MAX)
        basis = c.enum("weight_basis", default="auto", note="weight_basis not provided: used 'auto' (BMI-based selection)")
        if None in (age, sex, w, scr):
            return None
        if basis != "actual" and h is None:
            c.assume("height not provided: IBW/BMI cannot be computed, so actual body weight was used")
            basis = "actual"
        used = w
        if basis != "actual":
            ibw = _ibw_steps(c, sex, h)
            adj = ibw + 0.4 * (w - ibw)
            if basis == "ideal":
                used = ibw
            elif basis == "adjusted":
                used = adj
                c.step(f"AdjBW = {fmt(ibw)} + 0.4 x ({fmt(w)} - {fmt(ibw)}) = {fmt(adj)} kg")
            else:
                bmi_raw = w / (h / 100) ** 2
                bmi = round(bmi_raw, 1)
                c.step(f"BMI = {fmt(w)} / ({fmt(h / 100)})^2 = {fmt(bmi_raw)} kg/m^2 (classified on {bmi:.1f})")
                if bmi < 18.5:
                    used = w
                    c.assume("used actual body weight because BMI < 18.5 (underweight)")
                elif bmi < 25:
                    used = min(ibw, w)
                    c.assume("used min(IBW, actual weight) because BMI 18.5-24.9 (normal)")
                else:
                    used = adj
                    c.step(f"AdjBW = {fmt(ibw)} + 0.4 x ({fmt(w)} - {fmt(ibw)}) = {fmt(adj)} kg")
                    c.assume("used adjusted body weight because BMI >= 25 (overweight/obese)")
        coef = 0.85 if sex == "female" else 1.0
        crcl = (140 - age) * used * coef / (72 * scr)
        c.step(f"CrCl = (140 - {fmt(age)}) x {fmt(used)} kg x {coef} / (72 x {fmt(scr)}) = {fmt(crcl)} mL/min")
        return crcl


class CKDEPI2021(Calculator):
    id = "egfr_ckd_epi_2021"
    name = "eGFR (CKD-EPI 2021 creatinine, race-free)"
    medcalc_ids = (3,)
    category = "lab test"
    output_unit = "mL/min/1.73 m^2"
    aliases = ("egfr", "ckd-epi", "ckd epi", "gfr", "ckd-epi 2021", "glomerular filtration rate")
    description = "2021 CKD-EPI creatinine equation: 142 x min(SCr/k,1)^a x max(SCr/k,1)^-1.200 x 0.9938^age x 1.012 [female]."
    parameters = schema(["age", "sex", "creatinine"], age=qparam("Age.", "age"), sex=SEX,
                        creatinine=qparam("Serum creatinine.", "creatinine"))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        scr = c.qty("creatinine", positive=True, hi=SCR_MAX)
        if None in (age, sex, scr):
            return None
        k, a, f = (0.7, -0.241, 1.012) if sex == "female" else (0.9, -0.302, 1.0)
        g = 142 * min(scr / k, 1) ** a * max(scr / k, 1) ** -1.200 * 0.9938 ** age * f
        c.step(f"eGFR = 142 x min({fmt(scr)}/{k},1)^{a} x max({fmt(scr)}/{k},1)^-1.200 x 0.9938^{fmt(age)} x {f} = {fmt(g)}")
        if age < 18:
            c.assume("CKD-EPI is validated for adults (age >= 18)")
        return g


class MDRD(Calculator):
    id = "egfr_mdrd"
    name = "eGFR (MDRD, IDMS-traceable 175)"
    medcalc_ids = (9,)
    category = "lab test"
    output_unit = "mL/min/1.73 m^2"
    aliases = ("mdrd", "egfr mdrd", "gfr mdrd", "modification of diet in renal disease")
    description = "4-variable MDRD: 175 x SCr^-1.154 x age^-0.203 x 0.742 [female] x 1.212 [Black]."
    parameters = schema(["age", "sex", "creatinine"], age=qparam("Age.", "age"), sex=SEX,
                        creatinine=qparam("Serum creatinine.", "creatinine"),
                        black_race=bparam("Patient is Black (race coefficient 1.212)."))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        scr = c.qty("creatinine", positive=True, hi=SCR_MAX)
        black = c.flag("black_race", default=False, note="race not provided: race coefficient 1.0 (non-Black)")
        if None in (age, sex, scr):
            return None
        rf = 1.212 if black else 1.0
        sf = 0.742 if sex == "female" else 1.0
        g = 175 * scr ** -1.154 * age ** -0.203 * rf * sf
        c.step(f"eGFR = 175 x {fmt(scr)}^-1.154 x {fmt(age)}^-0.203 x {rf} x {sf} = {fmt(g)}")
        return g


class FreeWaterDeficit(Calculator):
    id = "free_water_deficit"
    name = "Free Water Deficit"
    medcalc_ids = (38,)
    category = "lab test"
    output_unit = "L"
    aliases = ("fwd", "free water deficit", "water deficit", "hypernatremia")
    description = ("Free water deficit = TBW fraction x weight x (Na/140 - 1). TBW fraction: child (<18) 0.6; adult "
                   "male 0.6, female 0.5; elderly (>=65) male 0.5, female 0.45.")
    parameters = schema(["age", "sex", "weight", "sodium"], age=qparam("Age.", "age"), sex=SEX,
                        weight=qparam("Body weight.", "mass"), sodium=qparam("Serum sodium.", "sodium"))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        w = c.qty("weight", positive=True)
        na = c.qty("sodium", positive=True)
        if None in (age, sex, w, na):
            return None
        if age < 18:
            f, grp = 0.6, "child"
        elif age < 65:
            f, grp = (0.6, "adult male") if sex == "male" else (0.5, "adult female")
        else:
            f, grp = (0.5, "elderly male") if sex == "male" else (0.45, "elderly female")
        fwd = f * w * (na / 140 - 1)
        c.step(f"TBW fraction ({grp}) = {f}; FWD = {f} x {fmt(w)} kg x ({fmt(na)}/140 - 1) = {fmt(fwd)} L")
        return fwd


class FENa(Calculator):
    id = "fractional_excretion_sodium"
    name = "Fractional Excretion of Sodium (FENa)"
    medcalc_ids = (40,)
    category = "lab test"
    output_unit = "%"
    aliases = ("fena", "fractional excretion of sodium", "prerenal vs intrinsic aki")
    description = "FENa (%) = (urine Na x serum Cr) / (serum Na x urine Cr) x 100; <1% suggests prerenal AKI."
    parameters = schema(["sodium", "creatinine", "urine_sodium", "urine_creatinine"],
                        sodium=qparam("Serum sodium.", "sodium"),
                        creatinine=qparam("Serum creatinine.", "creatinine"),
                        urine_sodium=qparam("Urine sodium.", "sodium"),
                        urine_creatinine=qparam("Urine creatinine.", "creatinine"))

    def run(self, c: Ctx):
        sna = c.qty("sodium", positive=True)
        scr = c.qty("creatinine", positive=True, hi=SCR_MAX)
        una = c.qty("urine_sodium", lo=0)
        ucr = c.qty("urine_creatinine", positive=True)
        if None in (sna, scr, una, ucr):
            return None
        fe = (una * scr) / (sna * ucr) * 100
        c.step(f"FENa = ({fmt(una)} x {fmt(scr)}) / ({fmt(sna)} x {fmt(ucr)}) x 100 = {fmt(fe)} %")
        return fe


CALCS = [CockcroftGault, CKDEPI2021, MeanArterialPressure, BMI, MDRD, IdealBodyWeight, MaintenanceFluids,
         FreeWaterDeficit, FENa, BSA, TargetWeight, AdjustedBodyWeight]
