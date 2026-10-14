#!/usr/bin/env python3
"""Validate the calculator library against MedCalc-Bench Verified TRAIN rows.

For every train row: Relevant Entities (gold extracted inputs) -> explicit key mapping below ->
calculator.compute() -> compare with the gold answer:
  decimal  correct if Lower Limit <= value <= Upper Limit
  integer  exact numeric equality
  date     exact 'MM/DD/YYYY' string; gestational age exact (weeks, days)

ONLY train_data.csv is read. test_data.csv is never opened by this script.

Outputs (next to this file):
  calculator_validation.json   per-calculator n/correct/%, disagreements, suspected label errors, id map
  calculator_validation.md     short human summary

Usage:  python medcalc/validate_calculators.py --train path/to/MedCalc-Bench-Verified/train_data.csv
Data: MedCalc-Bench Verified (CC-BY-SA 4.0).
"""

from __future__ import annotations

import argparse
import ast
import collections
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calculators import CalcInputError, by_medcalc_id, MEDCALC_ID_MAP  # noqa: E402

csv.field_size_limit(sys.maxsize)

# ------------------------------------------------------------------------------------------
# Explicit key mapping: MedCalc "Relevant Entities" key -> our parameter name, per calculator.
# Keys mapped to None are deliberately dropped (documented reason in DROPPED_KEYS).
# ------------------------------------------------------------------------------------------

COMMON = {"age": "age", "sex": "sex", "weight": "weight", "height": "height", "creatinine": "creatinine"}

