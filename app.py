from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from core.data import load_demo,read_uploads,DataError,SCHEMA
from core.engine import metrics,detect,scenario,recommend,SCENARIOS
from core.reports import workbook,pdf_report,LABELS,source_label,provenance

from core.performance_ui import render_performance
from core.transactions_ui import render_transactions
import base64
import plotly.io as pio

st.set_page_config(page_title='أمانة حائل | الإيرادات والأداء',page_icon='assets/hail_logo.png',layout='wide')
root=Path(__file__).parent
font_css=(root/'assets/font.css').read_text()
for font_file in (root/'assets').glob('arabic-ui-*.ttf'):
    font_css=font_css.replace(font_file.name,'data:font/ttf;base64,'+base64.b64encode(font_file.read_bytes()).decode())
st.markdown('<style>'+font_css+(root/'assets/theme.css').read_text()+'</style>',unsafe_allow_html=True)
pio.templates.default='plotly_white'
pio.templates['plotly_white'].layout.font.family='IBM Plex Sans Arabic, Tahoma, sans-serif'
pio.templates['plotly_white'].layout.font.color='#385147'
pio.templates['plotly_white'].layout.colorway=['#185C48','#B7A06A','#4A8194','#81988B']
if 'tables' not in st.session_state:st.session_state.tables=load_demo()
t=st.session_state.tables;m=metrics(t);opps=detect(t)
fingerprint=provenance(t)
if st.session_state.get('fingerprint')!=fingerprint:
    st.session_state.fingerprint=fingerprint
    st.session_state.selected=recommend(opps,m['gap'])
if 'mode' not in st.session_state:st.session_state.mode='متوسط'
logo=base64.b64encode((root/'assets/hail_logo.png').read_bytes()).decode()
st.markdown(f'<header class="gov-header"><div class="gov-brand"><img src="data:image/png;base64,{logo}" alt="شعار أمانة منطقة حائل"><span class="divider"></span><div class="gov-product">متابعة الإيرادات وأداء الأقسام<small>أمانة منطقة حائل</small></div></div><span class="gov-context">نسخة تجريبية · 5.1</span></header>',unsafe_allow_html=True)
NAV={'أداء الإدارات':'أداء الأقسام','لوحة الإيرادات':'الإيرادات','اكتشاف الفرص':'فرص زيادة الإيرادات','تحليل السيناريوهات':'تجربة الفرص','التقارير':'التقارير','البيانات والمنهجية':'إدخال البيانات','المؤشرات التفصيلية':'تفاصيل الأداء'}
page=st.radio('التنقل',list(NAV),format_func=lambda x:NAV[x],horizontal=True,key='main_navigation',label_visibility='collapsed')
if page!='أداء الإدارات':st.subheader(NAV[page])
if page not in ['أداء الإدارات','المؤشرات التفصيلية']:
    if t['revenues'].data_kind.iloc[0]=='synthetic':st.warning(source_label(t))
    else:st.info(source_label(t))
    st.caption(f"لقطة البيانات: {t['revenues'].as_of.iloc[0]} | السنة: {int(t['revenues'].year.iloc[0])} | المبالغ بالريال السعودي | أساس نقدي قبل الضريبة")

def money(x):return f'{x:,.0f} ر.س'
def cards():
    cols=st.columns(4)
    for col,label,val in zip(cols,['المستهدف السنوي','الإيرادات المحققة','الفجوة المتبقية','نسبة تحقيق المستهدف'],[f"{m['target']/1e6:,.1f} مليون",f"{m['achieved']/1e6:,.1f} مليون",f"{m['gap']/1e6:,.1f} مليون",f"{m['achievement']:.1f}%" if m['achievement'] is not None else 'غير معرّفة']):col.metric(label,val)
def view(df):
    st.dataframe(df.rename(columns=LABELS),hide_index=True,width='stretch')

