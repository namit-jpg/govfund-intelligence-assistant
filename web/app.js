const page = document.querySelector("#page");
const toast = document.querySelector("#toast");
const apiStatus = document.querySelector("#apiStatus");
const state = { page: "ai", runs: [], selectedRunId: null, runDetail: null, overview: null };

const money = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(Number(value || 0));

const todayIso = () => new Date().toISOString().slice(0, 10);

const esc = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

function inlineMarkdown(text) {
  return esc(text)
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    )
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function renderMarkdown(text) {
  const lines = String(text || "").split(/\r?\n/);
  const html = [];
  let listOpen = false;

  const closeList = () => {
    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 1, 4);
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li>${inlineMarkdown(bullet[1])}</li>`);
      continue;
    }
    closeList();
    html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }
  closeList();
  return `<article class="ai-brief">${html.join("")}</article>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let message = `${response.status} request failed`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response.blob();
}

function showToast(message, isError = false) {
  toast.className = isError ? "toast error" : "toast";
  toast.textContent = message;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 5000);
}

function compactPayload(form) {
  const payload = {};
  new FormData(form).forEach((value, key) => {
    const text = String(value || "").trim();
    if (!text) return;
    if (key === "contributor_state") payload[key] = text.toUpperCase();
    else if (["max_records", "min_amount", "max_amount"].includes(key)) payload[key] = Number(text);
    else payload[key] = text;
  });
  payload.per_page = 100;
  return payload;
}

function metric(label, value) {
  return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function table(rows, columns) {
  if (!rows || !rows.length) return `<div class="empty">No records available.</div>`;
  const headers = columns.map((column) => `<th>${esc(column.label)}</th>`).join("");
  const body = rows
    .map(
      (row) =>
        `<tr>${columns
          .map((column) => {
            const raw = row[column.key];
            const value = column.money ? money(raw) : raw;
            return `<td>${esc(value)}</td>`;
          })
          .join("")}</tr>`,
    )
    .join("");
  return `<div class="table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function groupRows(rows, key, valueKey = "amount", limit = 12) {
  const map = new Map();
  rows.forEach((row) => {
    const name = row[key];
    if (!name) return;
    const current = map.get(name) || { name, amount: 0, count: 0 };
    current.amount += Number(row[valueKey] || 0);
    current.count += 1;
    map.set(name, current);
  });
  return [...map.values()].sort((a, b) => b.amount - a.amount).slice(0, limit);
}

function chartBars(title, rows, mode = "amount") {
  if (!rows.length) return `<div class="chart-card"><h3>${esc(title)}</h3><div class="empty">No chartable data.</div></div>`;
  const max = Math.max(...rows.map((row) => (mode === "count" ? row.count : row.amount)), 1);
  const bars = rows
    .map((row) => {
      const value = mode === "count" ? row.count : row.amount;
      return `<div class="bar-row">
        <div title="${esc(row.name)}">${esc(row.name)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (value / max) * 100)}%"></div></div>
        <strong>${mode === "count" ? esc(value) : esc(money(value))}</strong>
      </div>`;
    })
    .join("");
  return `<div class="chart-card"><h3>${esc(title)}</h3>${bars}</div>`;
}

function chartMonthly(rows) {
  const map = new Map();
  rows.forEach((row) => {
    if (!row.transaction_date) return;
    const month = String(row.transaction_date).slice(0, 7);
    map.set(month, (map.get(month) || 0) + Number(row.amount || 0));
  });
  const points = [...map.entries()].sort().map(([name, amount]) => ({ name, amount }));
  return chartBars("Monthly Trend", points, "amount");
}

function renderCharts(rows) {
  const parties = groupRows(rows, "party", "amount", 10).map((row) => ({ ...row, amount: row.count }));
  return [
    chartMonthly(rows),
    chartBars("Top Employer / Company Signals", groupRows(rows, "contributor_employer")),
    chartBars("Top Recipients / Committees", groupRows(rows, "recipient_name")),
    chartBars("Party Distribution", parties, "count"),
  ].join("");
}

const fecColumns = [
  { key: "transaction_date", label: "Date" },
  { key: "amount", label: "Amount", money: true },
  { key: "contributor_name", label: "Contributor" },
  { key: "contributor_employer", label: "Employer / Company Signal" },
  { key: "contributor_city", label: "City" },
  { key: "contributor_state", label: "State" },
  { key: "recipient_name", label: "Recipient" },
  { key: "committee_name", label: "Committee" },
  { key: "party", label: "Party" },
  { key: "cycle", label: "Cycle" },
  { key: "source_record_id", label: "Source Record ID" },
];

async function loadRuns() {
  state.runs = await api("/ingestion/fec-runs?limit=20");
  if (!state.selectedRunId && state.runs.length) state.selectedRunId = state.runs[0].id;
}

async function loadRunDetail(runId) {
  if (!runId) {
    state.runDetail = null;
    return;
  }
  state.runDetail = await api(`/ingestion/fec-runs/${runId}?include_result=false`);
}

function renderRunSelect() {
  const select = document.querySelector("#runSelect");
  if (!state.runs.length) {
    select.innerHTML = `<option>No stored FEC snapshots</option>`;
    return;
  }
  select.innerHTML = state.runs
    .map(
      (run) =>
        `<option value="${run.id}" ${Number(state.selectedRunId) === Number(run.id) ? "selected" : ""}>#${run.id} - ${esc(run.status)} - ${esc(run.raw_records_fetched)} raw - ${esc(run.query_summary)}</option>`,
    )
    .join("");
}

