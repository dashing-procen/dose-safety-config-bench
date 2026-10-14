"""Laboratory-formula calculators: electrolytes, acid-base, lipids, liver, insulin resistance."""

from __future__ import annotations

import math

from .base import Calculator, Ctx, fmt, qparam, schema


class CalciumCorrection(Calculator):
    id = "calcium_correction_albumin"
    name = "Calcium Correction for Hypoalbuminemia"
    medcalc_ids = (7,)
    category = "lab test"
    output_unit = "mg/dL"
    aliases = ("corrected calcium", "calcium correction", "albumin corrected calcium", "payne")
    description = "Corrected Ca (mg/dL) = measured Ca + 0.8 x (normal albumin - albumin g/dL); normal albumin defaults to 4 g/dL."
    parameters = schema(["calcium", "albumin"], calcium=qparam("Total serum calcium.", "calcium"),
                        albumin=qparam("Serum albumin.", "albumin"),
                        normal_albumin=qparam("Reference ('normal') albumin, default 4 g/dL.", "albumin"))

    def run(self, c: Ctx):
        ca = c.qty("calcium", positive=True)
        alb = c.qty("albumin", positive=True)
        ref = c.qty("normal_albumin", required=False, default=4.0,
                    default_note="normal albumin not provided: used 4.0 g/dL")
        if ca is None or alb is None:
            return None
        v = ca + 0.8 * (ref - alb)
        c.step(f"Corrected Ca = {fmt(ca)} + 0.8 x ({fmt(ref)} - {fmt(alb)}) = {fmt(v)} mg/dL")
        return v


class SodiumCorrection(Calculator):
    id = "sodium_correction_hyperglycemia"
    name = "Sodium Correction for Hyperglycemia (Hillier 1999)"
    medcalc_ids = (26,)
    category = "lab test"
    output_unit = "mEq/L"
    aliases = ("corrected sodium", "sodium correction", "hyperglycemia sodium", "hillier", "pseudohyponatremia")
    description = "Corrected Na = measured Na + 0.024 x (glucose mg/dL - 100) (Hillier 1999, 2.4 mEq/L per 100 mg/dL)."
    parameters = schema(["sodium", "glucose"], sodium=qparam("Serum sodium.", "sodium"),
                        glucose=qparam("Serum glucose.", "glucose"))

    def run(self, c: Ctx):
        na = c.qty("sodium", positive=True)
        glu = c.qty("glucose", positive=True)
        if na is None or glu is None:
            return None
        v = na + 0.024 * (glu - 100)
        c.step(f"Corrected Na = {fmt(na)} + 0.024 x ({fmt(glu)} - 100) = {fmt(v)} mEq/L")
        return v


class SerumOsmolality(Calculator):
    id = "serum_osmolality_calculated"
    name = "Serum Osmolality (calculated)"
    medcalc_ids = (30,)
    category = "lab test"
    output_unit = "mOsm/kg"
    aliases = ("osmolality", "calculated osmolality", "serum osmolality", "osm", "osmolar gap")
    description = "Calculated osmolality = 2 x Na + BUN/2.8 + glucose/18 (mg/dL inputs)."
    parameters = schema(["sodium", "bun", "glucose"], sodium=qparam("Serum sodium.", "sodium"),
                        bun=qparam("Blood urea nitrogen.", "bun"), glucose=qparam("Serum glucose.", "glucose"))

    def run(self, c: Ctx):
        na = c.qty("sodium", positive=True)
        bun = c.qty("bun", lo=0)
        glu = c.qty("glucose", lo=0)
        if None in (na, bun, glu):
            return None
        v = 2 * na + bun / 2.8 + glu / 18
        c.step(f"Osm = 2 x {fmt(na)} + {fmt(bun)}/2.8 + {fmt(glu)}/18 = {fmt(v)} mOsm/kg")
        return v


class HOMAIR(Calculator):
    id = "homa_ir"
    name = "HOMA-IR (Homeostatic Model Assessment of Insulin Resistance)"
    medcalc_ids = (31,)
    category = "lab test"
    output_unit = None
    aliases = ("homa-ir", "homa ir", "homa", "insulin resistance")
    description = "HOMA-IR = fasting insulin (µIU/mL) x fasting glucose (mg/dL) / 405. Insulin pmol/L is converted with 6 pmol/L per µIU/mL."
    parameters = schema(["insulin", "glucose"], insulin=qparam("Fasting insulin.", "insulin"),
                        glucose=qparam("Fasting glucose.", "glucose"))

    def run(self, c: Ctx):
        ins = c.qty("insulin", positive=True)
        glu = c.qty("glucose", positive=True)
        if ins is None or glu is None:
            return None
        v = ins * glu / 405
        c.step(f"HOMA-IR = {fmt(ins)} x {fmt(glu)} / 405 = {fmt(v)}")
        return v


