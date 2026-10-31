"""Portable Python PDF and Excel exports; Arabic font bundled with its license."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import arabic_reshaper
from bidi.algorithm import get_display
from .engine import metrics

LABELS={'opportunity_id':'معرف الفرصة','asset_id':'معرف الأصل','title':'الفرصة','kind':'النوع','annual_potential':'إضافي سنوي محتمل (ريال)','one_off_potential':'تحصيل لمرة واحدة (ريال)','current_year':'إضافي حتى نهاية السنة (ريال)','cap':'سقف الإمكانات (ريال)','active_fraction':'جزء السنة المتاح','ease':'سهولة التنفيذ','risk':'المخاطر','reason':'الدليل','formula':'الحساب والافتراضات','review':'المراجعة المطلوبة','group':'مجموعة التعارض','score':'درجة الأولوية','scenario_annual':'سنوي في السيناريو (ريال)','scenario_one_off':'تحصيل في السيناريو (ريال)','scenario_current':'إضافي في السيناريو (ريال)'}

def provenance(t):
    raw=''.join(n+df.to_csv(index=False) for n,df in sorted(t.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def source_label(t):
    return 'Synthetic Data - بيانات تجريبية لا تمثل أرقام أمانة حائل' if t['revenues'].data_kind.iloc[0]=='synthetic' else 'بيانات مرفوعة من المستخدم؛ لم يتم التحقق الخارجي منها'

def workbook(t,opps=None,result=None):
    buf=BytesIO()
    sheets={}
    if result is not None:
        m=metrics(t)
        sheets['ملخص']=pd.DataFrame([
            ['النظام','منصة الإيرادات والأداء المؤسسي'],['المصدر',source_label(t)],
            ['تاريخ اللقطة',t['revenues'].as_of.iloc[0]],['بصمة البيانات',provenance(t)],
            ['طريقة التقدير','قواعد تحليلية؛ قيم تقديرية وليست توقعات مؤكدة'],
            ['أساس القياس','نقدي، ريال سعودي، قبل الضريبة، دون خصم تكاليف التنفيذ'],
            ['المستهدف',m['target']],['المحقق',m['achieved']],['الفجوة',m['gap']],
            ['السيناريو',result['mode']],['الإضافي حتى نهاية السنة',result['additional']],
            ['الفجوة بعد الفرص',result['remaining']],['فائض السيناريو',result['surplus']],
            ['إضافي سنوي متكرر',result['annual']],['تحصيل لمرة واحدة',result['one_off']],
            ['تنبيه','السنوي والتحصيل لا يجمعان لسد الفجوة؛ استخدم الإضافي حتى نهاية السنة فقط'],
        ],columns=['المؤشر','القيمة'])
        sheets['الفرص المختارة']=result['rows'].rename(columns=LABELS)
    if opps is not None:sheets['الفرص المكتشفة']=opps.rename(columns=LABELS)
    sheets.update(t)
    with pd.ExcelWriter(buf,engine='openpyxl') as writer:
        for name,df in sheets.items():
            # Neutralize formula injection in all imported text while keeping numeric cells numeric.
            safe=df.map(lambda x: "'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x)
            safe.to_excel(writer,sheet_name=name,index=False)
            ws=writer.sheets[name];ws.sheet_view.rightToLeft=True;ws.freeze_panes='A2'
            ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:
                cell.fill=PatternFill('solid',fgColor='12614F');cell.font=Font(color='FFFFFF',bold=True)
                cell.alignment=Alignment(horizontal='right',wrap_text=True)
            ws.row_dimensions[1].height=32
            for col in ws.columns:
                longest=max((len(str(c.value or '')) for c in col),default=12)
                ws.column_dimensions[get_column_letter(col[0].column)].width=min(65,max(18,longest+2))
                for c in col[1:]:
                    c.alignment=Alignment(horizontal='right',vertical='top',wrap_text=True)
                    if isinstance(c.value,(float,int)):c.number_format='#,##0.00'
            for row in range(2,ws.max_row+1):ws.row_dimensions[row].height=48
    return buf.getvalue()

def pdf_report(t,opps,result):
    font=Path(__file__).resolve().parents[1]/'assets/DejaVuSans.ttf'
    if 'Arabic' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('Arabic',str(font)))
    buf=BytesIO();c=canvas.Canvas(buf,pagesize=(595.28,841.89));c.setTitle('Municipal Revenue and Performance')
    W,H=595.28,841.89; y=0;page=0
    def rtl(s):return get_display(arabic_reshaper.reshape(str(s)))
    def newpage():
        nonlocal y,page
        if page:c.showPage()
        page+=1
        c.setFillColor(HexColor('#12614F'));c.rect(0,H-86,W,86,fill=1,stroke=0)
        c.setFillColor(HexColor('#FFFFFF'));c.setFont('Arabic',17)
        c.drawRightString(W-38,H-39,rtl('منصة الإيرادات والأداء المؤسسي'))
        c.setFont('Arabic',10);c.drawRightString(W-38,H-63,rtl('نموذج أولي مخصص لسياق أمانة منطقة حائل'))
        c.setFillColor(HexColor('#64736B'));c.setFont('Arabic',8)
        c.drawRightString(W-38,25,rtl(f'صفحة {page} | تقديرات للمراجعة وليست إيرادات مضمونة'))
        y=H-111
    def paragraph(text,size=10,color='#233C33',space=8):
        nonlocal y
        words=str(text).split();lines=[];line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if pdfmetrics.stringWidth(rtl(candidate),'Arabic',size)>W-80 and line:
                lines.append(line);line=word
            else:line=candidate
        if line:lines.append(line)
        for line in lines:
            if y<65:newpage()
            c.setFillColor(HexColor(color));c.setFont('Arabic',size);c.drawRightString(W-40,y,rtl(line));y-=size*1.65
        y-=space
    newpage();m=metrics(t)
    paragraph(source_label(t),11,'#976725')
    paragraph(f"تاريخ اللقطة: {t['revenues'].as_of.iloc[0]} | بصمة البيانات: {provenance(t)}")
    paragraph('الملخص التنفيذي',14,'#12614F')
    for label,val in [('المستهدف السنوي',m['target']),('الإيرادات المحققة',m['achieved']),('الفجوة الحالية',m['gap']),('الإضافي الممكن حتى نهاية السنة',result['additional']),('الفجوة المتبقية في السيناريو',result['remaining']),('الفائض في السيناريو',result['surplus'])]:
        paragraph(f'{label}: {val:,.2f} ريال سعودي',12)
    paragraph(f"السيناريو: {result['mode']} | عدد الفرص المختارة: {len(result['rows'])}")
    paragraph('يعتمد التقدير على قواعد معلنة ومدخلات المستخدم. تعتمد جودة النتائج على صحة المدخلات والافتراضات. أساس القياس نقدي قبل الضريبة ودون خصم تكاليف التنفيذ.')
    paragraph('الإيراد السنوي يمثل سنة تشغيل كاملة. يسد الفجوة فقط الإيراد الإضافي للفترة المتبقية، بعد مهلة التنفيذ، مع تحصيل المستحقات لمرة واحدة. الإيرادات الاعتيادية القادمة غير متنبأ بها هنا.')
    paragraph('التوصية: مراجعة الفرص المختارة بحسب ترتيب الأولوية، واعتماد التثمين والملكية والعقود وخطة التحصيل قبل التنفيذ. إذا بقيت فجوة فلا يعني مجموع الإمكانات السنوية أنها سُدّت.')
    newpage();paragraph('الفرص المكتشفة وأدلة التوصية',14,'#12614F')
    selected=set(result['rows'].opportunity_id)
    for row in opps.itertuples():
        if y<285:newpage()
        paragraph(f"{row.title} | {row.opportunity_id} | {'مختارة' if row.opportunity_id in selected else 'غير مختارة'}",12,'#12614F')
        paragraph(f'الأولوية: {row.score:.1f}/100 | سهولة التنفيذ: {row.ease:.0%} | المخاطر: {row.risk:.0%}')
        paragraph(row.reason);paragraph(row.formula)
        paragraph(f'السنوي الإضافي: {row.annual_potential:,.2f} ريال؛ التحصيل لمرة واحدة: {row.one_off_potential:,.2f} ريال؛ حتى نهاية السنة (متوسط): {row.current_year:,.2f} ريال.')
        if row.opportunity_id in selected:
            value=result['rows'].set_index('opportunity_id').loc[row.opportunity_id,'scenario_current']
            paragraph(f'مساهمة الفرصة في السيناريو المختار: {value:,.2f} ريال')
        paragraph('المراجعة: '+row.review,9)
    newpage();paragraph('المنهج والافتراضات',14,'#12614F')
    for text in [
        'الأصل الشاغر: المساحة × المعدل السنوي المرجعي × الإشغال المفترض، ناقص الإيراد الأساسي المدرج. يستبعد الأصل المقيد أو المرتبط بعقد نشط.',
        'التجديد: قيمة السوق المفترضة ناقص الأعلى بين الإيجار القائم والإيراد الأساسي. لا يحتسب الأثر قبل تاريخ التجديد أو انتهاء مهلة التنفيذ، أيهما أبعد.',
        'التحصيل: الرصيد غير المحصل × نسبة استرداد مفترضة للفترة المتبقية، ناقص التحصيل الأساسي المتوقع. الرصيد المحصل سابقًا والمستحق غير الحال مستبعدان.',
        'السيناريو المتحفظ = 70% من الإمكانات الإضافية الأساسية؛ المتوسط = 100%؛ المتفائل = 120%، مع سقف السوق عند إشغال كامل أو الرصيد غير المحصل بعد الأساس. هذه معاملات حساسية وليست فواصل ثقة.',
        'جزء السنة = عدد الأيام المتاحة بعد تاريخ اللقطة أو بدء التنفيذ حتى نهاية السنة ÷ أيام السنة. يفترض توزيع الإيجار نقديًا على الأيام، ويحتاج مواءمة مع جدول السداد الحقيقي.',
        'الترتيب = 50% للإضافي الممكن في السنة نسبة لأكبر فرصة + 30% لسهولة التنفيذ + 20% لانخفاض المخاطر. المخاطر والسهولة افتراضات؛ مخاطر التحصيل ترتفع مع عمر الدين. الدرجة نسبية وتتغير بتغير مجموعة الفرص.',
        'منع التكرار: معرف ثابت لكل أصل أو عقد أو فاتورة؛ منع اختيار أكثر من فرصة في مجموعة الأصل؛ استيراد ذري يرفض المعرفات المكررة. اختلاف المعرفات لنفس العقار يحتاج تدقيقًا بشريًا.',
        'قبل الاستخدام الفعلي: بيانات موثقة، مطابقة المحقق مع دفتر الأستاذ، إثبات عدم تداخل الفواتير مع إيرادات مستقبلية، مراجعة الأسعار والموافقات، ثم صلاحيات وسجل تدقيق وحماية بيانات واختبار قبول.'
    ]:paragraph(text)
    c.save();return buf.getvalue()
