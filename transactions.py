"""On-time completion KPI based on one received-transaction cohort per month."""
from pathlib import Path
from io import BytesIO
import numpy as np
import pandas as pd
from .data import DataError
from .performance import ROSTER

COLUMNS=['department_id','month','received','completed_on_time','data_kind']
COLORS={'مرتفع':('#008B51','#F0FAF5'),'متوسط':('#E4AC09','#FFFBEE'),'منخفض':('#DF2948','#FFF4F6'),'بيانات ناقصة':('#7A8790','#F4F6F7'),'لا معاملات':('#7A8790','#F4F6F7')}

def validate(roster,data):
    if not set(ROSTER)<=set(roster) or not set(COLUMNS)<=set(data):raise DataError('استخدمي القالب؛ بعض الأعمدة المطلوبة غير موجودة')
    r=roster[ROSTER].copy();d=data[COLUMNS].copy()
    if r.empty or len(r)>1000 or len(d)>50000:raise DataError('عدد الأقسام أو السجلات غير صالح')
    for table,cols in [(r,ROSTER),(d,['department_id','month','data_kind'])]:
        for c in cols:
            if table[c].isna().any():raise DataError(f'{c}: قيمة مفقودة')
            table[c]=table[c].astype(str).str.strip()
            if table[c].eq('').any():raise DataError(f'{c}: قيمة فارغة')
    if r.department_id.duplicated().any() or r.duplicated(['administration','department']).any():raise DataError('القسم مكرر')
    if d.duplicated(['department_id','month']).any():raise DataError('سجل القسم والشهر مكرر')
    if not d.department_id.isin(r.department_id).all():raise DataError('قسم غير مسجل في قائمة الأقسام')
    if not d.month.str.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])').all():raise DataError('الشهر بصيغة YYYY-MM')
    if not d.data_kind.isin(['synthetic','real']).all() or d.data_kind.nunique()>1:raise DataError('استخدمي وسمًا موحدًا: synthetic أو real')
    for c in ['received','completed_on_time']:
        source=d[c].map(lambda x:np.nan if isinstance(x,str) and not x.strip() else x)
        n=pd.to_numeric(source,errors='coerce')
        if (source.notna() & n.isna()).any() or np.isinf(n).any() or (n<0).any() or (n>1e9).any() or ((n.dropna()%1)!=0).any():raise DataError('أعداد المعاملات أعداد صحيحة من صفر إلى مليار أو خلايا فارغة')
        d[c]=n.astype(float)
    if (d.completed_on_time>d.received).any():raise DataError('المنجز في الوقت المحدد لا يمكن أن يتجاوز المستلم لنفس مجموعة المعاملات')
    return r,d

def load_demo():
    p=Path(__file__).resolve().parents[1]/'data'
    return validate(pd.read_csv(p/'transaction_departments.csv'),pd.read_csv(p/'transactions.csv'))

def evaluate(roster,data,month,administration=None,green=90,yellow=70):
    if not 0<yellow<green<=100:raise DataError('يلزم أن يكون 0 < الأصفر < الأخضر ≤ 100')
    r,d=validate(roster,data)
    if administration is not None:r=r[r.administration==administration]
    out=r.merge(d[d.month==month],how='left',on='department_id');out['month']=month
    complete=out[['received','completed_on_time']].notna().all(axis=1)
    out['rate']=np.where(complete & (out.received>0),out.completed_on_time/out.received*100,np.nan)
    out['status']=['بيانات ناقصة' if not c else 'لا معاملات' if row.received==0 else 'مرتفع' if row.rate>=green else 'متوسط' if row.rate>=yellow else 'منخفض' for c,row in zip(complete,out.itertuples())]
    return out

def totals(rows):
    complete=rows[['received','completed_on_time']].notna().all(axis=1)
    valid=rows[complete]
    received=float(valid.received.sum());done=float(valid.completed_on_time.sum())
    return dict(received=received,completed_on_time=done,rate=done/received*100 if received else None,complete=int(complete.sum()),count=len(rows))

def export_excel(roster,data,summary=None,green=90,yellow=70):
    from openpyxl.styles import Font,PatternFill,Alignment
    sheets={}
    if summary is not None:
        s=summary.copy();s['green_threshold']=green;s['yellow_threshold']=yellow
        sheets['monthly_summary']=s
    sheets.update({'departments':roster,'transactions':data})
    b=BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as writer:
        for name,d in sheets.items():
            safe=d.map(lambda x:"'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x)
            safe.to_excel(writer,sheet_name=name,index=False);ws=writer.sheets[name]
            ws.freeze_panes='A2';ws.sheet_view.rightToLeft=True;ws.auto_filter.ref=ws.dimensions
            for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='285B60')
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width=29
                for c in col:c.alignment=Alignment(wrap_text=True,vertical='top')
    return b.getvalue()

def read_upload(file,roster):
    try:
        if len(file.getvalue())>20*1024**2:raise DataError('الحد الأقصى 20 MB')
        if file.name.lower().endswith('.csv'):return validate(roster,pd.read_csv(BytesIO(file.getvalue()),dtype={'department_id':str,'month':str}))
        sheets=pd.read_excel(BytesIO(file.getvalue()),sheet_name=None,dtype={'department_id':str,'month':str})
        if not {'departments','transactions'}<=set(sheets):raise DataError('يلزم ورقتا departments وtransactions')
        return validate(sheets['departments'],sheets['transactions'])
    except DataError:raise
    except Exception as exc:raise DataError('تعذر قراءة الملف؛ استخدمي القالب المرفق') from exc
