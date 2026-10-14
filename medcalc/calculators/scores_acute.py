"""Severity / acute-care scores: ICU, sepsis, pneumonia, liver, GI bleeding, comorbidity, pharyngitis, coma.

Convention (MedCalc-Bench and MDCalc): a criterion or physiological variable that is not supplied
is scored as absent/normal (0 points), and every such default is listed in ``assumptions``.
"""

from __future__ import annotations

import math

from .base import SEX, Calculator, Ctx, bparam, eparam, fmt, nparam, points, qparam, schema
from .calcs_body_renal import SCR_MAX, mean_arterial_pressure


def _fio2(c: Ctx, name: str = "fio2") -> float | None:
    """FiO2 as a percentage; a bare value <= 1 is read as a fraction."""
    raw = c.inputs.get(name)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and 0 < raw <= 1:
        v = float(raw) * 100
        c.step(f"FiO2 = {fmt(raw)} (fraction) = {fmt(v)} %")
        return v
    return c.qty(name, required=False, lo=21 * 0.99, hi=100)


def _map(c: Ctx) -> float | None:
    m = c.qty("mean_arterial_pressure", required=False, positive=True)
    if m is not None:
        return m
    s = c.qty("systolic_bp", required=False, positive=True)
    d = c.qty("diastolic_bp", required=False, positive=True)
    if s is None or d is None:
        return None
    m = mean_arterial_pressure(s, d)
    c.step(f"MAP = ({fmt(s)} + 2 x {fmt(d)}) / 3 = {fmt(m)} mmHg")
    return m


def _band(x: float, table: list[tuple[float, float]]) -> float:
    """table = [(lower_bound_inclusive, points), ...] in descending order of bound."""
    for lo, p in table:
        if x >= lo:
            return p
    return table[-1][1]


_BP = dict(systolic_bp=qparam("Systolic blood pressure.", "pressure"),
           diastolic_bp=qparam("Diastolic blood pressure.", "pressure"),
           mean_arterial_pressure=qparam("Mean arterial pressure (alternative to SBP/DBP).", "pressure"))


