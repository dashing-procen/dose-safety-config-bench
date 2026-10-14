"""Cardiovascular / thromboembolic risk scores.

Convention (MedCalc-Bench and MDCalc): a criterion that is not supplied is scored as absent,
and every such default is listed in ``CalcResult.assumptions``.
"""

from __future__ import annotations

import math

from .calcs_body_renal import SCR_MAX
from .base import SEX, Calculator, Ctx, bparam, eparam, fmt, points, qparam, schema


class CHA2DS2VASc(Calculator):
    id = "cha2ds2_vasc"
    name = "CHA2DS2-VASc Score for Atrial Fibrillation Stroke Risk"
    medcalc_ids = (4,)
    category = "risk"
    output_unit = "points"
    aliases = ("cha2ds2-vasc", "chads-vasc", "chadsvasc", "cha2ds2vasc", "af stroke risk", "atrial fibrillation stroke")
    description = ("Annual stroke risk in non-valvular AF: CHF 1, hypertension 1, age 65-74 1 / >=75 2, diabetes 1, "
                   "prior stroke/TIA/thromboembolism 2, vascular disease 1, female sex 1 (0-9).")
    parameters = schema(["age", "sex"], age=qparam("Age.", "age"), sex=SEX,
                        chf=bparam("Congestive heart failure history."),
                        hypertension=bparam("Hypertension history."),
                        diabetes=bparam("Diabetes mellitus."),
                        stroke=bparam("Prior stroke."), tia=bparam("Prior transient ischaemic attack."),
                        thromboembolism=bparam("Prior systemic thromboembolism."),
                        vascular_disease=bparam("Vascular disease: prior MI, peripheral artery disease or aortic plaque."))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        f = {k: c.flag(k) for k in ("chf", "hypertension", "diabetes", "stroke", "tia", "thromboembolism",
                                    "vascular_disease")}
        if age is None or sex is None:
            return None
        t = [0]
        points(c, t, 2 if age >= 75 else 1 if age >= 65 else 0, f"Age {fmt(age)}")
        points(c, t, 1 if sex == "female" else 0, f"Sex {sex}")
        points(c, t, 1 if f["chf"] else 0, "CHF")
        points(c, t, 1 if f["hypertension"] else 0, "Hypertension")
        points(c, t, 2 if (f["stroke"] or f["tia"] or f["thromboembolism"]) else 0, "Stroke/TIA/thromboembolism")
        points(c, t, 1 if f["vascular_disease"] else 0, "Vascular disease")
        points(c, t, 1 if f["diabetes"] else 0, "Diabetes")
        return t[0]


class HASBLED(Calculator):
    id = "has_bled"
    name = "HAS-BLED Score for Major Bleeding Risk"
    medcalc_ids = (25,)
    category = "risk"
    output_unit = "points"
    aliases = ("has-bled", "hasbled", "bleeding risk anticoagulation")
    description = ("1-year major bleeding risk on anticoagulation: uncontrolled hypertension, abnormal renal function, "
                   "abnormal liver function, stroke, bleeding history/predisposition, labile INR, age >65, "
                   "bleeding-predisposing drugs, alcohol >=8 drinks/week (1 point each, 0-9).")
    parameters = schema(["age"], age=qparam("Age.", "age"),
                        hypertension=bparam("Uncontrolled hypertension (SBP > 160 mmHg)."),
                        renal_disease=bparam("Dialysis, transplant, Cr > 2.26 mg/dL (200 µmol/L)."),
                        liver_disease=bparam("Cirrhosis or bilirubin > 2x ULN with AST/ALT/ALP > 3x ULN."),
                        stroke=bparam("Prior stroke."),
                        prior_bleeding=bparam("Prior major bleeding or predisposition to bleeding."),
                        labile_inr=bparam("Labile INR (unstable/high INRs, TTR < 60%)."),
                        bleeding_medication=bparam("Antiplatelet agents or NSAIDs."),
                        alcohol_drinks_per_week={"type": "number", "description": "Alcoholic drinks per week (>= 8 scores 1)."},
                        alcohol_use=bparam("Alcohol use >= 8 drinks/week (alternative to the count)."))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        names = {"hypertension": "Hypertension", "renal_disease": "Renal disease", "liver_disease": "Liver disease",
                 "stroke": "Stroke history", "prior_bleeding": "Prior bleeding", "labile_inr": "Labile INR",
                 "bleeding_medication": "Bleeding-predisposing medication"}
        f = {k: c.flag(k) for k in names}
        drinks = c.num("alcohol_drinks_per_week", required=False, lo=0, log=False)
        if drinks is not None:
            alcohol = drinks >= 8
            alc_txt = f"Alcohol {fmt(drinks)} drinks/week"
        else:
            alcohol = c.flag("alcohol_use")
            alc_txt = "Alcohol >= 8 drinks/week"
        if age is None:
            return None
        t = [0]
        points(c, t, 1 if age > 65 else 0, f"Age {fmt(age)} (>65)")
        for k, label in names.items():
            points(c, t, 1 if f[k] else 0, label)
        points(c, t, 1 if alcohol else 0, alc_txt)
        return t[0]