KEYMAP: dict[int, dict[str, str | None]] = {
    2: dict(COMMON),
    3: dict(COMMON),
    4: {"age": "age", "sex": "sex", "Congestive Heart Failure": "chf", "Hypertension history": "hypertension",
        "Diabetes history": "diabetes", "Stroke": "stroke", "Transient Ischemic Attacks History": "tia",
        "Thromboembolism history": "thromboembolism", "Vascular disease history": "vascular_disease"},
    5: {"Systolic Blood Pressure": "systolic_bp", "Diastolic Blood Pressure": "diastolic_bp"},
    6: {"weight": "weight", "height": "height"},
    7: {"Calcium": "calcium", "Albumin": "albumin"},
    8: {"Clinical signs and symptoms of Deep Vein Thrombosis": "dvt_signs",
        "Pulmonary Embolism is #1 diagnosis OR equally likely": "pe_most_likely",
        "Heart Rate or Pulse": "heart_rate", "Immobilization for at least 3 days": "immobilization",
        "Surgery in the previous 4 weeks": "recent_surgery",
        "Previously Documented Pulmonary Embolism": "previous_pe",
        "Previously documented Deep Vein Thrombosis": "previous_dvt", "Hemoptysis": "hemoptysis",
        "Malignancy with treatment within 6 months or palliative": "malignancy"},
    9: {"age": "age", "sex": "sex", "creatinine": "creatinine", "Race": "black_race"},
    10: {"sex": "sex", "height": "height"},
    11: {"QT Interval": "qt_interval", "Heart Rate or Pulse": "heart_rate"},
    13: {"Last menstrual date": "last_menstrual_period", "cycle length": "cycle_length"},
    15: {"Bilirubin": "bilirubin", "Albumin": "albumin", "international normalized ratio": "inr",
         "Ascites": "ascites", "Encephalopathy": "encephalopathy"},
    16: {"Active cancer": "active_cancer", "Bedridden recently >3 days": "bedridden",
         "Major surgery within 12 weeks": "major_surgery",
         "Calf swelling >3 centimeters compared to the other leg": "calf_swelling",
         "Collateral (nonvaricose) superficial veins present": "collateral_veins",
         "Entire Leg Swollen": "entire_leg_swollen",
         "Localized tenderness along the deep venous system": "localized_tenderness",
         "Pitting edema, confined to symptomatic leg": "pitting_edema",
         "Paralysis, paresis, or recent plaster immobilization of the lower extremity": "paralysis_or_cast",
         "Previously documented Deep Vein Thrombosis": "previous_dvt",
         "Alternative diagnosis to Deep Vein Thrombosis as likely or more likely": "alternative_diagnosis"},
    17: {"Elevated-risk surgery": "high_risk_surgery", "History of ischemic heart disease": "ischemic_heart_disease",
         "Congestive Heart Failure criteria for the Cardiac Risk Index rule": "chf",
         "History of cerebrovascular disease": "cerebrovascular_disease",
         "Pre-operative treatment with insulin": "insulin", "Pre-operative creatinine": "creatinine"},
    18: {"age": "age", "Suspicion History": "history", "Electrocardiogram Test": "ecg", "Initial troponin": "troponin",
         "Hypertension history": "hypertension", "hypercholesterolemia": "hypercholesterolemia",
         "Diabetes mellitus": "diabetes", "obesity": "obesity", "smoking": "smoking",
         "parent or sibling with Cardiovascular disease before age 65": "family_history",
         "atherosclerotic disease": "atherosclerotic_disease",
         # MDCalc HEART lists prior CVA/TIA under atherosclerotic disease
         "Transient Ischemic Attacks History": "_tia_as_atherosclerotic"},
    19: {"age": "age", "Aspartate aminotransferase": "ast", "Alanine aminotransferase": "alt",
         "Platelet count": "platelets"},
    20: {"age": "age", "Exudate or swelling on tonsils": "tonsillar_exudate",
         "Tender/swollen anterior cervical lymph nodes": "anterior_cervical_nodes", "Temperature": "temperature",
         "Cough Absent": "cough_absent"},
    21: {"Best eye response": "eye", "Best verbal response": "verbal", "Best motor response": "motor"},
    22: {"weight": "weight"},
    23: {"creatinine": "creatinine", "Bilirubin": "bilirubin", "international normalized ratio": "inr",
         "Sodium": "sodium", "Dialysis at least twice in the past week": "dialysis_twice_past_week",
         "Continuous veno-venous hemodialysis for ≥24 hours in the past week": "cvvhd_24h_past_week"},
    24: {"input steroid": "_steroid", "target steroid": "target_steroid"},
    25: {"age": "age", "Hypertension": "hypertension", "Renal disease criteria for the HAS-BLED rule": "renal_disease",
         "Liver disease criteria for the HAS-BLED rule": "liver_disease", "Stroke": "stroke",
         "Prior major bleeding or predisposition to bleeding": "prior_bleeding",
         "Labile international normalized ratio": "labile_inr",
         "Medication usage predisposing to bleeding": "bleeding_medication",
         "Number of Alcoholic Drinks Per Week": "alcohol_drinks_per_week"},
    26: {"Sodium": "sodium", "Glucose": "glucose"},
    27: {"Blood Urea Nitrogen (BUN)": "bun", "Hemoglobin": "hemoglobin", "sex": "sex",
         "Systolic Blood Pressure": "systolic_bp", "Heart Rate or Pulse": "heart_rate", "Melena Present": "melena",
         "Recent Syncope": "syncope", "Hepatic disease history": "hepatic_disease",
         "Cardiac Failure Present": "cardiac_failure"},
    28: {"age": "age", "Temperature": "temperature", "Systolic Blood Pressure": "systolic_bp",
         "Diastolic Blood Pressure": "diastolic_bp", "Heart Rate or Pulse": "heart_rate",
         "respiratory rate": "respiratory_rate", "FiO2": "fio2", "PaO2": "pao2", "A-a gradient": "aa_gradient",
         "pH": "ph", "Sodium": "sodium", "Potassium": "potassium", "creatinine": "creatinine",
         "Acute renal failure": "acute_renal_failure", "Chronic renal failure": None,
         "Hematocrit": "hematocrit", "White blood cell count": "wbc", "Glasgow Coma Score": "gcs",
         "History of severe organ failure or immunocompromise": "chronic_health", "Surgery Type": "admission_type"},
    29: {"age": "age", "sex": "sex", "Nursing home resident": "nursing_home", "Neoplastic disease": "neoplastic_disease",
         "Liver disease history": "liver_disease", "Congestive Heart Failure": "chf",
         "Cerebrovascular disease history": "cerebrovascular_disease", "Renal disease history": "renal_disease",
         "Altered mental status": "altered_mental_status", "Pleural effusion on x-ray": "pleural_effusion",
         "respiratory rate": "respiratory_rate", "Systolic Blood Pressure": "systolic_bp",
         "Temperature": "temperature", "Heart Rate or Pulse": "heart_rate", "pH": "ph",
         "Blood Urea Nitrogen (BUN)": "bun", "Sodium": "sodium", "Glucose": "glucose", "Hematocrit": "hematocrit",
         "Partial pressure of oxygen": "pao2"},
    30: {"Sodium": "sodium", "Blood Urea Nitrogen (BUN)": "bun", "Glucose": "glucose"},
    31: {"Insulin": "insulin", "Glucose": "glucose"},
    32: {"age": "age", "Myocardial infarction": "myocardial_infarction", "Congestive Heart Failure": "chf",
         "Peripheral vascular disease": "peripheral_vascular_disease",
         "Cerebrovascular Accident": "cerebrovascular_accident", "Transient Ischemic Attacks History": "tia",
         "Dementia": "dementia", "Chronic Pulmonary Disease": "chronic_pulmonary_disease",
         "Connective tissue disease": "connective_tissue_disease", "Peptic ulcer disease": "peptic_ulcer_disease",
         "Liver disease severity": "liver_disease", "Diabetes mellitus": "diabetes", "Hemiplegia": "hemiplegia",
         "Moderate to severe Chronic Kidney Disease": "moderate_severe_ckd", "Solid tumor": "solid_tumor",
         "Leukemia": "leukemia", "Lymphoma": "lymphoma", "AIDS": "aids"},
    33: {"Fever in past 24 hours": "fever_past_24h", "Purulent tonsils": "purulent_tonsils",
         "Symptom onset <=3 days": "onset_within_3_days", "Severe tonsil inflammation": "severe_tonsil_inflammation",
         "Absence of cough or coryza": "no_cough_or_coryza"},
    36: {"age": "age", "sex": "sex", "Surgery Type": "surgery_type", "Mobility": "mobility",
         "Body Mass Index (BMI)": "bmi",
         "Major Surgery in the last month": "recent_major_surgery",
         "Congestive Heart Failure in the last month": "recent_chf", "Sepsis in the last month": "recent_sepsis",
         "Pneumonia in the last month": "recent_pneumonia",
         "Immobilizing plaster cast in the last month": "recent_plaster_cast",
         "Hip, pelvis, or leg fracture in the last month": "recent_fracture",
         "Stroke in the last month": "recent_stroke", "Multiple trauma in the last month": "recent_multiple_trauma",
         "Acute spinal cord injury causing paralysis in the last month": "recent_spinal_cord_injury",
         "Varicose veins": "varicose_veins", "Current swollen legs": "swollen_legs",
         "Current central venous access": "central_venous_access",
         "Previously documented Deep Vein Thrombosis": "previous_dvt",
         "Previously Documented Pulmonary Embolism": "previous_pe",
         "Family history of thrombosis": "family_history_thrombosis", "Positive Factor V Leiden": "factor_v_leiden",
         "Positive prothrombin 20210A": "prothrombin_20210a", "Elevated serum homocysteine": "elevated_homocysteine",
         "Positive lupus anticoagulant": "lupus_anticoagulant",
         "Elevated anticardiolipin antibody": "anticardiolipin_antibody",
         "Heparin-induced thrombocytopenia": "heparin_induced_thrombocytopenia",
         "Other congenital or acquired thrombophilia": "other_thrombophilia",
         "History of inflammatory bowel disease": "inflammatory_bowel_disease",
         "Acute Myocardial infarction": "acute_mi", "Chronic Obstructive Pulmonary Disease": "copd",
         "Present or previous malignancy": "malignancy"},
    38: {"age": "age", "sex": "sex", "weight": "weight", "Sodium": "sodium"},
    39: {"Sodium": "sodium", "Chloride": "chloride", "Bicarbonate": "bicarbonate"},
    40: {"Sodium": "sodium", "creatinine": "creatinine", "Urine sodium": "urine_sodium",
         "Urine creatinine": "urine_creatinine"},
    43: {"PaO2": "pao2", "FiO2": "fio2", "On mechanical ventilation": "mechanical_ventilation",
         "Continuous positive airway pressure": "cpap", "Platelet count": "platelets", "Glasgow Coma Score": "gcs",
         "Bilirubin": "bilirubin", "Systolic Blood Pressure": "systolic_bp",
         "Diastolic Blood Pressure": "diastolic_bp", "DOPamine": "dopamine", "DOBUTamine": "dobutamine",
         "creatinine": "creatinine", "Urine Output": "urine_output", "Hypotension": None},
    44: {"Total cholesterol": "total_cholesterol", "high-density lipoprotein cholesterol": "hdl",
         "Triglycerides": "triglycerides"},
    45: {"age": "age", "Confusion": "confusion", "Blood Urea Nitrogen (BUN)": "bun",
         "respiratory rate": "respiratory_rate", "Systolic Blood Pressure": "systolic_bp",
         "Diastolic Blood Pressure": "diastolic_bp"},
    46: {"age": "age", "sex": "sex", "Smoker": "smoker", "Total cholesterol": "total_cholesterol",
         "high-density lipoprotein cholesterol": "hdl", "Systolic Blood Pressure": "systolic_bp",
         "Blood pressure being treated with medicines": "bp_treated"},
    48: {"age": "age", "Heart Rate or Pulse": "heart_rate", "O₂ saturation percentage": "oxygen_saturation",
         "Unilateral Leg Swelling": "unilateral_leg_swelling", "Hemoptysis": "hemoptysis",
         "Recent surgery or trauma": "recent_surgery_or_trauma",
         "Previously Documented Pulmonary Embolism": "previous_pe",
         "Previously documented Deep Vein Thrombosis": "previous_dvt", "Hormone use": "hormone_use"},
    49: {},  # handled by _map_mme
    51: {"Temperature": "temperature", "Heart Rate or Pulse": "heart_rate", "respiratory rate": "respiratory_rate",
         "PaCO2": "paco2", "White blood cell count": "wbc"},
    56: {"QT Interval": "qt_interval", "Heart Rate or Pulse": "heart_rate"},
    57: {"QT Interval": "qt_interval", "Heart Rate or Pulse": "heart_rate"},
    58: {"QT Interval": "qt_interval", "Heart Rate or Pulse": "heart_rate"},
    59: {"QT Interval": "qt_interval", "Heart Rate or Pulse": "heart_rate"},
    60: {"weight": "weight", "height": "height"},
    61: {"Body Mass Index (BMI)": "target_bmi", "height": "height"},
    62: {"sex": "sex", "weight": "weight", "height": "height"},
    63: {"Sodium": "sodium", "Chloride": "chloride", "Bicarbonate": "bicarbonate"},
    64: {"Sodium": "sodium", "Chloride": "chloride", "Bicarbonate": "bicarbonate"},
    65: {"Sodium": "sodium", "Chloride": "chloride", "Bicarbonate": "bicarbonate", "Albumin": "albumin"},
    66: {"Sodium": "sodium", "Chloride": "chloride", "Bicarbonate": "bicarbonate", "Albumin": "albumin"},
    67: {"Sodium": "sodium", "Chloride": "chloride", "Bicarbonate": "bicarbonate", "Albumin": "albumin"},
    68: {"Last menstrual date": "last_menstrual_period"},
    69: {"Last menstrual date": "last_menstrual_period", "Current Date": "current_date"},
}

