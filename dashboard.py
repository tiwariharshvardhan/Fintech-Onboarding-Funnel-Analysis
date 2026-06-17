"""Conversion Funnel & Activation dashboard for the synthetic fintech journeys.

A Streamlit + Plotly app that turns the generated user-journey CSVs into a
product-analyst-style onboarding deep-dive: where do users drop, who drops, and
how long does it take them to activate.

Run it with:

    streamlit run dashboard.py

It reads `high_friction.csv` and `optimized.csv` from the working directory
(generate them first with `generate.py`). The "optimized" funnel is framed as a
redesigned onboarding flow, so the Compare mode reads as a before/after story.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Canonical funnel order
STAGES = [
    "landing",
    "signup",
    "identity_verification",
    "deposit",
    "first_trade",
]

# Human-friendly stage labels for charts and tables.
STAGE_LABELS = {
    "landing": "Landing",
    "signup": "Sign-up",
    "identity_verification": "KYC verified",
    "deposit": "Deposit funded",
    "first_trade": "First trade",
}

# The two shipped datasets, framed as a product before/after.
DATASETS = {
    "high_friction": {
        "path": "high_friction.csv",
        "label": "Current onboarding (high friction)",
    },
    "optimized": {
        "path": "optimized.csv",
        "label": "Redesigned onboarding (optimized)",
    },
}

ACTIVATION_STAGE = STAGES[-1]  # first_trade == the activation milestone
SEGMENT_DIMS = ["channel", "device"]
TS_COLS = [f"ts_{s}" for s in STAGES]

st.set_page_config(page_title="Fintech Onboarding Funnel", layout="wide")


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_dataset(path: str) -> pd.DataFrame:
    """Load one journey CSV, parsing timestamps and adding a landing-week key."""
    df = pd.read_csv(path)
    for col in TS_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    # `reached_<stage>` booleans drive every funnel metric. Landing is always 1;
    # any later stage is reached iff its timestamp is present.
    for s in STAGES:
        df[f"reached_{s}"] = df[f"ts_{s}"].notna()
    df["landing_week"] = df["ts_landing"].dt.to_period("W").dt.start_time
    return df


def available_datasets() -> dict:
    """Datasets whose CSV actually exists on disk."""
    return {k: v for k, v in DATASETS.items() if os.path.exists(v["path"])}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def funnel_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Per-stage reach counts, step conversion, and absolute drop-off."""
    rows = []
    prev = None
    landed = int(df[f"reached_{STAGES[0]}"].sum())
    for s in STAGES:
        count = int(df[f"reached_{s}"].sum())
        step = (count / prev * 100.0) if prev else 100.0
        overall = (count / landed * 100.0) if landed else 0.0
        drop = (prev - count) if prev is not None else 0
        rows.append(
            {
                "stage": s,
                "label": STAGE_LABELS[s],
                "users": count,
                "step_conv_pct": step,
                "overall_pct": overall,
                "dropoff": drop,
            }
        )
        prev = count
    return pd.DataFrame(rows)


def activation_rate(df: pd.DataFrame) -> float:
    n = len(df)
    return float(df[f"reached_{ACTIVATION_STAGE}"].mean() * 100.0) if n else 0.0


def time_to_convert(df: pd.DataFrame) -> pd.DataFrame:
    """Median hours between consecutive stages, over users who reached both."""
    rows = []
    for a, b in zip(STAGES[:-1], STAGES[1:]):
        mask = df[f"reached_{b}"]
        if mask.any():
            delta = (df.loc[mask, f"ts_{b}"] - df.loc[mask, f"ts_{a}"])
            hours = delta.dt.total_seconds() / 3600.0
            rows.append(
                {
                    "transition": f"{STAGE_LABELS[a]} → {STAGE_LABELS[b]}",
                    "median_hours": float(hours.median()),
                    "p90_hours": float(hours.quantile(0.90)),
                    "n": int(mask.sum()),
                }
            )
    return pd.DataFrame(rows)


def median_time_to_activate(df: pd.DataFrame) -> float | None:
    """Median hours from landing to first trade, over activated users."""
    mask = df[f"reached_{ACTIVATION_STAGE}"]
    if not mask.any():
        return None
    delta = df.loc[mask, f"ts_{ACTIVATION_STAGE}"] - df.loc[mask, "ts_landing"]
    return float((delta.dt.total_seconds() / 3600.0).median())


