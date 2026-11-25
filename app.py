import os
import streamlit as st
from p6_assistant import read_xer_bytes, run_checks, list_projects
from p6_assistant.report import to_excel
from p6_assistant import ai

st.set_page_config(page_title="P6 Schedule Assistant", page_icon="📐", layout="wide")
st.title("📐 P6 Schedule Assistant")
st.caption("Upload a Primavera P6 .xer file. Errors are found by deterministic checks; the AI only explains them.")

PRESETS = {
    "Local Ollama (private)": ("http://localhost:11434/v1", "llama3.1"),
    "Groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "Gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
}

with st.sidebar:
    st.header("Settings")
    resources = st.checkbox("My schedules are resource-loaded", value=False)
    st.divider()
    st.subheader("AI explainer (optional)")
    preset = st.selectbox("Provider", list(PRESETS))
    base_url = st.text_input("Base URL", PRESETS[preset][0])
    model = st.text_input("Model", PRESETS[preset][1])
    api_key = st.text_input("API key", os.environ.get("LLM_API_KEY", ""), type="password")
    st.info("Real project data is confidential. Prefer a local model, or get approval before using a cloud one.")


@st.cache_data(show_spinner="Parsing XER...")
def parse(raw: bytes):
    return read_xer_bytes(raw)


up = st.file_uploader("P6 export (.xer)", type=["xer"])
use_demo = st.button("Or try the demo file")
raw = up.getvalue() if up else None
if use_demo:
    path = os.path.join(os.path.dirname(__file__), "sample_data", "demo_bridge.xer")
    raw = open(path, "rb").read()
if raw is None:
    st.stop()

header, tables = parse(raw)
projects = list_projects(tables)
label = lambda r: f"{r.get('proj_short_name', r['proj_id'])}  ({int(r.get('activities', 0))} activities)"
opts = {label(r): r["proj_id"] for _, r in projects.iterrows()}
choice = st.selectbox("Project in this file", list(opts))


@st.cache_data(show_spinner="Running checks...")
def analyse(raw, proj_id, resources):
    _, t = parse(raw)
    return run_checks(t, proj_id, resources_matter=resources)


res = analyse(raw, opts[choice], resources)
s = res["summary"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Activities", f"{res['n_activities']:,}")
c2.metric("Incomplete", f"{res['n_incomplete']:,}")
c3.metric("Relationships", f"{res['n_links']:,}")
c4.metric("Checks to review", int((s["Status"] == "Review").sum()))
st.caption(f"Data date: {res['data_date']:%d %b %Y}")

tab1, tab2 = st.tabs(["Schedule health", "Ask the assistant"])
with tab1:
    show = s.drop(columns=["key"])
    st.dataframe(show.style.map(lambda v: "background-color:#fde2e2" if v == "Review" else
                                ("background-color:#e2f5e6" if v == "Pass" else ""), subset=["Status"]),
                 hide_index=True, use_container_width=True)
    st.download_button("Download Excel report", to_excel(res), "schedule_check_report.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for _, r in s[s["Count"] > 0].iterrows():
        with st.expander(f"{r['Check']}: {r['Count']} ({r['% of population']}%)  [{r['Status']}]"):
            st.write(r["Why it matters"])
            st.dataframe(res["detail"][r["key"]].head(500), hide_index=True, use_container_width=True)

with tab2:
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for m in st.session_state.chat:
        st.chat_message(m["role"]).write(m["content"])
    quick = st.pills("Quick asks", ["What should I fix first?", "Draft an email to the planner about open ends",
                                     "Is this schedule ready to submit?"]) if hasattr(st, "pills") else None
    q = st.chat_input("Ask about this schedule's problems...") or quick
    if q:
        st.chat_message("user").write(q)
        try:
            a = ai.ask(q, res, base_url, api_key or "none", model, history=st.session_state.chat)
        except Exception as e:
            a = f"Could not reach the AI provider: {e}"
        st.chat_message("assistant").write(a)
        st.session_state.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