class HEARTScore(Calculator):
    id = "heart_score"
    name = "HEART Score for Major Cardiac Events"
    medcalc_ids = (18,)
    category = "risk"
    output_unit = "points"
    aliases = ("heart score", "heart", "chest pain risk", "mace")
    description = ("6-week MACE risk in ED chest pain: History, ECG, Age, Risk factors, Troponin (0-2 each). "
                   "Risk factors: HTN, hypercholesterolaemia, DM, obesity (BMI>30), smoking, family history; "
                   ">=3 risk factors or known atherosclerotic disease (MI, PCI/CABG, stroke/TIA, PAD) = 2.")
    parameters = schema(
        ["history", "ecg", "age", "troponin"],
        history=eparam("Suspicion from history.", ["slightly suspicious", "moderately suspicious", "highly suspicious"]),
        ecg=eparam("ECG.", ["normal", "non-specific repolarization disturbance", "significant ST deviation"]),
        age=qparam("Age.", "age"),
        hypertension=bparam("Hypertension."), hypercholesterolemia=bparam("Hypercholesterolaemia."),
        diabetes=bparam("Diabetes mellitus."), obesity=bparam("Obesity (BMI > 30)."),
        smoking=bparam("Current smoker or quit < 3 months."),
        family_history=bparam("Parent or sibling with CVD before age 65."),
        atherosclerotic_disease=bparam("Known atherosclerotic disease: prior MI, PCI/CABG, stroke/TIA, PAD."),
        troponin=eparam("Initial troponin.", ["<= normal limit", "1-3x normal limit", "> 3x normal limit"]))

    def run(self, c: Ctx):
        hist = c.enum("history", aliases={"slightly": "slightly suspicious", "moderately": "moderately suspicious",
                                          "highly": "highly suspicious"})
        ecg = c.enum("ecg", aliases={"nonspecific repolarization disturbance": "non-specific repolarization disturbance",
                                     "significant st depression": "significant ST deviation"})
        age = c.qty("age", lo=0, hi=130)
        rf_names = ("hypertension", "hypercholesterolemia", "diabetes", "obesity", "smoking", "family_history")
        rf = {k: c.flag(k) for k in rf_names}
        ath = c.flag("atherosclerotic_disease")
        trop = c.enum("troponin", aliases={
            "less than or equal to normal limit": "<= normal limit", "normal": "<= normal limit",
            "between the normal limit or up to three times the normal limit": "1-3x normal limit",
            "greater than three times normal limit": "> 3x normal limit"})
        if None in (hist, ecg, age, trop):
            return None
        t = [0]
        points(c, t, ["slightly suspicious", "moderately suspicious", "highly suspicious"].index(hist), f"History: {hist}")
        points(c, t, ["normal", "non-specific repolarization disturbance", "significant ST deviation"].index(ecg), f"ECG: {ecg}")
        points(c, t, 2 if age >= 65 else 1 if age >= 45 else 0, f"Age {fmt(age)}")
        n = sum(1 for v in rf.values() if v)
        present = [k for k, v in rf.items() if v] + (["atherosclerotic disease"] if ath else [])
        rpts = 2 if (n >= 3 or ath) else 1 if n >= 1 else 0
        points(c, t, rpts, f"Risk factors ({', '.join(present) or 'none'})")
        points(c, t, ["<= normal limit", "1-3x normal limit", "> 3x normal limit"].index(trop), f"Troponin {trop}")
        return t[0]