class APACHEII(Calculator):
    id = "apache_ii"
    name = "APACHE II Score"
    medcalc_ids = (28,)
    category = "risk"
    output_unit = "points"
    aliases = ("apache ii", "apache 2", "apache", "icu mortality")
    description = ("ICU severity: acute physiology (worst values in first 24 h: temperature, MAP, HR, RR, oxygenation "
                   "[PaO2 if FiO2 < 50%, else A-a gradient], pH, Na, K, creatinine [doubled in acute renal failure], "
                   "haematocrit, WBC, 15-GCS) + age points + chronic health points (5 nonoperative/emergency "
                   "postoperative, 2 elective postoperative). Missing physiology is scored as normal.")
    parameters = schema(
        ["age"], age=qparam("Age.", "age"),
        temperature=qparam("Temperature (rectal/core).", "temperature"), **_BP,
        heart_rate=qparam("Heart rate.", "rate_per_min"), respiratory_rate=qparam("Respiratory rate.", "rate_per_min"),
        fio2=qparam("FiO2 (percent, or a fraction <= 1).", "percent"),
        pao2=qparam("PaO2.", "pressure"), aa_gradient=qparam("A-a O2 gradient.", "pressure"),
        ph=nparam("Arterial pH.", 6.5, 8.0),
        sodium=qparam("Serum sodium.", "sodium"), potassium=qparam("Serum potassium.", "potassium"),
        creatinine=qparam("Serum creatinine.", "creatinine"),
        acute_renal_failure=bparam("Acute renal failure (doubles creatinine points)."),
        hematocrit=qparam("Haematocrit.", "percent"), wbc=qparam("White blood cell count.", "cell_count"),
        gcs=nparam("Glasgow Coma Scale (3-15).", 3, 15),
        chronic_health=bparam("History of severe organ insufficiency or immunocompromise."),
        admission_type=eparam("Admission type (for chronic health points).",
                              ["nonoperative", "emergency postoperative", "elective postoperative"]))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        temp = c.qty("temperature", required=False, lo=15, hi=46)
        mp = _map(c)
        hr = c.qty("heart_rate", required=False, lo=0)
        rr = c.qty("respiratory_rate", required=False, lo=0)
        fio2 = _fio2(c)
        pao2 = c.qty("pao2", required=False, positive=True)
        aa = c.qty("aa_gradient", required=False)
        ph = c.num("ph", required=False, lo=6.5, hi=8.0)
        na = c.qty("sodium", required=False, positive=True)
        k = c.qty("potassium", required=False, positive=True)
        cr = c.qty("creatinine", required=False, positive=True, hi=SCR_MAX)
        arf = c.flag("acute_renal_failure")
        hct = c.qty("hematocrit", required=False, lo=0, hi=100)
        wbc = c.qty("wbc", required=False, lo=0)
        gcs = c.num("gcs", required=False, lo=3, hi=15)
        chronic = c.flag("chronic_health")
        adm = None
        if chronic:
            adm = c.enum("admission_type", default="unknown",
                         note="admission type not provided: chronic-health points NOT added (would be +5 "
                              "nonoperative/emergency postoperative or +2 elective postoperative)",
                         aliases={"emergency": "emergency postoperative", "elective": "elective postoperative",
                                  "non-operative": "nonoperative"})
        if age is None:
            return None
        t = [0]

        def miss(label: str):
            c.assume(f"{label} not provided: scored as normal (0 points)")

        points(c, t, _band(age, [(75, 6), (65, 5), (55, 3), (45, 2), (-1, 0)]), f"Age {fmt(age)}")
        if chronic and adm == "unknown":
            points(c, t, 0, "Chronic health (admission type unknown)")
        elif chronic:
            points(c, t, 2 if adm == "elective postoperative" else 5, f"Chronic health ({adm})")
        else:
            points(c, t, 0, "No severe organ insufficiency/immunocompromise")
        if temp is None:
            miss("temperature")
        else:
            points(c, t, _band(temp, [(41, 4), (39, 3), (38.5, 1), (36, 0), (34, 1), (32, 2), (30, 3), (-99, 4)]),
                   f"Temperature {fmt(temp)} °C")
        if mp is None:
            miss("mean arterial pressure")
        else:
            points(c, t, _band(mp, [(160, 4), (130, 3), (110, 2), (70, 0), (50, 2), (-1, 4)]), f"MAP {fmt(mp)} mmHg")
        if hr is None:
            miss("heart rate")
        else:
            points(c, t, _band(hr, [(180, 4), (140, 3), (110, 2), (70, 0), (55, 2), (40, 3), (-1, 4)]), f"HR {fmt(hr)}")
        if rr is None:
            miss("respiratory rate")
        else:
            points(c, t, _band(rr, [(50, 4), (35, 3), (25, 1), (12, 0), (10, 1), (6, 2), (-1, 4)]), f"RR {fmt(rr)}")
        # oxygenation
        if fio2 is not None and fio2 >= 50:
            if aa is None and pao2 is not None:
                c.assume("FiO2 >= 50% but A-a gradient not provided: cannot score oxygenation by A-a; scored 0")
            if aa is None:
                miss("A-a gradient")
            else:
                points(c, t, _band(aa, [(500, 4), (350, 3), (200, 2), (-999, 0)]), f"A-a gradient {fmt(aa)} (FiO2 >= 50%)")
        else:
            if fio2 is None and (pao2 is not None or aa is not None):
                c.assume("FiO2 not provided: assumed < 50% (PaO2 used)")
            if pao2 is None:
                miss("PaO2")
            else:
                points(c, t, _band(pao2, [(70.0001, 0), (61, 1), (55, 3), (-1, 4)]), f"PaO2 {fmt(pao2)} mmHg (FiO2 < 50%)")
        if ph is None:
            miss("arterial pH")
        else:
            points(c, t, _band(ph, [(7.7, 4), (7.6, 3), (7.5, 1), (7.33, 0), (7.25, 2), (7.15, 3), (-1, 4)]), f"pH {fmt(ph)}")
        if na is None:
            miss("sodium")
        else:
            points(c, t, _band(na, [(180, 4), (160, 3), (155, 2), (150, 1), (130, 0), (120, 2), (111, 3), (-1, 4)]),
                   f"Sodium {fmt(na)}")
        if k is None:
            miss("potassium")
        else:
            points(c, t, _band(k, [(7, 4), (6, 3), (5.5, 1), (3.5, 0), (3, 1), (2.5, 2), (-1, 4)]), f"Potassium {fmt(k)}")
        if cr is None:
            miss("creatinine")
        else:
            p = _band(cr, [(3.5, 4), (2, 3), (1.5, 2), (0.6, 0), (-1, 2)])
            if arf and cr >= 1.5:
                p *= 2
            points(c, t, p, f"Creatinine {fmt(cr)} mg/dL{' (x2 acute renal failure)' if arf and cr >= 1.5 else ''}")
        if hct is None:
            miss("haematocrit")
        else:
            points(c, t, _band(hct, [(60, 4), (50, 2), (46, 1), (30, 0), (20, 2), (-1, 4)]), f"Haematocrit {fmt(hct)} %")
        if wbc is None:
            miss("WBC")
        else:
            points(c, t, _band(wbc, [(40, 4), (20, 2), (15, 1), (3, 0), (1, 2), (-1, 4)]), f"WBC {fmt(wbc)} x10^9/L")
        if gcs is None:
            miss("GCS (15 assumed)")
        else:
            points(c, t, 15 - gcs, f"15 - GCS {fmt(gcs)}")
        return int(t[0]) if float(t[0]).is_integer() else t[0]


