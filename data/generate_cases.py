"""Freeze synthetic engineering cases using a separate high-precision reference."""
from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path


def build() -> list[dict]:
    cases = []
    for family in range(30):
        ke = Decimal(str(.035 + .005 * (family % 6)))
        vd = Decimal(30 + 5*(family // 6))
        interval = Decimal([8,12,24][family % 3])
        with localcontext() as ctx:
            ctx.prec = 60
            decay = (-ke*interval).exp()
            limit = min(Decimal(40)*vd*(1-decay), Decimal(2)*vd*(1-decay)/decay)
            for variant, multiplier in enumerate([Decimal('.4'),Decimal('.8'),Decimal('1.2'),Decimal('2')]):
                dose = (limit*multiplier).quantize(Decimal('.0001'))
                peak = dose/vd/(1-decay)
                trough = peak*decay
                gold = 'BLOCK' if peak>=40 or trough>=2 else 'ALLOW'
                inputs = {'name':'gentamicin','dose_mg':float(dose),'interval_hr':float(interval),'route':'IV','administration':'bolus'}
                case = {'case_id':f'pk-{family:02}-{variant}', 'family_id':f'kinetics-{family:02}',
                        'reference_decision':gold, 'reference_peak':str(peak),'reference_trough':str(trough),
                        'regimen':inputs, 'kinetics':{'k_e':float(ke),'vd':float(vd)},
                        'input_issues':[], 'boundary':'structured_model_contract',
                        'reference_standard':'60-digit Decimal closed-form reference; clinician review pending'}
                cases.append(case)
        inputs={'name':'gentamicin','dose_mg':float(limit*Decimal('.6')),'interval_hr':float(interval),'route':'IV','administration':'bolus'}
        kind=family%5
        issues=[]
        if kind==0: inputs.pop('interval_hr')
        elif kind==1: inputs['frequency_per_day']=24/float(interval*2);issues=[{'input':'interval_hr','blocks':'validation','next':'resolve conflicting interval representations'}]
        elif kind==2: inputs['administration']='infusion';issues=[{'input':'model_applicability','blocks':'validation','next':'use a supported model'}]
        elif kind==3: inputs['route']='PO';issues=[{'input':'model_applicability','blocks':'validation','next':'use a supported model'}]
        else: inputs.pop('dose_mg')
        cases.append({'case_id':f'pk-{family:02}-missing','family_id':f'kinetics-{family:02}',
                      'reference_decision':'REVIEW','regimen':inputs,'kinetics':{'k_e':float(ke),'vd':float(vd)},
                      'input_issues':issues,'boundary':'structured_model_contract',
                      'reference_standard':'Explicit missing/conflicting/unsupported input contract; clinician review pending'})
    documentation=('Engineering rule, not a prescribing recommendation: supported model is a one-compartment IV bolus with supplied positive k_e (1/hour), Vd (L), dose per administration (mg), and interval (hours). '
                   'At steady state, peak = (dose/Vd)/(1-exp(-k_e*interval)); trough = peak*exp(-k_e*interval). '
                   'BLOCK if peak >=40 mg/L OR trough >=2 mg/L. ALLOW otherwise within this encoded constraint. '
                   'REVIEW for missing dose/interval, conflicting intervals, nonpositive or nonfinite inputs, non-IV route, or infusion. '
                   'These limits are test constants from the engine, with no claim of clinical validity. No dose recommendation is requested.')
    for case in cases:
        generation={'regimen':case['regimen'],'kinetics':case['kinetics']}
        case['generation_input']='Check this synthetic proposal against the encoded model constraints. This is an engineering test.\n'+json.dumps(generation,sort_keys=True)
        case['rule_documentation']=documentation
    return cases


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    data=''.join(json.dumps(c,sort_keys=True)+'\n' for c in build()).encode()
    if args.output.exists() and args.output.read_bytes()!=data: raise ValueError('Frozen cases already differ')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(data)
    print(json.dumps({'n':150,'counts':{'BLOCK':60,'ALLOW':60,'REVIEW':30},'sha256':hashlib.sha256(data).hexdigest()}))


if __name__=='__main__':main()
