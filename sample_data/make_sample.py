"""Generate a small SYNTHETIC P6 .xer file with deliberately seeded schedule defects.

Real project schedules are confidential, so the repo's demo and tests use this fake data only.
Usage:  python sample_data/make_sample.py
"""
import os

HEADER = "ERMHDR\t8.2\t2026-01-01\tProject\tADMIN\tadmin\tdemo\tProject Management\tUSD"


def table(name, fields, rows):
    out = [f"%T\t{name}", "%F\t" + "\t".join(fields)]
    out += ["%R\t" + "\t".join(str(v) for v in r) for r in rows]
    return "\n".join(out)


def build():
    dd = "2026-01-15 00:00"
    proj = table("PROJECT", ["proj_id", "proj_short_name", "last_recalc_date", "clndr_id"],
                 [[1, "DEMO-BRIDGE", dd, 1]])
    cal = table("CALENDAR", ["clndr_id", "clndr_name", "day_hr_cnt", "default_flag"], [[1, "5 Day", 8, "Y"]])
    F = ["task_id", "proj_id", "wbs_id", "clndr_id", "status_code", "task_code", "task_name", "task_type",
         "total_float_hr_cnt", "target_drtn_hr_cnt", "cstr_type", "cstr_date", "act_start_date", "act_end_date",
         "early_start_date"]

    def t(i, code, name, status="TK_NotStart", typ="TT_Task", flt=80, dur=80, cstr="", cdate="", a_s="", a_e="",
          es="2026-02-01 08:00"):
        return [i, 1, 1, 1, status, code, name, typ, flt, dur, cstr, cdate, a_s, a_e, es]

    tasks = [
        t(1, "A100", "Mobilization", "TK_Complete", a_s="2025-11-03 08:00", a_e="2025-11-10 17:00", flt=0, dur=40),
        t(2, "A110", "Site clearing", "TK_Complete", a_s="2025-11-10 08:00", a_e="2025-11-28 17:00", flt=0, dur=120),
        t(3, "B100", "Excavation Abutment A", "TK_Active", a_s="2026-01-05 08:00", flt=0, dur=160, es="2026-01-05 08:00"),
        t(4, "B110", "Excavation Abutment B", "TK_Active", flt=0, dur=160, es="2026-01-05 08:00"),   # active, no actual start
        t(5, "B120", "Piling Abutment A", flt=0, dur=240),
        t(6, "B130", "Piling Abutment B", flt=16, dur=240),
        t(7, "C100", "Pier foundations", flt=2000, dur=2000),                                      # >44d duration + float
        t(8, "C110", "Pier columns", flt=-40, dur=300),                                            # negative float
        t(9, "C120", "Deck girders", flt=24, dur=200, cstr="CS_MEOB", cdate="2026-09-01 17:00"),   # hard constraint
        t(10, "C130", "Deck slab", flt=24, dur=200),
        t(11, "D100", "Approach roads", flt=40, dur=120),                                          # missing successor
        t(12, "D110", "Utilities relocation", flt=40, dur=120, es="2026-01-02 08:00"),             # forecast before data date
        t(13, "E100", "Bridge opening", typ="TT_FinMile", flt=0, dur=0),
        t(14, "E110", "Floating task with no logic", flt=900, dur=40),                              # no pred and no succ
        t(15, "E120", "Loop task X", flt=0, dur=40),
        t(16, "E130", "Loop task Y", flt=0, dur=40),
        t(17, "E140", "Future actual", "TK_Complete", a_s="2026-03-01 08:00", a_e="2026-03-05 17:00", flt=0, dur=40),
    ]
    task = table("TASK", F, tasks)
    # (task_id, pred_task_id, type, lag_hr)
    links = [
        (3, 1, "PR_FS", 0), (4, 1, "PR_FS", 0), (5, 3, "PR_FS", 0), (6, 4, "PR_FS", 0),
        (7, 5, "PR_FS", 0), (7, 6, "PR_FS", 0), (8, 7, "PR_FS", 0),
        (9, 8, "PR_FS", -80),          # lead
        (10, 9, "PR_SS", 40),          # SS + positive lag
        (13, 10, "PR_FS", 0),
        (13, 8, "PR_FS", 0),
        (11, 3, "PR_FS", 0), (12, 2, "PR_FS", 0), (12, 2, "PR_FS", 0),   # duplicate
        (15, 16, "PR_FS", 0), (16, 15, "PR_FS", 0),                       # loop
        (6, 999, "PR_FS", 0),          # dangling link to a non-existent activity
    ]
    pred = table("TASKPRED", ["task_pred_id", "task_id", "pred_task_id", "proj_id", "pred_proj_id", "pred_type", "lag_hr_cnt"],
                 [[i + 1, a, b, 1, 1, ty, lg] for i, (a, b, ty, lg) in enumerate(links)])
    rsrc = table("TASKRSRC", ["taskrsrc_id", "task_id", "proj_id"], [[1, 3, 1], [2, 5, 1], [3, 7, 1]])
    return "\r\n".join([HEADER, proj, cal, task, pred, rsrc, ""])


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(__file__), "demo_bridge.xer")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(build())
    print("wrote", path)