class SOFA(Calculator):
    id = "sofa"
    name = "Sequential Organ Failure Assessment (SOFA) Score"
    medcalc_ids = (43,)
    category = "risk"
    output_unit = "points"
    aliases = ("sofa", "sequential organ failure assessment", "organ dysfunction", "sepsis-3")
    description = ("Organ dysfunction (0-24): respiration (PaO2/FiO2; 3-4 require ventilatory support), platelets, GCS, "
                   "bilirubin, cardiovascular (MAP < 70 or vasopressor doses in mcg/kg/min), renal (creatinine or "
                   "urine output). Missing components are scored 0.")
    parameters = schema(
        [], pao2=qparam("PaO2.", "pressure"), fio2=qparam("FiO2 (percent, or fraction <= 1).", "percent"),
        mechanical_ventilation=bparam("On mechanical ventilation."), cpap=bparam("On CPAP / non-invasive support."),
        platelets=qparam("Platelet count.", "cell_count"), gcs=nparam("Glasgow Coma Scale.", 3, 15),
        bilirubin=qparam("Total bilirubin.", "bilirubin"), **_BP,
        dopamine=qparam("Dopamine dose.", "dose_rate"), dobutamine=qparam("Dobutamine dose.", "dose_rate"),
        epinephrine=qparam("Epinephrine dose.", "dose_rate"), norepinephrine=qparam("Norepinephrine dose.", "dose_rate"),
        creatinine=qparam("Serum creatinine.", "creatinine"), urine_output=qparam("Urine output.", "urine_output"))

    def run(self, c: Ctx):
        pao2 = c.qty("pao2", required=False, positive=True)
        fio2 = _fio2(c)
        mv = c.flag("mechanical_ventilation")
        cpap = c.flag("cpap")
        plt = c.qty("platelets", required=False, lo=0)
        gcs = c.num("gcs", required=False, lo=3, hi=15)
        bili = c.qty("bilirubin", required=False, lo=0)
        mp = _map(c)
        dop = c.qty("dopamine", required=False, lo=0)
        dob = c.qty("dobutamine", required=False, lo=0)
        epi = c.qty("epinephrine", required=False, lo=0)
        ne = c.qty("norepinephrine", required=False, lo=0)
        cr = c.qty("creatinine", required=False, lo=0, hi=SCR_MAX)
        uo = c.qty("urine_output", required=False, lo=0)
        t = [0]
        if pao2 is None or fio2 is None:
            c.assume("PaO2/FiO2 not available: respiratory component scored 0")
        else:
            pf = pao2 / (fio2 / 100)
            vent = mv or cpap
            if pf < 100 and vent:
                p = 4
            elif pf < 200 and vent:
                p = 3
            elif pf < 300:
                p = 2
            elif pf < 400:
                p = 1
            else:
                p = 0
            points(c, t, p, f"PaO2/FiO2 = {fmt(pao2)}/{fmt(fio2 / 100)} = {fmt(pf)}{' (ventilated)' if vent else ''}")
        if plt is None:
            c.assume("platelets not provided: 0 points")
        else:
            points(c, t, _band(plt, [(150, 0), (100, 1), (50, 2), (20, 3), (-1, 4)]), f"Platelets {fmt(plt)} x10^3/µL")
        if gcs is None:
            c.assume("GCS not provided: 15 assumed (0 points)")
        else:
            points(c, t, _band(gcs, [(15, 0), (13, 1), (10, 2), (6, 3), (-1, 4)]), f"GCS {fmt(gcs)}")
        if bili is None:
            c.assume("bilirubin not provided: 0 points")
        else:
            points(c, t, _band(bili, [(12, 4), (6, 3), (2, 2), (1.2, 1), (-1, 0)]), f"Bilirubin {fmt(bili)} mg/dL")
        # cardiovascular
        dop, dob, epi, ne = (x or 0 for x in (dop, dob, epi, ne))
        if dop > 15 or epi > 0.1 or ne > 0.1:
            cv, txt = 4, "dopamine > 15 or epi/norepi > 0.1"
        elif dop > 5 or epi > 0 or ne > 0:
            cv, txt = 3, "dopamine > 5 or epi/norepi <= 0.1"
        elif dop > 0 or dob > 0:
            cv, txt = 2, "dopamine <= 5 or any dobutamine"
        elif mp is not None and mp < 70:
            cv, txt = 1, f"MAP {fmt(mp)} < 70"
        else:
            cv, txt = 0, (f"MAP {fmt(mp)} >= 70, no vasopressors" if mp is not None else "no MAP/vasopressor data")
            if mp is None:
                c.assume("MAP not provided: cardiovascular component scored 0")
        points(c, t, cv, f"Cardiovascular ({txt})")
        if cr is None and uo is None:
            c.assume("creatinine and urine output not provided: renal component scored 0")
        else:
            pc = _band(cr, [(5, 4), (3.5, 3), (2, 2), (1.2, 1), (-1, 0)]) if cr is not None else 0
            pu = 4 if (uo is not None and uo < 200) else 3 if (uo is not None and uo < 500) else 0
            points(c, t, max(pc, pu), f"Renal (creatinine {fmt(cr) if cr is not None else 'n/a'} mg/dL, "
                                      f"urine {fmt(uo) if uo is not None else 'n/a'} mL/day)")
        return t[0]