if page=='لوحة الإيرادات':
    cards()
    st.caption('القيم المالية بالمليون ريال سعودي. تعرض الرسوم التفاصيل عند المرور على البيانات.')
    a,b=st.columns([1.6,1])
    with a:
        chart=t['revenues'].melt(id_vars='source',value_vars=['target','achieved'],var_name='measure',value_name='sar')
        chart['million']=chart.sar/1e6
        chart['measure']=chart.measure.map({'target':'المستهدف','achieved':'المحقق'})
        fig=px.bar(chart,x='source',y='million',color='measure',barmode='group',color_discrete_sequence=['#C4B58D','#1B8354'],labels={'source':'','million':'مليون ريال','measure':''},title='الإيرادات حسب المصدر',custom_data=['sar'])
        fig.update_traces(hovertemplate='%{x}<br>%{customdata[0]:,.0f} ريال<extra>%{fullData.name}</extra>')
        fig.update_layout(height=385,margin=dict(l=65,r=25,t=75,b=55),legend=dict(orientation='h',y=1.12,x=1,xanchor='right'),yaxis_tickformat=',.0f',title_x=.95,bargap=.35)
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
    with b:
        fig=px.pie(t['revenues'],names='source',values='achieved',hole=.73,color_discrete_sequence=['#1B8354','#75AF90','#C4B58D','#DCE7DF'])
        fig.update_traces(textinfo='none',hovertemplate='%{label}<br>%{value:,.0f} ريال<extra></extra>')
        fig.update_layout(height=385,title='توزيع الإيرادات المحققة',title_x=.95,margin=dict(l=25,r=25,t=75,b=45),legend=dict(orientation='h',y=-.12,x=.5,xanchor='center'),annotations=[dict(text=f"{m['achieved']/1e6:,.1f}<br>مليون ريال",x=.5,y=.5,showarrow=False,font_size=23)])
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
    st.markdown('<div class="section-label">فرص تقليص الفجوة</div>',unsafe_allow_html=True)
    shortlist=recommend(opps,m['gap']);res=scenario(opps,shortlist,'متوسط',m['gap'])
    x,y,z=st.columns(3)
    x.metric('فرص ذات مساهمة خلال السنة',str(len(shortlist)))
    y.metric('مساهمة محتملة خلال السنة',f"{res['additional']/1e6:,.2f} مليون")
    z.metric('الفجوة المتبقية بعد الفرص',f"{res['remaining']/1e6:,.2f} مليون")
    st.caption('وفق السيناريو المتوسط. هذه فرص إضافية للدراسة وليست توقعًا لكامل إيرادات السنة.')

elif page=='أداء الإدارات':
    render_transactions()

elif page=='المؤشرات التفصيلية':
    render_performance()

elif page=='اكتشاف الفرص':
    st.subheader('فرص مستخرجة من البيانات')
    st.caption('فرص مستخرجة من الأصول والعقود والمستحقات؛ التقديرات والافتراضات متاحة للمراجعة.')
    kinds=st.multiselect('نوع الفرصة',opps.kind.unique().tolist(),default=opps.kind.unique().tolist())
    shown=opps[opps.kind.isin(kinds)]
    view(shown[['opportunity_id','title','kind','annual_potential','one_off_potential','current_year','score']])
    st.caption('الأولوية: 50% للإيراد الإضافي الممكن خلال السنة، 30% للسهولة، 20% لانخفاض المخاطر. درجة نسبية وليست احتمال نجاح.')
    for row in shown.itertuples():
        with st.expander(f'{row.title} — {money(row.current_year)} حتى نهاية السنة'):
            st.write('**سبب الترشيح:** '+row.reason);st.write('**طريقة الحساب:** '+row.formula)
            st.write(f'**نسبة مدة التشغيل المتبقية من السنة:** {row.active_fraction:.3f} | **سهولة التنفيذ:** {row.ease:.0%} | **المخاطر:** {row.risk:.0%}')
            st.write('**المراجعة المطلوبة:** '+row.review)
    if shown.empty:st.info('لا توجد فرص مطابقة. لا ينشئ النظام فرصًا دون أدلة كافية في البيانات.')

elif page=='تحليل السيناريوهات':
    st.subheader('اختر الفرص التي تريد تجربتها')
    st.caption('جرّب تقديرًا متحفظًا أو متوسطًا أو متفائلًا. نستخدم 70% أو 100% أو 120% من التقدير الأساسي، دون تجاوز قيمة السوق أو المبلغ المستحق. النتائج تقديرية وليست مضمونة.')
    if st.button('اختيار التوصيات حسب الأولوية'):
        st.session_state.selected=recommend(opps,m['gap'])
    labels=opps.set_index('opportunity_id').title.to_dict()
    st.multiselect('الفرص المختارة',opps.opportunity_id.tolist(),key='selected',format_func=lambda x:labels[x])
    st.radio('السيناريو',list(SCENARIOS),key='mode',horizontal=True)
    res=scenario(opps,st.session_state.selected,st.session_state.mode,m['gap'])
    a,b,c=st.columns(3)
    a.metric('إضافي حتى نهاية السنة',money(res['additional']));b.metric('الفجوة بعد الفرص',money(res['remaining']));c.metric('المبلغ الزائد عن المستهدف',money(res['surplus']))
    st.caption(f"إضافي متكرر لسنة تشغيل كاملة: {money(res['annual'])} | تحصيل لمرة واحدة: {money(res['one_off'])}. لا تجمع هذين الرقمين لقياس سد فجوة السنة.")
    comparison=pd.DataFrame([{'السيناريو':mode,'إضافي حتى نهاية السنة':scenario(opps,st.session_state.selected,mode,m['gap'])['additional'],'الفجوة المتبقية':scenario(opps,st.session_state.selected,mode,m['gap'])['remaining']} for mode in SCENARIOS])
    st.plotly_chart(px.bar(comparison,x='السيناريو',y=['إضافي حتى نهاية السنة','الفجوة المتبقية'],barmode='stack',color_discrete_sequence=['#12614F','#D6C49C'],labels={'value':'ريال سعودي','variable':''}),width='stretch')
    view(res['rows'][['opportunity_id','title','scenario_annual','scenario_one_off','scenario_current']])
    if res['remaining']>0:st.warning('الفرص المختارة لا تغطي كامل الفجوة خلال السنة وفق هذه الافتراضات.')
    st.info('كل اختيار هو سيناريو للدراسة؛ لا يمثل اعتمادًا أو أمر تنفيذ.')