class RCRI(Calculator):
    id = "revised_cardiac_risk_index"
    name = "Revised Cardiac Risk Index (RCRI, Lee)"
    medcalc_ids = (17,)
    category = "risk"
    output_unit = "points"
    aliases = ("rcri", "lee index", "revised cardiac risk index", "preoperative cardiac risk")
    description = ("Peri-operative major cardiac event risk: high-risk surgery, ischaemic heart disease, CHF, "
                   "cerebrovascular disease, insulin treatment, creatinine > 2 mg/dL (1 point each).")
    parameters = schema([], high_risk_surgery=bparam("Intraperitoneal, intrathoracic or suprainguinal vascular surgery."),
                        ischemic_heart_disease=bparam("History of ischaemic heart disease."),
                        chf=bparam("History of congestive heart failure."),
                        cerebrovascular_disease=bparam("History of stroke or TIA."),
                        insulin=bparam("Pre-operative treatment with insulin."),
                        creatinine=qparam("Pre-operative creatinine (> 2 mg/dL scores 1).", "creatinine"))

    def run(self, c: Ctx):
        names = {"high_risk_surgery": "Elevated-risk surgery", "ischemic_heart_disease": "Ischaemic heart disease",
                 "chf": "CHF", "cerebrovascular_disease": "Cerebrovascular disease", "insulin": "Insulin treatment"}
        f = {k: c.flag(k) for k in names}
        cr = c.qty("creatinine", required=False, positive=True, hi=SCR_MAX)
        if cr is None:
            c.assume("absent: creatinine > 2 mg/dL (creatinine not provided)")
        t = [0]
        for k, label in names.items():
            points(c, t, 1 if f[k] else 0, label)
        points(c, t, 1 if (cr is not None and cr > 2) else 0, "Creatinine > 2 mg/dL")
        return t[0]


class FraminghamHardCHD(Calculator):
    id = "framingham_hard_chd"
    name = "Framingham Risk Score for Hard Coronary Heart Disease (ATP III)"
    medcalc_ids = (46,)
    category = "risk"
    output_unit = "%"
    decimals = 4
    aliases = ("framingham", "framingham risk score", "10-year chd risk", "atp iii", "hard chd")
    description = ("10-year risk (%) of MI or coronary death (ATP III Framingham equations), ages 30-79 without "
                   "diabetes or known CHD. Smoking-age term capped at 70 (men) / 78 (women).")
    parameters = schema(["age", "sex", "total_cholesterol", "hdl", "systolic_bp"],
                        age=qparam("Age.", "age"), sex=SEX,
                        smoker=bparam("Current smoker."),
                        total_cholesterol=qparam("Total cholesterol.", "cholesterol"),
                        hdl=qparam("HDL cholesterol.", "cholesterol"),
                        systolic_bp=qparam("Systolic blood pressure.", "pressure"),
                        bp_treated=bparam("On antihypertensive medication."))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        smk = c.flag("smoker", note="non-smoker assumed (smoking status not provided)")
        tc = c.qty("total_cholesterol", positive=True)
        hdl = c.qty("hdl", positive=True)
        sbp = c.qty("systolic_bp", positive=True)
        tx = c.flag("bp_treated", note="not on antihypertensive treatment (not provided)")
        if None in (age, sex, tc, hdl, sbp):
            return None
        la, ltc, lh, ls = math.log(age), math.log(tc), math.log(hdl), math.log(sbp)
        s, b = int(bool(smk)), int(bool(tx))
        if sex == "male":
            las = math.log(min(age, 70))
            x = (52.00961 * la + 20.014077 * ltc - 0.905964 * lh + 1.305784 * ls + 0.241549 * b
                 + 12.096316 * s - 4.605038 * la * ltc - 2.84367 * las * s - 2.93323 * la * la - 172.300168)
            risk = (1 - 0.9402 ** math.exp(x)) * 100
            c.step(f"Male equation: linear predictor = {fmt(x)}; risk = (1 - 0.9402^exp({fmt(x)})) x 100 = {fmt(risk)} %")
        else:
            las = math.log(min(age, 78))
            x = (31.764001 * la + 22.465206 * ltc - 1.187731 * lh + 2.552905 * ls + 0.420251 * b
                 + 13.07543 * s - 5.060998 * la * ltc - 2.996945 * las * s - 146.5933061)
            risk = (1 - 0.98767 ** math.exp(x)) * 100
            c.step(f"Female equation: linear predictor = {fmt(x)}; risk = (1 - 0.98767^exp({fmt(x)})) x 100 = {fmt(risk)} %")
        if not 30 <= age <= 79:
            c.assume("age outside the 30-79 validation range of the Framingham equations")
        return risk


