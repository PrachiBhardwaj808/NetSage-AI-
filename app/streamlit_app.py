"""
app/streamlit_app.py
====================
NetSage AI — Full Streamlit Dashboard
5 Pages: Dashboard | Troubleshoot Case | Review History | Responsible AI | Case Explorer
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import streamlit as st

from ai.diagnosis import diagnose_case
from checker.checker import run_all_checks, format_results_for_prompt
from utils.data_loader import (
    load_cases,
    load_reviews,
    save_review,
    get_dashboard_stats,
    get_case_options,
    load_case_by_id,
)

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NetSage AI",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.main { background: #0d1117; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f1923 0%, #111827 100%);
    border-right: 1px solid #1e2d3d;
}

/* Hero */
.hero-title {
    font-size: 2.4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.hero-sub {
    color: #64748b;
    font-size: 1rem;
    margin-bottom: 0;
}

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1.2rem 1rem;
    text-align: center;
}
.metric-val { font-size: 2rem; font-weight: 700; color: #38bdf8; }
.metric-label { color: #64748b; font-size: 0.8rem; margin-top: 0.2rem; text-transform: uppercase; letter-spacing: 0.05em; }

/* Verdict badges */
.badge-accepted { background:#064e3b; color:#34d399; padding:2px 10px; border-radius:9999px; font-size:0.8rem; font-weight:600; }
.badge-edited   { background:#451a03; color:#fb923c; padding:2px 10px; border-radius:9999px; font-size:0.8rem; font-weight:600; }
.badge-rejected { background:#450a0a; color:#f87171; padding:2px 10px; border-radius:9999px; font-size:0.8rem; font-weight:600; }

/* Evidence box */
.evidence-box {
    background: #0f2027;
    border-left: 3px solid #38bdf8;
    border-radius: 8px;
    padding: 1rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: #94a3b8;
    white-space: pre-wrap;
    overflow-x: auto;
}

/* Confidence bar */
.conf-bar-wrap { background:#1e293b; border-radius:9999px; height:10px; overflow:hidden; }
.conf-bar-fill  { height:10px; border-radius:9999px; transition:width 0.4s ease; }

/* Section headers */
.section-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #e2e8f0;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 0.4rem;
    margin-bottom: 0.8rem;
}
</style>
""", unsafe_allow_html=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def conf_color(conf: float) -> str:
    if conf >= 0.8:
        return "#34d399"
    if conf >= 0.6:
        return "#fb923c"
    return "#f87171"


