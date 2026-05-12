import io
import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT = 30
LONG_TIMEOUT = 240
MAX_TABLE_ROWS = 500
MAX_CHART_ROWS = 5000
SOURCE_CAVEAT = (
    "FEC employer fields represent the employer reported by individual contributors. "
    "They do not prove direct corporate donations."
)
FAST_PORTAL_URL = os.getenv("FAST_FRONTEND_URL", "http://127.0.0.1:8000/app/")
LEGACY_STREAMLIT_UI = os.getenv("LEGACY_STREAMLIT_UI", "0") == "1"

st.set_page_config(page_title="GovFund Intelligence Assistant", layout="wide")

if not LEGACY_STREAMLIT_UI:
    st.markdown(
        f"""
        <meta http-equiv="refresh" content="0; url={FAST_PORTAL_URL}">
        <div style="font-family:Inter,Arial,sans-serif;background:#f8fafc;color:#0f172a;padding:2rem;border:1px solid #cbd5e1;border-radius:10px;">
          <h1 style="margin-top:0;color:#0f172a;">GovFund Intelligence Assistant moved to the fast portal</h1>
          <p style="color:#334155;font-size:1rem;">The Streamlit UI is disabled by default because it was too slow for normal use.</p>
          <p><a style="display:inline-block;background:#1d4ed8;color:#ffffff;padding:0.75rem 1rem;border-radius:7px;text-decoration:none;font-weight:800;" href="{FAST_PORTAL_URL}">Open Fast JS Portal</a></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown(
    """
    <style>
      html, body, [class*="css"] { font-family: Inter, Arial, sans-serif; }
      .stApp { background: #f8fafc; }
      h1, h2, h3 { color: #0f172a; letter-spacing: 0; }
      h2 { font-size: 1.15rem !important; }
      h3 { font-size: 1rem !important; }
      p, li, label, .stMarkdown, .stCaption { color: #1e293b; }
      .stTextInput label, .stSelectbox label, .stNumberInput label, .stDateInput label, .stTextArea label, .stFileUploader label, .stSlider label {
        color: #0f172a !important;
        font-weight: 600;
        font-size: 0.85rem;
      }
      .stTextInput input, .stSelectbox select, .stNumberInput input, .stDateInput input, .stTextArea textarea {
        color: #0f172a !important;
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
      }
      .stSelectbox div[data-baseweb="select"] {
        background: #ffffff !important;
        border: 1px solid #94a3b8 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
      }
      .stSelectbox div[data-baseweb="select"] *,
      .stSelectbox div[data-baseweb="select"] > div,
      .stSelectbox div[data-baseweb="select"] span,
      .stSelectbox div[data-baseweb="select"] svg {
        color: #0f172a !important;
        fill: #0f172a !important;
        background-color: transparent !important;
      }
      div[data-baseweb="popover"],
      div[data-baseweb="popover"] > div,
      ul[data-baseweb="menu"],
      div[role="listbox"] {
        background: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #94a3b8 !important;
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16) !important;
      }
      li[role="option"],
      div[role="option"] {
        background: #ffffff !important;
        color: #0f172a !important;
      }
      li[role="option"] *,
      div[role="option"] * {
        color: #0f172a !important;
      }
      li[role="option"]:hover,
      div[role="option"]:hover,
      li[aria-selected="true"],
      div[aria-selected="true"] {
        background: #dbeafe !important;
        color: #0f172a !important;
      }
      li[aria-selected="true"] *,
      div[aria-selected="true"] * {
        color: #0f172a !important;
      }
      [style*="background-color: rgb(0, 0, 0)"],
      [style*="background: rgb(0, 0, 0)"],
      [style*="background-color:#000"],
      [style*="background:#000"] {
        color: #ffffff !important;
      }
      div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 0.85rem 1rem;
      }
      div[data-testid="stMetric"] label {
        color: #475569 !important;
        font-weight: 500;
        font-size: 0.8rem;
      }
      div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-size: 1.4rem;
        font-weight: 700;
      }
      div[data-testid="stDataFrame"], .stDataFrame {
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px;
        background: #ffffff !important;
      }
      div[data-testid="stDataFrame"] * {
        color: #0f172a !important;
      }
      div[data-testid="stVerticalBlock"] > div:has(.panel-card) {
        background: #ffffff;
        border: 1px solid #dbe3ef;
        border-radius: 10px;
        padding: 0.9rem;
      }
      .panel-card {
        background: #ffffff;
        border: 1px solid #dbe3ef;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.6rem 0;
      }
      .run-meta {
        background: #eef2ff;
        color: #172554;
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        padding: 0.75rem 0.9rem;
        font-size: 0.86rem;
      }
      .caveat {
        border: 1px solid #eab308;
        background: #fefce8;
        color: #422006;
        padding: 0.8rem 1rem;
        border-radius: 8px;
        margin: 0.75rem 0 1rem 0;
        font-size: 0.85rem;
      }
      .stButton button,
      .stDownloadButton button,
      div[data-testid="stBaseButton-secondary"],
      div[data-testid="stBaseButton-primary"] {
        background: #1d4ed8 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
      }
      .stButton button *,
      .stDownloadButton button *,
      .stButton button p,
      .stDownloadButton button p,
      .stButton button span,
      .stDownloadButton button span {
        color: #ffffff !important;
        fill: #ffffff !important;
      }
      .stButton button:hover,
      .stDownloadButton button:hover {
        background: #1e40af !important;
      }
      .stFormSubmitButton button {
        background: #059669 !important;
        color: #ffffff !important;
      }
      .stFormSubmitButton button *,
      .stFormSubmitButton button p,
      .stFormSubmitButton button span {
        color: #ffffff !important;
        fill: #ffffff !important;
      }
      .stFormSubmitButton button:hover {
        background: #047857 !important;
      }
      .stTabs [data-baseweb="tab"] {
        color: #475569 !important;
        font-weight: 500;
      }
      .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #1d4ed8 !important;
        border-bottom: 3px solid #1d4ed8;
      }
      .stSelectbox div[data-baseweb="select"] div { color: #0f172a !important; }
      div[role="radiogroup"] {
        gap: 0.35rem;
      }
      div[role="radiogroup"] label {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 0.45rem 0.75rem !important;
        min-height: 38px !important;
      }
      div[role="radiogroup"] label:has(input:checked) {
        background: #eff6ff !important;
        border-color: #1d4ed8 !important;
        border-bottom: 3px solid #1d4ed8 !important;
      }
      div[role="radiogroup"] label *,
      div[role="radiogroup"] label p {
        color: #0f172a !important;
        font-weight: 650 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method, path, **kwargs):
    try:
        response = requests.request(
            method,
            f"{API}{path}",
            timeout=kwargs.pop("timeout", REQUEST_TIMEOUT),
            **kwargs,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach the backend at {API}. {exc}") from exc

    if not response.ok:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = response.text or response.reason
        raise RuntimeError(detail or f"{response.status_code} request failed.")

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.content


@st.cache_data(ttl=20, show_spinner=False)
def fetch_json(path, params=None):
    return api_request("GET", path, params=params)


def post_json(path, payload, timeout=REQUEST_TIMEOUT):
    return api_request("POST", path, json=payload, timeout=timeout)


def post_file(path, file, mapping=None):
    files = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}
    data = {}
    if mapping:
        data["mapping_json"] = json.dumps(mapping)
    return api_request("POST", path, files=files, data=data, timeout=LONG_TIMEOUT)


def invalidate_cache():
    fetch_json.clear()


def money(value):
    return f"${float(value or 0):,.0f}"


def table(records, columns=None, height=360):
    df = pd.DataFrame(records or [])
    if df.empty:
        st.info("No records available.")
        return df
    if columns:
        present = [col for col in columns if col in df.columns]
        df = df[present]
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)
    return df


