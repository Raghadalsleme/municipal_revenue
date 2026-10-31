import html
from datetime import date
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from .data import DataError
from .performance import (load_performance,evaluate,validate_performance,performance_excel,
                          import_performance,STATUS_COLORS,FIELDS,LABELS,WEIGHTS,COLUMNS)

def render_performance():
    if 'performance_roster' not in st.session_state:
        st.session_state.performance_roster,st.session_state.performance_data=load_performance()
    roster=st.session_state.performance_roster;data=st.session_state.performance_data
    st.subheader('لوحة مدير الإدارة العامة')
    st.caption('المتابعة الشهرية للأقسام • قياس إنجاز الخطة والالتزام بالوقت وجودة المخرجات')
    if data.empty or (data.data_kind=='synthetic').all():
        st.warning('Synthetic Data — أسماء الأقسام والنتائج للتجربة ولا تمثل الهيكل أو الأداء الفعلي للأمانة.')
    else:st.info('بيانات أداء مدخلة من المستخدم؛ التصنيفات تعتمد على المستهدفات والأوزان المحددة.')
    administration=st.selectbox('الإدارة العامة',roster.administration.unique().tolist(),key='perf_admin')
    months=sorted(data.month.unique().tolist()) or [date.today().strftime('%Y-%m')]
    c1,c2,c3=st.columns([2,1,1])
    month=c1.selectbox('شهر المتابعة',months,index=len(months)-1,key='perf_month')
    green=c2.number_input('بداية الأخضر (%)',min_value=1,max_value=100,value=90,key='perf_green')
    yellow=c3.number_input('بداية الأصفر (%)',min_value=1,max_value=99,value=70,key='perf_yellow')
    if yellow>=green:st.error('يجب أن يكون حد الأصفر أقل من حد الأخضر.');return
    result=evaluate(roster,data,month,administration,green,yellow)
    previous=(pd.Period(month,freq='M')-1).strftime('%Y-%m')
    prev=evaluate(roster,data,previous,administration,green,yellow).set_index('department_id')
    complete=result.score.notna().sum()
    avg=result.score.mean()
    cols=st.columns(4)
    cols[0].metric('الأقسام التابعة',len(result))
    cols[1].metric('متوسط الأداء للأقسام المكتملة',f'{avg:.1f}%' if complete else 'غير متاح')
    cols[2].metric('الأقسام التي تحتاج تدخل',int((result.status=='يحتاج تدخل').sum()))
    cols[3].metric('اكتمال البيانات',f'{complete} / {len(result)}')
    st.caption(f'أخضر: {green}% فأعلى | أصفر: من {yellow}% إلى أقل من {green}% | أحمر: أقل من {yellow}% | رمادي: بيانات ناقصة. المتوسط لا يشمل الأقسام الناقصة.')
    st.markdown('<div class="section-label">أداء الأقسام خلال الشهر</div>',unsafe_allow_html=True)
    for start in range(0,len(result),3):
        columns=st.columns(3)
        for col,(_,row) in zip(columns,result.iloc[start:start+3].iterrows()):
            color=STATUS_COLORS[row.status];score=row.score
            old=prev.loc[row.department_id,'score']
            delta='لا تتوفر مقارنة بالشهر السابق' if pd.isna(old) or pd.isna(score) else f'التغير عن الشهر السابق: {score-old:+.1f} نقطة'
            with col:
                st.markdown(f'''<div class="department-card" style="--status:{color}"><div class="dept-top"><span class="status-tag">● {html.escape(row.status)}</span><span class="dept-id">{html.escape(row.department_id)}</span></div><h3>{html.escape(row.department)}</h3><div class="dept-score">{'—' if pd.isna(score) else f'{score:.1f}'}<span> / 100</span></div><div class="dept-track"><span style="width:{0 if pd.isna(score) else score}%"></span></div><p class="dept-delta">{delta}</p><p class="dept-reason">{html.escape(row.reason)}</p></div>''',unsafe_allow_html=True)
    left,right=st.columns([3,2])
    with left:
        st.subheader('مسار الأداء الشهري')
        history=pd.concat([evaluate(roster,data,m,administration,green,yellow)[['department','month','score']] for m in months],ignore_index=True)
        # Insert calendar gaps so missing months are never connected as if complete.
        calendar=pd.period_range(min(months),max(months),freq='M').astype(str)
        history=history.set_index(['department','month']).reindex(pd.MultiIndex.from_product([result.department,calendar],names=['department','month'])).reset_index()
        fig=px.line(history,x='month',y='score',color='department',markers=True,labels={'month':'الشهر','score':'درجة الأداء','department':'القسم'},color_discrete_sequence=['#145C48','#247DB0','#A88B49','#7E6AAB','#C06C4E','#647B8A'])
        fig.update_layout(yaxis_range=[0,105],legend=dict(orientation='h',y=-.3),height=400)
        fig.update_traces(connectgaps=False)
        st.plotly_chart(fig,width='stretch')
    with right:
        st.subheader('أولويات المتابعة')
        alerts=result[result.status.isin(['يحتاج تدخل','بيانات ناقصة','متوسط'])].sort_values('score',na_position='first')
        if alerts.empty:st.success('جميع الأقسام ضمن النطاق الأخضر لهذا الشهر.')
        for row in alerts.itertuples():
            st.markdown(f'**{row.department} — {row.status}**')
            st.caption(row.reason)
    st.subheader('تفاصيل مؤشرات القسم')
    selected=st.selectbox('القسم',result.department_id.tolist(),format_func=lambda x:result.set_index('department_id').loc[x,'department'],key='perf_dept')
    row=result.set_index('department_id').loc[selected]
    details=pd.DataFrame([{'المؤشر':LABELS[k],'الوزن':f'{WEIGHTS[k]:.0%}','المستهدف (%)':row[f'{k}_target'],'المحقق (%)':row[f'{k}_actual'],'تحقيق المستهدف (%)':min(100,row[f'{k}_actual']/row[f'{k}_target']*100) if pd.notna(row[f'{k}_target']) and pd.notna(row[f'{k}_actual']) else None} for k in FIELDS])
    st.dataframe(details,hide_index=True,width='stretch')
    st.caption('درجة القسم = 50% إنجاز الخطة + 30% الالتزام بالوقت + 20% الجودة. كل مؤشر = المحقق ÷ المستهدف، بسقف 100%. التصنيف لمتابعة أداء القسم وليس حكمًا على الموظفين.')
    summary=result.copy();summary['green_threshold']=green;summary['yellow_threshold']=yellow
    summary['completion_weight']=.5;summary['timeliness_weight']=.3;summary['quality_weight']=.2
    st.download_button('تنزيل تقرير الأداء وبياناته Excel',performance_excel(roster,data,summary),'department_performance.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with st.expander('إعداد الإدارة والأقسام وإدخال أداء شهر جديد'):
        st.caption('غيّري أسماء الإدارة والأقسام مع الحفاظ على المعرفات. أدخلي المستهدف والمحقق كنسب من 0 إلى 100. الفراغ يعني بيانات ناقصة.')
        edited_roster=st.data_editor(roster,num_rows='dynamic',hide_index=True,key='perf_roster_editor',column_config={'department_id':'معرف القسم','administration':'الإدارة العامة','department':'اسم القسم'})
        edit_month=st.text_input('الشهر المراد إدخاله أو تعديله',value=month,key='perf_edit_month')
        base=edited_roster[['department_id']].merge(data[data.month==edit_month].drop(columns=['month','data_kind']),on='department_id',how='left')
        config={'department_id':st.column_config.TextColumn('معرف القسم',disabled=True)}
        for k in FIELDS:
            for v,label in [('target','المستهدف'),('actual','المحقق')]:config[f'{k}_{v}']=st.column_config.NumberColumn(f'{LABELS[k]} — {label} %',min_value=0,max_value=100)
        edited=st.data_editor(base,hide_index=True,key=f'perf_editor_{edit_month}',column_config=config)
        if st.button('اعتماد بيانات الشهر في الجلسة',key='perf_save'):
            try:
                updated=edited.copy();updated['month']=edit_month
                kind=data.data_kind.iloc[0] if len(data) else 'real';updated['data_kind']=kind
                combined=pd.concat([data[data.month!=edit_month],updated[COLUMNS]],ignore_index=True)
                r,m=validate_performance(edited_roster,combined)
                st.session_state.performance_roster=r;st.session_state.performance_data=m
                st.rerun()
            except DataError as exc:st.error(str(exc)+' — لم تُعتمد التغييرات.')
        st.caption('التعديلات في ذاكرة الجلسة. احفظي ملف Excel قبل الإغلاق، ثم ارفعيه لاستكمال العمل. تعديل بيانات التجربة يبقيها موسومة synthetic؛ ارفعي ملفًا كاملًا بوسم real لبدء بيانات حقيقية دون خلط.')
    with st.expander('استيراد أو استعادة ملف أداء'):
        st.download_button('تنزيل قالب الأداء للأقسام الستة',performance_excel(*load_performance()),'performance_template.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        uploaded=st.file_uploader('Excel بورقتي departments وperformance، أو CSV للأداء فقط',type=['xlsx','csv'],key='perf_upload')
        if st.button('التحقق واستبدال بيانات الأداء',key='perf_import'):
            if uploaded is None:st.error('اختاري ملفًا أولًا.')
            else:
                try:
                    r,m=import_performance(uploaded,roster)
                    st.session_state.performance_roster=r;st.session_state.performance_data=m
                    for key in ['perf_admin','perf_month','perf_dept','perf_roster_editor']:
                        st.session_state.pop(key,None)
                    st.rerun()
                except DataError as exc:st.error(str(exc)+' — بقيت البيانات الحالية دون تغيير.')
    with st.expander('تعريف المؤشرات وقواعد المتابعة'):
        st.markdown((Path(__file__).resolve().parents[1]/'docs/PERFORMANCE.md').read_text())
