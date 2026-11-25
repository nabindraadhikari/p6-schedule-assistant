"""Schedule-quality checks for P6 data, modelled on the DCMA 14-point assessment plus integrity checks.

Every check returns a count, the share of the relevant population, the offending rows, and a
pass/review status against a threshold, so results are deterministic and explainable (no AI guessing).
"""
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd
import networkx as nx

HARD = {"CS_MSO", "CS_MEO", "CS_MSOB", "CS_MEOB", "CS_MANDSTART", "CS_MANDFIN"}
SKIP_TYPES = {"TT_WBS", "TT_LOE"}
MILESTONES = {"TT_MILE", "TT_FINMILE"}


@dataclass(frozen=True)
class CheckDef:
    key: str
    title: str
    threshold_pct: Optional[float]  # max % allowed before "Review"; None = informational
    why: str


CHECK_DEFS = {c.key: c for c in [
    CheckDef("no_pred", "Missing predecessor", 5, "Open start: nothing drives this activity, so its dates are unsupported."),
    CheckDef("no_succ", "Missing successor", 5, "Open end: a delay here pushes nothing, so it hides risk to the finish date."),
    CheckDef("leads", "Negative lag (leads)", 0, "Leads distort the critical path and are hard to audit; use SS with lag or split the activity."),
    CheckDef("lags", "Positive lag", 5, "Lags hide work and time that should be visible as activities."),
    CheckDef("fs_mix", "Non-FS relationships", 10, "Most links should be Finish-to-Start; heavy SS/FF/SF use makes logic fragile."),
    CheckDef("hard", "Hard constraints", 5, "Mandatory/On/On-or-Before constraints override logic and mask float."),
    CheckDef("neg_float", "Negative float", 0, "Activities forecast to miss a constraint or deadline."),
    CheckDef("high_float", "High float (>44 working days)", 5, "Often signals missing logic rather than real slack."),
    CheckDef("high_dur", "High duration (>44 working days)", 5, "Long activities are hard to progress and should be broken down."),
    CheckDef("bad_dates", "Invalid dates", 0, "Actuals after the data date, or unstarted work forecast before it."),
    CheckDef("status", "Status inconsistencies", 0, "Complete without actual finish, or in progress without actual start."),
    CheckDef("no_res", "No resources assigned", None, "Informational: only relevant if your schedules are resource-loaded."),
    CheckDef("bad_links", "Links to missing activities", 0, "Dangling relationships (often from partial exports or deleted activities)."),
    CheckDef("dups", "Duplicate relationships", 0, "The same pair is linked more than once."),
    CheckDef("loops", "Circular logic", 0, "Loops make schedule dates unreliable."),
]}


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _dt(s):
    return pd.to_datetime(s.replace("", np.nan), errors="coerce")


def prepare(tables):
    T = tables["TASK"].copy()
    R = tables.get("TASKPRED", pd.DataFrame(columns=["task_id", "pred_task_id", "proj_id", "pred_type", "lag_hr_cnt"])).copy()
    C = tables.get("CALENDAR", pd.DataFrame(columns=["clndr_id", "day_hr_cnt"]))
    hrs = dict(zip(C["clndr_id"], _num(C["day_hr_cnt"]).fillna(8)))
    T["day_hr"] = T["clndr_id"].map(hrs).fillna(8)
    for c in ["total_float_hr_cnt", "target_drtn_hr_cnt"]:
        T[c] = _num(T[c])
    for c in ["act_start_date", "act_end_date", "early_start_date", "cstr_date"]:
        T[c] = _dt(T[c])
    T["float_d"] = T["total_float_hr_cnt"] / T["day_hr"]
    T["dur_d"] = T["target_drtn_hr_cnt"] / T["day_hr"]
    R["lag_d"] = _num(R["lag_hr_cnt"]) / 8
    return T, R


def list_projects(tables):
    P = tables.get("PROJECT")
    if P is None or P.empty:
        return pd.DataFrame({"proj_id": sorted(tables["TASK"]["proj_id"].unique())})
    cnt = tables["TASK"].groupby("proj_id").size().rename("activities")
    out = P[["proj_id", "proj_short_name", "last_recalc_date"]].merge(cnt, on="proj_id", how="left")
    return out.fillna({"activities": 0})


