"""Strict, atomic import of complete datasets. Monetary basis: cash, SAR, net of VAT."""
from pathlib import Path
from io import BytesIO
import numpy as np
import pandas as pd

SCHEMA = {
 'revenues': ['source_id','source','year','as_of','target','achieved','data_kind'],
 'assets': ['asset_id','name','zone','asset_type','area_m2','status','market_rate','occupancy','delay_months','ease','risk','baseline_annual','data_kind'],
 'contracts': ['contract_id','asset_id','annual_rent','renewal_date','status','data_kind'],
 'receivables': ['invoice_id','contract_id','due_date','amount','collected','baseline_expected','recovery_rate','data_kind'],
}
NUMERIC = {
 'revenues':['year','target','achieved'],
 'assets':['area_m2','market_rate','occupancy','delay_months','ease','risk','baseline_annual'],
 'contracts':['annual_rent'],
 'receivables':['amount','collected','baseline_expected','recovery_rate'],
}
IDS = {'revenues':'source_id','assets':'asset_id','contracts':'contract_id','receivables':'invoice_id'}

class DataError(ValueError):
    pass

def validate(tables):
    if set(tables) != set(SCHEMA):
        raise DataError('يلزم توفير الجداول الأربعة كاملة: ' + ', '.join(SCHEMA))
    out = {}
    for name, cols in SCHEMA.items():
        d = tables[name].copy()
        if not set(cols).issubset(d.columns):
            raise DataError(f'{name}: أعمدة مفقودة: {set(cols)-set(d.columns)}')
        d = d[cols]
        if len(d)>50000:
            raise DataError(f'{name}: الحد الأقصى 50000 سجل')
        if d.isna().any().any():
            raise DataError(f'{name}: توجد قيم فارغة')
        for c in cols:
            if c not in NUMERIC[name]:
                d[c]=d[c].astype(str).str.strip()
                if d[c].eq('').any():
                    raise DataError(f'{name}.{c}: قيمة نصية فارغة')
        if d[IDS[name]].duplicated().any():
            raise DataError(f'{name}: معرفات مكررة؛ صحح المصدر قبل الاستيراد')
        for c in NUMERIC[name]:
            d[c] = pd.to_numeric(d[c],errors='coerce')
            if not np.isfinite(d[c]).all() or (d[c]<0).any() or (d[c]>1e15).any():
                raise DataError(f'{name}.{c}: يجب أن تكون الأرقام غير سالبة وألا تتجاوز 10^15')
        if not d.data_kind.isin(['synthetic','real']).all():
            raise DataError(f'{name}: data_kind يجب أن يكون synthetic أو real')
        out[name]=d
    r,a,c,v=(out[n] for n in SCHEMA)
    kinds=set().union(*(set(t.data_kind) for t in out.values()))
    if len(kinds)!=1:
        raise DataError('لا يمكن خلط البيانات الحقيقية والتجريبية')
    if r.empty or r.year.nunique()!=1 or r.as_of.nunique()!=1:
        raise DataError('الإيرادات مطلوبة لسنة واحدة وتاريخ لقطة موحد')
    if not r.year.between(2000,2100).all() or not (r.year%1==0).all():
        raise DataError('سنة غير صالحة')
    for name,col in [('revenues','as_of'),('contracts','renewal_date'),('receivables','due_date')]:
        d=out[name]
        parsed=pd.to_datetime(d[col],format='%Y-%m-%d',errors='coerce')
        if parsed.isna().any():
            raise DataError(f'{name}.{col}: استخدم YYYY-MM-DD')
        d[col]=parsed.dt.strftime('%Y-%m-%d')
    if pd.Timestamp(r.as_of.iloc[0]).year!=int(r.year.iloc[0]):
        raise DataError('تاريخ اللقطة خارج السنة المالية')
    for col in ['occupancy','ease','risk']:
        if not a[col].between(0,1).all():
            raise DataError(f'assets.{col}: القيمة بين 0 و1')
    if not v.recovery_rate.between(0,1).all():
        raise DataError('نسبة الاسترداد بين 0 و1')
    if not (a.delay_months%1==0).all() or (a.delay_months>60).any():
        raise DataError('مهلة التنفيذ عدد صحيح من 0 إلى 60 شهرًا')
    if not a.status.isin(['vacant','leased','restricted']).all() or not c.status.isin(['active','expired']).all():
        raise DataError('حالة أصل أو عقد غير معروفة')
    if not c.asset_id.isin(a.asset_id).all() or not v.contract_id.isin(c.contract_id).all():
        raise DataError('مرجع عقد أو أصل غير موجود')
    active=c[c.status=='active']
    if active.asset_id.duplicated().any():
        raise DataError('يدعم النموذج عقدًا نشطًا واحدًا لكل أصل')
    if not active.asset_id.isin(a.loc[a.status=='leased','asset_id']).all():
        raise DataError('العقد النشط يتطلب أصلًا بحالة leased')
    if not a.loc[a.status=='leased','asset_id'].isin(active.asset_id).all():
        raise DataError('الأصل المؤجر يتطلب عقدًا نشطًا')
    if (v.collected>v.amount).any() or (v.baseline_expected>v.amount-v.collected).any():
        raise DataError('التحصيل أو التحصيل الأساسي المتوقع يتجاوز الرصيد')
    return out

def load_demo():
    root=Path(__file__).resolve().parents[1]/'data'
    return validate({n:pd.read_csv(root/f'{n}.csv',dtype=str) for n in SCHEMA})

def read_uploads(files):
    """One workbook with four sheets OR exactly four named CSV files. No demo fallback."""
    if not files:
        raise DataError('اختر ملف Excel أو ملفات CSV الأربعة')
    if any(len(f.getvalue())>20*1024*1024 for f in files):
        raise DataError('الحد الأقصى لكل ملف 20 MB')
    try:
        if len(files)==1 and files[0].name.lower().endswith('.xlsx'):
            raw=pd.read_excel(BytesIO(files[0].getvalue()),sheet_name=None,dtype=str)
            if set(SCHEMA)-set(raw):
                raise DataError('ملف Excel لا يحتوي الأوراق الأربع المطلوبة')
            tables={n:raw[n] for n in SCHEMA}
        else:
            names=[Path(f.name).stem for f in files]
            if len(names)!=4 or set(names)!=set(SCHEMA):
                raise DataError('أسماء CSV المطلوبة: '+', '.join(n+'.csv' for n in SCHEMA))
            tables={Path(f.name).stem:pd.read_csv(BytesIO(f.getvalue()),dtype=str) for f in files}
        return validate(tables)
    except DataError:
        raise
    except Exception as e:
        raise DataError('تعذر قراءة الملفات؛ تحقق من الصيغة وترميز UTF-8') from e