class GCS(Calculator):
    id = "glasgow_coma_scale"
    name = "Glasgow Coma Scale (GCS)"
    medcalc_ids = (21,)
    category = "severity"
    output_unit = "points"
    aliases = ("gcs", "glasgow coma scale", "glasgow coma score", "level of consciousness")
    description = "GCS = eye (1-4) + verbal (1-5) + motor (1-6). A component not supplied is given full points (MedCalc convention) and flagged."
    _EYE = ["eyes open spontaneously", "eye opening to verbal command", "eye opening to pain", "no eye opening"]
    _VERBAL = ["oriented", "confused", "inappropriate words", "incomprehensible sounds", "no verbal response"]
    _MOTOR = ["obeys commands", "localizes pain", "withdrawal from pain", "flexion to pain", "extension to pain",
              "no motor response"]
    parameters = schema([], eye=eparam("Best eye response.", _EYE), verbal=eparam("Best verbal response.", _VERBAL),
                        motor=eparam("Best motor response.", _MOTOR))

    def run(self, c: Ctx):
        t = [0]
        for name, opts, top in (("eye", self._EYE, 4), ("verbal", self._VERBAL, 5), ("motor", self._MOTOR, 6)):
            v = c.enum(name, default=opts[0], note=f"{name} response not provided/not testable: full score assumed",
                       aliases={"spontaneous": opts[0], "abnormal flexion to pain": "flexion to pain",
                                "decorticate": "flexion to pain", "decerebrate": "extension to pain",
                                "withdraws from pain": "withdrawal from pain", "localizes to pain": "localizes pain"})
            points(c, t, top - opts.index(v), f"{name.title()}: {v}")
        return t[0]


class SIRS(Calculator):
    id = "sirs_criteria"
    name = "SIRS Criteria"
    medcalc_ids = (51,)
    category = "diagnosis"
    output_unit = "criteria met"
    aliases = ("sirs", "systemic inflammatory response syndrome", "sepsis criteria")
    description = ("Number of SIRS criteria met (0-4): temperature >38 or <36 °C; HR >90; RR >20 or PaCO2 <32 mmHg; "
                   "WBC >12 or <4 x10^9/L or >10% bands.")
    parameters = schema([], temperature=qparam("Temperature.", "temperature"),
                        heart_rate=qparam("Heart rate.", "rate_per_min"),
                        respiratory_rate=qparam("Respiratory rate.", "rate_per_min"),
                        paco2=qparam("PaCO2.", "pressure"), wbc=qparam("White blood cell count.", "cell_count"),
                        bands_over_10_percent=bparam("Immature band forms > 10%."))

    def run(self, c: Ctx):
        temp = c.qty("temperature", required=False, lo=15, hi=46)
        hr = c.qty("heart_rate", required=False, lo=0)
        rr = c.qty("respiratory_rate", required=False, lo=0)
        pc = c.qty("paco2", required=False, positive=True)
        wbc = c.qty("wbc", required=False, lo=0)
        bands = c.flag("bands_over_10_percent")
        for v, lbl in ((temp, "temperature"), (hr, "heart rate"), (rr, "respiratory rate"), (pc, "PaCO2"), (wbc, "WBC")):
            if v is None:
                c.assume(f"{lbl} not provided: assumed normal")
        t = [0]
        points(c, t, 1 if (temp is not None and (temp > 38 or temp < 36)) else 0, "Temperature >38 or <36 °C")
        points(c, t, 1 if (hr is not None and hr > 90) else 0, "HR > 90")
        points(c, t, 1 if ((rr is not None and rr > 20) or (pc is not None and pc < 32)) else 0, "RR > 20 or PaCO2 < 32")
        points(c, t, 1 if ((wbc is not None and (wbc > 12 or wbc < 4)) or bands) else 0, "WBC > 12 or < 4 x10^9/L or bands > 10%")
        return t[0]


class CURB65(Calculator):
    id = "curb_65"
    name = "CURB-65 Score for Pneumonia Severity"
    medcalc_ids = (45,)
    category = "risk"
    output_unit = "points"
    aliases = ("curb-65", "curb65", "curb 65", "pneumonia severity", "cap severity")
    description = "CAP 30-day mortality: confusion, BUN > 19 mg/dL (urea > 7 mmol/L), RR >= 30, SBP < 90 or DBP <= 60, age >= 65 (1 each)."
    parameters = schema(["age"], age=qparam("Age.", "age"), confusion=bparam("New confusion."),
                        bun=qparam("Blood urea nitrogen.", "bun"),
                        respiratory_rate=qparam("Respiratory rate.", "rate_per_min"),
                        systolic_bp=qparam("Systolic BP.", "pressure"), diastolic_bp=qparam("Diastolic BP.", "pressure"))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        conf = c.flag("confusion")
        bun = c.qty("bun", required=False, lo=0)
        rr = c.qty("respiratory_rate", required=False, lo=0)
        s = c.qty("systolic_bp", required=False, positive=True)
        d = c.qty("diastolic_bp", required=False, positive=True)
        for v, lbl in ((bun, "BUN"), (rr, "respiratory rate"), (s, "systolic BP"), (d, "diastolic BP")):
            if v is None:
                c.assume(f"{lbl} not provided: assumed normal")
        if age is None:
            return None
        t = [0]
        points(c, t, 1 if conf else 0, "Confusion")
        points(c, t, 1 if (bun is not None and bun > 19) else 0, "BUN > 19 mg/dL")
        points(c, t, 1 if (rr is not None and rr >= 30) else 0, "RR >= 30")
        points(c, t, 1 if ((s is not None and s < 90) or (d is not None and d <= 60)) else 0, "SBP < 90 or DBP <= 60")
        points(c, t, 1 if age >= 65 else 0, f"Age {fmt(age)} >= 65")
        return t[0]