DROPPED_KEYS = {
    (28, "Chronic renal failure"): "APACHE II creatinine points do not depend on chronic renal failure; only "
                                   "acute renal failure doubles them.",
    (43, "Hypotension"): "Not a SOFA criterion; the cardiovascular component is scored from MAP and vasopressor doses.",
}

APACHE_ADMISSION = {"emergency": "emergency postoperative", "elective": "elective postoperative",
                    "nonoperative": "nonoperative"}

_MME_DRUGS = {"HYDROcodone": "hydrocodone", "HYDROmorphone": "hydromorphone", "TraMADol": "tramadol",
              "Morphine": "morphine", "OxyCODONE": "oxycodone", "OxyMORphone": "oxymorphone", "Codeine": "codeine",
              "Methadone": "methadone", "Tapentadol": "tapentadol", "FentaNYL buccal": "fentanyl_buccal",
              "FentANYL patch": "fentanyl_transdermal", "Buprenorphine": "buprenorphine"}


def _repair_unit(v):
    """Repair a corrupted micro sign seen in a few rows ('\\x0b5IU/mL', '\\x00b5IU/mL' == 'µIU/mL')."""
    if isinstance(v, list) and len(v) == 2 and isinstance(v[1], str):
        u = v[1]
        if u.endswith("IU/mL") and u not in ("µIU/mL", "mIU/mL") and any(ord(ch) < 32 for ch in u):
            return [v[0], "µIU/mL"]
    return v


