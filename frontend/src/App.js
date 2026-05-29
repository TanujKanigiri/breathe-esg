import { useState, useEffect } from "react";
import axios from "axios";
const API = "/api";
const TENANT = "default";

const SCOPE_COLORS = { "1": "#f97316", "2": "#3b82f6", "3": "#8b5cf6" };
const SCOPE_LABELS = { "1": "Scope 1", "2": "Scope 2", "3": "Scope 3" };

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [filterScope, setFilterScope] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterFlagged, setFilterFlagged] = useState(false);

  const fetchRecords = async () => {
    setLoading(true);
    try {
      const params = { tenant_slug: TENANT };
      if (filterScope) params.scope = filterScope;
      if (filterStatus) params.status = filterStatus;
      if (filterFlagged) params.flagged = "true";
      const res = await axios.get(`${API}/records/`, { params });
      setRecords(res.data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const fetchStats = async () => {
    try {
      const res = await axios.get(`${API}/stats/`, {
        params: { tenant_slug: TENANT },
      });
      setStats(res.data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchRecords();
  }, [filterScope, filterStatus, filterFlagged]);

  const handleUpload = async (e, sourceType) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploadMsg("Uploading...");
    const form = new FormData();
    form.append("file", file);
    form.append("tenant_slug", TENANT);
    try {
      const res = await axios.post(`${API}/ingest/${sourceType}/`, form);
      setUploadMsg(
        `Done — ${res.data.rows_ok} rows ingested, ${res.data.rows_failed} failed`
      );
      fetchStats();
      fetchRecords();
    } catch (err) {
      setUploadMsg("✗ Upload failed — check file format");
    }
  };

  const handleReview = async (id, status) => {
    try {
      await axios.post(`${API}/records/${id}/review/`, { status });
      setRecords((prev) =>
        prev.map((r) =>
          r.id === id ? { ...r, review_status: status, is_locked: status === "approved" } : r
        )
      );
      fetchStats();
    } catch (err) {
      alert(err.response?.data?.error || "Review failed");
    }
  };

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#0f172a", color: "#e2e8f0" }}>
      {/* Header */}
      <div style={{ background: "#1e293b", borderBottom: "1px solid #334155", padding: "16px 32px", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 32, height: 32, background: "#22c55e", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: "#fff", fontSize: 14 }}>B</div>
        <span style={{ fontWeight: 600, fontSize: 18 }}>Breathe ESG</span>
        <span style={{ color: "#64748b", marginLeft: 8 }}>Emissions Data Platform</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {["dashboard", "upload", "records"].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              style={{ padding: "6px 16px", borderRadius: 6, border: "none", cursor: "pointer", fontWeight: 500, fontSize: 14,
                background: tab === t ? "#22c55e" : "transparent",
                color: tab === t ? "#fff" : "#94a3b8" }}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: "32px" }}>

        {/* DASHBOARD TAB */}
        {tab === "dashboard" && stats && (
          <div>
            <h2 style={{ margin: "0 0 24px", color: "#f1f5f9" }}>Overview</h2>
            {/* Stat Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 32 }}>
              {[
                { label: "Total CO₂e", value: `${(stats.total_co2e_kg / 1000).toFixed(2)} tCO₂e`, color: "#22c55e" },
                { label: "Total Records", value: stats.total_records, color: "#3b82f6" },
                { label: "Flagged", value: stats.flagged_count, color: "#f97316" },
                { label: "Pending Review", value: stats.by_status?.pending || 0, color: "#eab308" },
              ].map((s) => (
                <div key={s.label} style={{ background: "#1e293b", borderRadius: 12, padding: 20, borderLeft: `4px solid ${s.color}` }}>
                  <div style={{ fontSize: 13, color: "#64748b", marginBottom: 8 }}>{s.label}</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value}</div>
                </div>
              ))}
            </div>
            {/* Scope Breakdown */}
            <div style={{ background: "#1e293b", borderRadius: 12, padding: 24, marginBottom: 24 }}>
              <h3 style={{ margin: "0 0 20px", color: "#f1f5f9", fontSize: 16 }}>Emissions by Scope</h3>
              <div style={{ display: "flex", gap: 24 }}>
                {Object.entries(stats.by_scope || {}).map(([key, val]) => {
                  const scope = key.replace("scope_", "");
                  const total = Object.values(stats.by_scope).reduce((a, b) => a + b, 0);
                  const pct = total > 0 ? (val / total) * 100 : 0;
                  return (
                    <div key={key} style={{ flex: 1, textAlign: "center" }}>
                      <div style={{ fontSize: 13, color: "#64748b", marginBottom: 8 }}>{SCOPE_LABELS[scope]}</div>
                      <div style={{ height: 8, background: "#334155", borderRadius: 4, marginBottom: 8 }}>
                        <div style={{ height: "100%", width: `${pct}%`, background: SCOPE_COLORS[scope], borderRadius: 4 }} />
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: SCOPE_COLORS[scope] }}>{(val / 1000).toFixed(2)}</div>
                      <div style={{ fontSize: 12, color: "#64748b" }}>tCO₂e</div>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Review Status */}
            <div style={{ background: "#1e293b", borderRadius: 12, padding: 24 }}>
              <h3 style={{ margin: "0 0 16px", color: "#f1f5f9", fontSize: 16 }}>Review Pipeline</h3>
              <div style={{ display: "flex", gap: 16 }}>
                {[["pending", "#eab308"], ["approved", "#22c55e"], ["rejected", "#ef4444"]].map(([s, c]) => (
                  <div key={s} style={{ flex: 1, background: "#0f172a", borderRadius: 8, padding: 16, textAlign: "center" }}>
                    <div style={{ fontSize: 24, fontWeight: 700, color: c }}>{stats.by_status?.[s] || 0}</div>
                    <div style={{ fontSize: 13, color: "#64748b", textTransform: "capitalize", marginTop: 4 }}>{s}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* UPLOAD TAB */}
        {tab === "upload" && (
          <div style={{ maxWidth: 720 }}>
            <h2 style={{ margin: "0 0 8px", color: "#f1f5f9" }}>Upload Data</h2>
            <p style={{ color: "#64748b", marginBottom: 32 }}>Upload CSV files from each source. Data will be parsed and normalized automatically.</p>
            {uploadMsg && (
              <div style={{ padding: "12px 16px", borderRadius: 8, marginBottom: 24,
                background: uploadMsg.startsWith("✓") ? "#14532d" : "#450a0a",
                color: uploadMsg.startsWith("✓") ? "#86efac" : "#fca5a5", fontSize: 14 }}>
                {uploadMsg}
              </div>
            )}
            {[
              { type: "sap_flat_file", label: "SAP Flat File", desc: "MB51 goods movement export. Expects columns: MENGE, MEINS, MAKTX, BUDAT, WERKS", color: "#f97316" },
              { type: "utility_csv", label: "Utility Electricity CSV", desc: "Portal export with usage (kWh/MWh), billing period start/end, meter ID", color: "#3b82f6" },
              { type: "concur_csv", label: "Concur Travel CSV", desc: "Expense export with expense_type, origin, destination, travel_date, amount", color: "#8b5cf6" },
            ].map((src) => (
              <div key={src.type} style={{ background: "#1e293b", borderRadius: 12, padding: 24, marginBottom: 16, borderLeft: `4px solid ${src.color}` }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6, color: "#f1f5f9" }}>{src.label}</div>
                <div style={{ fontSize: 13, color: "#64748b", marginBottom: 16 }}>{src.desc}</div>
                <label style={{ display: "inline-block", padding: "8px 20px", background: src.color, color: "#fff",
                  borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 500 }}>
                  Choose CSV file
                  <input type="file" accept=".csv" style={{ display: "none" }}
                    onChange={(e) => handleUpload(e, src.type)} />
                </label>
              </div>
            ))}
          </div>
        )}

        {/* RECORDS TAB */}
        {tab === "records" && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, color: "#f1f5f9" }}>Records</h2>
              <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                <select value={filterScope} onChange={(e) => setFilterScope(e.target.value)}
                  style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px", fontSize: 13 }}>
                  <option value="">All Scopes</option>
                  <option value="1">Scope 1</option>
                  <option value="2">Scope 2</option>
                  <option value="3">Scope 3</option>
                </select>
                <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                  style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px", fontSize: 13 }}>
                  <option value="">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
                <button onClick={() => setFilterFlagged(!filterFlagged)}
                  style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #334155", cursor: "pointer", fontSize: 13,
                    background: filterFlagged ? "#7c2d12" : "#1e293b", color: filterFlagged ? "#fdba74" : "#94a3b8" }}>
                  ⚑ Flagged only
                </button>
              </div>
            </div>

            {loading ? (
              <div style={{ color: "#64748b", textAlign: "center", padding: 40 }}>Loading...</div>
            ) : records.length === 0 ? (
              <div style={{ color: "#64748b", textAlign: "center", padding: 40 }}>No records yet. Upload a file to get started.</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#1e293b", color: "#64748b" }}>
                      {["Scope", "Category", "Date", "Raw Value", "CO₂e (kg)", "Source", "Flags", "Status", "Actions"].map((h) => (
                        <th key={h} style={{ padding: "10px 12px", textAlign: "left", fontWeight: 500, whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((r, i) => (
                      <tr key={r.id} style={{ background: i % 2 === 0 ? "#0f172a" : "#1a2537", borderBottom: "1px solid #1e293b" }}>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{ background: SCOPE_COLORS[r.scope] + "33", color: SCOPE_COLORS[r.scope],
                            padding: "2px 8px", borderRadius: 4, fontWeight: 600, fontSize: 12 }}>
                            S{r.scope}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", color: "#cbd5e1" }}>{r.category.replace(/_/g, " ")}</td>
                        <td style={{ padding: "10px 12px", color: "#94a3b8" }}>{r.activity_date || "—"}</td>
                        <td style={{ padding: "10px 12px", color: "#94a3b8" }}>{r.raw_activity_value} {r.raw_unit}</td>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#f1f5f9" }}>
                          {r.co2e_kg ? r.co2e_kg.toFixed(2) : "—"}
                        </td>
                        <td style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>{r.source_type?.replace(/_/g, " ")}</td>
                        <td style={{ padding: "10px 12px" }}>
                          {r.is_flagged && (
                            <span title={r.flag_reason} style={{ background: "#7c2d1233", color: "#fb923c",
                              padding: "2px 8px", borderRadius: 4, fontSize: 11, cursor: "help" }}>
                              ⚑ flagged
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{
                            padding: "2px 8px", borderRadius: 4, fontSize: 12, fontWeight: 500,
                            background: r.review_status === "approved" ? "#14532d" : r.review_status === "rejected" ? "#450a0a" : "#422006",
                            color: r.review_status === "approved" ? "#86efac" : r.review_status === "rejected" ? "#fca5a5" : "#fde68a",
                          }}>
                            {r.review_status}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          {!r.is_locked && r.review_status === "pending" && (
                            <div style={{ display: "flex", gap: 6 }}>
                              <button onClick={() => handleReview(r.id, "approved")}
                                style={{ padding: "4px 10px", background: "#14532d", color: "#86efac",
                                  border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12 }}>
                                ✓ Approve
                              </button>
                              <button onClick={() => handleReview(r.id, "rejected")}
                                style={{ padding: "4px 10px", background: "#450a0a", color: "#fca5a5",
                                  border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12 }}>
                                ✗ Reject
                              </button>
                            </div>
                          )}
                          {r.is_locked && <span style={{ color: "#475569", fontSize: 12 }}>🔒 locked</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}