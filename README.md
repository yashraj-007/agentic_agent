# Agentic AI Research Assistant

An **autonomous AI agent** built with **Google Gemini** and **Streamlit**.
Give it a goal in plain English: it **plans** the steps, **decides which tools to use** on its own,
**observes** the results, **reflects** and retries if needed, and finally returns a sourced answer.
It also has **short-term memory** (the conversation) and **long-term memory** (saved notes).

##  Features

| Agentic capability | How it is implemented |
|---|---|
| **Goal understanding & planning** | System prompt makes Gemini break each goal into steps and state a plan |
| **Autonomous tool selection** | Gemini *function calling*: the model chooses which tool(s) to call and with what arguments |
| **ReAct loop** (Reason → Act → Observe) | Hand-written loop in `agent.py`, repeats until the goal is complete |
| **Self-correction** | Tool errors are returned to the model, which retries with another tool or query |
| **Short-term memory** | Full conversation history is sent on every turn |
| **Long-term memory** | `save_note` / `read_notes` tools persist notes in `notes.json` |
| **Safety guard** | Max-step limit, safe calculator (no `eval`), request timeouts |
| **Transparency** | Every plan, tool call, arguments and observation is shown live in the UI |

###  Tools the agent can use

| Tool | Purpose | API used (all free, no key) |
|---|---|---|
| `web_search` | Search the internet for current info | DuckDuckGo (`ddgs`) |
| `read_webpage` | Read the text of a web page | `requests` + BeautifulSoup |
| `wikipedia_lookup` | Encyclopedia summary of a topic | Wikipedia REST API |
| `calculator` | Exact math (compound interest, etc.) | Safe AST evaluator |
| `get_weather` | Current weather + 3-day forecast | Open-Meteo |
| `get_current_datetime` | Today's date/time in any timezone | Python `zoneinfo` |
| `save_note` | Save information to long-term memory | Local JSON file |
| `read_notes` | Recall saved notes | Local JSON file |

---