function renderRunDetail() {
  const detail = state.runDetail;
  const rows = detail?.records || [];
  const today = todayIso();
  const futureRows = rows.filter((row) => row.transaction_date && String(row.transaction_date).slice(0, 10) > today);
  const futureNotice = futureRows.length
      ? `<div class="warning span-charts"><strong>${futureRows.length}</strong> source row${futureRows.length === 1 ? "" : "s"} in this snapshot have future transaction dates after ${esc(today)}. They are preserved because they came from OpenFEC, but review the source records before drawing conclusions.</div>`
    : "";
  document.querySelector("#runSummary").innerHTML = detail
    ? [
        metric("Status", detail.status),
        metric("Pages", detail.pages_processed || 0),
        metric("Raw Records", detail.raw_records_fetched || 0),
        metric("Inserted", detail.inserted_count || 0),
        metric("Duplicates", detail.duplicate_count || 0),
        metric("Loaded Rows", rows.length),
      ].join("")
    : `<div class="empty">No snapshot selected.</div>`;
  document.querySelector("#fecResultCaption").textContent = detail
    ? `Snapshot #${detail.id}. Showing compact rows for fast review.`
    : "Select or run a query.";
  document.querySelector("#fecTable").innerHTML = futureNotice + table(rows, fecColumns);
  document.querySelector("#fecCharts").innerHTML = futureNotice + renderCharts(rows);
}

