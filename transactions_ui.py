from pathlib import Path
from datetime import date
import html
import math
import pandas as pd
import plotly.express as px
import streamlit as st
from .data import DataError
from .transactions import load_demo,evaluate,totals,export_excel,read_upload,validate,COLUMNS,COLORS


def ring(rate,color):
    label='—' if pd.isna(rate) else f'{rate:.0f}%'
    offset=263.894*(1-(0 if pd.isna(rate) else rate)/100)
    return f'<svg class="tx-ring" width="106" height="106" viewBox="0 0 106 106" role="img" aria-label="نسبة الإنجاز {label}"><circle cx="53" cy="53" r="42" fill="none" stroke="#E9ECEB" stroke-width="11"/><circle cx="53" cy="53" r="42" fill="none" stroke="{color}" stroke-width="11" stroke-linecap="round" stroke-dasharray="263.894" stroke-dashoffset="{offset:.3f}" transform="rotate(-90 53 53)"/><text x="53" y="61" text-anchor="middle" fill="#143F43" font-size="23" font-weight="600">{label}</text></svg>'

def dashboard_markup(rows,total):
    def count(v):return '—' if pd.isna(v) else f'{v:,.0f}'
    overall='—' if total['rate'] is None else format(total['rate'],'.1f')+'%'
    aside=f'<aside class="tx-summary" dir="rtl"><div class="tx-summary-title">مؤشرات رئيسية<small>إنجاز المعاملات في موعدها</small></div><div class="tx-summary-item"><span>إجمالي المعاملات المستلمة</span><strong>{count(total["received"])}</strong><small>معاملة</small></div><div class="tx-summary-item"><span>المنجزة في الوقت المحدد</span><strong>{count(total["completed_on_time"])}</strong><small>معاملة</small></div><div class="tx-summary-item"><span>نسبة الإنجاز الإجمالية</span><strong>{overall}</strong><small>للصفوف مكتملة البيانات</small></div><div class="tx-summary-note">الالتزام بالوقت<br>يعزز جودة الخدمة<br>ويدعم رضا المستفيدين</div></aside>'
    header='<div class="tx-table-head"><span>الإدارة / القسم</span><span>المعاملات المستلمة</span><span>المنجزة في الوقت المحدد</span><span>نسبة الإنجاز في الوقت المحدد</span><span>الحالة</span></div>'
    table=''
    for row in rows.itertuples():
        color,bg=COLORS[row.status]
        table+=f'<div class="tx-row" style="--status:{color};--tint:{bg}"><div class="tx-name" dir="rtl"><span class="tx-dept-symbol" aria-hidden="true">{html.escape(row.department_id)}</span><strong>{html.escape(row.department)}</strong></div><div class="tx-count" dir="rtl"><small class="tx-mobile-label">المعاملات المستلمة</small><strong>{count(row.received)}</strong><small>معاملة</small></div><div class="tx-count" dir="rtl"><small class="tx-mobile-label">المنجزة في الوقت المحدد</small><strong>{count(row.completed_on_time)}</strong><small>معاملة</small></div><div class="tx-gauge">{ring(row.rate,color)}</div><div class="tx-badge-wrap"><span class="tx-badge" dir="rtl"><i></i>{html.escape({'مرتفع':'جيد','متوسط':'يحتاج تحسين','منخفض':'يحتاج متابعة'}.get(row.status,row.status))}</span></div></div>'
    return '<div class="tx-layout">'+aside+'<section class="tx-table" aria-label="أداء الأقسام">'+header+table+'</section></div>'


