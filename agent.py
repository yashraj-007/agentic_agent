"""
agent.py - The "brain" of the agent.

Implements a ReAct-style agent loop (Reason -> Act -> Observe -> repeat):

  1. The user's goal + conversation memory go to Gemini with the list of tools.
  2. Gemini REASONS and either:
       a) asks to call one or more tools  -> we ACT (run them) and send back the
          OBSERVATION (result), then loop again, or
       b) returns a final answer          -> the loop stops.
  3. A step limit stops runaway loops.

The loop is written by hand (automatic function calling is turned off) so every
step can be shown to the user in the UI.
"""

from typing import Generator

from google import genai
from google.genai import types

from tools import TOOL_MAP, TOOLS

SYSTEM_PROMPT = """You are an autonomous AI Research Agent.

Your job is to fully complete the user's goal by planning and using tools on your own.

How you work:
1. PLAN: Break the goal into small steps. Briefly state your plan in 1-3 short lines.
2. ACT: Call the right tool(s) for each step. You may call several tools in a row.
   - Use web_search / read_webpage for current or uncertain facts.
   - Use wikipedia_lookup for background and definitions.
   - Use calculator for ANY arithmetic. Never do math in your head.
   - Use get_current_datetime when the answer depends on today's date.
   - Use get_weather for weather questions.
   - Use save_note when the user asks you to remember/save something; use read_notes to recall.
3. OBSERVE & REFLECT: Check each tool result. If it failed or is not enough, try another
   tool or a different query instead of giving up.
4. ANSWER: When you have enough information, give a clear, well-structured final answer
   in Markdown. List the source URLs you used at the end under "Sources".

Rules: Do not make up facts or URLs. If something cannot be found, say so honestly.
Keep answers concise and useful."""

DEFAULT_MODEL = "gemini-flash-latest"


class ResearchAgent:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, max_steps: int = 8):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_steps = max_steps
        self.history: list[types.Content] = []   # short-term (conversation) memory

        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=TOOLS,
            temperature=0.3,
            # We run the tool loop ourselves so each step is visible.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def list_models(self) -> list[str]:
        """Return Gemini model names that support text generation (for the UI dropdown)."""
        names = []
        for m in self.client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if "generateContent" in actions and "gemini" in m.name:
                names.append(m.name.replace("models/", ""))
        return sorted(names)

    def reset(self):
        self.history = []

    @staticmethod
    def _run_tool(name: str, args: dict) -> str:
        fn = TOOL_MAP.get(name)
        if fn is None:
            return f"Error: unknown tool '{name}'."
        try:
            if "max_results" in args:                 # Gemini may send numbers as floats
                args["max_results"] = int(args["max_results"])
            return str(fn(**args))
        except Exception as e:
            return f"Error while running {name}: {e}"

    def run(self, user_goal: str) -> Generator[dict, None, None]:
        """Run the agent on a goal. Yields events so the UI can show each step live.

        Event types: "thought", "tool_call", "tool_result", "final", "error".
        """
        start_len = len(self.history)                   # to roll back on failure
        self.history.append(types.Content(role="user", parts=[types.Part(text=user_goal)]))

        for step in range(1, self.max_steps + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=self.history, config=self.config
                )
            except Exception as e:
                del self.history[start_len:]
                yield {"type": "error", "text": f"Gemini API error: {e}"}
                return

            if not response.candidates or not response.candidates[0].content:
                del self.history[start_len:]
                yield {"type": "error", "text": "The model returned an empty response. Try rephrasing."}
                return

            model_content = response.candidates[0].content
            self.history.append(model_content)          # keep full content (incl. thought signatures)

            parts = model_content.parts or []
            text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
            calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

            if not calls:                               # no more tools needed -> final answer
                yield {"type": "final", "text": text or "(No answer returned.)", "steps": step}
                return

            if text.strip():                            # the agent's plan / reasoning
                yield {"type": "thought", "text": text.strip(), "step": step}

            response_parts = []
            for call in calls:
                args = dict(call.args or {})
                yield {"type": "tool_call", "name": call.name, "args": args, "step": step}
                result = self._run_tool(call.name, args)
                yield {"type": "tool_result", "name": call.name, "result": result, "step": step}
                response_parts.append(
                    types.Part.from_function_response(name=call.name, response={"result": result})
                )

            # Send observations back to the model for the next reasoning step
            self.history.append(types.Content(role="user", parts=response_parts))

        del self.history[start_len:]
        yield {"type": "error",
               "text": f"Stopped after {self.max_steps} steps without a final answer. "
                       "Try a more specific goal or raise the step limit."}