def _anion_gap(c: Ctx):
    na = c.qty("sodium", positive=True)
    cl = c.qty("chloride", positive=True)
    hco3 = c.qty("bicarbonate", positive=True)
    if None in (na, cl, hco3):
        return None, None
    ag = na - (cl + hco3)
    c.step(f"Anion gap = {fmt(na)} - ({fmt(cl)} + {fmt(hco3)}) = {fmt(ag)} mEq/L")
    return ag, hco3


def _albumin_corr(c: Ctx, ag: float | None):
    alb = c.qty("albumin", positive=True)
    if ag is None or alb is None:
        return None
    acag = ag + 2.5 * (4 - alb)
    c.step(f"Albumin-corrected AG = {fmt(ag)} + 2.5 x (4 - {fmt(alb)}) = {fmt(acag)} mEq/L")
    return acag


_AG_PARAMS = dict(sodium=qparam("Serum sodium.", "sodium"), chloride=qparam("Serum chloride.", "chloride"),
                  bicarbonate=qparam("Serum bicarbonate (HCO3-).", "bicarbonate"))
_ALB = dict(albumin=qparam("Serum albumin.", "albumin"))


def _delta_ratio(c: Ctx, gap: float, hco3: float, label: str) -> float | None:
    denom = 24 - hco3
    if denom == 0:
        c.step("24 - HCO3 = 0: delta ratio undefined")
        c.assume("delta ratio undefined because bicarbonate equals 24 mEq/L")
        return None
    v = gap / denom
    c.step(f"{label} = {fmt(gap)} / (24 - {fmt(hco3)}) = {fmt(v)}")
    return v


class AnionGap(Calculator):
    id = "anion_gap"
    name = "Anion Gap"
    medcalc_ids = (39,)
    category = "lab test"
    output_unit = "mEq/L"
    aliases = ("ag", "anion gap", "hagma", "metabolic acidosis")
    description = "Anion gap = Na - (Cl + HCO3)."
    parameters = schema(["sodium", "chloride", "bicarbonate"], **_AG_PARAMS)

    def run(self, c: Ctx):
        return _anion_gap(c)[0]


class DeltaGap(Calculator):
    id = "delta_gap"
    name = "Delta Gap"
    medcalc_ids = (63,)
    category = "lab test"
    output_unit = "mEq/L"
    aliases = ("delta gap", "excess anion gap")
    description = "Delta gap = anion gap - 12 (normal AG)."
    parameters = schema(["sodium", "chloride", "bicarbonate"], **_AG_PARAMS)

    def run(self, c: Ctx):
        ag, _ = _anion_gap(c)
        if ag is None:
            return None
        c.step(f"Delta gap = {fmt(ag)} - 12 = {fmt(ag - 12)} mEq/L")
        return ag - 12


class DeltaRatio(Calculator):
    id = "delta_ratio"
    name = "Delta Ratio"
    medcalc_ids = (64,)
    category = "lab test"
    output_unit = None
    aliases = ("delta ratio", "delta-delta", "delta delta")
    description = "Delta ratio = (anion gap - 12) / (24 - HCO3); separates pure HAGMA from mixed disorders."
    parameters = schema(["sodium", "chloride", "bicarbonate"], **_AG_PARAMS)

    def run(self, c: Ctx):
        ag, hco3 = _anion_gap(c)
        if ag is None:
            return None
        c.step(f"Delta gap = {fmt(ag)} - 12 = {fmt(ag - 12)}")
        return _delta_ratio(c, ag - 12, hco3, "Delta ratio")


class AlbuminCorrectedAG(Calculator):
    id = "albumin_corrected_anion_gap"
    name = "Albumin Corrected Anion Gap"
    medcalc_ids = (65,)
    category = "lab test"
    output_unit = "mEq/L"
    aliases = ("albumin corrected anion gap", "corrected anion gap", "acag")
    description = "Albumin-corrected AG = AG + 2.5 x (4 - albumin g/dL)."
    parameters = schema(["sodium", "chloride", "bicarbonate", "albumin"], **_AG_PARAMS, **_ALB)

    def run(self, c: Ctx):
        ag, _ = _anion_gap(c)
        return _albumin_corr(c, ag)