def simulate_step_uplift(df: pd.DataFrame, stage: str, new_step_pct: float) -> dict:
    """Project the activation impact of lifting one step's conversion.

    The funnel is multiplicative, so improving step ``stage`` from its current
    step-conversion to ``new_step_pct`` scales that stage and everything below
    it by the same ratio, holding all other step rates constant. This is the
    standard back-of-envelope ``+X% at the leaky step`` estimate.
    """
    fc = funnel_counts(df)
    row = fc[fc["stage"] == stage].iloc[0]
    landed = fc.iloc[0]["users"]
    old_act_users = fc.iloc[-1]["users"]
    old_step = row["step_conv_pct"] / 100.0
    new_step = min(max(new_step_pct / 100.0, 0.0), 1.0)
    ratio = (new_step / old_step) if old_step > 0 else 1.0
    new_act_users = old_act_users * ratio
    return {
        "stage_label": STAGE_LABELS[stage],
        "old_step_pct": old_step * 100.0,
        "new_step_pct": new_step * 100.0,
        "old_act_pct": (old_act_users / landed * 100.0) if landed else 0.0,
        "new_act_pct": (new_act_users / landed * 100.0) if landed else 0.0,
        "incr_users": new_act_users - old_act_users,
        "landed": int(landed),
    }


def segment_rates(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Activation rate and volume by a segment dimension."""
    g = df.groupby(dim)
    out = pd.DataFrame(
        {
            "users": g.size(),
            "activation_pct": g[f"reached_{ACTIVATION_STAGE}"].mean() * 100.0,
        }
    ).reset_index()
    return out.sort_values("activation_pct", ascending=False)


def stage_conv_by_segment(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Step conversion at each stage, per segment value (for the heatmap)."""
    rows = []
    for value, sub in df.groupby(dim):
        prev = None
        for s in STAGES:
            count = int(sub[f"reached_{s}"].sum())
            if prev:
                rows.append(
                    {"segment": value, "stage": STAGE_LABELS[s],
                     "step_conv_pct": count / prev * 100.0}
                )
            prev = count
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
PALETTE = {"high_friction": "#ef553b", "optimized": "#00cc96"}


def funnel_figure(frames: dict) -> go.Figure:
    """One Plotly funnel trace per selected dataset."""
    fig = go.Figure()
    for key, df in frames.items():
        fc = funnel_counts(df)
        fig.add_trace(
            go.Funnel(
                name=DATASETS[key]["label"],
                y=fc["label"],
                x=fc["users"],
                textinfo="value+percent initial",
                marker={"color": PALETTE.get(key)},
            )
        )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def segment_bar(frames: dict, dim: str) -> go.Figure:
    fig = go.Figure()
    for key, df in frames.items():
        sr = segment_rates(df, dim)
        fig.add_trace(
            go.Bar(
                name=DATASETS[key]["label"],
                x=sr[dim],
                y=sr["activation_pct"],
                marker_color=PALETTE.get(key),
                text=[f"{v:.1f}%" for v in sr["activation_pct"]],
                textposition="outside",
            )
        )
    fig.update_layout(
        barmode="group",
        margin=dict(l=10, r=10, t=30, b=10),
        height=340,
        yaxis_title="Activation rate (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def heatmap_figure(df: pd.DataFrame, dim: str) -> go.Figure:
    sc = stage_conv_by_segment(df, dim)
    pivot = sc.pivot(index="segment", columns="stage", values="step_conv_pct")
    # Keep stages in funnel order (skip landing, which has no step conversion).
    ordered = [STAGE_LABELS[s] for s in STAGES[1:] if STAGE_LABELS[s] in pivot.columns]
    pivot = pivot[ordered]
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale="RdYlGn",
            zmin=0,
            zmax=100,
            text=np.round(pivot.values, 1),
            texttemplate="%{text}%",
            colorbar=dict(title="Step conv. %"),
        )
    )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=320)
    return fig


def weekly_activation_figure(frames: dict) -> go.Figure:
    fig = go.Figure()
    for key, df in frames.items():
        g = df.groupby("landing_week")
        weekly = (g[f"reached_{ACTIVATION_STAGE}"].mean() * 100.0)
        # Trim the final partial week so the trend line doesn't dip artificially.
        weekly = weekly.iloc[:-1] if len(weekly) > 1 else weekly
        fig.add_trace(
            go.Scatter(
                name=DATASETS[key]["label"],
                x=weekly.index,
                y=weekly.values,
                mode="lines+markers",
                line=dict(color=PALETTE.get(key)),
            )
        )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=320,
        yaxis_title="Activation rate (%)",
        xaxis_title="Landing week",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