def clean_params(params):
    return {key: value for key, value in params.items() if value not in (None, "", "All")}


CHART_COLORS = ["#1d4ed8", "#047857", "#b45309", "#7c3aed", "#be123c", "#0369a1"]


def style_chart(fig):
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#0f172a", size=13),
        margin=dict(l=18, r=18, t=30, b=24),
        legend=dict(font=dict(color="#0f172a"), bgcolor="rgba(255,255,255,0.85)"),
    )
    fig.update_xaxes(color="#0f172a", gridcolor="#e2e8f0", zerolinecolor="#cbd5e1", title_font=dict(color="#0f172a"), tickfont=dict(color="#0f172a"))
    fig.update_yaxes(color="#0f172a", gridcolor="#e2e8f0", zerolinecolor="#cbd5e1", title_font=dict(color="#0f172a"), tickfont=dict(color="#0f172a"))
    return fig


def chart_or_empty(df, kind, *, key=None, **kwargs):
    if df.empty:
        st.info("No chartable records yet.")
        return
    if "color_discrete_sequence" not in kwargs:
        kwargs["color_discrete_sequence"] = CHART_COLORS
    fig = getattr(px, kind)(df, **kwargs)
    style_chart(fig)
    st.plotly_chart(fig, use_container_width=True, key=key)


def render_header():
    st.title("GovFund Intelligence Assistant")
    st.caption("Production-oriented campaign finance intelligence portal for FEC and TEC public records.")
    st.markdown(f"<div class='caveat'>{SOURCE_CAVEAT}</div>", unsafe_allow_html=True)


