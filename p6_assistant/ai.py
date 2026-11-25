"""Optional AI layer. The checks are computed by code; the model only explains and drafts.

Works with any OpenAI-compatible endpoint, so you can use a free-tier cloud model or a local one:
  Local (private, free):  base_url=http://localhost:11434/v1   (Ollama)   api_key=ollama
  Groq:                   base_url=https://api.groq.com/openai/v1
  Gemini:                 base_url=https://generativelanguage.googleapis.com/v1beta/openai/
Check each provider's current free-tier limits and data policy before sending real project data.
"""
import requests

SYSTEM = (
    "You are an assistant for a construction project scheduler using Primavera P6. "
    "You are given the computed results of schedule-quality checks. Use ONLY those results; never invent "
    "numbers or activity IDs. Be concise and practical: explain what the issues mean for the schedule, "
    "prioritise what to fix first, and draft wording the scheduler can send to a project team when asked."
)


def summarize_for_llm(result, max_examples=8) -> str:
    lines = [f"Project {result['proj_id']} | data date {result['data_date']:%Y-%m-%d} | "
             f"{result['n_incomplete']} incomplete activities | {result['n_links']} relationships", ""]
    for _, r in result["summary"].iterrows():
        lines.append(f"- {r['Check']}: {r['Count']} ({r['% of population']}%), status {r['Status']}")
        for _, row in result["detail"][r["key"]].head(max_examples).iterrows():
            lines.append("    e.g. " + " | ".join(str(v) for v in row.values[:4]))
    return "\n".join(lines)


def ask(question, result, base_url, api_key, model, history=None, timeout=60):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "system", "content": "Schedule check results:\n" + summarize_for_llm(result)}]
    msgs += history or []
    msgs.append({"role": "user", "content": question})
    r = requests.post(base_url.rstrip("/") + "/chat/completions", timeout=timeout,
                      headers={"Authorization": f"Bearer {api_key}"},
                      json={"model": model, "messages": msgs, "temperature": 0.2})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
