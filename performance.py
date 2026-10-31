"""Monthly department performance: deterministic KPI scoring, no employee ranking."""
from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
from .data import DataError

ROSTER=['department_id','administration','department']
FIELDS=['completion','timeliness','quality']
LABELS={'completion':'إنجاز الخطة','timeliness':'الالتزام بالوقت','quality':'جودة المخرجات'}
WEIGHTS={'completion':.5,'timeliness':.3,'quality':.2}
COLUMNS=['department_id','month']+[f'{k}_{v}' for k in FIELDS for v in ['target','actual']]+['data_kind']
STATUS_COLORS={'جيد':'#197449','متوسط':'#AF790B','يحتاج تدخل':'#B63738','بيانات ناقصة':'#667581'}

def validate_performance(roster,metrics):
    r=roster.copy();m=metrics.copy()
    if not set(ROSTER)<=set(r) or not set(COLUMNS)<=set(m):raise DataError('أعمدة الأداء المطلوبة ناقصة؛ استخدم قالب الأداء')
    r=r[ROSTER];m=m[COLUMNS]
    if r.empty or len(r)>1000 or len(m)>50000:raise DataError('يلزم قسم واحد على الأقل؛ الحد 1000 قسم و50000 سجل')
    for d,cols in [(r,ROSTER),(m,['department_id','month','data_kind'])]:
        for col in cols:
            if d[col].isna().any():raise DataError(f'{col}: قيمة مفقودة')
            d[col]=d[col].astype(str).str.strip()
            if d[col].eq('').any():raise DataError(f'{col}: قيمة فارغة')
    if r.department_id.duplicated().any() or r.duplicated(['administration','department']).any():raise DataError('معرف أو اسم قسم مكرر ضمن الإدارة')
    if m.duplicated(['department_id','month']).any():raise DataError('لا يجوز تكرار سجل القسم في الشهر نفسه')
    if not m.department_id.isin(r.department_id).all():raise DataError('يوجد سجل أداء لقسم غير موجود')
    if not m.month.str.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])').all():raise DataError('الشهر بصيغة YYYY-MM بين 2000 و2099')
    if not m.data_kind.isin(['synthetic','real']).all() or m.data_kind.nunique()>1:raise DataError('لا تخلط البيانات الحقيقية والتجريبية في الأداء')
    for k in FIELDS:
        for v in ['target','actual']:
            col=f'{k}_{v}';original=m[col].map(lambda value: np.nan if isinstance(value,str) and not value.strip() else value)
            nums=pd.to_numeric(original,errors='coerce')
            if (original.notna() & nums.isna()).any() or np.isinf(nums).any() or (nums<0).any() or (nums>100).any():raise DataError(f'{col}: نسبة من 0 إلى 100 أو خلية فارغة')
            if v=='target' and nums.eq(0).any():raise DataError('المستهدف يجب أن يكون أكبر من صفر؛ استخدم خلية فارغة عند عدم توفره')
            m[col]=nums.astype(float)
    return r,m

def load_performance():
    root=Path(__file__).resolve().parents[1]/'data'
    return validate_performance(pd.read_csv(root/'departments.csv'),pd.read_csv(root/'performance.csv'))

def evaluate(roster,metrics,month,administration=None,green=90,yellow=70):
    if not 0<yellow<green<=100:raise DataError('الحدود المطلوبة: 0 < الأصفر < الأخضر ≤ 100')
    r,m=validate_performance(roster,metrics)
    if administration is not None:r=r[r.administration==administration]
    out=r.merge(m[m.month==month],on='department_id',how='left')
    out['month']=month
    scores=[]
    for _,row in out.iterrows():
        complete=all(pd.notna(row[f'{k}_{v}']) for k in FIELDS for v in ['target','actual'])
        score=sum(min(100,row[f'{k}_actual']/row[f'{k}_target']*100)*WEIGHTS[k] for k in FIELDS) if complete else np.nan
        scores.append(score)
    out['score']=scores
    out['status']=out.score.map(lambda s:'بيانات ناقصة' if pd.isna(s) else 'جيد' if s>=green else 'متوسط' if s>=yellow else 'يحتاج تدخل')
    def reason(row):
        missing=[LABELS[k] for k in FIELDS if pd.isna(row[f'{k}_target']) or pd.isna(row[f'{k}_actual'])]
        if missing:return 'لم يكتمل إدخال: '+'، '.join(missing)
        weak=[f'{LABELS[k]}: {row[f"{k}_actual"]:g}% من مستهدف {row[f"{k}_target"]:g}%' for k in FIELDS if row[f'{k}_actual']<row[f'{k}_target']]
        return '؛ '.join(weak) if weak else 'تحققت جميع المستهدفات المحددة للشهر'
    out['reason']=out.apply(reason,axis=1) if len(out) else pd.Series(dtype=str)
    return out

def performance_excel(roster,metrics,summary=None):
    from openpyxl.styles import Font,PatternFill,Alignment
    buf=BytesIO();sheets={}
    if summary is not None:sheets['monthly_summary']=summary
    sheets.update({'departments':roster,'performance':metrics})
    with pd.ExcelWriter(buf,engine='openpyxl') as writer:
        for n,d in sheets.items():
            safe=d.map(lambda x:"'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x)
            safe.to_excel(writer,sheet_name=n,index=False)
            ws=writer.sheets[n];ws.sheet_view.rightToLeft=True;ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
            for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='123D35')
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width=28
                for c in col:c.alignment=Alignment(wrap_text=True,vertical='top')
    return buf.getvalue()

def import_performance(file,current_roster):
    try:
        if len(file.getvalue())>20*1024**2:raise DataError('حجم الملف يتجاوز 20 MB')
        if file.name.lower().endswith('.csv'):
            return validate_performance(current_roster,pd.read_csv(BytesIO(file.getvalue()),dtype={'department_id':str,'month':str}))
        sheets=pd.read_excel(BytesIO(file.getvalue()),sheet_name=None,dtype={'department_id':str,'month':str})
        if not {'departments','performance'}<=set(sheets):raise DataError('يلزم ورقتا departments وperformance')
        return validate_performance(sheets['departments'],sheets['performance'])
    except DataError:raise
    except Exception as exc:raise DataError('تعذر قراءة ملف الأداء؛ استخدم القالب') from exc