def _map_mme(ents: dict) -> dict:
    items = []
    for label, drug in _MME_DRUGS.items():
        d = ents.get(f"{label} Dose")
        n = ents.get(f"{label} Dose Per Day")
        if d is None and n is None:
            continue
        items.append({"drug": drug, "dose": {"value": d[0], "unit": d[1]} if d else None,
                      "doses_per_day": n[0] if isinstance(n, list) else n})
    return {"opioids": items}


def map_inputs(cid: int, ents: dict) -> dict:
    if cid == 49:
        return _map_mme(ents)
    km = KEYMAP[cid]
    out: dict = {}
    for k, v in ents.items():
        if k not in km:
            raise KeyError(f"calculator {cid}: unmapped Relevant Entities key {k!r}")
        p = km[k]
        if p is None:
            continue
        v = _repair_unit(v)
        if p == "black_race":
            out[p] = str(v).strip().lower() == "black"
        elif p == "_steroid":
            out["input_steroid"], out["dose"] = v[0], [v[1], v[2]]
        elif p == "_tia_as_atherosclerotic":
            out["atherosclerotic_disease"] = bool(out.get("atherosclerotic_disease")) or bool(v)
        elif p == "atherosclerotic_disease":
            out[p] = bool(out.get(p)) or bool(v)
        elif p == "admission_type":
            out[p] = APACHE_ADMISSION.get(str(v).lower(), v)
        elif cid == 36 and p == "surgery_type":
            out[p] = str(v).lower()
        else:
            out[p] = v
    if cid == 28 and "admission_type" in out and not out.get("chronic_health"):
        out.pop("admission_type")
    return out


