from pathlib import Path
from io import BytesIO
import pandas as pd
import numpy as np
import pytest
from core.transactions import *
from core.data import DataError
from streamlit.testing.v1 import AppTest

@pytest.fixture
def data():return load_demo()

def test_reference_and_correct_totals(data):
 r,d=data;s=evaluate(r,d,'2026-09');t=totals(s)
 assert s.rate.iloc[:3].tolist()==[60,80,95]
 assert s.status.iloc[:3].tolist()==['منخفض','متوسط','مرتفع']
 assert totals(s.iloc[:3])['completed_on_time']==810
 assert t['received']==1800 and t['completed_on_time']==1320
 assert t['rate']==pytest.approx(73.3333333333)

def test_missing_and_zero(data):
 r,d=data;d=d[d.department_id!='T01'].copy();d.loc[d.department_id=='T02',['received','completed_on_time']]=0
 s=evaluate(r,d,'2026-09');assert s.status.iloc[0]=='بيانات ناقصة';assert s.status.iloc[1]=='لا معاملات'
 assert totals(s)['complete']==5
 assert totals(evaluate(r,d,'2020-01'))['rate'] is None

def test_boundaries(data):
 r,d=data;d['received']=100
 for n,status in [(90,'مرتفع'),(70,'متوسط'),(69,'منخفض'),(0,'منخفض')]:
  d['completed_on_time']=n;assert (evaluate(r,d,'2026-09').status==status).all()

@pytest.mark.parametrize('bad',[-1,1.5,np.inf,'bad',501])
def test_invalid(data,bad):
 r,d=data;d['completed_on_time']=d.completed_on_time.astype(object);d.loc[0,'completed_on_time']=bad
 with pytest.raises(DataError):validate(r,d)

def test_duplicate_and_import(data):
 r,d=data
 with pytest.raises(DataError):validate(r,pd.concat([d,d.iloc[[0]]]))
 class F(BytesIO):name='test.xlsx'
 rr,dd=read_upload(F(export_excel(r,d)),r)
 assert totals(evaluate(rr,dd,'2026-09'))==totals(evaluate(r,d,'2026-09'))

def test_real_ui(data):
 at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
 assert not at.exception
 text=' '.join(m.value for m in at.markdown)
 assert '1,800' in text and '1,320' in text and '73.3%' in text
 at.selectbox(key='tx_month').set_value('2026-04').run();assert not at.exception
 assert '1,170' in ' '.join(m.value for m in at.markdown)
 at.text_input(key='tx_edit_month').set_value('2026-10').run();at.button(key='tx_save').click().run()
 assert not at.exception
 at.selectbox(key='tx_month').set_value('2026-10').run()
 assert 'بيانات ناقصة' in ' '.join(m.value for m in at.markdown)
