"""Persist cross-agent session memory and preferences between turns."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionMemory:
    # Full conversation — every user + agent turn, tagged by agent
    history: list[dict] = field(default_factory=list)

    # Extracted long-term facts about the user (budget, allergies, diet …)
    preferences: dict = field(default_factory=dict)

    # What each agent last produced — readable by every other agent
    last_results: dict = field(default_factory=dict)

    # Entities pulled from conversation (reused across agents)
    entities: dict = field(default_factory=lambda: {
        "topics": [], "products": [], "dates": [], "people": [], "constraints": []
    })

    # Which agent just ran + what the user last asked
    last_agent: str = ""
    last_query: str = ""

    # ── writes ────────────────────────────────────────────────────────────────

    def add_turn(self, role: str, content: str, agent: str = "") -> None:
        """Append one turn (user or assistant) to history."""
        self.history.append({
            "role": role,        # "user" | "assistant"
            "content": content,
            "agent": agent,
            "timestamp": datetime.now().isoformat(),
        })
        # keep last 20 turns to avoid prompt bloat
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def set_result(self, agent: str, result: str) -> None:
        """Store what an agent produced so other agents can read it."""
        self.last_results[agent] = result[:500]   # cap to avoid prompt bloat
        self.last_agent = agent

    def update_preferences(self, new_prefs: dict) -> None:
        """Merge new preferences into the persistent preference dict."""
        self.preferences.update(new_prefs)

    # ── reads ─────────────────────────────────────────────────────────────────

    def context_for_prompt(self) -> str:
        """Return a compact string injected into every agent's system prompt."""
        lines: list[str] = []

        if self.preferences:
            lines.append(f"User preferences: {json.dumps(self.preferences)}")

        if self.entities.get("topics"):
            lines.append(f"Topics discussed: {', '.join(self.entities['topics'][-10:])}")

        if self.last_results:
            for agent, result in self.last_results.items():
                lines.append(f"What {agent} agent found: {result[:300]}")

        if self.last_agent:
            lines.append(f"Last agent used: {self.last_agent}")

        recent = [
            f"{t['role']} ({t.get('agent', '')}): {t['content']}"
            for t in self.history[-6:]
        ]
        if recent:
            lines.append("Recent conversation:\n" + "\n".join(recent))

        return "\n".join(lines) if lines else "No prior context."

    # ── persistence ───────────────────────────────────────────────────────────

    def save(self, path: str = "opensight_memory.json") -> None:
        """Persist memory to disk after every agent turn."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "history":      self.history,
                    "preferences":  self.preferences,
                    "last_results": self.last_results,
                    "entities":     self.entities,
                    "last_agent":   self.last_agent,
                    "last_query":   self.last_query,
                }, f, default=str, indent=2)
        except Exception as e:
                print("[memory] save error")

    @classmethod
    def load(cls, path: str = "opensight_memory.json") -> "SessionMemory":
        """Load persisted memory, or return a fresh instance if none exists."""
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # guarantee all entity keys exist even on old/partial saves
            entities = data.get("entities", {})
            for key in ("topics", "products", "dates", "people", "constraints"):
                entities.setdefault(key, [])
            return cls(
                history=data.get("history", []),
                preferences=data.get("preferences", {}),
                last_results=data.get("last_results", {}),
                entities=entities,
                last_agent=data.get("last_agent", ""),
                last_query=data.get("last_query", ""),
            )
        except Exception as e:
            print("[memory] load error — starting fresh")
            return cls()