def render_confidence(conf: float):
    pct = int(conf * 100)
    color = conf_color(conf)
    st.markdown(
        f"""
        <div style="margin: 4px 0 12px 0;">
            <span style="color:{color}; font-weight:600; font-size:1.1rem;">{pct}%</span>
            <span style="color:#475569; font-size:0.8rem; margin-left:8px;">confidence</span>
            <div class="conf-bar-wrap" style="margin-top:6px;">
                <div class="conf-bar-fill" style="width:{pct}%; background:{color};"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(decision: str) -> str:
    cls = {"Accepted": "badge-accepted", "Edited": "badge-edited", "Rejected": "badge-rejected"}.get(decision, "")
    return f'<span class="{cls}">{decision}</span>'


def make_pie(labels, sizes, colors, title):
    fig, ax = plt.subplots(figsize=(4, 4), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, colors=colors, autopct="%1.0f%%",
        startangle=90, pctdistance=0.8,
        wedgeprops=dict(edgecolor="#0d1117", linewidth=2),
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(9)
    patches = [mpatches.Patch(color=colors[i], label=labels[i]) for i in range(len(labels))]
    ax.legend(handles=patches, loc="lower center", bbox_to_anchor=(0.5, -0.15),
              ncol=2, frameon=False, fontsize=8,
              labelcolor="white")
    ax.set_title(title, color="white", fontsize=11, pad=10)
    fig.tight_layout()
    return fig


def make_bar(labels, values, color, title, xlabel="Count"):
    fig, ax = plt.subplots(figsize=(5, 3), facecolor="#0d1117")
    ax.set_facecolor("#111827")
    bars = ax.barh(labels, values, color=color, edgecolor="#0d1117", height=0.55)
    ax.bar_label(bars, padding=4, color="white", fontsize=9)
    ax.set_xlabel(xlabel, color="#64748b", fontsize=9)
    ax.set_title(title, color="white", fontsize=11)
    ax.tick_params(colors="white", labelsize=9)
    ax.spines[:].set_color("#1e293b")
    ax.xaxis.label.set_color("#64748b")
    fig.tight_layout()
    return fig


# ─── Sidebar navigation ───────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## NetSage AI")
    st.markdown('<p style="color:#475569; font-size:0.8rem;">Cisco Network Troubleshooting</p>', unsafe_allow_html=True)
    st.divider()

    page = st.radio(
        "Navigate",
        ["Dashboard", "Troubleshoot Case", "Review History", "Responsible AI", "Case Explorer"],
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown('<p style="color:#334155; font-size:0.7rem;">Flow: Evidence → Rules → AI → Human Review → Log → Dashboard</p>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if page == "Dashboard":
    st.markdown('<p class="hero-title">NetSage AI Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Evidence-driven Cisco troubleshooting — AI-assisted, human-verified</p>', unsafe_allow_html=True)
    st.divider()

    try:
        stats = get_dashboard_stats()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        st.stop()

    # ── Metrics row ──
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    metrics = [
        (m1, stats["total_cases"], "Total Cases", "#38bdf8"),
        (m2, stats["total_reviewed"], "Reviewed", "#818cf8"),
        (m3, stats["accepted"], "Accepted", "#34d399"),
        (m4, stats["edited"], "Edited", "#fb923c"),
        (m5, stats["rejected"], "Rejected", "#f87171"),
        (m6, f"{stats['agreement_rate']}%", "AI Agreement", "#c084fc"),
    ]
    for col, val, label, color in metrics:
        with col:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-val" style="color:{color};">{val}</div>'
                f'<div class="metric-label">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row ──
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        cat_data = stats["cases_by_category"]
        if cat_data:
            labels = [d["category"] for d in cat_data]
            sizes = [d["count"] for d in cat_data]
            palette = ["#38bdf8","#818cf8","#c084fc","#34d399","#fb923c","#f87171","#fbbf24","#a3e635"]
            colors = palette[: len(labels)]
            st.pyplot(make_pie(labels, sizes, colors, "Cases by Category"))

    with col_b:
        sev_data = stats["cases_by_severity"]
        if sev_data:
            sev_color_map = {"critical": "#f87171", "high": "#fb923c", "medium": "#fbbf24", "low": "#34d399"}
            labels = [d["severity"].title() for d in sev_data]
            values = [d["count"] for d in sev_data]
            colors = [sev_color_map.get(d["severity"].lower(), "#818cf8") for d in sev_data]
            st.pyplot(make_bar(labels, values, colors, "Cases by Severity"))

    with col_c:
        if stats["total_reviewed"] > 0:
            dec_labels = ["Accepted", "Edited", "Rejected"]
            dec_vals = [stats["accepted"], stats["edited"], stats["rejected"]]
            dec_colors = ["#34d399", "#fb923c", "#f87171"]
            st.pyplot(make_pie(dec_labels, dec_vals, dec_colors, "Human Review Decisions"))
        else:
            st.info("No reviews recorded yet. Run a troubleshooting session to see review data.")

    # ── Cases needing human correction ──
    st.divider()
    st.markdown("#### Cases Requiring Human Correction")
    corrected = stats["corrected_cases"]
    if corrected:
        for c in corrected:
            with st.expander(f"{c['case_id']} — {c['human_decision']}"):
                col1, col2 = st.columns(2)
                col1.markdown(f"**AI Diagnosis:** {c['ai_root_cause']}")
                col1.markdown(f"**Confidence:** {float(c['ai_confidence']):.0%}")
                col2.markdown(f"**Human Correction:** {c.get('human_correction', '—')}")
                col2.markdown(f"**Reason:** {c.get('review_reason', '—')}")
    else:
        st.info("No corrected cases yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — TROUBLESHOOT CASE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Troubleshoot Case":
    st.markdown('<p class="hero-title">Troubleshoot Case</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Select a case → inspect evidence → run checker → get AI diagnosis → review</p>', unsafe_allow_html=True)
    st.divider()

    # Case selector
    try:
        options = get_case_options()
    except Exception as e:
        st.error(f"Cannot load cases: {e}")
        st.stop()

    selected = st.selectbox("Select Case", options, key="case_selector")
    case_id = selected.split(" — ")[0].strip()
    case = load_case_by_id(case_id)

    if not case:
        st.error("Case not found.")
        st.stop()

    # ── Case overview ──
    ov1, ov2, ov3 = st.columns(3)
    ov1.metric("Category", case["category"])
    ov2.metric("Severity", case["severity"].title())
    ov3.metric("OSI Layer", case["osi_layer"])

    with st.expander("Symptom & Topology", expanded=True):
        c1, c2 = st.columns(2)
        c1.markdown("**Symptom**")
        c1.markdown(f"> {case['symptom']}")
        c2.markdown("**Topology**")
        c2.markdown(f"> {case['topology']}")
        st.markdown(f"**Device Context:** {case['device_context']}")

    with st.expander("Show Command Output", expanded=True):
        st.markdown(f"**Commands:** `{case['show_commands']}`")
        st.markdown(
            f'<div class="evidence-box">{case["show_output"]}</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Step 1: Rule Checker ──
    st.markdown("### Step 1 — Run Deterministic Rule Checker")
    st.caption("These checks are independent of AI — pure Python logic")

    if st.button("Run Rule Checker", type="secondary", key="run_checker"):
        with st.spinner("Running checks..."):
            results = run_all_checks(case)
            st.session_state["rule_results"] = results

    if "rule_results" in st.session_state:
        results = st.session_state["rule_results"]
        detected = [r for r in results if r["detected"]]
        passed = [r for r in results if not r["detected"]]

        rc1, rc2 = st.columns(2)
        rc1.metric("Checks Run", len(results))
        rc2.metric("Issues Found", len(detected), delta=len(detected) if detected else None)

        if detected:
            st.markdown("**Detected Issues:**")
            for r in detected:
                st.error(f"**[{r['check']}]** {r['message']}\n\n_Evidence: {r['evidence']}_")

        if passed:
            with st.expander(f"{len(passed)} checks passed"):
                for r in passed:
                    st.success(f"**{r['check']}** — {r['message']}")

    st.divider()

    # ── Step 2: AI Diagnosis ──
    st.markdown("### Step 2 — Run AI Diagnosis")
    st.caption("Sends case + rule checker results to Gemini AI → returns structured JSON")

    if st.button("Run AI Diagnosis", type="primary", key="run_ai"):
        rule_res = st.session_state.get("rule_results", [])
        with st.spinner("NetSage AI is analysing the evidence..."):
            diag = diagnose_case(case, rule_res)
            st.session_state["ai_diag"] = diag

    if "ai_diag" in st.session_state:
        diag = st.session_state["ai_diag"]

        if "error" in diag:
            st.warning(f"AI Note: {diag['error']}")

        st.markdown('<p class="section-header">AI Diagnosis Result</p>', unsafe_allow_html=True)

        d1, d2, d3 = st.columns(3)
        d1.markdown(f"**Root Cause**\n\n{diag.get('root_cause', '—')}")
        d2.markdown(f"**OSI Layer**\n\n{diag.get('osi_layer', '—')}")
        with d3:
            render_confidence(float(diag.get("confidence", 0)))

        # Evidence
        evidence = diag.get("evidence", [])
        if evidence:
            st.markdown("**Evidence Cited by AI**")
            for ev in evidence:
                st.markdown(f"- {ev}")

        # Next command
        st.info(f"**Recommended Next Command:** `{diag.get('next_command', '—')}`")

        # Fix steps
        fix_steps = diag.get("fix_steps", [])
        if fix_steps:
            st.markdown("**Fix Steps**")
            for i, step in enumerate(fix_steps, 1):
                st.code(step, language="text")

        # Verification
        verif = diag.get("verification_steps", [])
        if verif:
            st.markdown("**Verification Steps**")
            for v in verif:
                st.markdown(f"- `{v}`")

        # Reasoning
        with st.expander("AI Reasoning Summary"):
            st.markdown(diag.get("reasoning_summary", "—"))

        st.divider()

        # ── Step 3: Human Review ──
        st.markdown("### Step 3 — Human Review (Required)")
        st.warning("The AI diagnosis **must** be reviewed before any fix is applied. This is mandatory.")

        with st.form("review_form", clear_on_submit=True):
            reviewer = st.text_input("Your Name", placeholder="e.g. Prachi Bhardwaj")
            decision = st.radio(
                "Review Decision",
                ["Accepted", "Edited", "Rejected"],
                horizontal=True,
            )
            correction = st.text_area(
                "Correction / Comment",
                placeholder="If Edited or Rejected: describe the correct diagnosis or reason",
                height=80,
            )
            reason = st.text_area(
                "Review Reason",
                placeholder="Why did you accept, edit, or reject this diagnosis?",
                height=80,
            )
            submitted = st.form_submit_button("Save Review", type="primary")

        if submitted:
            if not reviewer.strip():
                st.error("Please enter your name.")
            elif not reason.strip():
                st.error("Please provide a review reason.")
            else:
                try:
                    save_review(
                        case_id=case_id,
                        ai_root_cause=diag.get("root_cause", ""),
                        ai_confidence=diag.get("confidence", 0.0),
                        human_decision=decision,
                        human_correction=correction,
                        review_reason=reason,
                        reviewer=reviewer,
                    )
                    # Clear diagnosis from session after save
                    del st.session_state["ai_diag"]
                    if "rule_results" in st.session_state:
                        del st.session_state["rule_results"]
                    st.success(f"Review saved: **{decision}** for {case_id}")
                    st.balloons()
                except Exception as e:
                    st.error(f"Failed to save review: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — REVIEW HISTORY
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Review History":
    st.markdown('<p class="hero-title">Review History</p>', unsafe_allow_html=True)
    st.divider()

    try:
        reviews = load_reviews()
    except Exception as e:
        st.error(f"Cannot load reviews: {e}")
        st.stop()

    if reviews.empty:
        st.info("No reviews yet. Complete a troubleshooting session to record the first review.")
        st.stop()

    # Filters
    f1, f2 = st.columns(2)
    dec_filter = f1.multiselect(
        "Filter by Decision",
        ["Accepted", "Edited", "Rejected"],
        default=["Accepted", "Edited", "Rejected"],
    )
    case_filter = f2.text_input("Filter by Case ID", placeholder="e.g. CASE-021")

    filtered = reviews[reviews["human_decision"].isin(dec_filter)]
    if case_filter.strip():
        filtered = filtered[filtered["case_id"].str.contains(case_filter.strip(), case=False)]

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Reviews", len(reviews))
    m2.metric("Accepted", len(reviews[reviews["human_decision"] == "Accepted"]))
    m3.metric("Edited", len(reviews[reviews["human_decision"] == "Edited"]))
    m4.metric("Rejected", len(reviews[reviews["human_decision"] == "Rejected"]))

    st.divider()

    # Detailed cards
    for _, row in filtered.iterrows():
        dec_html = badge(row["human_decision"])
        with st.expander(f"{row['case_id']}  {row['human_decision']}  —  {row['timestamp']}"):
            st.markdown(dec_html, unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.markdown(f"**AI Diagnosis:**  \n{row['ai_root_cause']}")
            conf_val = float(row.get("ai_confidence", 0) or 0)
            c1.markdown(f"**AI Confidence:** {conf_val:.0%}")
            c2.markdown(f"**Human Correction:**  \n{row.get('human_correction', '—') or '—'}")
            c2.markdown(f"**Reason:**  \n{row.get('review_reason', '—') or '—'}")
            st.caption(f"Reviewer: {row.get('reviewer', '—')} | {row['timestamp']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — RESPONSIBLE AI
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Responsible AI":
    st.markdown('<p class="hero-title">Responsible AI</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Demonstrating that AI is assistive, not authoritative — all diagnoses require human verification</p>', unsafe_allow_html=True)
    st.divider()

    try:
        stats = get_dashboard_stats()
        reviews = load_reviews()
    except Exception as e:
        st.error(f"Cannot load data: {e}")
        st.stop()

    # ── Principles ──
    with st.expander("Responsible AI Principles (NetSage AI)", expanded=True):
        st.markdown("""
| Principle | Implementation |
|---|---|
| **Human-in-the-loop** | Every AI diagnosis must be Accept / Edit / Reject before any fix is applied |
| **Transparency** | AI cites exact evidence; confidence scores are shown |
| **Honesty** | AI states when evidence is insufficient; never fabricates output |
| **Non-autonomy** | AI never modifies network configuration — it only advises |
| **Auditability** | All decisions are logged with reviewer name and timestamp |
| **Accountability** | Human engineers own the final decision |
        """)

    # ── Agreement Rate ──
    st.markdown("### AI–Human Agreement Rate")
    rate = stats["agreement_rate"]
    color = "#34d399" if rate >= 70 else "#fb923c" if rate >= 50 else "#f87171"
    st.markdown(
        f'<div style="font-size:3rem; font-weight:700; color:{color}; text-align:center;">{rate}%</div>'
        f'<div style="text-align:center; color:#64748b; margin-bottom:1rem;">of reviewed cases were Accepted without correction</div>',
        unsafe_allow_html=True,
    )
    formula = f"Accepted ({stats['accepted']}) / Total Reviewed ({stats['total_reviewed']}) x 100 = {rate}%"
    st.code(formula, language="text")

    st.divider()

    # ── Cases where AI was corrected ──
    st.markdown("### Cases Where AI Was Corrected or Rejected")
    corrected = stats["corrected_cases"]

    if not corrected:
        st.info("No corrected cases yet. Pre-seeded corrections from the reviews.csv will appear here.")
    else:
        for i, c in enumerate(corrected, 1):
            conf_val = float(c.get("ai_confidence", 0) or 0)
            decision_badge = badge(c["human_decision"])
            with st.container():
                st.markdown(f"#### {i}. {c['case_id']} &nbsp; {decision_badge}", unsafe_allow_html=True)
                st.markdown(f"**AI Diagnosis:** {c['ai_root_cause']}")
                st.markdown(
                    f'<div class="conf-bar-wrap" style="width:200px;">'
                    f'<div class="conf-bar-fill" style="width:{int(conf_val*100)}%; background:{conf_color(conf_val)};"></div>'
                    f'</div><span style="color:{conf_color(conf_val)}; font-size:0.85rem;">'
                    f' {conf_val:.0%} confidence</span>',
                    unsafe_allow_html=True,
                )
                if c.get("human_correction"):
                    st.markdown(f"**Human Correction:** {c['human_correction']}")
                st.markdown(f"**Reason:** _{c.get('review_reason', '—')}_")
                st.markdown(f"<hr style='border-color:#1e293b;'>", unsafe_allow_html=True)

    # ── Summary analysis ──
    st.divider()
    st.markdown("### Why AI Gets Corrected")
    st.markdown("""
Common reasons identified in this dataset:

| Reason | Example |
|---|---|
| **Incomplete diagnosis** | AI identified primary fault but missed a secondary contributing issue |
| **Low confidence hallucination** | AI made a specific claim when evidence was insufficient |
| **Wrong NAT type recommendation** | AI recommended interface overload when pool NAT was required |
| **Missed root cause** | AI identified symptom (e.g. ACL direction) but not why the wrong direction was chosen |
| **Trunk VLAN vs native VLAN confusion** | AI conflated allowed VLAN list with native VLAN setting |

**Conclusion:** AI diagnosis should always be treated as a starting point, not a final answer.
    """)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — CASE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Case Explorer":
    st.markdown('<p class="hero-title">Case Explorer</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Browse, search and filter all 30 Cisco troubleshooting cases</p>', unsafe_allow_html=True)
    st.divider()

    try:
        df = load_cases()
    except Exception as e:
        st.error(f"Cannot load cases: {e}")
        st.stop()

    # Filters
    f1, f2, f3 = st.columns(3)
    cat_filter = f1.multiselect(
        "Category", sorted(df["category"].unique()), default=sorted(df["category"].unique())
    )
    sev_filter = f2.multiselect(
        "Severity", sorted(df["severity"].unique()), default=sorted(df["severity"].unique())
    )
    search = f3.text_input("Search (title / symptom / fault)", placeholder="e.g. VLAN, ACL, OSPF")

    filtered = df[df["category"].isin(cat_filter) & df["severity"].isin(sev_filter)]
    if search.strip():
        mask = (
            filtered["title"].str.contains(search, case=False)
            | filtered["symptom"].str.contains(search, case=False)
            | filtered["expected_fault"].str.contains(search, case=False)
            | filtered["case_id"].str.contains(search, case=False)
        )
        filtered = filtered[mask]

    st.markdown(f"**Showing {len(filtered)} of {len(df)} cases**")
    st.divider()

    # Case cards
    for _, row in filtered.iterrows():
        sev_color = {"critical": "#f87171", "high": "#fb923c", "medium": "#fbbf24", "low": "#34d399"}.get(
            row["severity"].lower(), "#818cf8"
        )
        with st.expander(f"**{row['case_id']}** — {row['title']}  |  `{row['category']}`"):
            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"**Symptom:** {row['symptom']}")
                st.markdown(f"**Expected Fault:** {row['expected_fault']}")
                st.markdown(f"**Concept:** {row['concept']}")
            with col2:
                st.markdown(
                    f"**Severity:** <span style='color:{sev_color}'>{row['severity'].title()}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**OSI Layer:** {row['osi_layer']}")
                st.markdown(f"**Show Commands:** `{row['show_commands']}`")
                st.markdown(f"**Next Command:** `{row['expected_next_command']}`")
                st.markdown(f"**Verification:** `{row['verification_command']}`")

            with st.expander("Show Output"):
                st.markdown(
                    f'<div class="evidence-box">{row["show_output"]}</div>',
                    unsafe_allow_html=True,
                )
            with st.expander("Expected Fix"):
                st.code(row["expected_fix"], language="text")