def render_overview():
    overview = fetch_json("/analytics/overview")
    kpis = overview.get("kpis", {})
    monthly = pd.DataFrame(overview.get("monthly_trend", []))
    source_split = pd.DataFrame(overview.get("source_split", []))
    employers = pd.DataFrame(overview.get("top_employers", []))
    recipients = pd.DataFrame(overview.get("top_recipients", []))
    parties = pd.DataFrame(overview.get("party_distribution", []))
    topics = pd.DataFrame(overview.get("topic_distribution", []))
    geo = overview.get("geo_distribution", {})
    high_value = overview.get("recent_high_value", [])

    cols = st.columns(4)
    cols[0].metric("Total Records", f"{kpis.get('total_records', 0):,}")
    cols[1].metric("Total Amount", money(kpis.get("total_contribution_amount")))
    cols[2].metric("FEC / TEC", f"{kpis.get('fec_records', 0):,} / {kpis.get('tec_records', 0):,}")
    cols[3].metric("Quality Warnings", f"{kpis.get('data_quality_warning_count', 0):,}")

    cols = st.columns(4)
    cols[0].metric("Employer / Company Signals", f"{kpis.get('unique_employer_company_signals', 0):,}")
    cols[1].metric("Unique Contributors", f"{kpis.get('unique_contributors', 0):,}")
    cols[2].metric("Unique Recipients", f"{kpis.get('unique_recipients', 0):,}")
    cols[3].metric("Last Successful Ingestion", kpis.get("last_successful_ingestion") or "None")

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        st.subheader("Monthly Contribution Trend")
        chart_or_empty(monthly, "line", key="overview_monthly", x="month", y="total_amount", color="source_system", markers=True)
        st.subheader("Top Employer / Company Signals")
        chart_or_empty(employers.head(12).sort_values("total_amount"), "bar", key="overview_employers", x="total_amount", y="employer_company_signal", orientation="h")
        st.subheader("Top Recipients")
        chart_or_empty(recipients.head(12).sort_values("total_amount"), "bar", key="overview_recipients", x="total_amount", y="recipient_name", orientation="h")
    with right:
        st.subheader("Source Split")
        chart_or_empty(source_split, "pie", key="overview_source_split", names="source_system", values="transaction_count", hole=0.45)
        st.subheader("Party Distribution")
        if not parties.empty and "party" in parties:
            chart_or_empty(parties.head(10), "bar", key="overview_parties", x="party", y="transaction_count")
        else:
            st.info("Party data is not available in the current dataset.")
        st.subheader("Topic Tags")
        chart_or_empty(topics.head(12), "bar", key="overview_topics", x="topic_tag", y="transaction_count")

    geo_cols = st.columns(2)
    with geo_cols[0]:
        st.subheader("Top States")
        table(geo.get("states", []), height=220)
    with geo_cols[1]:
        st.subheader("Top Cities")
        table(geo.get("cities", []), height=220)

    st.subheader("Recent High-Value Records")
    table(
        high_value,
        ["transaction_date", "amount", "source_system", "contributor_name", "contributor_employer", "recipient_name", "party", "source_record_id"],
    )


def _fec_records_from_run(run_detail):
    if run_detail.get("records") is not None:
        return run_detail.get("records", [])
    result = run_detail.get("result") or {}
    return result.get("records", []) if isinstance(result, dict) else []


def _fec_display_frame(records):
    df = pd.DataFrame(records or [])
    if df.empty:
        return df
    if "topic_tags_json" in df.columns:
        df["topic_tags"] = df["topic_tags_json"].apply(
            lambda value: ", ".join(item.get("tag", "") for item in json.loads(value or "[]") if item.get("tag"))
            if isinstance(value, str)
            else ""
        )
    keep = [
        "transaction_date",
        "amount",
        "contributor_name",
        "contributor_employer",
        "contributor_city",
        "contributor_state",
        "recipient_name",
        "committee_name",
        "candidate_name",
        "party",
        "office",
        "district",
        "cycle",
        "topic_tags",
        "source_record_id",
    ]
    present = [column for column in keep if column in df.columns]
    out = df[present].copy()
    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    return out


