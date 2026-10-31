"""Deterministic explainable opportunity engine. No random scores, no trained ML."""
import calendar
import math
import numpy as np
import pandas as pd
from .data import validate

SCENARIOS={'متحفظ':0.7,'متوسط':1.0,'متفائل':1.2}
COLUMNS=['opportunity_id','asset_id','title','kind','annual_potential','one_off_potential','current_year','cap','active_fraction','ease','risk','reason','formula','review','group','score']

def metrics(tables):
    r=tables['revenues']
    target=float(r.target.sum()); achieved=float(r.achieved.sum())
    return {'target':target,'achieved':achieved,'gap':max(0,target-achieved),
            'surplus':max(0,achieved-target),'achievement':achieved/target*100 if target else None}

def fraction(start, as_of):
    end=pd.Timestamp(year=as_of.year+1,month=1,day=1)
    start=max(pd.Timestamp(start),as_of+pd.Timedelta(days=1))
    return max(0,(end-start).days)/(366 if calendar.isleap(as_of.year) else 365)

def detect(tables):
    t=validate(tables)
    as_of=pd.Timestamp(t['revenues'].as_of.iloc[0]); records=[]
    assets=t['assets'].set_index('asset_id')
    def add(oid,aid,title,kind,annual,once,cap,frac,ease,risk,reason,formula,review,group):
        if annual+once<=0: return
        records.append(dict(zip(COLUMNS[:-1],[oid,aid,title,kind,annual,once,(annual*frac+once),cap,frac,ease,risk,reason,formula,review,group])))
    for aid,a in assets.iterrows():
        if a.status!='vacant': continue
        gross=a.area_m2*a.market_rate
        net=max(0,gross*a.occupancy-a.baseline_annual)
        f=fraction(as_of+pd.DateOffset(months=int(a.delay_months)),as_of)
        add('LEASE:'+aid,aid,'استثمار '+a['name'],'تأجير أصل',net,0,max(0,gross-a.baseline_annual),f,a.ease,a.risk,
            f'الأصل {aid} شاغر؛ المساحة {a.area_m2:,.0f} م²؛ معدل مرجعي مدخل {a.market_rate:,.0f} ريال/م²/سنة.',
            f'({a.area_m2:,.0f} × {a.market_rate:,.0f} × {a.occupancy:.0%}) − {a.baseline_annual:,.0f} = {net:,.0f} ريال/سنة؛ مهلة {a.delay_months:.0f} أشهر.',
            'تثمين السوق والتحقق من الملكية والاستخدام والموافقات والطرح؛ لا يعني الترشيح السماح بالتنفيذ','ASSET:'+aid)
    for c in t['contracts'].itertuples():
        if c.status!='active': continue
        a=assets.loc[c.asset_id]
        if a.status=='restricted': continue
        renewal=pd.Timestamp(c.renewal_date)
        # Only upcoming renewals in next 12 months; never silently rewrite an existing lease.
        if not as_of<renewal<=as_of+pd.DateOffset(years=1): continue
        gross=a.area_m2*a.market_rate
        base=max(c.annual_rent,a.baseline_annual)
        delta=max(0,gross*a.occupancy-base)
        f=fraction(max(renewal,as_of+pd.DateOffset(months=int(a.delay_months))),as_of)
        add('RENEW:'+c.contract_id,c.asset_id,'مراجعة تجديد '+a['name'],'تجديد عقد',delta,0,max(0,gross-base),f,a.ease,a.risk,
            f'العقد {c.contract_id} يتجدد {c.renewal_date}؛ الإيجار الحالي {c.annual_rent:,.0f} ريال؛ المرجع المدخل أعلى.',
            f'({a.area_m2:,.0f} × {a.market_rate:,.0f} × {a.occupancy:.0%}) − max({c.annual_rent:,.0f}, {a.baseline_annual:,.0f}) = {delta:,.0f} ريال/سنة.',
            'مراجعة شروط التجديد والتقييم والاعتمادات؛ لا تعديل آلي للعقد','ASSET:'+c.asset_id)
    for v in t['receivables'].itertuples():
        if pd.Timestamp(v.due_date)>as_of or (as_of.month==12 and as_of.day==31): continue
        remaining=v.amount-v.collected
        # recovery_rate is incremental intervention TOTAL collection probability in remaining year.
        gain=max(0,remaining*v.recovery_rate-v.baseline_expected)
        aid=t['contracts'].set_index('contract_id').loc[v.contract_id,'asset_id']
        days=(as_of-pd.Timestamp(v.due_date)).days
        risk=min(.9,.25+days/730)
        add('COLLECT:'+v.invoice_id,aid,'تحسين تحصيل '+v.invoice_id,'تحصيل مستحق',0,gain,max(0,remaining-v.baseline_expected),0,.85,risk,
            f'الفاتورة {v.invoice_id} متأخرة {days} يومًا؛ الرصيد {remaining:,.0f} ريال؛ لم يُحتسب المحصل سابقًا.',
            f'({remaining:,.0f} × {v.recovery_rate:.0%}) − {v.baseline_expected:,.0f} = {gain:,.0f} ريال لمرة واحدة؛ النسبة تخص الفترة المتبقية.',
            'مطابقة الرصيد والنزاعات وعدم سبق إدراجه ضمن المحقق؛ اعتماد خطة التحصيل','INVOICE:'+v.invoice_id)
    out=pd.DataFrame(records,columns=COLUMNS)
    if out.empty:return out
    value=out.current_year
    out['score']=np.round(100*(.5*value/max(float(value.max()),1)+.3*out.ease+.2*(1-out.risk)),1)
    return out.sort_values(['score','opportunity_id'],ascending=[False,True]).reset_index(drop=True)

def scenario(opps,selected,mode,gap):
    if mode not in SCENARIOS: raise ValueError('سيناريو غير معروف')
    if not math.isfinite(gap) or gap<0: raise ValueError('فجوة غير صالحة')
    if opps.opportunity_id.duplicated().any(): raise ValueError('معرف فرصة مكرر')
    selected=list(dict.fromkeys(selected))
    if set(selected)-set(opps.opportunity_id): raise ValueError('فرصة غير موجودة')
    rows=opps[opps.opportunity_id.isin(selected)].copy()
    if rows.group.duplicated().any():raise ValueError('فرص متعارضة على المورد نفسه')
    factor=SCENARIOS[mode]
    rows['scenario_annual']=np.minimum(rows.annual_potential*factor,rows.cap).round(2)
    rows['scenario_one_off']=np.minimum(rows.one_off_potential*factor,rows.cap).round(2)
    rows['scenario_current']=(rows.scenario_annual*rows.active_fraction+rows.scenario_one_off).round(2)
    total=float(rows.scenario_current.sum())
    return {'mode':mode,'additional':total,'remaining':max(0,gap-total),'surplus':max(0,total-gap),
            'annual':float(rows.scenario_annual.sum()),'one_off':float(rows.scenario_one_off.sum()),'rows':rows}

def recommend(opps,gap):
    """Greedy ranked shortlist, not a claim of global optimization."""
    chosen=[]; groups=set(); amount=0
    for row in opps.itertuples():
        if amount>=gap:break
        if row.current_year<=0 or row.group in groups:continue
        chosen.append(row.opportunity_id);groups.add(row.group);amount+=row.current_year
    return chosen
