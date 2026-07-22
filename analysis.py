import pandas as pd

ON_TARGET_BAND = 0.10  # within +/-10% of estimate counts as "on target"
SIZE_BUCKETS = [(0, 2, "0-2h"), (2, 8, "2-8h"), (8, 16, "8-16h"), (16, 1e9, "16h+")]
REQUIRED = {"task_id", "assignee", "estimated_hours", "actual_hours", "status"}


def _bucket(est):
    for lo, hi, label in SIZE_BUCKETS:
        if lo < est <= hi:
            return label
    return SIZE_BUCKETS[0][2]


def _r(x, n=1):
    return round(float(x), n)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Validate, clean, and derive the per-task columns the analysis needs."""
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")

    df = df.copy()
    df["estimated_hours"] = pd.to_numeric(df["estimated_hours"], errors="coerce")
    df["actual_hours"] = pd.to_numeric(df["actual_hours"], errors="coerce")
    df = df.dropna(subset=["estimated_hours", "actual_hours"])
    df = df[df["estimated_hours"] > 0]
    if df.empty:
        raise ValueError("No valid rows after cleaning — check the numeric columns.")

    df["variance_hours"] = df["actual_hours"] - df["estimated_hours"]
    df["slip_ratio"] = df["actual_hours"] / df["estimated_hours"]
    df["slip_pct"] = (df["slip_ratio"] - 1) * 100
    df["size_bucket"] = df["estimated_hours"].apply(_bucket)
    df["outcome"] = pd.cut(
        df["slip_ratio"],
        bins=[-1e9, 1 - ON_TARGET_BAND, 1 + ON_TARGET_BAND, 1e9],
        labels=["under", "on_target", "over"],
    )
    return df


def analyze(df: pd.DataFrame) -> dict:
    df = prepare(df)
    est, act = df["estimated_hours"].sum(), df["actual_hours"].sum()
    counts = df["outcome"].value_counts()

    headline = {
        "task_count": int(len(df)),
        "estimated_hours": _r(est),
        "actual_hours": _r(act),
        "variance_hours": _r(act - est),
        "portfolio_slip_pct": _r((act / est - 1) * 100),
        "median_task_slip_pct": _r(df["slip_pct"].median()),
        "tasks_over": int(counts.get("over", 0)),
        "tasks_on_target": int(counts.get("on_target", 0)),
        "tasks_under": int(counts.get("under", 0)),
        "on_target_rate_pct": _r(counts.get("on_target", 0) / len(df) * 100),
    }

    ga = df.groupby("assignee")
    by_assignee = (
        pd.DataFrame({
            "tasks": ga.size(),
            "estimated_hours": ga["estimated_hours"].sum().round(1),
            "actual_hours": ga["actual_hours"].sum().round(1),
            "median_slip_pct": ga["slip_pct"].median().round(1),
            "overrun_hours": ga["variance_hours"].sum().round(1),
        }).reset_index().sort_values("median_slip_pct", ascending=False)
    )
    by_assignee["slip_pct"] = (
        (by_assignee["actual_hours"] / by_assignee["estimated_hours"] - 1) * 100
    ).round(1)

    gs = df.groupby("status")
    by_status = (
        pd.DataFrame({
            "tasks": gs.size(),
            "actual_hours": gs["actual_hours"].sum().round(1),
            "median_slip_pct": gs["slip_pct"].median().round(1),
            "overrun_hours": gs["variance_hours"].sum().round(1),
        }).reset_index().sort_values("median_slip_pct", ascending=False)
    )

    order = [b[2] for b in SIZE_BUCKETS]
    gz = df.groupby("size_bucket")
    by_size = pd.DataFrame({
        "tasks": gz.size(),
        "median_slip_pct": gz["slip_pct"].median().round(1),
        "overrun_hours": gz["variance_hours"].sum().round(1),
        "on_target_rate_pct": gz["outcome"].apply(lambda s: (s == "on_target").mean() * 100).round(1),
    }).reset_index()
    by_size["size_bucket"] = pd.Categorical(by_size["size_bucket"], categories=order, ordered=True)
    by_size = by_size.sort_values("size_bucket")

    over = df[df["variance_hours"] > 0].sort_values("variance_hours", ascending=False)
    total_over = over["variance_hours"].sum()
    top_n = max(1, int(len(df) * 0.20))
    concentration = {
        "total_overrun_hours": _r(total_over),
        "top_20pct_task_count": int(top_n),
        "top_20pct_share_pct": _r(over.head(top_n)["variance_hours"].sum() / total_over * 100),
        "tasks_causing_half_of_overrun": int((over["variance_hours"].cumsum() < total_over * 0.5).sum() + 1),
    }

    open_work = df[df["status"] != "Done"]
    blocked = df[df["status"] == "Blocked"]
    wip = {
        "open_tasks": int(len(open_work)),
        "hours_sunk_in_open_work": _r(open_work["actual_hours"].sum()),
        "blocked_tasks": int(len(blocked)),
        "hours_sunk_in_blocked_work": _r(blocked["actual_hours"].sum()),
        "blocked_share_of_open_hours_pct": _r(
            blocked["actual_hours"].sum() / max(open_work["actual_hours"].sum(), 1e-9) * 100
        ),
    }

    worst_cols = ["task_id", "assignee", "status", "estimated_hours",
                  "actual_hours", "variance_hours", "slip_pct"]
    worst = df.sort_values("variance_hours", ascending=False).head(8)[worst_cols].copy()
    worst["slip_pct"] = worst["slip_pct"].round(0)

    return {
        "headline": headline,
        "by_assignee": by_assignee,
        "by_status": by_status,
        "by_size": by_size,
        "concentration": concentration,
        "wip_exposure": wip,
        "worst_tasks": worst,
        "scatter": df[["task_id", "assignee", "status", "estimated_hours", "actual_hours"]].copy(),
    }