def render_transactions():
    if 'tx_roster' not in st.session_state:st.session_state.tx_roster,st.session_state.tx_data=load_demo()
    r=st.session_state.tx_roster;d=st.session_state.tx_data
    st.subheader('متابعة الأقسام شهريًا')
    st.caption('اختر الشهر لمعرفة ما أُنجز في موعده، والأقسام التي تحتاج متابعة. الألوان تقيس الالتزام بالموعد فقط.')
    if st.session_state.get('tx_notice'):st.success(st.session_state.tx_notice)
    cols=st.columns([2,1,1])
    admin=cols[0].selectbox('الإدارة العامة',r.administration.unique().tolist(),key='tx_admin')
    months=sorted(d.month.unique()) or [date.today().strftime('%Y-%m')]
    arabic_months=['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']
    month=cols[1].selectbox('الشهر',months,index=len(months)-1,key='tx_month',format_func=lambda x:arabic_months[int(x[5:])-1]+' '+x[:4])
    with cols[2]:
        st.markdown('<div class="tx-indicator-label"><small>المؤشر الرئيسي</small><strong>سرعة إنجاز المعاملات</strong></div>',unsafe_allow_html=True)
    with st.expander('متى يظهر اللون الأخضر أو الأصفر؟'):
        g,y=st.columns(2)
        green=g.number_input('اللون الأخضر يبدأ من (%)',min_value=1,max_value=100,value=90,key='tx_green')
        yellow=y.number_input('اللون الأصفر يبدأ من (%)',min_value=1,max_value=99,value=70,key='tx_yellow')
    if yellow>=green:st.error('حد المستوى المرتفع يجب أن يكون أعلى من المستوى المتوسط');return
    rows=evaluate(r,d,month,admin,green,yellow);total=totals(rows)
    st.markdown(dashboard_markup(rows,total),unsafe_allow_html=True)
    st.caption(f'جيد (أخضر): {green}% فأعلى · يحتاج تحسين (أصفر): من {yellow}% إلى أقل من {green}% · يحتاج متابعة (أحمر): أقل من {yellow}% · اكتمال البيانات: {total["complete"]} من {total["count"]} أقسام')
    if total['complete']<total['count']:st.info('الإجماليات والنسبة الإجمالية تشمل الصفوف مكتملة البيانات فقط. الأقسام الناقصة تظهر بالرمادي.')
    st.caption('طريقة الحساب: المعاملات المنجزة في موعدها ÷ المعاملات المستلمة × 100.')
    st.caption('بيانات عرض تجريبية' if d.empty or (d.data_kind=='synthetic').all() else 'المصدر: بيانات المستخدم')
    with st.expander('مقارنة الأشهر السابقة'):
        history=pd.concat([evaluate(r,d,m,admin,green,yellow) for m in months],ignore_index=True)
        calendar=pd.period_range(min(months),max(months),freq='M').astype(str)
        history=history.set_index(['department_id','month']).reindex(pd.MultiIndex.from_product([rows.department_id,calendar],names=['department_id','month'])).reset_index()
        history['department']=history.department_id.map(r.set_index('department_id').department)
        fig=px.line(history,x='month',y='rate',color='department',markers=True,labels={'month':'الشهر','rate':'نسبة الإنجاز (%)','department':'القسم'})
        fig.update_traces(connectgaps=False);fig.update_layout(yaxis_range=[0,105],legend=dict(orientation='h',y=-.3))
        st.plotly_chart(fig,width='stretch')
        st.dataframe(rows[['department','received','completed_on_time','rate','status']].rename(columns={'department':'القسم','received':'المستلمة','completed_on_time':'المنجزة في الوقت المحدد','rate':'نسبة الإنجاز %','status':'المؤشر'}),hide_index=True,width='stretch')
    st.download_button('تصدير تقرير المؤشرات Excel',export_excel(r,d,rows,green,yellow),'monthly_indicators.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with st.expander('تعديل أعداد المعاملات وأسماء الأقسام'):
        edited_r=st.data_editor(r,num_rows='dynamic',hide_index=True,key='tx_roster_edit',column_config={'department_id':'معرف القسم','administration':'الإدارة العامة','department':'القسم'})
        newmonth=st.text_input('شهر الإدخال YYYY-MM',value=month,key='tx_edit_month')
        base=edited_r[['department_id']].merge(d[d.month==newmonth][['department_id','received','completed_on_time']],on='department_id',how='left')
        edited=st.data_editor(base,hide_index=True,key=f'tx_counts_{newmonth}',column_config={'department_id':st.column_config.TextColumn('القسم',disabled=True),'received':st.column_config.NumberColumn('المعاملات المستلمة',min_value=0,step=1),'completed_on_time':st.column_config.NumberColumn('المنجزة في الوقت المحدد',min_value=0,step=1)})
        st.caption('يجب أن يكون المنجز جزءًا من المعاملات المستلمة في الشهر نفسه، وليس معاملات متراكمة من أشهر أخرى. الفراغ يعني عدم توفر البيانات.')
        if st.button('حفظ أعداد الشهر',key='tx_save'):
            try:
                updated=edited.copy();updated['month']=newmonth;updated['data_kind']=d.data_kind.iloc[0] if len(d) else 'real'
                combined=pd.concat([d[d.month!=newmonth],updated[COLUMNS]],ignore_index=True)
                rr,dd=validate(edited_r,combined)
                st.session_state.tx_roster=rr;st.session_state.tx_data=dd;st.session_state.tx_notice='تم حفظ أعداد الشهر '+newmonth;st.rerun()
            except DataError as exc:st.error(str(exc)+' — لم تتغير البيانات المعتمدة.')
        st.caption('الحفظ في الجلسة فقط. نزّلي ملف Excel للاحتفاظ بالتعديلات واستعادتها لاحقًا.')
    with st.expander('رفع ملف أداء الأقسام'):
        st.download_button('تنزيل قالب المعاملات',export_excel(*load_demo()),'transactions_template.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        uploaded=st.file_uploader('Excel بورقتي departments وtransactions، أو CSV للمعاملات',type=['xlsx','csv'],key='tx_upload')
        if st.button('التحقق واستيراد المعاملات',key='tx_import'):
            if uploaded is None:st.error('اختاري ملفًا أولًا')
            else:
                try:
                    rr,dd=read_upload(uploaded,r);st.session_state.tx_roster=rr;st.session_state.tx_data=dd
                    st.session_state.tx_notice='تم استخدام الملف وتحديث أداء الأقسام.'
                    for key in ['tx_admin','tx_month','tx_roster_edit']:st.session_state.pop(key,None)
                    st.rerun()
                except DataError as exc:st.error(str(exc)+' — بقيت البيانات السابقة كما هي.')
    with st.expander('شرح طريقة حساب الأداء'):
        st.markdown((Path(__file__).resolve().parents[1]/'docs/TRANSACTIONS.md').read_text())
