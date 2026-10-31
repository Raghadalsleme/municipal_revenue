from io import BytesIO
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from openpyxl import load_workbook
from core.data import load_demo,validate,read_uploads,DataError,SCHEMA
from core.engine import metrics,detect,scenario,recommend,fraction
from core.reports import pdf_report,workbook

@pytest.fixture
def data():return load_demo()

def test_gap(data):
    m=metrics(data)
    assert (m['target'],m['achieved'],m['gap'],m['achievement'])==(100e6,80e6,20e6,80)

def test_surplus_zero_target(data):
    data['revenues']['target']=0;m=metrics(data)
    assert m['gap']==0 and m['achievement'] is None and m['surplus']==80e6
    assert recommend(detect(data),0)==[]

def test_exact_estimates(data):
    o=detect(data).set_index('opportunity_id')
    assert o.loc['LEASE:A01','annual_potential']==2160000
    assert o.loc['LEASE:A01','current_year']==pytest.approx(2160000*63/365)
    assert o.loc['COLLECT:I01','one_off_potential']==2100000
    assert o.loc['RENEW:C01','annual_potential']==1080000
    assert o.loc['RENEW:C01','current_year']==pytest.approx(1080000*61/365)
    assert 'COLLECT:I04' not in o.index and 'COLLECT:I05' not in o.index
    assert 'LEASE:A06' not in o.index
    assert o.loc['LEASE:A07','current_year']==0
    assert o.loc['RENEW:C02','current_year']==0

def test_data_driven(data):
    before=detect(data).set_index('opportunity_id');data['assets'].loc[0,'occupancy']=.5
    after=detect(data).set_index('opportunity_id')
    assert after.loc['LEASE:A01','annual_potential']==1350000
    assert after.loc['LEASE:A01','current_year']<before.loc['LEASE:A01','current_year']

def test_scenarios_dedup_cap(data):
    o=detect(data);ids=o.opportunity_id.tolist();a=scenario(o,ids+ids,'متوسط',20e6)
    assert a['additional']==pytest.approx(o.current_year.round(2).sum())
    vals=[scenario(o,ids,s,20e6)['additional'] for s in ['متحفظ','متوسط','متفائل']]
    assert vals[0]<vals[1]<vals[2]
    opt=scenario(o,ids,'متفائل',20e6)['rows']
    assert (opt.scenario_one_off<=opt.cap).all() and (opt.scenario_annual<=opt.cap).all()

def test_empty_selection(data):
    r=scenario(detect(data),[],'متوسط',20e6)
    assert r['additional']==0 and r['remaining']==20e6

def test_scenario_surplus(data):
    o=detect(data);r=scenario(o,o.opportunity_id,'متوسط',1)
    assert r['remaining']==0 and r['surplus']==r['additional']-1

def test_conflicting_and_duplicate_opportunities(data):
    o=detect(data);dup=o.iloc[[0]].copy();dup['opportunity_id']='OTHER'
    conflict=pd.concat([o,dup],ignore_index=True)
    with pytest.raises(ValueError,match='متعارضة'):scenario(conflict,[o.iloc[0].opportunity_id,'OTHER'],'متوسط',20e6)
    with pytest.raises(ValueError,match='مكرر'):scenario(pd.concat([o,o]),[],'متوسط',20e6)
    with pytest.raises(ValueError):scenario(o,['MISSING'],'متوسط',20e6)

@pytest.mark.parametrize('field,value',[('occupancy',1.1),('risk',-.1),('area_m2',np.inf),('market_rate',float('nan')),('delay_months',.5)])
def test_invalid_numeric(data,field,value):
    data['assets'][field]=data['assets'][field].astype(float);data['assets'].loc[0,field]=value
    with pytest.raises(DataError):validate(data)

@pytest.mark.parametrize('name',list(SCHEMA))
def test_duplicate_ids(data,name):
    data[name]=pd.concat([data[name],data[name].iloc[[0]]])
    with pytest.raises(DataError,match='مكررة'):validate(data)

def test_references_and_conflicts(data):
    data['contracts'].loc[0,'asset_id']='MISSING'
    with pytest.raises(DataError):validate(data)
    data=load_demo();data['assets'].loc[3,'status']='vacant'
    with pytest.raises(DataError):validate(data)

def test_invalid_balances_and_mixed(data):
    data['receivables'].loc[0,'collected']=9e6
    with pytest.raises(DataError):validate(data)
    data=load_demo();data['assets'].loc[0,'data_kind']='real'
    with pytest.raises(DataError):validate(data)