class WellsPE(Calculator):
    id = "wells_pe"
    name = "Wells' Criteria for Pulmonary Embolism"
    medcalc_ids = (8,)
    category = "risk"
    output_unit = "points"
    decimals = 1
    aliases = ("wells pe", "wells criteria pe", "wells pulmonary embolism", "wells' criteria for pe")
    description = ("Pre-test probability of PE: DVT signs 3, PE most likely 3, HR > 100 1.5, immobilisation >=3 d or "
                   "surgery in 4 wk 1.5, prior PE/DVT 1.5, haemoptysis 1, malignancy 1.")
    parameters = schema([], dvt_signs=bparam("Clinical signs and symptoms of DVT."),
                        pe_most_likely=bparam("PE is the #1 diagnosis or equally likely."),
                        heart_rate=qparam("Heart rate (> 100 scores 1.5).", "rate_per_min"),
                        immobilization=bparam("Immobilisation at least 3 days."),
                        recent_surgery=bparam("Surgery in the previous 4 weeks."),
                        previous_pe=bparam("Previously documented PE."),
                        previous_dvt=bparam("Previously documented DVT."),
                        hemoptysis=bparam("Haemoptysis."),
                        malignancy=bparam("Malignancy with treatment within 6 months or palliative."))

    def run(self, c: Ctx):
        f = {k: c.flag(k) for k in ("dvt_signs", "pe_most_likely", "immobilization", "recent_surgery",
                                    "previous_pe", "previous_dvt", "hemoptysis", "malignancy")}
        hr = c.qty("heart_rate", required=False, positive=True)
        if hr is None:
            c.assume("heart rate not provided: assumed <= 100 (0 points)")
        t = [0.0]
        points(c, t, 3 if f["dvt_signs"] else 0, "Clinical signs of DVT")
        points(c, t, 3 if f["pe_most_likely"] else 0, "PE #1 diagnosis or equally likely")
        points(c, t, 1.5 if (hr is not None and hr > 100) else 0, "Heart rate > 100")
        points(c, t, 1.5 if (f["immobilization"] or f["recent_surgery"]) else 0, "Immobilisation >= 3 d or surgery < 4 wk")
        points(c, t, 1.5 if (f["previous_pe"] or f["previous_dvt"]) else 0, "Previous PE or DVT")
        points(c, t, 1 if f["hemoptysis"] else 0, "Haemoptysis")
        points(c, t, 1 if f["malignancy"] else 0, "Malignancy")
        return t[0]


class WellsDVT(Calculator):
    id = "wells_dvt"
    name = "Wells' Criteria for DVT"
    medcalc_ids = (16,)
    category = "risk"
    output_unit = "points"
    aliases = ("wells dvt", "wells criteria dvt", "wells deep vein thrombosis")
    description = ("Pre-test probability of DVT: active cancer, bedridden >3 d or major surgery <12 wk, calf swelling "
                   ">3 cm, collateral superficial veins, entire leg swollen, localized deep-vein tenderness, pitting "
                   "oedema in symptomatic leg, paralysis/paresis/plaster, previous DVT (+1 each); alternative "
                   "diagnosis at least as likely (-2).")
    parameters = schema([], active_cancer=bparam("Active cancer (treatment or palliation within 6 months)."),
                        bedridden=bparam("Bedridden recently > 3 days."),
                        major_surgery=bparam("Major surgery within 12 weeks."),
                        calf_swelling=bparam("Calf swelling > 3 cm compared with the other leg."),
                        collateral_veins=bparam("Collateral (non-varicose) superficial veins."),
                        entire_leg_swollen=bparam("Entire leg swollen."),
                        localized_tenderness=bparam("Localized tenderness along the deep venous system."),
                        pitting_edema=bparam("Pitting oedema confined to the symptomatic leg."),
                        paralysis_or_cast=bparam("Paralysis, paresis or recent plaster immobilisation of the leg."),
                        previous_dvt=bparam("Previously documented DVT."),
                        alternative_diagnosis=bparam("Alternative diagnosis at least as likely as DVT."))

    def run(self, c: Ctx):
        keys = ("active_cancer", "bedridden", "major_surgery", "calf_swelling", "collateral_veins",
                "entire_leg_swollen", "localized_tenderness", "pitting_edema", "paralysis_or_cast",
                "previous_dvt", "alternative_diagnosis")
        f = {k: c.flag(k) for k in keys}
        t = [0]
        points(c, t, 1 if f["active_cancer"] else 0, "Active cancer")
        points(c, t, 1 if (f["bedridden"] or f["major_surgery"]) else 0, "Bedridden > 3 d or major surgery < 12 wk")
        for k in ("calf_swelling", "collateral_veins", "entire_leg_swollen", "localized_tenderness", "pitting_edema",
                  "paralysis_or_cast", "previous_dvt"):
            points(c, t, 1 if f[k] else 0, k.replace("_", " "))
        points(c, t, -2 if f["alternative_diagnosis"] else 0, "Alternative diagnosis as likely")
        return t[0]