# --------------------------------------------------------------------------- #
# Sidebar / filters
# --------------------------------------------------------------------------- #
def apply_filters(df: pd.DataFrame, channels, devices, date_range) -> pd.DataFrame:
    out = df
    if channels:
        out = out[out["channel"].isin(channels)]
    if devices:
        out = out[out["device"].isin(devices)]
    if date_range and len(date_range) == 2:
        start, end = date_range
        landing = out["ts_landing"]
        start_ts = pd.Timestamp(start, tz="UTC")
        # Include the whole end day.
        end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        out = out[(landing >= start_ts) & (landing < end_ts)]
    return out


def leak_stage_key(df: pd.DataFrame) -> str:
    """Stage key of the step with the largest absolute drop-off (post-landing)."""
    fc = funnel_counts(df)
    return str(fc.iloc[1:].sort_values("dropoff", ascending=False).iloc[0]["stage"])


def biggest_leak(df: pd.DataFrame) -> dict:
    fc = funnel_counts(df)
    # Largest absolute drop-off after landing.
    leak = fc.iloc[1:].sort_values("dropoff", ascending=False).iloc[0]
    # The transition is from the previous stage into `leak`.
    idx = fc.index[fc["stage"] == leak["stage"]][0]
    prev = fc.iloc[idx - 1]
    return {
        "from": prev["label"],
        "to": leak["label"],
        "dropoff": int(leak["dropoff"]),
        "step_conv": float(leak["step_conv_pct"]),
    }


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("Fintech Onboarding — Conversion Funnel & Activation")
    st.caption(
        "Where do new users drop, who drops, and how long do they take to "
        f"reach activation ({STAGE_LABELS[ACTIVATION_STAGE]})? "
        "Synthetic data — see README for the generator."
    )

    datasets = available_datasets()
    if not datasets:
        st.error(
            "No datasets found. Generate them first, e.g.\n\n"
            "`python generate.py --preset high_friction --out high_friction.csv`"
        )
        st.stop()

    st.sidebar.header("Filters")
    options = list(datasets.keys())
    view = st.sidebar.radio(
        "View",
        options=options + (["Compare both"] if len(options) > 1 else []),
        format_func=lambda k: DATASETS[k]["label"] if k in DATASETS else k,
    )
    selected_keys = options if view == "Compare both" else [view]

    raw = {k: load_dataset(datasets[k]["path"]) for k in selected_keys}
    union = pd.concat(raw.values(), ignore_index=True)

    channels = st.sidebar.multiselect(
        "Acquisition channel", sorted(union["channel"].dropna().unique())
    )
    devices = st.sidebar.multiselect(
        "Device", sorted(union["device"].dropna().unique())
    )
    min_d = union["ts_landing"].min().date()
    max_d = union["ts_landing"].max().date()
    date_range = st.sidebar.date_input(
        "Landing date range", value=(min_d, max_d), min_value=min_d, max_value=max_d
    )

    frames = {
        k: apply_filters(df, channels, devices, date_range) for k, df in raw.items()
    }
    if all(len(f) == 0 for f in frames.values()):
        st.warning("No users match the current filters.")
        st.stop()

    # ---- KPI row ---------------------------------------------------------- #
    st.subheader("Headline metrics")
    primary_key = selected_keys[0]
    primary = frames[primary_key]
    fc = funnel_counts(primary)
    signup_rate = fc.loc[fc["stage"] == "signup", "overall_pct"].iloc[0]
    kyc_rate = fc.loc[fc["stage"] == "identity_verification", "overall_pct"].iloc[0]
    act = activation_rate(primary)
    tta = median_time_to_activate(primary)

    cols = st.columns(5)
    cols[0].metric("Users landed", f"{len(primary):,}")
    cols[1].metric("Sign-up rate", f"{signup_rate:.1f}%")
    cols[2].metric("KYC rate", f"{kyc_rate:.1f}%")
    cols[3].metric("Activation rate", f"{act:.1f}%")
    cols[4].metric(
        "Median time-to-activate",
        f"{tta/24:.1f} days" if tta is not None else "—",
    )
    if len(selected_keys) > 1:
        st.caption(f"KPIs above reflect: **{DATASETS[primary_key]['label']}**.")

    # ---- Funnel ----------------------------------------------------------- #
    st.subheader("Onboarding funnel")
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(funnel_figure(frames), use_container_width=True)
    with right:
        st.markdown("**Step conversion & drop-off**")
        table = fc[["label", "users", "step_conv_pct", "dropoff"]].copy()
        table.columns = ["Stage", "Users", "Step conv. %", "Drop-off"]
        table["Step conv. %"] = table["Step conv. %"].map(lambda v: f"{v:.1f}%")
        st.dataframe(table, hide_index=True, use_container_width=True)

    # ---- Auto insight ----------------------------------------------------- #
    leak = biggest_leak(primary)
    st.info(
        f"**Biggest leak ({DATASETS[primary_key]['label']}):** "
        f"{leak['from']} → {leak['to']} loses **{leak['dropoff']:,} users** "
        f"(only {leak['step_conv']:.1f}% convert this step). "
        "This is where a fix yields the largest absolute gain."
    )

    # ---- What-if impact simulator ---------------------------------------- #
    st.subheader("What-if: step-conversion impact simulator")
    st.caption(
        "Pick a funnel step and a target conversion to estimate the lift in "
        "overall activation, holding every other step constant. Use it to "
        "prioritise: a small gain at the leakiest step usually beats a big gain "
        "at a small one."
    )
    step_options = STAGES[1:]  # landing has no step conversion to improve
    sim_cols = st.columns([2, 3])
    with sim_cols[0]:
        target_stage = st.selectbox(
            "Improve this step",
            step_options,
            index=step_options.index(leak_stage_key(primary)),
            format_func=lambda s: STAGE_LABELS[s],
        )
        current_step = funnel_counts(primary)
        cur_pct = current_step.loc[
            current_step["stage"] == target_stage, "step_conv_pct"
        ].iloc[0]
        target_pct = st.slider(
            f"Target step conversion for {STAGE_LABELS[target_stage]} (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(round(cur_pct, 1)),
            step=0.5,
            help=f"Currently {cur_pct:.1f}%.",
        )
    sim = simulate_step_uplift(primary, target_stage, target_pct)
    with sim_cols[1]:
        m = st.columns(3)
        m[0].metric(
            f"{sim['stage_label']} step conv.",
            f"{sim['new_step_pct']:.1f}%",
            delta=f"{sim['new_step_pct'] - sim['old_step_pct']:+.1f} pts",
        )
        m[1].metric(
            "Overall activation",
            f"{sim['new_act_pct']:.2f}%",
            delta=f"{sim['new_act_pct'] - sim['old_act_pct']:+.2f} pts",
        )
        m[2].metric(
            "Incremental activated users",
            f"{sim['incr_users']:+,.0f}",
            help=f"Over the {sim['landed']:,} landed users in the current view.",
        )
    st.caption(
        "Assumption: downstream step conversions stay fixed; only the selected "
        "step changes. A first-order estimate, not a behavioural model."
    )

    # ---- Segments --------------------------------------------------------- #
    st.subheader("Segment breakdown")
    seg_dim = st.radio(
        "Slice by", SEGMENT_DIMS, horizontal=True,
        format_func=str.capitalize,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Activation rate by {seg_dim}**")
        st.plotly_chart(segment_bar(frames, seg_dim), use_container_width=True)
    with c2:
        st.markdown(
            f"**Step conversion by {seg_dim}** — {DATASETS[primary_key]['label']}"
        )
        st.plotly_chart(heatmap_figure(primary, seg_dim), use_container_width=True)

    # ---- Time-to-convert -------------------------------------------------- #
    st.subheader("Time to convert")
    ttc = time_to_convert(primary)
    if not ttc.empty:
        disp = ttc.copy()
        disp["median_hours"] = disp["median_hours"].map(lambda v: f"{v:.1f} h")
        disp["p90_hours"] = disp["p90_hours"].map(lambda v: f"{v:.1f} h")
        disp.columns = ["Transition", "Median", "P90 (slow tail)", "Users"]
        st.dataframe(disp, hide_index=True, use_container_width=True)

    # ---- Trend ------------------------------------------------------------ #
    st.subheader("Activation rate over time (by landing cohort)")
    st.plotly_chart(weekly_activation_figure(frames), use_container_width=True)

    with st.expander("How to read this dashboard"):
        st.markdown(
            "- **Funnel**: users reaching each stage. The steepest step is the "
            "priority fix.\n"
            "- **Segment breakdown**: which channel/device leaks where. Watch "
            "Android at the KYC step — camera/document friction shows up as a "
            "lower step-conversion cell in the heatmap.\n"
            "- **Time to convert**: long medians (especially the P90 tail) flag "
            "steps that are slow, not just leaky — e.g. manual KYC review.\n"
            "- **Compare both**: read *high friction* as today's flow and "
            "*optimized* as a redesigned onboarding — the gap is the opportunity."
        )


if __name__ == "__main__":
    main()