def _fec_snapshot_charts(records):
    df = pd.DataFrame(records or [])
    if df.empty:
        st.info("No records in this FEC snapshot yet.")
        return
    if len(df) > MAX_CHART_ROWS:
        st.caption(f"Charts use the first {MAX_CHART_ROWS:,} records from this snapshot for responsiveness.")
        df = df.head(MAX_CHART_ROWS).copy()
    df["amount"] = pd.to_numeric(df.get("amount"), errors="coerce").fillna(0)
    df["transaction_date"] = pd.to_datetime(df.get("transaction_date"), errors="coerce")
    df["month"] = df["transaction_date"].dt.strftime("%Y-%m")

    chart_cols = st.columns(2, gap="large")
    with chart_cols[0]:
        monthly = df.dropna(subset=["month"]).groupby("month", as_index=False).agg(total_amount=("amount", "sum"), record_count=("amount", "size"))
        st.markdown("#### Monthly Trend")
        chart_or_empty(monthly, "line", key="fec_monthly", x="month", y="total_amount", markers=True)

        employers = (
            df.dropna(subset=["contributor_employer"])
            .groupby("contributor_employer", as_index=False)
            .agg(total_amount=("amount", "sum"), record_count=("amount", "size"))
            .sort_values("total_amount", ascending=False)
            .head(12)
        )
        st.markdown("#### Top Employer / Company Signals")
        chart_or_empty(employers.sort_values("total_amount"), "bar", key="fec_employers", x="total_amount", y="contributor_employer", orientation="h")

    with chart_cols[1]:
        recipients = (
            df.dropna(subset=["recipient_name"])
            .groupby("recipient_name", as_index=False)
            .agg(total_amount=("amount", "sum"), record_count=("amount", "size"))
            .sort_values("total_amount", ascending=False)
            .head(12)
        )
        st.markdown("#### Top Recipients / Committees")
        chart_or_empty(recipients.sort_values("total_amount"), "bar", key="fec_recipients", x="total_amount", y="recipient_name", orientation="h")

        parties = (
            df.dropna(subset=["party"])
            .groupby("party", as_index=False)
            .agg(record_count=("amount", "size"), total_amount=("amount", "sum"))
            .sort_values("record_count", ascending=False)
            .head(12)
        )
        st.markdown("#### Party Distribution")
        chart_or_empty(parties, "bar", key="fec_parties", x="party", y="record_count")

    geo_cols = st.columns(2, gap="large")
    with geo_cols[0]:
        states = df.dropna(subset=["contributor_state"]).groupby("contributor_state", as_index=False).agg(record_count=("amount", "size")).sort_values("record_count", ascending=False).head(15)
        st.markdown("#### Top States")
        table(states.to_dict("records"), height=260)
    with geo_cols[1]:
        high_value = df.sort_values("amount", ascending=False).head(15)
        st.markdown("#### High-Value Records")
        table(_fec_display_frame(high_value.to_dict("records")).to_dict("records"), height=260)


def render_fec_tab():
    st.subheader("FEC")
    config = fetch_json("/ingestion/config")
    fec_ready = bool(config.get("fec", {}).get("enabled"))
    st.markdown(f"<div class='caveat'>{SOURCE_CAVEAT}</div>", unsafe_allow_html=True)
    if not fec_ready:
        st.warning(config.get("fec", {}).get("status_message", "FEC_API_KEY is not configured."))

    with st.form("fec_query_form"):
        cols = st.columns(4)
        contributor_name = cols[0].text_input("Contributor name")
        contributor_employer = cols[1].text_input("Employer / company signal")
        contributor_state = cols[2].text_input("State", placeholder="TX")
        contributor_city = cols[3].text_input("City")
        cols = st.columns(4)
        committee_id = cols[0].text_input("Committee ID")
        candidate_id = cols[1].text_input("Candidate ID")
        cycle = cols[2].text_input("Cycle / two-year period", placeholder="2024")
        max_records = cols[3].number_input("Max records", min_value=1, max_value=100000, value=50, step=25)
        cols = st.columns(4)
        min_date = cols[0].date_input("Min date", value=None, key="fec_tab_min_date")
        max_date = cols[1].date_input("Max date", value=None, key="fec_tab_max_date")
        min_amount = cols[2].number_input("Min amount", min_value=0.0, value=0.0, step=100.0, key="fec_tab_min_amount")
        max_amount = cols[3].number_input("Max amount", min_value=0.0, value=0.0, step=100.0, key="fec_tab_max_amount")
        submit = st.form_submit_button("Submit FEC Query", use_container_width=True, disabled=not fec_ready)

    if submit:
        payload = clean_params(
            {
                "contributor_name": contributor_name,
                "contributor_employer": contributor_employer,
                "contributor_state": contributor_state.upper() if contributor_state else None,
                "contributor_city": contributor_city,
                "committee_id": committee_id,
                "candidate_id": candidate_id,
                "two_year_transaction_period": cycle,
                "min_date": min_date.isoformat() if min_date else None,
                "max_date": max_date.isoformat() if max_date else None,
                "min_amount": min_amount if min_amount else None,
                "max_amount": max_amount if max_amount else None,
                "per_page": 100,
                "max_records": int(max_records),
            }
        )
        try:
            with st.spinner("Fetching OpenFEC records and storing the query snapshot..."):
                response = post_json("/ingestion/fec", payload, timeout=LONG_TIMEOUT)
            invalidate_cache()
            st.session_state["selected_fec_run_id"] = response.get("fec_query_run_id")
            st.success(
                f"FEC {response['status']}: pages {response['pages_processed']}, raw {response['raw_records_fetched']}, "
                f"inserted {response['inserted_count']}, duplicates {response['duplicate_count']}."
            )
            for error in response.get("errors", []):
                st.warning(error)
        except RuntimeError as exc:
            st.error(str(exc))

    runs = fetch_json("/ingestion/fec-runs", params={"limit": 20})
    if runs:
        run_options = {
            (
                f"#{run['id']} - {run['status']} - {run.get('raw_records_fetched', 0)} raw"
                f" - {run.get('query_summary') or ''}"
            ): run["id"]
            for run in runs
        }
        default_run = st.session_state.get("selected_fec_run_id") or runs[0]["id"]
        labels = list(run_options.keys())
        default_index = next((i for i, label in enumerate(labels) if run_options[label] == default_run), 0)
        selected_label = st.selectbox("Stored FEC query snapshots", labels, index=default_index)
        selected_run_id = run_options[selected_label]
        st.session_state["selected_fec_run_id"] = selected_run_id
        detail = fetch_json(f"/ingestion/fec-runs/{selected_run_id}", params={"include_result": False})
        records = _fec_records_from_run(detail)

        meta_cols = st.columns(5)
        meta_cols[0].metric("Status", detail.get("status", "unknown"))
        meta_cols[1].metric("Pages", f"{detail.get('pages_processed', 0):,}")
        meta_cols[2].metric("Raw Records", f"{detail.get('raw_records_fetched', 0):,}")
        meta_cols[3].metric("Inserted", f"{detail.get('inserted_count', 0):,}")
        meta_cols[4].metric("Duplicates", f"{detail.get('duplicate_count', 0):,}")

        st.markdown(
            f"<div class='run-meta'>Snapshot #{selected_run_id} is stored in the database and can be reused for AI analysis, exports, and graphs.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Prepare Stored FEC Snapshot JSON", use_container_width=True):
            with st.spinner("Loading full stored JSON snapshot..."):
                st.session_state[f"fec_json_{selected_run_id}"] = fetch_json(f"/ingestion/fec-runs/{selected_run_id}/json")
        result_json = st.session_state.get(f"fec_json_{selected_run_id}")
        if result_json is not None:
            st.download_button(
                "Download Stored FEC Snapshot JSON",
                json.dumps(result_json, indent=2, default=str),
                file_name=f"fec_query_run_{selected_run_id}.json",
                mime="application/json",
                use_container_width=True,
            )

        st.markdown("### Query Results")
        display_df = _fec_display_frame(records)
        if display_df.empty:
            st.info("This snapshot has no records.")
        else:
            if len(display_df) > MAX_TABLE_ROWS:
                st.caption(f"Showing first {MAX_TABLE_ROWS:,} rows for responsiveness. Download the JSON snapshot for the full result set.")
            st.dataframe(display_df.head(MAX_TABLE_ROWS), use_container_width=True, hide_index=True, height=420)
            with st.expander("Inspect compact JSON rows"):
                st.json(records[:50])

        st.markdown("### Snapshot Graphs")
        _fec_snapshot_charts(records)
    else:
        st.info("No FEC query snapshots have been stored yet.")


