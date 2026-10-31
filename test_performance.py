from pathlib import Path
from io import BytesIO
import numpy as np
import pandas as pd
import pytest
from core.data import DataError
from core.performance import *
from streamlit.testing.v1 import AppTest

@pytest.fixture
def data():return load_performance()

def test_sample_statuses(data):
    r,m=data;s=evaluate(r,m,'2026-09')
    assert len(s)==6
    assert s.status.tolist()==['جيد','جيد','متوسط','متوسط','يحتاج تدخل','يحتاج تدخل']
    assert s.score.mean()==pytest.approx(81.6666667)

def test_missing_rows_and_values(data):
    r,m=data;m=m[~((m.department_id=='D01') & (m.month=='2026-09'))].copy()
    m.loc[(m.department_id=='D02') & (m.month=='2026-09'),'quality_actual']=np.nan
    s=evaluate(r,m,'2026-09')
    assert len(s)==6 and (s.status=='بيانات ناقصة').sum()==2
    assert s.score.isna().sum()==2
    assert evaluate(r,m,'2026-01').score.isna().all()

def test_boundaries_weights_and_cap(data):
    r,m=data
    for k in FIELDS:m[f'{k}_target']=100;m[f'{k}_actual']=90
    assert (evaluate(r,m,'2026-09').status=='جيد').all()
    for k in FIELDS:m[f'{k}_actual']=70
    assert (evaluate(r,m,'2026-09').status=='متوسط').all()
    for k in FIELDS:m[f'{k}_actual']=69.9
    assert (evaluate(r,m,'2026-09').status=='يحتاج تدخل').all()
    for k in FIELDS:m[f'{k}_target']=50;m[f'{k}_actual']=100
    assert (evaluate(r,m,'2026-09').score==100).all()
    m['completion_actual']=0
    assert (evaluate(r,m,'2026-09').score==50).all()

def test_reject_invalid(data):
    r,m=data
    with pytest.raises(DataError):validate_performance(r,pd.concat([m,m.iloc[[0]]]))
    for bad in [-1,101,np.inf,'bad']:
        q=m.copy();q['quality_actual']=q.quality_actual.astype(object);q.loc[0,'quality_actual']=bad
        with pytest.raises(DataError):validate_performance(r,q)
    q=m.copy();q.loc[0,'completion_target']=0
    with pytest.raises(DataError):validate_performance(r,q)
    q=m.copy();q.loc[0,'month']='2026-13'
    with pytest.raises(DataError):validate_performance(r,q)
    q=m.copy();q.loc[0,'department_id']='X'
    with pytest.raises(DataError):validate_performance(r,q)
    with pytest.raises(DataError):evaluate(r,m,'2026-09',green=60,yellow=80)

def test_export_import(data):
    r,m=data
    class F(BytesIO):name='test.xlsx'
    rr,mm=import_performance(F(performance_excel(r,m,evaluate(r,m,'2026-09'))),r)
    assert evaluate(rr,mm,'2026-09').score.tolist()==evaluate(r,m,'2026-09').score.tolist()

def test_ui_dashboard_month_and_threshold(data):
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    at.radio(key='main_navigation').set_value('المؤشرات التفصيلية').run()
    assert not at.exception
    assert at.metric[0].value=='6'
    assert at.metric[2].value=='2'
    at.selectbox(key='perf_month').set_value('2026-04').run()
    assert not at.exception
    assert at.metric[1].value=='75.8%'
    at.number_input(key='perf_green').set_value(60).run()
    assert at.error and not at.exception

def test_ui_save_new_month():
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    at.radio(key='main_navigation').set_value('المؤشرات التفصيلية').run()
    at.text_input(key='perf_edit_month').set_value('2026-10').run()
    at.button(key='perf_save').click().run()
    assert not at.exception
    assert '2026-10' in at.session_state['performance_data'].month.tolist()
    at.selectbox(key='perf_month').set_value('2026-10').run()
    assert at.metric[3].value=='0 / 6'


def test_administration_scope_and_custom_thresholds(data):
    r,m=data
    r.loc[0,'administration']='إدارة ثانية'
    scoped=evaluate(r,m,'2026-09','إدارة ثانية')
    assert len(scoped)==1 and scoped.iloc[0].department_id=='D01'
    custom=evaluate(r,m,'2026-09',green=99,yellow=80)
    assert custom.status.tolist()==['جيد','متوسط','متوسط','متوسط','يحتاج تدخل','يحتاج تدخل']

def test_ui_import_performance(data):
    r,m=data
    r.loc[0,'department']='قسم الاختبار'
    m['data_kind']='real'
    content=performance_excel(r,m)
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    at.radio(key='main_navigation').set_value('المؤشرات التفصيلية').run()
    at.file_uploader(key='perf_upload').set_value(('performance.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')).run()
    at.button(key='perf_import').click().run()
    assert not at.exception
    assert at.session_state['performance_roster'].iloc[0].department=='قسم الاختبار'
    assert (at.session_state['performance_data'].data_kind=='real').all()