async function renderFec() {
  page.innerHTML = document.querySelector("#fecTemplate").innerHTML;
  await loadRuns();
  renderRunSelect();
  await loadRunDetail(state.selectedRunId);
  renderRunDetail();

  document.querySelector("#refreshRuns").addEventListener("click", async () => {
    await loadRuns();
    renderRunSelect();
    await loadRunDetail(state.selectedRunId);
    renderRunDetail();
    showToast("Snapshots refreshed.");
  });

  document.querySelector("#runSelect").addEventListener("change", async (event) => {
    state.selectedRunId = Number(event.target.value);
    await loadRunDetail(state.selectedRunId);
    renderRunDetail();
  });

  document.querySelector("#downloadXlsx").addEventListener("click", async () => {
    if (!state.selectedRunId) return;
    const button = document.querySelector("#downloadXlsx");
    button.disabled = true;
    button.textContent = "Downloading...";
    try {
      const blob = await api(`/ingestion/fec-runs/${state.selectedRunId}/xlsx`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `fec_snapshot_${state.selectedRunId}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      button.disabled = false;
      button.textContent = "Download Stored XLSX";
    }
  });

  document.querySelector("#fecForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("button[type='submit']");
    button.disabled = true;
    button.textContent = "Fetching OpenFEC records...";
    try {
      const result = await api("/ingestion/fec", { method: "POST", body: JSON.stringify(compactPayload(event.target)) });
      state.selectedRunId = result.fec_query_run_id;
      await loadRuns();
      renderRunSelect();
      await loadRunDetail(state.selectedRunId);
      renderRunDetail();
      showToast(`FEC ${result.status}: ${result.raw_records_fetched} raw, ${result.inserted_count} inserted, ${result.duplicate_count} duplicates.`);
    } catch (error) {
      showToast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "Submit FEC Query";
    }
  });
}

function renderOverviewCharts(data) {
  const employers = (data.top_employers || []).map((row) => ({ name: row.employer_company_signal, amount: row.total_amount, count: row.transaction_count }));
  const recipients = (data.top_recipients || []).map((row) => ({ name: row.recipient_name, amount: row.total_amount, count: row.transaction_count }));
  const sources = (data.source_split || []).map((row) => ({ name: row.source_system, amount: row.total_amount, count: row.transaction_count }));
  const topics = (data.topic_distribution || []).map((row) => ({ name: row.topic_tag, amount: row.total_amount, count: row.transaction_count }));
  return [
    chartBars("Source Split", sources),
    chartBars("Top Employer / Company Signals", employers),
    chartBars("Top Recipients", recipients),
    chartBars("Topic Tags", topics, "count"),
  ].join("");
}

async function renderOverview() {
  const data = await api("/analytics/overview");
  const kpis = data.kpis || {};
  page.innerHTML = `
    <section class="panel">
      <div class="section-title"><h2>Dataset Overview</h2><span>All stored ingested records, not a single query</span></div>
      <div class="ai-note">This page summarizes the current local database across all completed imports and FEC snapshots. The total amount is a point-in-time aggregate of stored records, not a fresh live FEC total and not limited to the last visible query.</div>
      <div class="metric-grid">
        ${metric("Total Records", kpis.total_records || 0)}
        ${metric("Total Amount", money(kpis.total_contribution_amount))}
        ${metric("FEC Records", kpis.fec_records || 0)}
        ${metric("Unique Recipients", kpis.unique_recipients || 0)}
        ${metric("Employer / Company Signals", kpis.unique_employer_company_signals || 0)}
        ${metric("Quality Warnings", kpis.data_quality_warning_count || 0)}
      </div>
    </section>
    <section class="panel"><div class="chart-grid">${renderOverviewCharts(data)}</div></section>
    <section class="panel">
      <div class="section-title"><h2>Recent High-Value Records</h2><span>Top source-backed rows</span></div>
      ${table(data.recent_high_value || [], fecColumns)}
    </section>
  `;
}

async function renderSearch() {
  page.innerHTML = `
    <section class="panel">
      <div class="section-title"><h2>Search Donations</h2><span>Contributor, employer/business, recipient, committee, or source ID</span></div>
      <form id="searchForm" class="form-grid">
        <label class="span-all">Search term<input name="q" placeholder="Example: Alex Mealer, AECOM, Sammons, C008..." /></label>
        <label>Source<select name="source_system"><option>All</option><option>FEC</option><option>TEC</option></select></label>
        <label>Contributor<input name="contributor_name" /></label>
        <label>Employer / company signal<input name="contributor_employer" /></label>
        <label>Recipient<input name="recipient" /></label>
        <label>State<input name="state" maxlength="2" /></label>
        <label>Cycle<input name="cycle" /></label>
        <label>Min amount<input name="min_amount" type="number" min="0" /></label>
        <label>Max amount<input name="max_amount" type="number" min="0" /></label>
        <button class="primary span-all" type="submit">Search</button>
      </form>
    </section>
    <section class="panel">
      <div class="section-title"><h2>Donation Results</h2><button id="exportSearchXlsx" class="secondary small-button" type="button">Export Results to Excel</button></div>
      <div id="searchResults"></div>
    </section>
  `;
  let lastParams = "limit=100";
  const renderResults = async (params = "limit=100") => {
    lastParams = params;
    const data = await api(`/transactions?${params}`);
    const currentParams = new URLSearchParams(params);
    const noResultsNote =
      Number(data.total || 0) === 0 && currentParams.get("q")
        ? `<div class="warning">No matching local ingested records were found for "${esc(currentParams.get("q"))}". This is not a ChatGPT/web search; run a targeted FEC Data Pull or check candidate/committee aliases if coverage is expected.</div>`
        : "";
    document.querySelector("#searchResults").innerHTML = `<p><strong>${esc(data.total || 0)}</strong> matching records. Showing ${esc(data.limit || 100)}.</p>${noResultsNote}${table(data.items || [], fecColumns)}`;
  };
  await renderResults();
  document.querySelector("#searchForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const params = new URLSearchParams();
    new FormData(event.target).forEach((value, key) => {
      const text = String(value || "").trim();
      if (text && text !== "All") params.set(key, key === "state" ? text.toUpperCase() : text);
    });
    params.set("limit", "100");
    await renderResults(params.toString());
  });
  document.querySelector("#exportSearchXlsx").addEventListener("click", () => {
    const params = new URLSearchParams(lastParams);
    params.delete("limit");
    window.location.href = `/exports/transactions.xlsx?${params.toString()}`;
  });
}

async function renderAi() {
  const status = await api("/ai/status");
  page.innerHTML = `
    <section class="panel ai-hero">
      <div class="section-title"><h2>AI Intelligence Query</h2><span>Detailed analyst memo</span></div>
      <div class="ai-note">Ask a plain-language question. The AI now produces a fuller analyst memo: donation facts come from locally ingested FEC/TEC records, while web/news context prioritizes independent news, campaign-finance trackers, watchdog/nonprofit sources, and public records over company marketing pages. Employer fields remain employer/company signals, not proof of direct corporate giving.</div>
      ${
        !status.enabled
          ? `<div class="error">${esc(status.message || "AI is not configured. Add OPENAI_API_KEY to enable AI briefing.")}</div>`
          : `<form id="aiForm" class="ai-query-form">
              <label>What do you want to know?
                <textarea name="question" rows="5" placeholder="Example: Who has donated to Alex Mealer in 2026?"></textarea>
              </label>
              <div class="prompt-examples" aria-label="Example prompts">
                <button type="button" data-prompt="Who has donated to Alex Mealer in 2026?">Alex Mealer 2026 donors</button>
                <button type="button" data-prompt="Compare employer/company signals for AECOM and Fluor in the current FEC records.">Compare companies</button>
                <button type="button" data-prompt="Which recipients in the current records appear most relevant to infrastructure, construction, energy, roads, water, or public works?">Infrastructure relevance</button>
              </div>
              <label class="inline-check"><input name="include_web_context" type="checkbox" checked /> Include web/news context for richer analysis</label>
              <button class="primary" type="submit">Generate Detailed Intelligence Memo</button>
            </form>
            <div id="aiOutput"></div>`
      }
    </section>
  `;
  const form = document.querySelector("#aiForm");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    button.textContent = "Generating Answer...";
    document.querySelector("#aiOutput").innerHTML = `<section class="panel ai-panel"><div class="empty">Searching local records, gathering public context, and writing a detailed intelligence memo...</div></section>`;
    
    try {
      const values = Object.fromEntries(new FormData(event.target).entries());
      const result = await api("/ai/ask", {
        method: "POST",
        body: JSON.stringify({
          question: values.question,
          insight_type: "freeform_campaign_finance_question",
          include_web_context: Boolean(values.include_web_context),
          filters: {},
        }),
      });
      document.querySelector("#aiOutput").innerHTML = `<section class="panel ai-panel">${renderMarkdown(result.output_text || result.message || "")}</section>`;
    } catch (error) {
      document.querySelector("#aiOutput").innerHTML = `<section class="panel ai-panel error">${esc(error.message)}</section>`;
    } finally {
      button.disabled = false;
      button.textContent = "Generate Detailed Intelligence Memo";
    }
  });
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      form.querySelector("textarea[name='question']").value = button.dataset.prompt;
    });
  });
}

function renderTracker() {
  page.innerHTML = `
    <section class="panel">
      <div class="section-title"><h2>Donation Tracker</h2><span>Monitor competitors, legislators, PACs, committees, and recipients</span></div>
      <form id="trackerForm" class="tracker-form">
        <label>Business / employer signals to monitor, up to 10
          <textarea name="businesses" rows="4" placeholder="One per line: AECOM&#10;Fluor&#10;Sammons"></textarea>
        </label>
        <label>Legislators / recipients / PACs to monitor, up to 20
          <textarea name="recipients" rows="4" placeholder="One per line: Alex Mealer&#10;Friends of Ben McAdams"></textarea>
        </label>
        <div class="form-grid">
          <label>From date<input name="date_from" type="date" /></label>
          <label>To date<input name="date_to" type="date" /></label>
          <label>Monitoring cadence<select name="cadence"><option>Monthly</option><option>Historical only</option></select></label>
          <label>Alert threshold<input name="min_amount" type="number" min="0" step="100" placeholder="Optional amount" /></label>
        </div>
        <button class="primary" type="submit">Save Monitoring List</button>
      </form>
      <div id="trackerResult"></div>
      <div class="tracker-grid">
        <div class="tracker-step"><strong>1</strong><h3>Select What To Monitor</h3><p>Business names, employer/company signals, legislators, PACs, committees, and recipients.</p></div>
        <div class="tracker-step"><strong>2</strong><h3>Choose Timeline</h3><p>Monthly monitoring or a historical date range for before/after comparisons.</p></div>
        <div class="tracker-step"><strong>3</strong><h3>Review Activity</h3><p>See new donations, recipient activity, source IDs, duplicates, and data quality flags.</p></div>
        <div class="tracker-step"><strong>4</strong><h3>Export Report</h3><p>Generate Excel-ready evidence packs for printing and client review.</p></div>
      </div>
      <div class="warning">This tracker saves monitoring lists for review. Automated alert delivery is not enabled yet; that remains a production hardening step.</div>
    </section>
  `;
  document.querySelector("#trackerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.target).entries());
    const businesses = String(values.businesses || "").split(/\r?\n/).map((v) => v.trim()).filter(Boolean).slice(0, 10);
    const recipients = String(values.recipients || "").split(/\r?\n/).map((v) => v.trim()).filter(Boolean).slice(0, 20);
    const entities = [
      ...businesses.map((name) => ({ entity_name: name, entity_type: "EMPLOYER_SIGNAL" })),
      ...recipients.map((name) => ({ entity_name: name, entity_type: "RECIPIENT" })),
    ];
    if (!entities.length) {
      document.querySelector("#trackerResult").innerHTML = `<div class="error">Add at least one business, employer signal, legislator, PAC, committee, or recipient.</div>`;
      return;
    }
    const result = await api("/watchlists", {
      method: "POST",
      body: JSON.stringify({
        name: `Monitoring list ${new Date().toLocaleDateString()}`,
        watchlist_type: "donation_monitor",
        description: "Client-facing donation monitoring list",
        entities,
        filters: { date_from: values.date_from, date_to: values.date_to, cadence: values.cadence, min_amount: values.min_amount },
      }),
    });
    document.querySelector("#trackerResult").innerHTML = `<div class="toast">Monitoring list saved as watchlist #${esc(result.id)}. Use Search Donations and Data & Exports for current evidence review.</div>`;
  });
}

async function renderData() {
  const [transactions, raw, audits, flags] = await Promise.all([
    api("/transactions?limit=100"),
    api("/transactions/raw?limit=50"),
    api("/ingestion/audit-logs?limit=50"),
    api("/ingestion/data-quality-flags?limit=100"),
  ]);
  page.innerHTML = `
    <section class="panel">
      <div class="section-title"><h2>Data & Exports</h2><span>Lazy exports, compact previews</span></div>
      <div class="grid two">
        <a class="secondary button-link" href="/exports/audit-logs">Download Audit CSV</a>
        <a class="secondary button-link" href="/exports/data-quality-flags">Download Quality CSV</a>
      </div>
    </section>
    <section class="panel"><h2>Normalized Transactions</h2>${table(transactions.items || [], fecColumns)}</section>
    <section class="panel"><h2>Raw Records</h2>${table(raw.items || [], [
      { key: "id", label: "ID" },
      { key: "source_system", label: "Source" },
      { key: "source_record_id", label: "Source Record ID" },
      { key: "ingested_at", label: "Ingested" },
    ])}</section>
    <section class="panel"><h2>Source Audit Logs</h2>${table(audits || [], [
      { key: "id", label: "ID" },
      { key: "source_system", label: "Source" },
      { key: "status", label: "Status" },
      { key: "pages_processed", label: "Pages" },
      { key: "raw_records_fetched", label: "Raw" },
      { key: "inserted_count", label: "Inserted" },
      { key: "duplicate_count", label: "Duplicates" },
      { key: "started_at", label: "Started" },
    ])}</section>
    <section class="panel"><h2>Data Quality Flags</h2>${table(flags || [], [
      { key: "id", label: "ID" },
      { key: "flag_type", label: "Flag" },
      { key: "severity", label: "Severity" },
      { key: "message", label: "Message" },
      { key: "created_at", label: "Created" },
    ])}</section>
  `;
}

async function render() {
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.page === state.page));
  page.innerHTML = `<section class="panel"><div class="empty">Loading ${esc(state.page)}...</div></section>`;
  try {
    if (state.page === "ai") await renderAi();
    else if (state.page === "tracker") renderTracker();
    else if (state.page === "fec") await renderFec();
    else if (state.page === "overview") await renderOverview();
    else if (state.page === "search") await renderSearch();
    else await renderData();
  } catch (error) {
    page.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.page = button.dataset.page;
    render();
  });
});

api("/health")
  .then(() => {
    apiStatus.textContent = "API connected";
  })
  .catch(() => {
    apiStatus.textContent = "API offline";
    apiStatus.style.background = "#fee2e2";
    apiStatus.style.color = "#991b1b";
  });

render();