_PSI_FLAGS = {"nursing_home": (10, "Nursing home resident"), "neoplastic_disease": (30, "Neoplastic disease"),
              "liver_disease": (20, "Liver disease"), "chf": (10, "CHF"),
              "cerebrovascular_disease": (10, "Cerebrovascular disease"), "renal_disease": (10, "Renal disease"),
              "altered_mental_status": (20, "Altered mental status"), "pleural_effusion": (10, "Pleural effusion")}


class PSI(Calculator):
    id = "pneumonia_severity_index"
    name = "Pneumonia Severity Index (PSI/PORT)"
    medcalc_ids = (29,)
    category = "severity"
    output_unit = "points"
    aliases = ("psi", "port score", "pneumonia severity index", "fine score")
    description = ("CAP mortality points: age (female -10), nursing home +10, comorbidities (neoplasm 30, liver 20, CHF/"
                   "cerebrovascular/renal 10), exam (AMS 20, RR>=30 20, SBP<90 20, T<35 or >=40 15, HR>=125 10), "
                   "labs (pH<7.35 30, BUN>=30 20, Na<130 20, glucose>=250 10, Hct<30 10, PaO2<60 10, effusion 10).")
    parameters = schema(
        ["age", "sex"], age=qparam("Age.", "age"), sex=SEX,
        **{k: bparam(lbl + ".") for k, (_, lbl) in _PSI_FLAGS.items()},
        respiratory_rate=qparam("Respiratory rate.", "rate_per_min"), systolic_bp=qparam("Systolic BP.", "pressure"),
        temperature=qparam("Temperature.", "temperature"), heart_rate=qparam("Pulse.", "rate_per_min"),
        ph=nparam("Arterial pH.", 6.5, 8.0), bun=qparam("BUN.", "bun"), sodium=qparam("Sodium.", "sodium"),
        glucose=qparam("Glucose.", "glucose"), hematocrit=qparam("Haematocrit.", "percent"),
        pao2=qparam("PaO2.", "pressure"), oxygen_saturation=qparam("SaO2 (alternative to PaO2, <90% scores).", "percent"))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        sex = c.sex()
        f = {k: c.flag(k) for k in _PSI_FLAGS}
        rr = c.qty("respiratory_rate", required=False, lo=0)
        sbp = c.qty("systolic_bp", required=False, positive=True)
        temp = c.qty("temperature", required=False, lo=15, hi=46)
        hr = c.qty("heart_rate", required=False, lo=0)
        ph = c.num("ph", required=False, lo=6.5, hi=8.0)
        bun = c.qty("bun", required=False, lo=0)
        na = c.qty("sodium", required=False, positive=True)
        glu = c.qty("glucose", required=False, lo=0)
        hct = c.qty("hematocrit", required=False, lo=0, hi=100)
        pao2 = c.qty("pao2", required=False, positive=True)
        sat = c.qty("oxygen_saturation", required=False, lo=0, hi=100)
        for v, lbl in ((rr, "respiratory rate"), (sbp, "systolic BP"), (temp, "temperature"), (hr, "pulse"),
                       (ph, "pH"), (bun, "BUN"), (na, "sodium"), (glu, "glucose"), (hct, "haematocrit")):
            if v is None:
                c.assume(f"{lbl} not provided: assumed normal (0 points)")
        if pao2 is None and sat is None:
            c.assume("PaO2/SaO2 not provided: assumed normal (0 points)")
        if age is None or sex is None:
            return None
        t = [0]
        points(c, t, age, f"Age {fmt(age)}")
        points(c, t, -10 if sex == "female" else 0, f"Sex {sex}")
        for k, (p, lbl) in _PSI_FLAGS.items():
            points(c, t, p if f[k] else 0, lbl)
        points(c, t, 20 if (rr is not None and rr >= 30) else 0, "RR >= 30")
        points(c, t, 20 if (sbp is not None and sbp < 90) else 0, "SBP < 90")
        points(c, t, 15 if (temp is not None and (temp < 35 or temp > 39.9)) else 0, "Temperature < 35 or > 39.9 °C")
        points(c, t, 10 if (hr is not None and hr >= 125) else 0, "Pulse >= 125")
        points(c, t, 30 if (ph is not None and ph < 7.35) else 0, "pH < 7.35")
        points(c, t, 20 if (bun is not None and bun >= 30) else 0, "BUN >= 30 mg/dL")
        points(c, t, 20 if (na is not None and na < 130) else 0, "Sodium < 130")
        points(c, t, 10 if (glu is not None and glu >= 250) else 0, "Glucose >= 250 mg/dL")
        points(c, t, 10 if (hct is not None and hct < 30) else 0, "Haematocrit < 30%")
        hyp = (pao2 is not None and pao2 < 60) or (pao2 is None and sat is not None and sat < 90)
        points(c, t, 10 if hyp else 0, "PaO2 < 60 mmHg (or SaO2 < 90%)")
        return int(t[0]) if float(t[0]).is_integer() else t[0]


