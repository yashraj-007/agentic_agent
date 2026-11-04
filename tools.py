"""
tools.py - The "hands" of the agent.

Each function below is a TOOL the agent can decide to call on its own.
Gemini reads each function's name, type hints and docstring to understand
what the tool does and when to use it, so the docstrings matter.
"""

import ast
import json
import math
import operator
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AgenticResearchAssistant/1.0 (student project)"}
NOTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.json")
TIMEOUT = 15


# ---------------------------------------------------------------- 1. Web search
def web_search(query: str, max_results: int = 5) -> str:
    """Search the internet for up-to-date information on any topic.

    Use this for current events, recent facts, news, or anything you are not sure about.

    Args:
        query: The search query, e.g. "latest Mars rover discoveries".
        max_results: How many results to return (1-10).
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:  # older package name
            from duckduckgo_search import DDGS
        max_results = max(1, min(int(max_results), 10))
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title')}\n   URL: {r.get('href')}\n   {r.get('body')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


# ------------------------------------------------------------- 2. Read a webpage
def read_webpage(url: str) -> str:
    """Open a web page and return its main text (first ~4000 characters).

    Use this after web_search when you need more detail than the search snippet.

    Args:
        url: Full URL starting with http:// or https://
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:4000] if text else "Page had no readable text."
    except Exception as e:
        return f"Could not read page: {e}"


# ------------------------------------------------------------------ 3. Wikipedia
def wikipedia_lookup(topic: str) -> str:
    """Get a short, reliable encyclopedia summary of a topic from Wikipedia.

    Use this for definitions, background, history, people, places and concepts.

    Args:
        topic: The subject to look up, e.g. "Alan Turing" or "Photosynthesis".
    """
    try:
        search = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": topic, "limit": 1, "format": "json"},
            headers=HEADERS,
            timeout=TIMEOUT,
        ).json()
        if not search[1]:
            return f"No Wikipedia article found for '{topic}'."
        title = search[1][0]
        summary = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(title),
            headers=HEADERS,
            timeout=TIMEOUT,
        ).json()
        url = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
        return f"{summary.get('title', title)}: {summary.get('extract', 'No summary.')}\nSource: {url}"
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"


# ------------------------------------------------------------------ 4. Calculator
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {name: getattr(math, name) for name in (
    "sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "floor", "ceil",
    "factorial", "radians", "degrees", "asin", "acos", "atan")}
_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})
_CONSTS = {"pi": math.pi, "e": math.e}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("Exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_safe_eval(a) for a in node.args])
    raise ValueError("Unsupported expression")


def calculator(expression: str) -> str:
    """Evaluate a math expression exactly. Always use this instead of doing math in your head.

    Supports + - * / // % **, parentheses, pi, e and functions like sqrt, log, sin, cos,
    factorial, round, abs, min, max.

    Args:
        expression: e.g. "(25 * 4) + sqrt(144)" or "1500 * (1 + 0.07) ** 10"
    """
    try:
        result = _safe_eval(ast.parse(expression.replace("^", "**"), mode="eval"))
        return f"{expression} = {result}"
    except Exception as e:
        return f"Could not calculate '{expression}': {e}"


# --------------------------------------------------------------------- 5. Weather
def get_weather(city: str) -> str:
    """Get the current weather and a 3-day forecast for a city.

    Args:
        city: City name, e.g. "Chennai" or "London".
    """
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1}, headers=HEADERS, timeout=TIMEOUT,
        ).json()
        if not geo.get("results"):
            return f"City '{city}' not found."
        place = geo["results"][0]
        wx = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"], "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 3, "timezone": "auto",
            },
            headers=HEADERS, timeout=TIMEOUT,
        ).json()
        cur, daily = wx["current"], wx["daily"]
        out = [
            f"Weather in {place['name']}, {place.get('country', '')}:",
            f"Now: {cur['temperature_2m']}°C, humidity {cur['relative_humidity_2m']}%, "
            f"wind {cur['wind_speed_10m']} km/h",
        ]
        for d, hi, lo, rain in zip(daily["time"], daily["temperature_2m_max"],
                                   daily["temperature_2m_min"], daily["precipitation_probability_max"]):
            out.append(f"{d}: {lo}°C - {hi}°C, rain chance {rain}%")
        return "\n".join(out)
    except Exception as e:
        return f"Weather lookup failed: {e}"


# ------------------------------------------------------------------ 6. Date/time
def get_current_datetime(timezone: str = "Asia/Kolkata") -> str:
    """Get the current date and time. Use this whenever the answer depends on today's date.

    Args:
        timezone: IANA timezone name, e.g. "Asia/Kolkata", "UTC", "America/New_York".
    """
    try:
        now = datetime.now(ZoneInfo(timezone))
    except Exception:
        now, timezone = datetime.now(ZoneInfo("UTC")), "UTC"
    return now.strftime(f"%A, %d %B %Y, %I:%M %p ({timezone})")


# ------------------------------------------------------------- 7 & 8. Memory/notes
def _load_notes() -> list:
    if not os.path.exists(NOTES_FILE):
        return []
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_note(title: str, content: str) -> str:
    """Save a note to long-term memory so it can be recalled later, even in a new chat.

    Use this when the user asks you to remember, save or note something,
    or to store the final result of a research task.

    Args:
        title: Short title for the note.
        content: The text to save.
    """
    notes = _load_notes()
    notes.append({"title": title, "content": content,
                  "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)
    return f"Saved note '{title}'. Total notes: {len(notes)}."


def read_notes(keyword: str = "") -> str:
    """Read notes saved earlier in long-term memory, optionally filtered by a keyword.

    Args:
        keyword: Optional word to filter notes by (leave empty to list all).
    """
    notes = _load_notes()
    if keyword:
        k = keyword.lower()
        notes = [n for n in notes if k in n["title"].lower() or k in n["content"].lower()]
    if not notes:
        return "No saved notes found."
    return "\n\n".join(f"[{n['saved_at']}] {n['title']}\n{n['content']}" for n in notes)


# Registry: everything the agent is allowed to use
TOOLS = [web_search, read_webpage, wikipedia_lookup, calculator,
         get_weather, get_current_datetime, save_note, read_notes]
TOOL_MAP = {fn.__name__: fn for fn in TOOLS}

TOOL_ICONS = {
    "web_search": "🔎", "read_webpage": "🌐", "wikipedia_lookup": "📚", "calculator": "🧮",
    "get_weather": "🌦️", "get_current_datetime": "🕒", "save_note": "💾", "read_notes": "🗂️",
}