def run_checks(tables, proj_id, data_date=None, resources_matter=False):
    """Run all checks on one project. Returns dict with summary DataFrame and per-check detail frames."""
    T, R = prepare(tables)
    proj_id = str(proj_id)
    P = tables.get("PROJECT")
    if data_date is None and P is not None and "last_recalc_date" in P:
        v = P.loc[P["proj_id"] == proj_id, "last_recalc_date"]
        data_date = pd.to_datetime(v.iloc[0], errors="coerce") if len(v) else None
    data_date = data_date if data_date is not None and not pd.isna(data_date) else pd.Timestamp.today().normalize()

    real = T[(T.proj_id == proj_id) & ~T.task_type.str.upper().isin(SKIP_TYPES)]
    inc = real[real.status_code != "TK_Complete"]
    is_mile = inc.task_type.str.upper().isin(MILESTONES)
    Rp = R[R.proj_id == proj_id]
    names = T[["task_id", "task_code", "task_name"]]
    has_pred, has_succ = set(R.task_id), set(R.pred_task_id)
    TR = tables.get("TASKRSRC", pd.DataFrame(columns=["task_id"]))

    link_cols = ["task_code", "task_name", "pred_type", "lag_d"]
    cols_issue = ["task_code", "task_name", "issue"]
    bad_dates = pd.concat([
        real[(real.act_start_date > data_date) | (real.act_end_date > data_date)].assign(issue="Actual date after data date"),
        inc[(inc.status_code == "TK_NotStart") & (inc.early_start_date < data_date)].assign(issue="Not started, forecast before data date"),
    ])
    status = pd.concat([
        real[(real.status_code == "TK_Complete") & real.act_end_date.isna()].assign(issue="Complete without actual finish"),
        real[(real.status_code == "TK_Active") & real.act_start_date.isna()].assign(issue="In progress without actual start"),
    ])
    detail = {
        "no_pred": inc[~inc.task_id.isin(has_pred)][["task_code", "task_name"]],
        "no_succ": inc[~inc.task_id.isin(has_succ)][["task_code", "task_name"]],
        "leads": Rp[Rp.lag_d < 0].merge(names, on="task_id")[link_cols],
        "lags": Rp[Rp.lag_d > 0].merge(names, on="task_id")[link_cols],
        "fs_mix": Rp[Rp.pred_type != "PR_FS"].merge(names, on="task_id")[link_cols],
        "hard": inc[inc.cstr_type.isin(HARD)][["task_code", "task_name", "cstr_type", "cstr_date"]],
        "neg_float": inc[inc.float_d < 0][["task_code", "task_name", "float_d"]],
        "high_float": inc[inc.float_d > 44][["task_code", "task_name", "float_d"]],
        "high_dur": inc[(inc.dur_d > 44) & ~is_mile][["task_code", "task_name", "dur_d"]],
        "bad_dates": bad_dates.reindex(columns=cols_issue),
        "status": status.reindex(columns=cols_issue),
        "no_res": inc[~inc.task_id.isin(set(TR.task_id)) & ~is_mile & (inc.dur_d > 0)][["task_code", "task_name"]],
        "bad_links": Rp[~Rp.pred_task_id.isin(set(T.task_id))][["task_id", "pred_task_id", "pred_type"]],
        "dups": Rp[Rp.duplicated(["task_id", "pred_task_id"], keep=False)].merge(names, on="task_id")[link_cols],
    }
    G = nx.DiGraph()
    G.add_edges_from(zip(R.pred_task_id, R.task_id))
    loops = [c for c in nx.strongly_connected_components(G.subgraph(set(inc.task_id))) if len(c) > 1]
    detail["loops"] = pd.DataFrame({
        "activities_in_loop": [len(c) for c in loops],
        "example_codes": [", ".join(names[names.task_id.isin(list(c)[:5])].task_code) for c in loops]})

    n_act, n_link = len(inc), len(Rp)
    base = {"leads": n_link, "lags": n_link, "fs_mix": n_link, "bad_links": n_link, "dups": n_link,
            "bad_dates": len(real), "status": len(real)}
    rows = []
    for key, d in CHECK_DEFS.items():
        cnt = len(detail[key])
        b = base.get(key, n_act)
        pct = 100 * cnt / b if b else 0.0
        if d.threshold_pct is None and not (key == "no_res" and resources_matter):
            st = "Info"
        elif d.threshold_pct is None:
            st = "Pass" if pct <= 5 else "Review"
        else:
            st = "Pass" if pct <= d.threshold_pct else "Review"
        rows.append({"Check": d.title, "Count": cnt, "% of population": round(pct, 1),
                     "Allowed %": d.threshold_pct, "Status": st, "Why it matters": d.why, "key": key})
    return {"proj_id": proj_id, "data_date": data_date, "n_activities": len(real), "n_incomplete": n_act,
            "n_links": n_link, "summary": pd.DataFrame(rows), "detail": detail}
