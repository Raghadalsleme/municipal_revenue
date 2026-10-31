from pathlib import Path
from core.data import load_demo
from core.engine import detect,metrics,recommend,scenario
from core.reports import workbook,pdf_report

t=load_demo();o=detect(t);m=metrics(t);r=scenario(o,recommend(o,m['gap']),'متوسط',m['gap'])
p=Path(__file__).parent/'examples';p.mkdir(exist_ok=True)
(p/'synthetic_input_template.xlsx').write_bytes(workbook(t))
(p/'synthetic_results.xlsx').write_bytes(workbook(t,o,r))
(p/'synthetic_report.pdf').write_bytes(pdf_report(t,o,r))
o.to_csv(p/'opportunities.csv',index=False,encoding='utf-8-sig')
print(f"Opportunities={len(o)}, additional={r['additional']:,.2f}, remaining={r['remaining']:,.2f}")

from core.performance import load_performance,evaluate,performance_excel
roster,performance=load_performance()
(p/'performance_template.xlsx').write_bytes(performance_excel(roster,performance))
(p/'performance_september.xlsx').write_bytes(performance_excel(roster,performance,evaluate(roster,performance,'2026-09')))

from core.transactions import load_demo as load_transactions, evaluate as evaluate_transactions, export_excel
roster,transactions=load_transactions()
(p/'transactions_template.xlsx').write_bytes(export_excel(roster,transactions))
(p/'transactions_september.xlsx').write_bytes(export_excel(roster,transactions,evaluate_transactions(roster,transactions,'2026-09')))
