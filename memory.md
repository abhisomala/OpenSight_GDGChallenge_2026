# OpenSight — Shared Conversational Memory

## The Problem
Each agent currently lives in isolation. The shopping agent doesn't know what the research agent found. The router doesn't remember you're allergic to peanuts. Every query starts from zero.

## The Fix: One Shared `SessionMemory` Object

A single `memory.py` module that every agent reads from and writes to. The server owns one instance per user session and passes it into every agent call.

---

## What Gets Stored

```python
@dataclass
class SessionMemory:
    # Full conversation — every user + agent turn, tagged by agent
    history: list[dict]          # [{ role, content, agent, timestamp }]

    # Extracted long-term facts about the user
    preferences: dict            # { "allergies": ["peanuts"], "budget": 15, "diet": "gluten-free" }

    # What each agent last produced — readable by all other agents
    last_results: dict           # { "shopping": "...", "research": "...", "calendar": "..." }

    # Entities pulled from conversation (reused across agents)
    entities: dict               # { "topics": [], "products": [], "dates": [], "people": [] }

    # Which agent just ran — so router has context for follow-ups
    last_agent: str
    last_query: str
```

---

## How It Flows

```
User: "Find research on sleep and melatonin"
  → Research agent runs, stores result in memory.last_results["research"]
  → memory.entities["topics"] = ["sleep", "melatonin"]

User: "Now find me a melatonin supplement under $20"
  → Router sees last_agent = "research", entities has "melatonin"
  → Shopping agent gets full context — knows the topic, the budget, why they're asking
  → Shopping agent stores result in memory.last_results["shopping"]

User: "Schedule a reminder to take it tonight at 9"
  → Calendar agent reads last_results["shopping"] to know WHAT to remind about
  → Creates event: "Take melatonin supplement — from OpenSight"
```

---

## Files to Create/Change

| File | Action | What |
|---|---|---|
| `memory.py` | **CREATE** | `SessionMemory` dataclass + helper methods |
| `server.py` | **EDIT** | Create one `SessionMemory` per session, pass to all agents |
| `agents/router.py` | **EDIT** | Inject memory into Gemini prompt as context |
| `agents/shopping.py` | **EDIT** | Read preferences/entities, write last_results["shopping"] |
| `agents/research.py` | **EDIT** | Write last_results["research"] + entities["topics"] |
| `agents/calendar.py` | **EDIT** | Read last_results from other agents to fill event details |
| `agents/general.py` | **EDIT** | Read + write, extract entities from response |

---

## memory.py — Full Spec

```python
from dataclasses import dataclass, field
from datetime import datetime
import json

@dataclass
class SessionMemory:
    history: list[dict] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)
    last_results: dict = field(default_factory=dict)
    entities: dict = field(default_factory=lambda: {
        "topics": [], "products": [], "dates": [], "people": [], "constraints": []
    })
    last_agent: str = ""
    last_query: str = ""

    def add_turn(self, role: str, content: str, agent: str = ""):
        self.history.append({
            "role": role,        # "user" | "assistant"
            "content": content,
            "agent": agent,
            "timestamp": datetime.now().isoformat()
        })
        # Keep last 20 turns max to avoid prompt bloat
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def set_result(self, agent: str, result: str):
        self.last_results[agent] = result
        self.last_agent = agent

    def update_preferences(self, new_prefs: dict):
        self.preferences.update(new_prefs)

    def context_for_prompt(self) -> str:
        """Returns a compact string injected into every agent's system prompt."""
        lines = []
        if self.preferences:
            lines.append(f"User preferences: {json.dumps(self.preferences)}")
        if self.entities["topics"]:
            lines.append(f"Topics discussed: {', '.join(self.entities['topics'])}")
        if self.last_results:
            for agent, result in self.last_results.items():
                lines.append(f"What {agent} agent found: {result[:300]}")
        if self.last_agent:
            lines.append(f"Last agent used: {self.last_agent}")
        recent = [f"{t['role']} ({t['agent']}): {t['content']}" 
                  for t in self.history[-6:]]
        if recent:
            lines.append("Recent conversation:\n" + "\n".join(recent))
        return "\n".join(lines) if lines else "No prior context."
```

---

## How Each Agent Uses It

Every agent's `execute(query, memory)` signature gains a `memory` parameter:

```python
# In each agent — read context at the top
context = memory.context_for_prompt()
# Inject into system prompt:
system_prompt = f"""You are the [X] agent.

CONVERSATION CONTEXT:
{context}

Answer the user's query using this context where relevant.
"""

# At the bottom — write results back
memory.set_result("shopping", final_summary)
memory.add_turn("assistant", final_summary, agent="shopping")

# Extract and store any new preferences found in the query
# (have Gemini do this as a side call, or do it with simple regex)
if "under $" in query:
    budget = extract_budget(query)
    memory.update_preferences({"budget": budget})
if "peanut" in query or "allerg" in query:
    memory.update_preferences({"allergies": extract_allergies(query)})
```

---

## Preference Extraction (Automatic)

Add a lightweight extraction call in `router.py` before routing. One small Gemini call:

```python
def extract_preferences(query: str, memory: SessionMemory):
    prompt = f"""
Extract any user preferences or constraints from this query.
Return JSON only: {{"budget": null, "allergies": [], "diet": [], "topics": []}}
If nothing found, return all nulls/empty.
Query: {query}
"""
    result = gemini_call(prompt)  # reuse existing model
    prefs = json.loads(result)
    if prefs.get("budget"):
        memory.update_preferences({"budget": prefs["budget"]})
    if prefs.get("allergies"):
        existing = memory.preferences.get("allergies", [])
        memory.update_preferences({"allergies": list(set(existing + prefs["allergies"]))})
    # etc.
```

This runs on every query, so preferences accumulate automatically over the session.

---

## Session Persistence (Optional but Good)

Save memory to disk between app restarts so preferences survive:

```python
# In memory.py
def save(self, path="opensight_memory.json"):
    with open(path, "w") as f:
        json.dump(self.__dict__, f, default=str)

@classmethod
def load(cls, path="opensight_memory.json") -> "SessionMemory":
    if not os.path.exists(path):
        return cls()
    with open(path) as f:
        data = json.load(f)
    return cls(**data)
```

Load on startup in `server.py`, save after every agent turn.

---

## The Demo Moment This Unlocks

> "Find research on melatonin and sleep"
> *[Research agent finds 3 papers, stores in memory]*

> "Now buy me a melatonin supplement, something the research would support"
> *[Shopping agent reads research result, searches for evidence-backed dosage, finds product]*

> "Schedule a reminder to take it tonight at 10pm"
> *[Calendar agent reads product name from shopping result, creates: "Take Natrol Melatonin 5mg — OpenSight"]*

**Three agents. One continuous conversation. No repetition from the user.**
This is the 30-second demo clip that wins competitions.