class PERC(Calculator):
    id = "perc_rule"
    name = "PERC Rule for Pulmonary Embolism"
    medcalc_ids = (48,)
    category = "diagnosis"
    output_unit = "criteria met"
    aliases = ("perc", "perc rule", "pulmonary embolism rule-out criteria")
    description = ("Number of PERC criteria met (0 = PE can be ruled out in low-pretest-probability patients): age >=50, "
                   "HR >=100, SaO2 <95%, unilateral leg swelling, haemoptysis, recent surgery/trauma, prior PE/DVT, "
                   "hormone use.")
    parameters = schema(["age"], age=qparam("Age.", "age"),
                        heart_rate=qparam("Heart rate.", "rate_per_min"),
                        oxygen_saturation=qparam("SaO2 on room air.", "percent"),
                        unilateral_leg_swelling=bparam("Unilateral leg swelling."),
                        hemoptysis=bparam("Haemoptysis."),
                        recent_surgery_or_trauma=bparam("Surgery or trauma within 4 weeks requiring general anaesthesia."),
                        previous_pe=bparam("Prior PE."), previous_dvt=bparam("Prior DVT."),
                        hormone_use=bparam("Oral contraceptives, hormone replacement or oestrogen use."))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        hr = c.qty("heart_rate", required=False, positive=True)
        sat = c.qty("oxygen_saturation", required=False, lo=0, hi=100)
        if hr is None:
            c.assume("heart rate not provided: assumed < 100")
        if sat is None:
            c.assume("O2 saturation not provided: assumed >= 95%")
        f = {k: c.flag(k) for k in ("unilateral_leg_swelling", "hemoptysis", "recent_surgery_or_trauma",
                                    "previous_pe", "previous_dvt", "hormone_use")}
        if age is None:
            return None
        t = [0]
        points(c, t, 1 if age >= 50 else 0, f"Age {fmt(age)} >= 50")
        points(c, t, 1 if (hr is not None and hr >= 100) else 0, "HR >= 100")
        points(c, t, 1 if (sat is not None and sat < 95) else 0, "SaO2 < 95%")
        points(c, t, 1 if f["unilateral_leg_swelling"] else 0, "Unilateral leg swelling")
        points(c, t, 1 if f["hemoptysis"] else 0, "Haemoptysis")
        points(c, t, 1 if f["recent_surgery_or_trauma"] else 0, "Recent surgery or trauma")
        points(c, t, 1 if (f["previous_pe"] or f["previous_dvt"]) else 0, "Prior PE or DVT")
        points(c, t, 1 if f["hormone_use"] else 0, "Hormone use")
        return t[0]


_CAPRINI_SURGERY = ["none", "minor", "major", "laparoscopic", "arthroscopic",
                    "elective major lower extremity arthroplasty"]
_CAPRINI_SURG_PTS = {"none": 0, "minor": 1, "major": 2, "laparoscopic": 2, "arthroscopic": 2,
                     "elective major lower extremity arthroplasty": 5}