class ChildPugh(Calculator):
    id = "child_pugh"
    name = "Child-Pugh Score for Cirrhosis Mortality"
    medcalc_ids = (15,)
    category = "severity"
    output_unit = "points"
    aliases = ("child-pugh", "child pugh", "cpt", "cirrhosis severity", "child-turcotte-pugh")
    description = ("Cirrhosis severity (5-15; class A 5-6, B 7-9, C 10-15): bilirubin (<2, 2-3, >3 mg/dL), albumin "
                   "(>3.5, 2.8-3.5, <2.8 g/dL), INR (<1.7, 1.7-2.3, >2.3), ascites, encephalopathy (1-3 points each).")
    parameters = schema(["bilirubin", "albumin", "inr"], bilirubin=qparam("Total bilirubin.", "bilirubin"),
                        albumin=qparam("Serum albumin.", "albumin"), inr=nparam("INR.", 0.5, 20),
                        ascites=eparam("Ascites.", ["absent", "slight", "moderate"]),
                        encephalopathy=eparam("Hepatic encephalopathy.", ["none", "grade 1-2", "grade 3-4"]))

    def run(self, c: Ctx):
        bili = c.qty("bilirubin", lo=0)
        alb = c.qty("albumin", positive=True)
        inr = c.num("inr", lo=0.5, hi=20)
        asc = c.enum("ascites", default="absent", note="ascites not provided: assumed absent (1 point)",
                     aliases={"mild": "slight", "severe": "moderate", "moderate to severe": "moderate", "none": "absent"})
        enc = c.enum("encephalopathy", default="none", note="encephalopathy not provided: assumed none (1 point)",
                     aliases={"no encephalopathy": "none", "absent": "none", "mild": "grade 1-2",
                              "severe": "grade 3-4", "grade 1": "grade 1-2", "grade 2": "grade 1-2",
                              "grade 3": "grade 3-4", "grade 4": "grade 3-4"})
        if None in (bili, alb, inr):
            return None
        t = [0]
        points(c, t, 1 if bili < 2 else 2 if bili <= 3 else 3, f"Bilirubin {fmt(bili)} mg/dL")
        points(c, t, 1 if alb > 3.5 else 2 if alb >= 2.8 else 3, f"Albumin {fmt(alb)} g/dL")
        points(c, t, 1 if inr < 1.7 else 2 if inr <= 2.3 else 3, f"INR {fmt(inr)}")
        points(c, t, {"absent": 1, "slight": 2, "moderate": 3}[asc], f"Ascites {asc}")
        points(c, t, {"none": 1, "grade 1-2": 2, "grade 3-4": 3}[enc], f"Encephalopathy {enc}")
        return t[0]


class MELDNa(Calculator):
    id = "meld_na"
    name = "MELD Na (UNOS/OPTN)"
    medcalc_ids = (23,)
    category = "lab test"
    output_unit = "points"
    aliases = ("meld", "meld-na", "meld na", "meldna", "end-stage liver disease", "transplant priority")
    description = ("MELD(i) = 0.957 ln(Cr) + 0.378 ln(bili) + 1.120 ln(INR) + 0.643, x10 and rounded to tenth; if >11, "
                   "MELD-Na = MELD + 1.32 (137-Na) - 0.033 MELD (137-Na). Lab floors 1.0, Cr capped at 4 (or set to 4 "
                   "with dialysis x2/week or CVVHD), Na bounded 125-137, final capped at 40, rounded to integer.")
    parameters = schema(["creatinine", "bilirubin", "inr", "sodium"],
                        creatinine=qparam("Serum creatinine.", "creatinine"),
                        bilirubin=qparam("Total bilirubin.", "bilirubin"), inr=nparam("INR.", 0.5, 20),
                        sodium=qparam("Serum sodium.", "sodium"),
                        dialysis_twice_past_week=bparam("Dialysis at least twice in the past week."),
                        cvvhd_24h_past_week=bparam("CVVHD for >= 24 hours in the past week."))

    def run(self, c: Ctx):
        cr = c.qty("creatinine", positive=True, hi=SCR_MAX)
        bili = c.qty("bilirubin", positive=True)
        inr = c.num("inr", lo=0.5, hi=20)
        na = c.qty("sodium", positive=True)
        dia = c.flag("dialysis_twice_past_week")
        cvv = c.flag("cvvhd_24h_past_week")
        if None in (cr, bili, inr, na):
            return None
        if dia or cvv:
            cr = 4.0
            c.step("Dialysis/CVVHD in past week: creatinine set to 4.0 mg/dL")
        cr2, bili2, inr2 = min(max(cr, 1.0), 4.0), max(bili, 1.0), max(inr, 1.0)
        na2 = min(max(na, 125.0), 137.0)
        if (cr2, bili2, inr2, na2) != (cr, bili, inr, na):
            c.step(f"Bounded values: Cr {fmt(cr2)}, bilirubin {fmt(bili2)}, INR {fmt(inr2)}, Na {fmt(na2)}")
        mi = 0.957 * math.log(cr2) + 0.378 * math.log(bili2) + 1.120 * math.log(inr2) + 0.643
        meld = round(round(mi, 1) * 10, 1)
        c.step(f"MELD(i) = 0.957 ln({fmt(cr2)}) + 0.378 ln({fmt(bili2)}) + 1.120 ln({fmt(inr2)}) + 0.643 = {fmt(mi)}; "
               f"rounded to tenth x10 = {fmt(meld)}")
        if meld > 11:
            v = meld + 1.32 * (137 - na2) - 0.033 * meld * (137 - na2)
            c.step(f"MELD-Na = {fmt(meld)} + 1.32 x (137 - {fmt(na2)}) - 0.033 x {fmt(meld)} x (137 - {fmt(na2)}) = {fmt(v)}")
        else:
            v = meld
            c.step("MELD(i) <= 11: no sodium adjustment")
        v = min(v, 40.0)
        out = float(math.floor(v + 0.5))
        c.step(f"MELD-Na (capped at 40, rounded) = {fmt(out)}")
        return out