def render_search_explorer():
    st.subheader("Search Explorer")
    with st.form("search_filters"):
        cols = st.columns(4)
        source = cols[0].selectbox("Source", ["All", "FEC", "TEC"])
        min_date = cols[1].date_input("Min date", value=None)
        max_date = cols[2].date_input("Max date", value=None)
        topic = cols[3].text_input("Topic tag")
        cols = st.columns(4)
        min_amount = cols[0].number_input("Min amount", min_value=0.0, value=0.0, step=100.0)
        max_amount = cols[1].number_input("Max amount", min_value=0.0, value=0.0, step=100.0)
        state = cols[2].text_input("State")
        city = cols[3].text_input("City")
        cols = st.columns(4)
        contributor = cols[0].text_input("Contributor")
        employer = cols[1].text_input("Employer / company signal")
        recipient = cols[2].text_input("Recipient / candidate / committee")
        party = cols[3].text_input("Party")
        cols = st.columns(3)
        cycle = cols[0].text_input("Cycle")
        tx_type = cols[1].text_input("Transaction type")
        quality = cols[2].text_input("Data quality flag")
        submitted = st.form_submit_button("Search", use_container_width=True)

    params = clean_params(
        {
            "source_system": source,
            "min_date": min_date.isoformat() if min_date else None,
            "max_date": max_date.isoformat() if max_date else None,
            "min_amount": min_amount if min_amount else None,
            "max_amount": max_amount if max_amount else None,
            "contributor_name": contributor,
            "contributor_employer": employer,
            "recipient": recipient,
            "party": party,
            "state": state.upper() if state else None,
            "city": city,
            "cycle": cycle,
            "topic_tag": topic,
            "transaction_type": tx_type,
            "data_quality_flag": quality,
            "limit": 100,
        }
    )
    results = fetch_json("/transactions", params=params if submitted or params else {"limit": 100})
    st.caption(f"{results.get('total', 0):,} matching records. Showing up to {results.get('limit', 100):,}.")
    df = table(
        results.get("items", []),
        [
            "transaction_date",
            "amount",
            "source_system",
            "contributor_name",
            "contributor_employer",
            "contributor_entity_name",
            "recipient_name",
            "committee_name",
            "candidate_name",
            "party",
            "office",
            "district",
            "topic_tags_json",
            "confidence_score",
            "source_record_id",
        ],
    )
    if not df.empty:
        st.download_button("Export Displayed Records to CSV", df.to_csv(index=False), "govfund_filtered_records.csv", "text/csv")


def _option_names(records, key):
    return [row.get(key) for row in records if row.get(key)]