# ------------------------------------------------------------------------------------------
# Suspected gold-label errors (row number -> reasoning), established by reading the TRAIN
# Ground Truth Explanation of each disagreeing row. Filled in after inspection.
# ------------------------------------------------------------------------------------------
SUSPECTED_LABEL_ERRORS: dict[int, str] = {
    10130: "Dialysis >= 2x in the past week is True, so UNOS sets creatinine to 4.0 mg/dL; the gold explanation "
           "states the dialysis, then contradicts itself ('reported to not have done dialysis') and floors Cr at 1.0.",
    10174: "Dialysis >= 2x in the past week is True, so UNOS sets creatinine to 4.0 mg/dL; the gold explanation "
           "ignores it and floors Cr at 1.0.",
    10533: "Gold explanation computes MAP = 69.67 mmHg and then states it is 'at least 70 mmHg' (0 points); APACHE II "
           "gives 2 points for MAP 50-69.",
    9575: "Glasgow Coma Score entity is 2, which is impossible (GCS range 3-15); the calculator rejects it.",
    9578: "Glasgow Coma Score entity is 1, which is impossible (GCS range 3-15); the calculator rejects it.",
    6664: "Temperature entity is 98.0 'degrees celsius' (clearly 98.0 °F); gold scores it as > 38 °C. The calculator "
          "rejects a 98 °C body temperature as impossible.",
}


def _homa_pmol_inverted(row, ents, got, err) -> bool:
    ins = ents.get("Insulin")
    if not (isinstance(ins, list) and str(ins[1]).lower() == "pmol/l") or got is None:
        return False
    return abs(float(row["Ground Truth Answer"]) / (float(got) * 36.0) - 1) < 0.02


def _impossible_creatinine(row, ents, got, err) -> bool:
    return bool(err) and "creatinine" in err and "above the plausible range" in err


