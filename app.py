from pathlib import Path
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis
import insights as insights_mod

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "sample_tasks.csv"

# ---- palette (echoes the original dashboard) --------------------------------
INK, INK2, INK3 = "#14202E", "#41536A", "#7A8A9C"
PAPER, SURFACE, RULE = "#E7EBEF", "#FBFCFD", "#DBE2E8"
SLIP, AHEAD, HOLD = "#B03A48", "#2F7A78", "#C77D1E"
STATUS_COLOR = {"Done": INK2, "In Progress": AHEAD, "In Review": HOLD, "Blocked": SLIP}
SEV_COLOR = {"critical": SLIP, "warning": HOLD, "watch": AHEAD}

st.set_page_config(page_title="Pyngyn — Delivery Insights", page_icon="📊", layout="wide")

st.markdown(f"""
<style>
  .stApp {{ background:{PAPER}; }}
  h1,h2,h3 {{ letter-spacing:-.01em; }}
  .mono {{ font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace; }}
  .card {{
    background:{SURFACE}; border:1px solid {RULE}; border-left:4px solid {INK3};
    padding:18px 20px; margin-bottom:14px; border-radius:2px;
  }}
  .card .sev {{ font-family:ui-monospace,Menlo,monospace; font-size:11px; font-weight:700;
    letter-spacing:.14em; text-transform:uppercase; float:right; }}
  .card h4 {{ margin:0 0 6px; font-size:19px; color:{INK}; }}
  .card .metric {{ font-family:ui-monospace,Menlo,monospace; font-size:20px; font-weight:700;
    display:inline-block; margin:4px 0 8px; }}
  .card .mlabel {{ font-family:ui-monospace,Menlo,monospace; font-size:11px; color:{INK3};
    letter-spacing:.03em; margin-left:8px; }}
  .card .body {{ color:{INK2}; font-size:15px; line-height:1.55; margin:0 0 10px; }}
  .card .action {{ border-top:1px dotted {RULE}; padding-top:9px; font-size:13.5px; color:{INK}; }}
  .card .action b {{ font-family:ui-monospace,Menlo,monospace; font-size:10px; letter-spacing:.12em;
    color:{INK3}; margin-right:8px; }}
  .hero-do {{ background:{SURFACE}; border-left:4px solid {SLIP}; padding:12px 16px;
    color:{INK}; font-size:15px; margin-top:8px; border-radius:2px; }}
  div[data-testid="stMetricValue"] {{ font-family:ui-monospace,Menlo,monospace; }}
</style>
""", unsafe_allow_html=True)


# ---- data plumbing ----------------------------------------------------------
def run_pipeline(df: pd.DataFrame, regen: bool):
    """Analyze the frame, then (re)generate insights and stash in session state."""
    stats = analysis.analyze(df)
    st.session_state.stats = stats
    if regen or "insights" not in st.session_state:
        with st.spinner("Asking the model for insights…"):
            st.session_state.insights, st.session_state.source = insights_mod.generate(stats)


def load_sample():
    run_pipeline(pd.read_csv(SAMPLE), regen=True)
    st.session_state.loaded_label = "Sample data"


if "stats" not in st.session_state:
    load_sample()


# ---- header + controls ------------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.markdown(f"<div class='mono' style='color:{INK3};font-size:12px;letter-spacing:.16em'>"
                f"PYNGYN · DELIVERY INSIGHTS</div>", unsafe_allow_html=True)
with right:
    c1, c2 = st.columns(2)
    if c1.button("Use sample data", width="stretch"):
        load_sample()
        st.rerun()
    regen_clicked = c2.button("Regenerate insights", type="primary", width="stretch")

up = st.file_uploader("Upload a task CSV", type="csv", label_visibility="collapsed")
if up is not None:
    try:
        df_up = pd.read_csv(up)
        run_pipeline(df_up, regen=True)
        st.session_state.loaded_label = f"Loaded {up.name}"
    except Exception as e:
        st.error(f"Couldn't read that CSV — {e}")

if regen_clicked and "stats" in st.session_state:
    with st.spinner("Regenerating insights…"):
        st.session_state.insights, st.session_state.source = insights_mod.generate(st.session_state.stats)

stats = st.session_state.stats
ins = st.session_state.insights
source = st.session_state.source
H, C, W = stats["headline"], stats["concentration"], stats["wip_exposure"]

st.caption(f"{st.session_state.get('loaded_label','Sample data')}  ·  "
           f"{H['task_count']} tasks analyzed  ·  insights: {source}")


# ---- hero: the model's top finding -----------------------------------------
top = ins[0]
st.markdown(f"<div class='mono' style='color:{INK3};font-size:12px;letter-spacing:.14em'>"
            f"MOST SEVERE FINDING</div>", unsafe_allow_html=True)
st.title(top["headline"])
st.markdown(f"<p style='font-size:17px;color:{INK2};max-width:60ch'>{top['body']}</p>",
            unsafe_allow_html=True)
st.markdown(f"<div class='hero-do'><b class='mono' style='color:{SLIP};font-size:11px;"
            f"letter-spacing:.12em'>DO&nbsp;&nbsp;</b>{top['action']}</div>", unsafe_allow_html=True)

