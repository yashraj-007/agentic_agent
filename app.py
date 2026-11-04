"""
app.py - Streamlit web interface for the Agentic AI Research Assistant.

Run with:  streamlit run app.py
"""

import json
import os

import streamlit as st

from agent import DEFAULT_MODEL, ResearchAgent
from tools import NOTES_FILE, TOOL_ICONS, TOOLS

st.set_page_config(page_title="Agentic AI Research Assistant", page_icon="🤖", layout="wide")

FALLBACK_MODELS = [DEFAULT_MODEL, "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
EXAMPLES = [
    "What is the weather in Chennai right now, and should I carry an umbrella tomorrow?",
    "Research the latest developments in solar energy and save a short summary as a note.",
    "Who was Srinivasa Ramanujan? How many years ago was he born?",
    "If I invest ₹50,000 at 8% annual interest compounded yearly, what will I have after 12 years?",
]


def get_api_key() -> str:
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY", "")


@st.cache_data(show_spinner=False, ttl=3600)
def available_models(api_key: str) -> list[str]:
    try:
        models = ResearchAgent(api_key).list_models()
        flash = [m for m in models if "flash" in m]
        return [DEFAULT_MODEL] + [m for m in flash if m != DEFAULT_MODEL] or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


def render_trace(trace: list[dict]):
    """Show the agent's reasoning and tool usage step by step."""
    for ev in trace:
        if ev["type"] == "thought":
            st.markdown(f"**🧠 Step {ev['step']} – Plan / reasoning:** {ev['text']}")
        elif ev["type"] == "tool_call":
            icon = TOOL_ICONS.get(ev["name"], "🛠️")
            st.markdown(f"**{icon} Step {ev['step']} – Calling `{ev['name']}`**")
            st.code(json.dumps(ev["args"], ensure_ascii=False, indent=2), language="json")
        elif ev["type"] == "tool_result":
            with st.expander(f"👀 Observation from `{ev['name']}`"):
                st.text(ev["result"][:3000])


# ------------------------------------------------------------------- Sidebar
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = get_api_key()
    if not api_key:
        api_key = st.text_input("Gemini API key", type="password",
                                help="Get a free key at https://aistudio.google.com/apikey")
    else:
        st.success("API key loaded from secrets/environment")

    model = st.selectbox("Model", available_models(api_key) if api_key else FALLBACK_MODELS)
    max_steps = st.slider("Max agent steps", 3, 15, 8,
                          help="Safety limit on how many reason→act cycles the agent may run.")

    if st.button("🗑️ New conversation", use_container_width=True):
        st.session_state.messages = []
        if "agent" in st.session_state:
            st.session_state.agent.reset()
        st.rerun()

    st.divider()
    st.subheader("🧰 Agent tools")
    for fn in TOOLS:
        first_line = (fn.__doc__ or "").strip().splitlines()[0]
        st.markdown(f"{TOOL_ICONS.get(fn.__name__, '🛠️')} **{fn.__name__}** – {first_line}")

    st.divider()
    st.subheader("🗂️ Saved notes (long-term memory)")
    if os.path.exists(NOTES_FILE):
        try:
            with open(NOTES_FILE, encoding="utf-8") as f:
                notes = json.load(f)
        except Exception:
            notes = []
        for n in reversed(notes[-10:]):
            with st.expander(f"{n['title']} ({n['saved_at']})"):
                st.write(n["content"])
        if not notes:
            st.caption("No notes yet.")
    else:
        st.caption("No notes yet. Ask the agent to save something!")

# ---------------------------------------------------------------------- Main
st.title("🤖 Agentic AI Research Assistant")
st.caption("An autonomous agent that **plans**, **chooses tools**, **observes results** and "
           "**reflects** until your goal is done. Powered by Google Gemini.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# (Re)create the agent if the key/model/step limit changes, keeping memory
if api_key:
    agent = st.session_state.get("agent")
    if agent is None or agent.model != model or agent.max_steps != max_steps \
            or st.session_state.get("agent_key") != api_key:
        new_agent = ResearchAgent(api_key, model=model, max_steps=max_steps)
        if agent is not None:
            new_agent.history = agent.history
        st.session_state.agent = new_agent
        st.session_state.agent_key = api_key

# Example goals
if not st.session_state.messages:
    st.markdown("#### Try a goal:")
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        if cols[i % 2].button(ex, key=f"ex{i}", use_container_width=True):
            st.session_state.pending = ex
            st.rerun()

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("trace"):
            with st.expander(f"🔍 Agent steps ({len([e for e in msg['trace'] if e['type'] == 'tool_call'])} tool calls)"):
                render_trace(msg["trace"])
        st.markdown(msg["content"])

prompt = st.chat_input("Give the agent a goal...") or st.session_state.pop("pending", None)

if prompt:
    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar first.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        trace, answer = [], ""
        with st.status("🤖 Agent is working...", expanded=True) as status:
            for ev in st.session_state.agent.run(prompt):
                if ev["type"] in ("thought", "tool_call", "tool_result"):
                    trace.append(ev)
                    render_trace([ev])
                    if ev["type"] == "tool_call":
                        status.update(label=f"🤖 Using {ev['name']}...")
                elif ev["type"] == "final":
                    answer = ev["text"]
                    status.update(label=f"✅ Done in {ev['steps']} step(s)", state="complete", expanded=False)
                elif ev["type"] == "error":
                    answer = f"⚠️ {ev['text']}"
                    status.update(label="⚠️ Agent stopped", state="error", expanded=False)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer, "trace": trace})
    st.rerun()