SUSPECTED_LABEL_ERROR_RULES: list[tuple[int, str, object]] = [
    (31, "Insulin given in pmol/L: the gold explanation MULTIPLIES by 6 to get µIU/mL (1 µIU/mL = 6 pmol/L, so it must "
         "divide). Gold = correct value x 36 in every such row.", _homa_pmol_inverted),
] + [
    (cid, "Serum creatinine converts to a physically impossible value (> 40 mg/dL): the note/entity unit is a typo "
          "(e.g. 'mmol/L' for µmol/L, or mg/L recorded as mg/dL) and the gold answer is a physiologically impossible "
          "clearance/GFR computed literally. The calculator raises CalcInputError instead.", _impossible_creatinine)
    for cid in (2, 3, 9, 23, 28, 40, 43)
]



def parse_gold(row: dict):
    ot = row["Output Type"]
    a = row["Ground Truth Answer"].strip()
    if ot == "date":
        if a.startswith("("):
            w, d = ast.literal_eval(a)
            return (int(str(w).split()[0]), int(str(d).split()[0]))
        return a
    return float(a)


def is_correct(row: dict, got) -> bool:
    if got is None:
        return False
    ot = row["Output Type"]
    gold = parse_gold(row)
    if ot == "date":
        return got == gold
    if ot == "integer":
        try:
            return abs(float(got) - gold) < 1e-9
        except (TypeError, ValueError):
            return False
    lo, hi = float(row["Lower Limit"]), float(row["Upper Limit"])
    lo, hi = min(lo, hi), max(lo, hi)
    return lo - 1e-9 <= float(got) <= hi + 1e-9


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True, help="MedCalc-Bench Verified train_data.csv")
    ap.add_argument("--out", default=str(HERE / "calculator_validation.json"))
    ap.add_argument("--max-disagreements", type=int, default=200)
    args = ap.parse_args()
    if "test" in Path(args.train).name.lower():
        raise SystemExit("refusing to validate on test data")

    rows = list(csv.DictReader(open(args.train, encoding="utf-8")))
    per: dict[int, dict] = {}
    cat_tot: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for row in rows:
        cid = int(row["Calculator ID"])
        calc = by_medcalc_id(cid)
        rec = per.setdefault(cid, {"medcalc_id": cid, "medcalc_name": row["Calculator Name"], "id": calc.id,
                                   "category": row["Category"], "output_type": row["Output Type"], "n": 0,
                                   "correct": 0, "disagreements": [], "suspected_label_errors": []})
        rec["n"] += 1
        ents = ast.literal_eval(row["Relevant Entities"])
        err = None
        res = None
        try:
            inputs = map_inputs(cid, ents)
            res = calc.compute(inputs)
            got = res.value
        except CalcInputError as exc:
            got, err = None, f"CalcInputError: {exc}"
        ok = is_correct(row, got)
        rn = int(row["Row Number"])
        if ok:
            rec["correct"] += 1
            cat_tot[row["Category"]][1] += 1
        else:
            reason = SUSPECTED_LABEL_ERRORS.get(rn)
            if reason is None:
                for rc, why, pred in SUSPECTED_LABEL_ERROR_RULES:
                    if rc == cid and pred(row, ents, got, err):  # type: ignore[operator]
                        reason = why
                        break
            d = {"row": rn, "expected": row["Ground Truth Answer"], "lower": row["Lower Limit"],
                 "upper": row["Upper Limit"], "got": got if not isinstance(got, tuple) else list(got),
                 "entities": row["Relevant Entities"]}
            if err:
                d["error"] = err
            if res is not None and res.missing:
                d["missing"] = res.missing
            if reason:
                d["reason"] = reason
                rec["suspected_label_errors"].append(d)
            else:
                rec["disagreements"].append(d)
        cat_tot[row["Category"]][0] += 1

    total = sum(r["n"] for r in per.values())
    correct = sum(r["correct"] for r in per.values())
    n_label = sum(len(r["suspected_label_errors"]) for r in per.values())
    calcs = []
    for cid in sorted(per):
        r = per[cid]
        r["pct"] = round(100 * r["correct"] / r["n"], 2)
        denom = r["n"] - len(r["suspected_label_errors"])
        r["pct_excluding_suspected_label_errors"] = round(100 * r["correct"] / denom, 2) if denom else None
        r["n_disagreements"] = len(r["disagreements"])
        r["n_suspected_label_errors"] = len(r["suspected_label_errors"])
        r["disagreements"] = r["disagreements"][: args.max_disagreements]
        calcs.append(r)
    out = {
        "dataset": "MedCalc-Bench Verified train_data.csv (CC-BY-SA 4.0)",
        "rows": total, "correct": correct, "overall_pct": round(100 * correct / total, 3),
        "suspected_label_errors": n_label,
        "overall_pct_excluding_suspected_label_errors": round(100 * correct / (total - n_label), 3),
        "per_category": {k: {"n": v[0], "correct": v[1], "pct": round(100 * v[1] / v[0], 2)}
                         for k, v in sorted(cat_tot.items())},
        "medcalc_id_map": {str(k): v for k, v in MEDCALC_ID_MAP.items()},
        "dropped_keys": {f"{k[0]}:{k[1]}": v for k, v in DROPPED_KEYS.items()},
        "calculators": calcs,
    }
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    write_md(out, Path(args.out).with_suffix(".md"))
    print(f"overall {correct}/{total} = {out['overall_pct']}%  (suspected label errors: {n_label}; "
          f"excluding them {out['overall_pct_excluding_suspected_label_errors']}%)")
    for k, v in out["per_category"].items():
        print(f"  {k:12s} {v['correct']}/{v['n']} = {v['pct']}%")
    for r in calcs:
        flag = "" if r["pct"] >= 98 else "  <98"
        print(f"  {r['medcalc_id']:>3} {r['id']:40s} {r['correct']:>4}/{r['n']:<4} {r['pct']:6.2f}%  "
              f"(label errs {r['n_suspected_label_errors']}, unexplained {r['n_disagreements']}){flag}")
    return 0