def render_company_dossier():
    st.subheader("Company / Employer Dossier")
    st.markdown(f"<div class='caveat'>{SOURCE_CAVEAT}</div>", unsafe_allow_html=True)
    employers = fetch_json("/analytics/top-employers")
    options = _option_names(employers, "employer_company_signal")
    selected = st.selectbox("Select employer/company signal", options or [""], index=0)
    typed = st.text_input("Or type exact employer/company signal", value=selected or "")
    if not typed:
        st.info("No employer/company signals are available yet.")
        return
    dossier = fetch_json("/analytics/company-dossier", params={"employer": typed})
    kpis = dossier.get("kpis", {})
    cols = st.columns(5)
    cols[0].metric("Matched Records", f"{kpis.get('matched_records', 0):,}")
    cols[1].metric("Total Amount", money(kpis.get("total_amount")))
    cols[2].metric("Unique Contributors", f"{kpis.get('unique_contributors', 0):,}")
    cols[3].metric("Unique Recipients", f"{kpis.get('unique_recipients', 0):,}")
    cols[4].metric("Date Range", " - ".join([str(x) for x in kpis.get("date_range", []) if x]) or "N/A")

    cols = st.columns(2)
    with cols[0]:
        st.subheader("Monthly Timeline")
        chart_or_empty(pd.DataFrame(dossier.get("monthly_timeline", [])), "line", key="company_monthly", x="month", y="total_amount", color="source_system", markers=True)
        st.subheader("Top Recipients")
        table(dossier.get("top_recipients", []), height=260)
    with cols[1]:
        st.subheader("Topic Distribution")
        chart_or_empty(pd.DataFrame(dossier.get("topic_distribution", [])), "bar", key="company_topics", x="topic_tag", y="transaction_count")
        st.subheader("Party Distribution")
        table(dossier.get("party_distribution", []), height=260)

    st.subheader("Top Contributors")
    table(dossier.get("top_contributors", []), height=250)
    st.subheader("Source Evidence")
    table(dossier.get("recent_records", []), ["transaction_date", "amount", "source_system", "contributor_name", "recipient_name", "party", "source_record_id"])


def render_recipient_dossier():
    st.subheader("Recipient / Committee Dossier")
    recipients = fetch_json("/analytics/top-recipients")
    options = _option_names(recipients, "recipient_name")
    selected = st.selectbox("Select recipient/candidate/committee/filer", options or [""], index=0)
    typed = st.text_input("Or type exact recipient name", value=selected or "")
    if not typed:
        st.info("No recipients are available yet.")
        return
    dossier = fetch_json("/analytics/recipient-dossier", params={"recipient": typed})
    kpis = dossier.get("kpis", {})
    cols = st.columns(5)
    cols[0].metric("Matched Records", f"{kpis.get('matched_records', 0):,}")
    cols[1].metric("Total Amount", money(kpis.get("total_amount")))
    cols[2].metric("Unique Contributors", f"{kpis.get('unique_contributors', 0):,}")
    cols[3].metric("Employer Signals", f"{kpis.get('unique_employer_company_signals', 0):,}")
    cols[4].metric("Party", kpis.get("party") or "N/A")
    st.caption(f"Office: {kpis.get('office') or 'N/A'} | District: {kpis.get('district') or 'N/A'}")

    cols = st.columns(2)
    with cols[0]:
        st.subheader("Monthly Timeline")
        chart_or_empty(pd.DataFrame(dossier.get("monthly_timeline", [])), "line", key="recipient_monthly", x="month", y="total_amount", color="source_system", markers=True)
        st.subheader("Top Employer / Company Signals")
        table(dossier.get("top_employers", []), height=260)
    with cols[1]:
        st.subheader("Topic Tags")
        chart_or_empty(pd.DataFrame(dossier.get("topic_distribution", [])), "bar", key="recipient_topics", x="topic_tag", y="transaction_count")
        st.subheader("Top Contributors")
        table(dossier.get("top_contributors", []), height=260)

    st.subheader("Source Evidence")
    table(dossier.get("source_evidence", []), ["transaction_date", "amount", "source_system", "contributor_name", "contributor_employer", "source_record_id"])


def render_network_map():
    st.subheader("Network Map")
    cols = st.columns(5)
    source = cols[0].selectbox("Source", ["All", "FEC", "TEC"], key="network_source")
    min_amount = cols[1].number_input("Minimum amount", min_value=0.0, value=0.0, step=100.0)
    topic = cols[2].text_input("Topic", key="network_topic")
    employer = cols[3].text_input("Employer signal", key="network_employer")
    recipient = cols[4].text_input("Recipient", key="network_recipient")
    max_nodes = st.slider("Max nodes", 10, 80, 40)
    data = fetch_json(
        "/analytics/network",
        params=clean_params(
            {
                "source_system": source,
                "min_amount": min_amount if min_amount else None,
                "topic_tag": topic,
                "contributor_employer": employer,
                "recipient": recipient,
                "max_nodes": max_nodes,
            }
        ),
    )
    if not data.get("nodes") or not data.get("links"):
        st.info("Not enough connected real records to draw a network yet.")
        return
    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(label=data["nodes"], pad=12, thickness=14),
                link=dict(
                    source=[link["source"] for link in data["links"]],
                    target=[link["target"] for link in data["links"]],
                    value=[link["value"] for link in data["links"]],
                ),
            )
        ]
    )
    fig.update_layout(height=620, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True, key="network_sankey")