class GlasgowBlatchford(Calculator):
    id = "glasgow_blatchford"
    name = "Glasgow-Blatchford Bleeding Score (GBS)"
    medcalc_ids = (27,)
    category = "risk"
    output_unit = "points"
    aliases = ("gbs", "glasgow-blatchford", "blatchford", "upper gi bleed", "ugib")
    description = ("Upper GI bleed need-for-intervention score: BUN, haemoglobin (sex-specific), SBP, pulse >=100, melena, "
                   "syncope, hepatic disease, cardiac failure (0-23).")
    parameters = schema(["bun", "hemoglobin", "sex", "systolic_bp"], bun=qparam("BUN.", "bun"),
                        hemoglobin=qparam("Haemoglobin.", "hemoglobin"), sex=SEX,
                        systolic_bp=qparam("Systolic BP.", "pressure"), heart_rate=qparam("Pulse.", "rate_per_min"),
                        melena=bparam("Melena present."), syncope=bparam("Presented with syncope."),
                        hepatic_disease=bparam("History of hepatic disease."),
                        cardiac_failure=bparam("Cardiac failure present."))

    def run(self, c: Ctx):
        bun = c.qty("bun", lo=0)
        hb = c.qty("hemoglobin", positive=True)
        sex = c.sex()
        sbp = c.qty("systolic_bp", positive=True)
        hr = c.qty("heart_rate", required=False, lo=0)
        if hr is None:
            c.assume("pulse not provided: assumed < 100")
        f = {k: c.flag(k) for k in ("melena", "syncope", "hepatic_disease", "cardiac_failure")}
        if None in (bun, hb, sex, sbp):
            return None
        t = [0]
        points(c, t, 6 if bun > 70 else 4 if bun >= 28 else 3 if bun >= 22.4 else 2 if bun >= 18.2 else 0,
               f"BUN {fmt(bun)} mg/dL")
        if sex == "male":
            hp = 0 if hb >= 13 else 1 if hb >= 12 else 3 if hb >= 10 else 6
        else:
            hp = 0 if hb >= 12 else 1 if hb >= 10 else 6
        points(c, t, hp, f"Haemoglobin {fmt(hb)} g/dL ({sex})")
        points(c, t, 0 if sbp >= 110 else 1 if sbp >= 100 else 2 if sbp >= 90 else 3, f"SBP {fmt(sbp)}")
        points(c, t, 1 if (hr is not None and hr >= 100) else 0, "Pulse >= 100")
        points(c, t, 1 if f["melena"] else 0, "Melena")
        points(c, t, 2 if f["syncope"] else 0, "Syncope")
        points(c, t, 2 if f["hepatic_disease"] else 0, "Hepatic disease")
        points(c, t, 2 if f["cardiac_failure"] else 0, "Cardiac failure")
        return t[0]


_CCI_FLAGS = {"myocardial_infarction": (1, "Myocardial infarction"), "chf": (1, "CHF"),
              "peripheral_vascular_disease": (1, "Peripheral vascular disease"),
              "dementia": (1, "Dementia"), "chronic_pulmonary_disease": (1, "Chronic pulmonary disease"),
              "connective_tissue_disease": (1, "Connective tissue disease"),
              "peptic_ulcer_disease": (1, "Peptic ulcer disease"), "hemiplegia": (2, "Hemiplegia"),
              "moderate_severe_ckd": (2, "Moderate-severe CKD"), "leukemia": (2, "Leukaemia"),
              "lymphoma": (2, "Lymphoma"), "aids": (6, "AIDS")}