class AlbuminCorrectedDeltaGap(Calculator):
    id = "albumin_corrected_delta_gap"
    name = "Albumin Corrected Delta Gap"
    medcalc_ids = (66,)
    category = "lab test"
    output_unit = "mEq/L"
    aliases = ("albumin corrected delta gap", "corrected delta gap")
    description = "Albumin-corrected delta gap = albumin-corrected AG - 12."
    parameters = schema(["sodium", "chloride", "bicarbonate", "albumin"], **_AG_PARAMS, **_ALB)

    def run(self, c: Ctx):
        ag, _ = _anion_gap(c)
        acag = _albumin_corr(c, ag)
        if acag is None:
            return None
        c.step(f"Albumin-corrected delta gap = {fmt(acag)} - 12 = {fmt(acag - 12)} mEq/L")
        return acag - 12


class AlbuminCorrectedDeltaRatio(Calculator):
    id = "albumin_corrected_delta_ratio"
    name = "Albumin Corrected Delta Ratio"
    medcalc_ids = (67,)
    category = "lab test"
    output_unit = None
    aliases = ("albumin corrected delta ratio", "corrected delta ratio")
    description = "Albumin-corrected delta ratio = (albumin-corrected AG - 12) / (24 - HCO3)."
    parameters = schema(["sodium", "chloride", "bicarbonate", "albumin"], **_AG_PARAMS, **_ALB)

    def run(self, c: Ctx):
        ag, hco3 = _anion_gap(c)
        acag = _albumin_corr(c, ag)
        if acag is None:
            return None
        c.step(f"Albumin-corrected delta gap = {fmt(acag)} - 12 = {fmt(acag - 12)}")
        return _delta_ratio(c, acag - 12, hco3, "Albumin-corrected delta ratio")


class LDLFriedewald(Calculator):
    id = "ldl_friedewald"
    name = "LDL Cholesterol (Friedewald, calculated)"
    medcalc_ids = (44,)
    category = "lab test"
    output_unit = "mg/dL"
    aliases = ("ldl", "ldl-c", "calculated ldl", "friedewald", "ldl cholesterol")
    description = "LDL = total cholesterol - HDL - triglycerides/5 (mg/dL); unreliable when TG >= 400 mg/dL."
    parameters = schema(["total_cholesterol", "hdl", "triglycerides"],
                        total_cholesterol=qparam("Total cholesterol.", "cholesterol"),
                        hdl=qparam("HDL cholesterol.", "cholesterol"),
                        triglycerides=qparam("Triglycerides.", "triglycerides"))

    def run(self, c: Ctx):
        tc = c.qty("total_cholesterol", positive=True)
        hdl = c.qty("hdl", positive=True)
        tg = c.qty("triglycerides", lo=0)
        if None in (tc, hdl, tg):
            return None
        v = tc - hdl - tg / 5
        c.step(f"LDL = {fmt(tc)} - {fmt(hdl)} - {fmt(tg)}/5 = {fmt(v)} mg/dL")
        if tg >= 400:
            c.assume("triglycerides >= 400 mg/dL: Friedewald estimate is unreliable")
        return v


class FIB4(Calculator):
    id = "fib4_index"
    name = "Fibrosis-4 (FIB-4) Index"
    medcalc_ids = (19,)
    category = "lab test"
    output_unit = None
    aliases = ("fib-4", "fib4", "fibrosis-4", "liver fibrosis")
    description = "FIB-4 = age x AST / (platelets [10^9/L] x sqrt(ALT)); <1.3 low, >2.67 high probability of advanced fibrosis."
    parameters = schema(["age", "ast", "alt", "platelets"], age=qparam("Age.", "age"),
                        ast=qparam("Aspartate aminotransferase.", "enzyme"),
                        alt=qparam("Alanine aminotransferase.", "enzyme"),
                        platelets=qparam("Platelet count.", "cell_count"))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        ast = c.qty("ast", positive=True)
        alt = c.qty("alt", positive=True)
        plt = c.qty("platelets", positive=True)
        if None in (age, ast, alt, plt):
            return None
        v = age * ast / (plt * math.sqrt(alt))
        c.step(f"FIB-4 = {fmt(age)} x {fmt(ast)} / ({fmt(plt)} x sqrt({fmt(alt)})) = {fmt(v)}")
        return v


CALCS = [CalciumCorrection, SodiumCorrection, SerumOsmolality, HOMAIR, AnionGap, DeltaGap, DeltaRatio,
         AlbuminCorrectedAG, AlbuminCorrectedDeltaGap, AlbuminCorrectedDeltaRatio, LDLFriedewald, FIB4]