elif page=='التقارير':
    st.subheader('تقرير السيناريو الحالي')
    res=scenario(opps,st.session_state.selected,st.session_state.mode,m['gap'])
    st.write(f"السيناريو: **{res['mode']}** | الفرص المختارة: **{len(res['rows'])}**")
    st.write(f"الفجوة الحالية: **{money(m['gap'])}** | الفجوة بعد الفرص: **{money(res['remaining'])}**")
    st.caption('لتغيير الفرص أو السيناريو انتقل إلى تجربة الفرص. يتضمن التقرير جميع الفرص مع تمييز المختارة وأسبابها وافتراضاتها.')
    a,b=st.columns(2)
    with a:st.download_button('تنزيل تقرير PDF',pdf_report(t,opps,res),'municipal_revenue_report.pdf','application/pdf')
    with b:st.download_button('تصدير Excel',workbook(t,opps,res),'municipal_revenue_results.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    view(res['rows'][['title','scenario_current','review']])

else:
    st.write('حدّث أرقام الإيرادات من ملف Excel. ستظهر النتائج الجديدة في صفحة الإيرادات بعد قبول الملف.')
    st.caption('١. نزّل ملف المثال  ←  ٢. عدّل الأرقام مع إبقاء أسماء الأوراق والأعمدة  ←  ٣. ارفع الملف واضغط «استخدام الملف»')
    if st.session_state.get('revenue_notice'):
        st.success(st.session_state.revenue_notice)
    st.info('البيانات المستخدمة الآن: '+st.session_state.get('revenue_source','بيانات المثال'))
    st.download_button('تنزيل ملف مثال Excel',workbook(load_demo()),'synthetic_input_template.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    uploads=st.file_uploader('اختر ملف Excel المعدّل، أو ملفات CSV الأربعة',type=['csv','xlsx'],accept_multiple_files=True,key='revenue_upload_'+str(st.session_state.get('upload_version',0)))
    left,right=st.columns(2)
    if left.button('استخدام الملف',type='primary',key='apply_revenue'):
        st.session_state.pop('revenue_notice',None)
        try:
            validated=read_uploads(uploads)
            st.session_state.tables=validated
            st.session_state.revenue_source='، '.join(f.name for f in uploads)
            st.session_state.revenue_notice='تم قبول الملف وتحديث الإيرادات والفرص. يمكنك الآن فتح صفحة الإيرادات للاطلاع على النتائج.'
            st.rerun()
        except DataError as e:st.error('لم يُقبل الملف: '+str(e)+' — بقيت البيانات السابقة كما هي.')
    if right.button('الرجوع لبيانات المثال',key='reset_revenue'):
        st.session_state.tables=load_demo()
        st.session_state.revenue_source='بيانات المثال'
        st.session_state.revenue_notice='تمت إعادة بيانات المثال وإزالة الملف المرفوع من هذه الصفحة.'
        st.session_state.upload_version=st.session_state.get('upload_version',0)+1
        st.rerun()
    st.caption('تبقى التعديلات أثناء الجلسة الحالية فقط. احتفظ بملفك لإعادة رفعه عند تشغيل التطبيق مرة أخرى.')
    table_names={'revenues':'الإيرادات','assets':'الأصول والأراضي','contracts':'العقود','receivables':'المبالغ المستحقة'}
    st.markdown('#### مراجعة البيانات الحالية')
    for n,d in t.items():
        with st.expander(f'{table_names[n]} — {len(d)} سجل'):
            st.dataframe(d.rename(columns=LABELS),hide_index=True,width='stretch')
    with st.expander('شرح أعمدة الملف'):
        st.markdown((Path(__file__).parent/'docs/DATA_DICTIONARY.md').read_text())
    with st.expander('كيف تُحسب الفرص؟'):
        st.markdown((Path(__file__).parent/'docs/METHODOLOGY.md').read_text())

st.markdown('<div class="gov-footer"><span>أمانة منطقة حائل · منصة الإيرادات والأداء المؤسسي</span><span>نسخة عرض · الإصدار 5.1</span></div>',unsafe_allow_html=True)