def render_ai_room():
    st.subheader("AI Briefing Room")
    status = fetch_json("/ai/status")
    if not status.get("enabled"):
        st.warning(status.get("message"))
        st.caption("Deterministic analytics remain available throughout the portal.")
        return
    brief_type = st.selectbox(
        "Brief type",
        [
            "company_employer_signal_brief",
            "recipient_committee_brief",
            "competitor_comparison",
            "monthly_monitoring_brief",
            "spike_anomaly_explanation",
            "infrastructure_topic_relevance_brief",
            "custom_question",
        ],
    )
    question = st.text_area("Question over current ingested records", "Summarize the most important source-backed patterns.")
    runs = fetch_json("/ingestion/fec-runs", params={"limit": 20})
    run_labels = ["Whole database"] + [
        f"FEC snapshot #{run['id']} - {run['status']} - {run.get('raw_records_fetched', 0)} raw"
        for run in runs
    ]
    selected_run_label = st.selectbox("Analysis source", run_labels)
    selected_run_id = None
    if selected_run_label != "Whole database":
        selected_run_id = runs[run_labels.index(selected_run_label) - 1]["id"]
    cols = st.columns(3)
    employer = cols[0].text_input("Employer/company filter")
    recipient = cols[1].text_input("Recipient filter")
    topic = cols[2].text_input("Topic filter")
    if st.button("Generate Grounded Brief", use_container_width=True):
        response = post_json(
            "/ai/ask",
            {
                "question": question,
                "insight_type": brief_type,
                "filters": clean_params({"fec_query_run_id": selected_run_id, "contributor_employer": employer, "recipient": recipient, "topic_tag": topic}),
            },
            timeout=LONG_TIMEOUT,
        )
        if response.get("mode") == "error":
            st.error(response.get("message"))
        elif response.get("mode") == "compliance_block":
            st.warning(response.get("message"))
        else:
            st.markdown(response.get("output_text") or response.get("message", ""))
        st.caption(response.get("compliance_footer", ""))


def _fetch_export(endpoint):
    try:
        return api_request("GET", endpoint)
    except RuntimeError:
        return None