def write_md(out: dict, path: Path) -> None:
    L = ["# Calculator validation on MedCalc-Bench Verified (train split)", "",
         f"Generated by `prompt-evals/medcalc/validate_calculators.py`. Gold = Relevant Entities -> calculator; "
         f"decimal answers must fall in [Lower, Upper], integers/dates must match exactly. Test split never read.", "",
         f"**Overall: {out['correct']}/{out['rows']} = {out['overall_pct']}%** "
         f"({out['suspected_label_errors']} suspected gold-label errors; excluding them "
         f"{out['overall_pct_excluding_suspected_label_errors']}%).", "",
         "| Category | n | correct | % |", "|---|---:|---:|---:|"]
    for k, v in out["per_category"].items():
        L.append(f"| {k} | {v['n']} | {v['correct']} | {v['pct']} |")
    L += ["", "| MedCalc ID | MedCalc name | our id | n | correct | % | suspected label errors | unexplained |",
          "|---:|---|---|---:|---:|---:|---:|---:|"]
    for r in out["calculators"]:
        L.append(f"| {r['medcalc_id']} | {r['medcalc_name']} | `{r['id']}` | {r['n']} | {r['correct']} | {r['pct']} | "
                 f"{r['n_suspected_label_errors']} | {r['n_disagreements']} |")
    L += ["", "## Suspected gold-label errors", ""]
    reasons: dict[str, list[int]] = collections.defaultdict(list)
    for r in out["calculators"]:
        for d in r["suspected_label_errors"]:
            reasons[f"{r['medcalc_id']} `{r['id']}`: {d['reason']}"].append(d["row"])
    for k, rows in reasons.items():
        L.append(f"- {k} Rows ({len(rows)}): {', '.join(map(str, sorted(rows)))}")
    if not reasons:
        L.append("- none")
    L += ["", "## Remaining (unexplained) disagreements", ""]
    any_d = False
    for r in out["calculators"]:
        for d in r["disagreements"][:15]:
            any_d = True
            L.append(f"- {r['medcalc_id']} `{r['id']}` row {d['row']}: expected {d['expected']}, got {d['got']}"
                     + (f" ({d.get('error')})" if d.get("error") else ""))
    if not any_d:
        L.append("- none")
    L += ["", "## Dropped entity keys", ""] + [f"- `{k}`: {v}" for k, v in out["dropped_keys"].items()]
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
