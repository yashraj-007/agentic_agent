"""
cli.py - Run the same agent from the terminal (no web UI).

Usage:
    export GEMINI_API_KEY="your-key"      (Windows: set GEMINI_API_KEY=your-key)
    python cli.py
"""

import os
import sys

from agent import ResearchAgent


def main():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("Set the GEMINI_API_KEY environment variable first.")
    agent = ResearchAgent(key)
    print("Agentic AI Research Assistant (type 'exit' to quit, 'reset' to clear memory)\n")
    while True:
        goal = input("You: ").strip()
        if goal.lower() in ("exit", "quit"):
            break
        if goal.lower() == "reset":
            agent.reset()
            print("Memory cleared.\n")
            continue
        if not goal:
            continue
        for ev in agent.run(goal):
            if ev["type"] == "thought":
                print(f"  [plan]   {ev['text']}")
            elif ev["type"] == "tool_call":
                print(f"  [action] {ev['name']}({ev['args']})")
            elif ev["type"] == "tool_result":
                print(f"  [result] {ev['result'][:200].replace(chr(10), ' ')}...")
            elif ev["type"] in ("final", "error"):
                print(f"\nAgent: {ev['text']}\n")


if __name__ == "__main__":
    main()