def render_data_exports():
    st.subheader("Data & Exports")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Prepare Excel Workbook", use_container_width=True):
            with st.spinner("Preparing workbook..."):
                st.session_state["export_excel"] = _fetch_export("/exports/excel")
        if st.session_state.get("export_excel") is not None:
            st.download_button(
                "Download Full Excel Workbook",
                io.BytesIO(st.session_state["export_excel"]),
                "govfund_export.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with col2:
        if st.button("Prepare Audit CSV", use_container_width=True):
            st.session_state["export_audit"] = _fetch_export("/exports/audit-logs")
        if st.session_state.get("export_audit") is not None:
            st.download_button(
                "Download Audit Logs CSV",
                io.BytesIO(st.session_state["export_audit"]),
                "govfund_audit_logs.csv",
                "text/csv",
                use_container_width=True,
            )
    with col3:
        if st.button("Prepare Quality CSV", use_container_width=True):
            st.session_state["export_flags"] = _fetch_export("/exports/data-quality-flags")
        if st.session_state.get("export_flags") is not None:
            st.download_button(
                "Download Quality Flags CSV",
                io.BytesIO(st.session_state["export_flags"]),
                "govfund_data_quality_flags.csv",
                "text/csv",
                use_container_width=True,
            )

    view = st.radio(
        "Data view",
        ["Normalized Transactions", "Raw Records", "Source Audit Logs", "Data Quality Flags"],
        horizontal=True,
    )
    if view == "Normalized Transactions":
        result = fetch_json("/transactions", params={"limit": 100})
        table(result.get("items", []), height=460)
    elif view == "Raw Records":
        result = fetch_json("/transactions/raw", params={"limit": 100})
        table(result.get("items", []), ["id", "source_system", "source_record_id", "source_url", "ingested_at"], height=460)
    elif view == "Source Audit Logs":
        table(fetch_json("/ingestion/audit-logs"), height=460)
    else:
        table(fetch_json("/ingestion/data-quality-flags"), height=460)


def render_admin():
    st.subheader("Admin / Data Sources")
    config = fetch_json("/ingestion/config")
    cols = st.columns(3)
    cols[0].metric("FEC Status", "Enabled" if config["fec"]["enabled"] else "Needs key")
    cols[1].metric("TEC Status", "File import")
    cols[2].metric("AI Status", "Enabled" if config["ai"]["enabled"] else "Not configured")
    st.caption(config["fec"]["status_message"])

    st.markdown("### FEC OpenFEC Ingestion")
    with st.form("fec_ingest"):
        cols = st.columns(4)
        contributor_name = cols[0].text_input("Contributor name")
        contributor_employer = cols[1].text_input("Employer/company signal")
        contributor_state = cols[2].text_input("State")
        contributor_city = cols[3].text_input("City")
        cols = st.columns(4)
        committee_id = cols[0].text_input("Committee ID")
        candidate_id = cols[1].text_input("Candidate ID")
        min_date = cols[2].date_input("Min date", value=None, key="fec_min")
        max_date = cols[3].date_input("Max date", value=None, key="fec_max")
        cols = st.columns(4)
        min_amount = cols[0].number_input("Min amount", min_value=0.0, value=0.0, step=100.0, key="fec_min_amount")
        max_amount = cols[1].number_input("Max amount", min_value=0.0, value=0.0, step=100.0, key="fec_max_amount")
        cycle = cols[2].text_input("Cycle / two-year period")
        max_records = cols[3].number_input("Max records", min_value=1, max_value=100000, value=5000, step=500)
        run_fec = st.form_submit_button("Run FEC Ingestion", use_container_width=True, disabled=not config["fec"]["enabled"])
    if run_fec:
        payload = clean_params(
            {
                "contributor_name": contributor_name,
                "contributor_employer": contributor_employer,
                "contributor_state": contributor_state.upper() if contributor_state else None,
                "contributor_city": contributor_city,
                "committee_id": committee_id,
                "candidate_id": candidate_id,
                "min_date": min_date.isoformat() if min_date else None,
                "max_date": max_date.isoformat() if max_date else None,
                "min_amount": min_amount if min_amount else None,
                "max_amount": max_amount if max_amount else None,
                "two_year_transaction_period": cycle,
                "per_page": 100,
                "max_records": int(max_records),
            }
        )
        response = post_json("/ingestion/fec", payload, timeout=LONG_TIMEOUT)
        invalidate_cache()
        st.success(
            f"FEC {response['status']}: pages {response['pages_processed']}, raw {response['raw_records_fetched']}, "
            f"inserted {response['inserted_count']}, duplicates {response['duplicate_count']}."
        )
        if response.get("errors"):
            st.warning("; ".join(response["errors"]))

    st.markdown("### TEC CSV/XLSX Import")
    upload = st.file_uploader("Upload official TEC CSV/XLSX export", type=["csv", "xlsx", "xls"])
    if upload:
        if st.button("Preview TEC Mapping", use_container_width=True):
            preview = post_file("/ingestion/tec-preview", upload)
            st.session_state["tec_preview"] = preview
            st.session_state["tec_mapping"] = preview.get("mapping", {})
        preview = st.session_state.get("tec_preview")
        if preview:
            st.caption(f"Mapping confidence: {preview.get('confidence')}")
            for warning in preview.get("warnings", []):
                st.warning(warning)
            table(preview.get("preview_rows", []), height=220)
            columns = [""] + preview.get("columns", [])
            mapping = st.session_state.get("tec_mapping", {})
            st.markdown("Manual mapping")
            fields = ["transaction_date", "amount", "recipient_name", "contributor_name", "contributor_entity_name", "contributor_employer", "filer_id", "filer_name", "source_record_id", "transaction_type", "purpose"]
            for field in fields:
                current = mapping.get(field) or ""
                index = columns.index(current) if current in columns else 0
                mapping[field] = st.selectbox(field, columns, index=index, key=f"map_{field}") or None
            st.session_state["tec_mapping"] = mapping
            if st.button("Import TEC File", use_container_width=True):
                response = post_file("/ingestion/tec-file", upload, mapping=mapping)
                invalidate_cache()
                st.success(
                    f"TEC {response['status']}: raw {response['raw_records_fetched']}, "
                    f"inserted {response['inserted_count']}, duplicates {response['duplicate_count']}."
                )
                for warning in response.get("warnings", []):
                    st.info(warning)

    st.markdown("### Latest Audit Logs")
    table(fetch_json("/ingestion/audit-logs"), height=320)
    st.markdown("### Data Quality Flags")
    table(fetch_json("/ingestion/data-quality-flags"), height=320)


render_header()

try:
    page = st.radio(
        "Navigation",
        [
            "FEC",
            "Overview",
            "Search Explorer",
            "Company / Employer Dossier",
            "Recipient / Committee Dossier",
            "Network Map",
            "AI Briefing Room",
            "Data & Exports",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    if page == "FEC":
        render_fec_tab()
    elif page == "Overview":
        render_overview()
    elif page == "Search Explorer":
        render_search_explorer()
    elif page == "Company / Employer Dossier":
        render_company_dossier()
    elif page == "Recipient / Committee Dossier":
        render_recipient_dossier()
    elif page == "Network Map":
        render_network_map()
    elif page == "AI Briefing Room":
        render_ai_room()
    elif page == "Data & Exports":
        render_data_exports()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()