def test_invalid_dates(data):
    data['revenues'].loc[0,'as_of']='2027-01-01'
    with pytest.raises(DataError):validate(data)
    data=load_demo();data['contracts'].loc[0,'renewal_date']='invalid'
    with pytest.raises(DataError):validate(data)

def test_no_opportunities(data):
    for n in ['assets','contracts','receivables']:data[n]=data[n].iloc[:0]
    o=detect(data)
    assert o.empty and recommend(o,20e6)==[]
    assert scenario(o,[],'متوسط',20e6)['remaining']==20e6

def test_year_end_and_leap(data):
    data['revenues']['as_of']='2026-12-31'
    assert detect(data).current_year.sum()==0
    assert fraction(pd.Timestamp('2024-12-31'),pd.Timestamp('2024-12-30'))==1/366

class Upload(BytesIO):
    def __init__(self,name,content):super().__init__(content);self.name=name

def test_import_roundtrip(data):
    files=[Upload(n+'.csv',df.to_csv(index=False).encode()) for n,df in data.items()]
    assert metrics(read_uploads(files))==metrics(data)
    imported=read_uploads([Upload('data.xlsx',workbook(data))])
    assert len(detect(imported))==len(detect(data))

def test_import_incomplete():
    with pytest.raises(DataError):read_uploads([Upload('assets.csv',b'hello\n1')])

def test_export_values_pdf_and_formula_injection(data):
    o=detect(data);r=scenario(o,recommend(o,20e6),'متوسط',20e6)
    data['assets'].loc[0,'name']='=HYPERLINK("bad")'
    wb=load_workbook(BytesIO(workbook(data,o,r)))
    summary=dict(wb['ملخص'].iter_rows(min_row=2,values_only=True))
    assert summary['الفجوة']==20e6
    assert summary['الإضافي حتى نهاية السنة']==pytest.approx(r['additional'])
    assert wb['assets']['B2'].data_type=='s' and wb['assets']['B2'].value.startswith("'=")
    assert wb['assets'].sheet_view.rightToLeft
    pdf=pdf_report(data,o,r)
    assert pdf.startswith(b'%PDF') and len(pdf)>20000

def test_ui_pages_and_selection():
    from streamlit.testing.v1 import AppTest
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    assert not at.exception
    at.radio(key='main_navigation').set_value('لوحة الإيرادات').run()
    assert at.metric[0].value=='100.0 مليون'
    for page in ['اكتشاف الفرص','تحليل السيناريوهات','التقارير','البيانات والمنهجية']:
        at.radio(key='main_navigation').set_value(page).run();assert not at.exception
    at.radio(key='main_navigation').set_value('تحليل السيناريوهات').run()
    at.multiselect[0].set_value([]).run()
    assert at.metric[0].value=='0 ر.س' and at.metric[1].value=='20,000,000 ر.س'
    at.radio(key='mode').set_value('متفائل').run()
    assert not at.exception

def test_ui_upload_rejection_and_success(data):
    from streamlit.testing.v1 import AppTest
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    at.radio(key='main_navigation').set_value('البيانات والمنهجية').run()
    at.file_uploader[0].set_value([('bad.csv',b'x\n1','text/csv')]).run()
    at.button[0].click().run()
    assert at.error and not at.exception
    assert metrics(at.session_state['tables'])['gap']==20e6
    data['revenues']['target']=data['revenues']['target']*2
    uploads=[(n+'.csv',df.to_csv(index=False).encode(),'text/csv') for n,df in data.items()]
    at.file_uploader[0].set_value(uploads).run();at.button[0].click().run()
    assert not at.exception
    assert metrics(at.session_state['tables'])['gap']==120e6

def test_reset_upload_feedback():
    from streamlit.testing.v1 import AppTest
    at=AppTest.from_file('../app.py',default_timeout=20).run()
    at.radio(key='main_navigation').set_value('البيانات والمنهجية').run()
    data=load_demo();data['revenues']['target']*=2
    at.file_uploader[0].set_value([('changed.xlsx',workbook(data),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]).run()
    at.button(key='apply_revenue').click().run()
    assert not at.exception
    assert 'تم قبول الملف' in at.success[0].value
    assert metrics(at.session_state.tables)['target']==200_000_000
    at.button(key='reset_revenue').click().run()
    assert 'تمت إعادة بيانات المثال' in at.success[0].value
    assert metrics(at.session_state.tables)['target']==100_000_000
    assert at.session_state.upload_version==1
    assert not at.file_uploader[0].value