st.write("")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Over estimate", f"{H['portfolio_slip_pct']:.1f}%",
          help=f"{H['estimated_hours']}h estimated vs {H['actual_hours']}h actual")
m2.metric("Landed on target", f"{H['on_target_rate_pct']:.1f}%", help="within ±10% of estimate")
m3.metric("Caused half the overrun", f"{C['tasks_causing_half_of_overrun']} tasks")
m4.metric("Sunk into blocked work", f"{W['hours_sunk_in_blocked_work']:.0f}h")

st.divider()


# ---- charts -----------------------------------------------------------------
def slip_rail(cut_key: str, label_col: str):
    d = stats[cut_key].copy()
    d = d.iloc[::-1]  # plotly draws bottom-up; keep most-severe on top
    colors = [SLIP if v >= 0 else AHEAD for v in d["median_slip_pct"]]
    fig = go.Figure(go.Bar(
        x=d["median_slip_pct"], y=d[label_col].astype(str), orientation="h",
        marker_color=colors,
        text=[f"{'+' if v > 0 else ''}{v}%" for v in d["median_slip_pct"]],
        textposition="outside",
        hovertemplate="%{y}: %{x:+.1f}% median slip<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=2, line_color=INK)
    fig.add_annotation(x=0, y=1.06, yref="paper", text="ESTIMATE", showarrow=False,
                       font=dict(family="monospace", size=10, color=INK))
    fig.update_layout(
        height=90 + 46 * len(d), margin=dict(l=10, r=30, t=26, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="median slip vs estimate (%)", zeroline=False, gridcolor=RULE,
                   tickfont=dict(family="monospace", size=11)),
        yaxis=dict(tickfont=dict(family="monospace", size=12)),
        font=dict(color=INK2), showlegend=False,
    )
    return fig


def parity_scatter():
    s = stats["scatter"]
    vals = pd.concat([s["estimated_hours"], s["actual_hours"]])
    lo, hi = max(0.25, vals.min() * 0.8), vals.max() * 1.25
    fig = go.Figure()
    for status, color in STATUS_COLOR.items():
        sub = s[s["status"] == status]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["estimated_hours"], y=sub["actual_hours"], mode="markers", name=status,
            marker=dict(color=color, size=8, opacity=0.8),
            customdata=sub[["task_id", "assignee"]],
            hovertemplate="%{customdata[0]} · %{customdata[1]}<br>"
                          "est %{x}h → actual %{y}h<extra></extra>",
        ))
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="On estimate",
                             line=dict(color=INK, width=1.5, dash="dash"), hoverinfo="skip"))
    fig.update_layout(
        height=430, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(type="log", title="estimated hours (log)", range=[math.log10(lo), math.log10(hi)],
                   gridcolor=RULE, tickfont=dict(family="monospace", size=10)),
        yaxis=dict(type="log", title="actual hours (log)", range=[math.log10(lo), math.log10(hi)],
                   gridcolor=RULE, tickfont=dict(family="monospace", size=10)),
        legend=dict(orientation="h", y=-0.18, font=dict(family="monospace", size=10)),
        font=dict(color=INK2),
    )
    return fig


col_ins, col_charts = st.columns([1, 1], gap="large")

with col_charts:
    st.subheader("Slip rail")
    cut_label = st.radio("Break down by", ["Task size", "Assignee", "Status"],
                         horizontal=True, label_visibility="collapsed")
    cut_map = {"Task size": ("by_size", "size_bucket"),
               "Assignee": ("by_assignee", "assignee"),
               "Status": ("by_status", "status")}
    key, col = cut_map[cut_label]
    st.plotly_chart(slip_rail(key, col), width="stretch", config={"displayModeBar": False})

    note = {
        "by_size": "Estimates hold on small work and come apart on large work.",
        "by_assignee": "A stable multiple is a calibration gap, not a speed problem.",
        "by_status": "The clock runs whether or not the task moves.",
    }[key]
    st.caption(note)

    st.subheader("Every task against its estimate")
    st.caption("Above the dashed line = took longer than estimated.")
    st.plotly_chart(parity_scatter(), width="stretch", config={"displayModeBar": False})

with col_ins:
    st.subheader("What else it found")
    for i in ins[1:]:
        color = SEV_COLOR.get(i["severity"], INK3)
        st.markdown(f"""
        <div class="card" style="border-left-color:{color}">
          <span class="sev" style="color:{color}">{i['severity']}</span>
          <h4>{i['headline']}</h4>
          <span class="metric" style="color:{color}">{i['metric']}</span>
          <span class="mlabel">{i['metric_label']}</span>
          <p class="body">{i['body']}</p>
          <div class="action"><b>DO</b>{i['action']}</div>
        </div>""", unsafe_allow_html=True)


# ---- worst tasks table ------------------------------------------------------
st.divider()
st.subheader("The tasks doing the damage")
st.caption("Ranked by hours over estimate")
worst = stats["worst_tasks"].rename(columns={
    "task_id": "Task", "assignee": "Assignee", "status": "Status",
    "estimated_hours": "Est (h)", "actual_hours": "Actual (h)",
    "variance_hours": "Over by (h)", "slip_pct": "Slip %",
})
st.dataframe(worst, hide_index=True, width="stretch")

st.caption("Numbers computed in Python (pandas); insights written by Claude. "
           "The headline is the model's own top finding.")