_CAPRINI_FLAGS = {  # name: (points, label)
    "recent_major_surgery": (1, "Major surgery in the last month"),
    "recent_chf": (1, "CHF in the last month"),
    "recent_sepsis": (1, "Sepsis in the last month"),
    "recent_pneumonia": (1, "Pneumonia in the last month"),
    "recent_plaster_cast": (2, "Immobilising plaster cast in the last month"),
    "recent_fracture": (5, "Hip, pelvis or leg fracture in the last month"),
    "recent_stroke": (5, "Stroke in the last month"),
    "recent_multiple_trauma": (5, "Multiple trauma in the last month"),
    "recent_spinal_cord_injury": (5, "Acute spinal cord injury with paralysis in the last month"),
    "varicose_veins": (1, "Varicose veins"),
    "swollen_legs": (1, "Current swollen legs"),
    "central_venous_access": (2, "Current central venous access"),
    "family_history_thrombosis": (3, "Family history of thrombosis"),
    "factor_v_leiden": (3, "Positive factor V Leiden"),
    "prothrombin_20210a": (3, "Positive prothrombin 20210A"),
    "elevated_homocysteine": (3, "Elevated serum homocysteine"),
    "lupus_anticoagulant": (3, "Positive lupus anticoagulant"),
    "anticardiolipin_antibody": (3, "Elevated anticardiolipin antibody"),
    "heparin_induced_thrombocytopenia": (3, "Heparin-induced thrombocytopenia"),
    "other_thrombophilia": (3, "Other congenital or acquired thrombophilia"),
    "inflammatory_bowel_disease": (1, "History of inflammatory bowel disease"),
    "acute_mi": (1, "Acute myocardial infarction"),
    "copd": (1, "COPD"),
    "malignancy": (2, "Present or previous malignancy"),
}


class Caprini(Calculator):
    id = "caprini_vte"
    name = "Caprini Score for Venous Thromboembolism (2005)"
    medcalc_ids = (36,)
    category = "risk"
    output_unit = "points"
    aliases = ("caprini", "caprini score", "vte risk surgical", "venous thromboembolism risk")
    description = ("Surgical VTE risk (Caprini 2005): age, type of surgery, recent events (<=1 month), venous disease and "
                   "thrombophilia, mobility, other history (IBD, BMI>25, acute MI, COPD, malignancy).")
    parameters = schema(
        ["age"], age=qparam("Age.", "age"), sex=SEX,
        surgery_type=eparam("Type of surgery (major = >45 min; laparoscopic/arthroscopic >45 min).", _CAPRINI_SURGERY),
        mobility=eparam("Mobility.", ["normal", "bed rest", "confined to bed >72 hours"]),
        previous_dvt=bparam("History of DVT."), previous_pe=bparam("History of PE."),
        bmi=qparam("Body mass index (> 25 scores 1).", "bmi"),
        **{k: bparam(lbl + ".") for k, (_, lbl) in _CAPRINI_FLAGS.items()})

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        surg = c.enum("surgery_type", default="none", note="no surgery assumed (surgery type not provided)",
                      aliases={"major >45 min": "major", "elective major lower extremity arthroplasty": "elective major lower extremity arthroplasty"})
        mob = c.enum("mobility", default="normal", note="normal mobility assumed (not provided)",
                     aliases={"on bed rest": "bed rest", "normal, out of bed": "normal",
                              "confined to bed > 72 hours": "confined to bed >72 hours"})
        f = {k: c.flag(k) for k in _CAPRINI_FLAGS}
        dvt = c.flag("previous_dvt")
        pe = c.flag("previous_pe")
        bmi = c.qty("bmi", required=False, positive=True)
        if bmi is None:
            c.assume("absent: BMI > 25 (BMI not provided)")
        c.sex(required=False)
        if age is None:
            return None
        t = [0]
        points(c, t, 3 if age >= 75 else 2 if age >= 61 else 1 if age >= 41 else 0, f"Age {fmt(age)}")
        points(c, t, _CAPRINI_SURG_PTS[surg], f"Surgery: {surg}")
        for k, (p, lbl) in _CAPRINI_FLAGS.items():
            if k in ("inflammatory_bowel_disease",):
                continue
            if k == "family_history_thrombosis":
                points(c, t, 3 if (dvt or pe) else 0, "History of DVT or PE")
            points(c, t, p if f[k] else 0, lbl)
        points(c, t, {"normal": 0, "bed rest": 1, "confined to bed >72 hours": 2}[mob], f"Mobility: {mob}")
        points(c, t, 1 if f["inflammatory_bowel_disease"] else 0, "History of IBD")
        points(c, t, 1 if (bmi is not None and bmi > 25) else 0, "BMI > 25")
        return t[0]


CALCS = [CHA2DS2VASc, WellsPE, WellsDVT, RCRI, HEARTScore, HASBLED, Caprini, FraminghamHardCHD, PERC]