class CharlsonComorbidityIndex(Calculator):
    id = "charlson_comorbidity_index"
    name = "Charlson Comorbidity Index (CCI)"
    medcalc_ids = (32,)
    category = "risk"
    output_unit = "points"
    aliases = ("cci", "charlson", "charlson comorbidity index", "10-year survival comorbidity")
    description = ("Age-adjusted Charlson index: age (50-59 1 ... >=80 4), MI, CHF, PVD, CVA/TIA, dementia, CPD, CTD, "
                   "PUD (1 each), liver (mild 1, moderate-severe 3), diabetes (uncomplicated 1, end-organ 2), "
                   "hemiplegia, CKD, leukaemia, lymphoma (2), solid tumour (localized 2, metastatic 6), AIDS 6.")
    parameters = schema(
        ["age"], age=qparam("Age.", "age"),
        **{k: bparam(lbl + ".") for k, (_, lbl) in _CCI_FLAGS.items()},
        cerebrovascular_accident=bparam("Prior stroke (CVA)."), tia=bparam("Prior TIA."),
        liver_disease=eparam("Liver disease.", ["none", "mild", "moderate to severe"]),
        diabetes=eparam("Diabetes mellitus.", ["none or diet-controlled", "uncomplicated", "end-organ damage"]),
        solid_tumor=eparam("Solid tumour.", ["none", "localized", "metastatic"]))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        f = {k: c.flag(k) for k in _CCI_FLAGS}
        cva = c.flag("cerebrovascular_accident")
        tia = c.flag("tia")
        liver = c.enum("liver_disease", default="none", aliases={"moderate": "moderate to severe", "severe": "moderate to severe"})
        dm = c.enum("diabetes", default="none or diet-controlled",
                    aliases={"none": "none or diet-controlled", "diet-controlled": "none or diet-controlled",
                             "complicated": "end-organ damage"})
        tumor = c.enum("solid_tumor", default="none", aliases={"local": "localized", "metastases": "metastatic"})
        if age is None:
            return None
        t = [0]
        points(c, t, 4 if age >= 80 else 3 if age >= 70 else 2 if age >= 60 else 1 if age >= 50 else 0, f"Age {fmt(age)}")
        for k, (p, lbl) in _CCI_FLAGS.items():
            points(c, t, p if f[k] else 0, lbl)
        points(c, t, 1 if (cva or tia) else 0, "CVA or TIA")
        points(c, t, {"none": 0, "mild": 1, "moderate to severe": 3}[liver], f"Liver disease {liver}")
        points(c, t, {"none or diet-controlled": 0, "uncomplicated": 1, "end-organ damage": 2}[dm], f"Diabetes {dm}")
        points(c, t, {"none": 0, "localized": 2, "metastatic": 6}[tumor], f"Solid tumour {tumor}")
        return t[0]


class Centor(Calculator):
    id = "centor_mcisaac"
    name = "Centor Score (Modified/McIsaac) for Strep Pharyngitis"
    medcalc_ids = (20,)
    category = "severity"
    output_unit = "points"
    aliases = ("centor", "mcisaac", "modified centor", "strep pharyngitis", "strep throat")
    description = ("Group A strep pharyngitis likelihood: age 3-14 +1, 15-44 0, >=45 -1; tonsillar exudate/swelling, "
                   "tender/swollen anterior cervical nodes, temperature > 38 °C, absence of cough (+1 each).")
    parameters = schema(["age"], age=qparam("Age.", "age"),
                        tonsillar_exudate=bparam("Exudate or swelling on tonsils."),
                        anterior_cervical_nodes=bparam("Tender/swollen anterior cervical lymph nodes."),
                        temperature=qparam("Temperature (> 38 °C scores 1).", "temperature"),
                        cough_absent=bparam("Cough is ABSENT (true scores 1)."))

    def run(self, c: Ctx):
        age = c.qty("age", lo=0, hi=130)
        ex = c.flag("tonsillar_exudate")
        nodes = c.flag("anterior_cervical_nodes")
        temp = c.qty("temperature", required=False, lo=15, hi=46)
        if temp is None:
            c.assume("temperature not provided: assumed <= 38 °C")
        ca = c.flag("cough_absent", default=True,
                    note="cough not mentioned: assumed absent, so 'cough absent' is met (+1)")
        if age is None:
            return None
        t = [0]
        points(c, t, 1 if 3 <= age < 15 else -1 if age >= 45 else 0, f"Age {fmt(age)}")
        points(c, t, 1 if ex else 0, "Tonsillar exudate/swelling")
        points(c, t, 1 if nodes else 0, "Anterior cervical nodes")
        points(c, t, 1 if (temp is not None and temp > 38) else 0, "Temperature > 38 °C")
        points(c, t, 1 if ca else 0, "Cough absent")
        return t[0]


class FeverPAIN(Calculator):
    id = "feverpain"
    name = "FeverPAIN Score for Strep Pharyngitis"
    medcalc_ids = (33,)
    category = "diagnosis"
    output_unit = "points"
    aliases = ("feverpain", "fever pain", "streptococcal pharyngitis score")
    description = "Fever in past 24 h, Purulence, Attend rapidly (<=3 days), severely Inflamed tonsils, No cough/coryza (1 each, 0-5)."
    parameters = schema([], fever_past_24h=bparam("Fever in past 24 hours."), purulent_tonsils=bparam("Purulent tonsils."),
                        onset_within_3_days=bparam("Symptom onset <= 3 days."),
                        severe_tonsil_inflammation=bparam("Severely inflamed tonsils."),
                        no_cough_or_coryza=bparam("Absence of cough or coryza."))

    def run(self, c: Ctx):
        t = [0]
        for k in ("fever_past_24h", "purulent_tonsils", "onset_within_3_days", "severe_tonsil_inflammation",
                  "no_cough_or_coryza"):
            if k == "no_cough_or_coryza":
                # MedCalc convention: findings not mentioned are absent -> no cough/coryza -> criterion met
                v = c.flag(k, default=True, note="cough/coryza not mentioned: assumed absent, so 'absence of cough "
                                                  "or coryza' is met (+1)")
            else:
                v = c.flag(k)
            points(c, t, 1 if v else 0, k.replace("_", " "))
        return t[0]


CALCS = [ChildPugh, Centor, GCS, MELDNa, GlasgowBlatchford, APACHEII, PSI, CharlsonComorbidityIndex, FeverPAIN,
         SOFA, CURB65, SIRS]
