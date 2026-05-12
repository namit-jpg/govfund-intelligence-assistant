from io import BytesIO, StringIO
import pandas as pd

def build_excel_export(
    kpis,
    monthly,
    top_rec,
    top_emp,
    txns,
    source_split=None,
    executive_report=None,
    audit_logs=None,
    data_quality_flags=None,
    raw_records=None,
):
    out=BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        pd.DataFrame([{'summary':'GovFund Intelligence Assistant export','note':'All rows are sourced from ingested public records.'}]).to_excel(w,sheet_name='Executive Summary',index=False)
        pd.DataFrame([kpis]).to_excel(w,sheet_name='KPI Snapshot',index=False)
        pd.DataFrame(monthly).to_excel(w,sheet_name='Monthly Trend',index=False)
        pd.DataFrame(top_rec).to_excel(w,sheet_name='Top Recipients',index=False)
        pd.DataFrame(top_emp).to_excel(w,sheet_name='Top Employers',index=False)
        if source_split:
            pd.DataFrame(source_split).to_excel(w,sheet_name='Source Split',index=False)
        if executive_report:
            report_rows = [{'section':'headline','content':executive_report.get('headline','')},{'section':'summary','content':executive_report.get('summary','')},{'section':'compliance_note','content':executive_report.get('compliance_note','')}]
            report_rows += [{'section':'highlight','content':x} for x in executive_report.get('highlights',[])]
            report_rows += [{'section':'risk','content':x} for x in executive_report.get('risks',[])]
            report_rows += [{'section':'recommended_action','content':x} for x in executive_report.get('recommended_actions',[])]
            pd.DataFrame(report_rows).to_excel(w,sheet_name='Monthly Executive Report',index=False)
        pd.DataFrame(txns).to_excel(w,sheet_name='Filtered Transactions',index=False)
        if raw_records is not None:
            pd.DataFrame(raw_records).to_excel(w,sheet_name='Raw Records',index=False)
        if audit_logs is not None:
            pd.DataFrame(audit_logs).to_excel(w,sheet_name='Source Audit Logs',index=False)
        if data_quality_flags is not None:
            pd.DataFrame(data_quality_flags).to_excel(w,sheet_name='Data Quality Flags',index=False)
        notes=pd.DataFrame({'compliance_notes':['Data is based on public campaign finance records.','FEC employer fields are employer/company signals reported by individual contributors, not proof of direct corporate donations.','Individual contributor information must not be used for solicitation or commercial misuse.','Aggregated insights are for research and transparency purposes.','No wrongdoing, donor intent, bribery, or pay-to-play activity is inferred from contribution activity.']})
        notes.to_excel(w,sheet_name='Compliance Notes',index=False)
    out.seek(0); return out


def build_csv_export(rows):
    text = StringIO()
    pd.DataFrame(rows).to_csv(text, index=False)
    out = BytesIO(text.getvalue().encode("utf-8"))
    out.seek(0)
    return out
