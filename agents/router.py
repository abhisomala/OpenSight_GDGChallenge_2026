import os
import json
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-pro-latest",
]

SYSTEM_PROMPT = """
You are a planner for a voice assistant called OpenSight.
Given a user message, determine if it requires one or multiple steps to complete.

Available agents:
- SHOPPING: finding, comparing, buying, or searching for products on Amazon. Always preserve price constraints exactly as stated by the user (e.g. "under $800", "less than $500").
- CALENDAR: scheduling, booking, checking or creating Google Calendar events
- RESEARCH: finding academic papers or studies on a topic. Also use RESEARCH for any follow-up questions about papers that were previously mentioned, such as asking about authors, methodology, findings, or details of a specific paper.
- GENERAL: greetings, follow-up questions, definitions, opinions, math, weather, jokes, anything that doesn't require browsing Amazon, accessing a calendar, or finding academic papers. When in doubt use GENERAL.

Respond ONLY with a JSON object like this:

For a single step:
{
  "steps": [
    {"intent": "SHOPPING", "query": "good laptop under $500"}
  ]
}

For multiple steps:
{
  "steps": [
    {"intent": "RESEARCH", "query": "best laptops for machine learning"},
    {"intent": "SHOPPING", "query": "{{PREVIOUS_RESULT}}"}
  ]
}

Use "{{PREVIOUS_RESULT}}" as a placeholder when a step depends on the output of the previous step.
Always return valid JSON with a "steps" array. Never return anything else.
Keep all responses under 3 sentences. Be direct and concise.
"""


RESEARCH_FOLLOWUP_PATTERN = re.compile(
    r"\b(author|who wrote|who made|first paper|second paper|that paper|the paper|tell me more|methodology|findings|published|journal|when was)\b",
    re.IGNORECASE,
)


def _has_recent_research_context(history: list | None) -> bool:
    if not history:
        return False
    for turn in history[-3:]:
        assistant_text = str(turn.get("assistant", "")).lower()
        if any(phrase in assistant_text for phrase in [
            "research", "paper", "study", "journal", "published", "authors"
        ]):
            return True
    return False


async def generate_with_fallback(contents: str) -> str:
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents
            )
            return response.text.strip()
        except Exception as e:
            print(f"[gemini] {model} failed: {e}, trying next...")
    raise Exception("All Gemini models unavailable")


async def extract_preferences(query: str, memory) -> None:
    """Lightweight Gemini call that extracts budget/allergies/diet/topics
    from the current query and writes them into shared memory.
    Skips very short or purely navigational queries."""
    if len(query.split()) < 4:
        return

    prompt = (
        'Extract any user preferences or constraints from this query.\n'
        'Return JSON only — no explanation, no markdown:\n'
        '{"budget": null, "allergies": [], "diet": [], "topics": []}\n'
        'If nothing is found, return all nulls/empty arrays.\n'
        f'Query: {query}'
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        raw = re.sub(r"```json|```", "", response.text).strip()
        prefs = json.loads(raw)

        new_prefs: dict = {}
        if prefs.get("budget") is not None:
            new_prefs["budget"] = prefs["budget"]
        if prefs.get("allergies"):
            existing = memory.preferences.get("allergies", [])
            merged = list(set(existing + prefs["allergies"]))
            new_prefs["allergies"] = merged
        if prefs.get("diet"):
            diet = prefs["diet"]
            if isinstance(diet, str):
                diet = [diet]
            existing = memory.preferences.get("diet", [])
            new_prefs["diet"] = list(set(existing + diet))
        if new_prefs:
            memory.update_preferences(new_prefs)

        topics = prefs.get("topics") or []
        existing_topics = set(memory.entities.get("topics", []))
        for t in topics:
            if t and t not in existing_topics:
                memory.entities["topics"].append(t)
                existing_topics.add(t)

    except Exception as e:
        print(f"[router] preference extraction skipped: {e}")


async def plan_intent(user_text: str, history: list | None = None, memory=None) -> list:
    history = history or []

    # extract preferences on every query (uses lightest model, safe to await)
    if memory is not None:
        await extract_preferences(user_text, memory)

    # force RESEARCH for follow-up questions about papers
    if _has_recent_research_context(history) and RESEARCH_FOLLOWUP_PATTERN.search(user_text):
        # find the last research response to give context
        last_research = ""
        for turn in reversed(history):
            if any(phrase in turn.get("assistant", "").lower() for phrase in ["paper", "study", "research", "journal"]):
                last_research = turn.get("assistant", "")
                break
        enriched_query = f"{user_text} [context: {last_research}]" if last_research else user_text
        return [{"intent": "RESEARCH", "query": enriched_query}]

    history_text = ""
    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    # inject shared memory context so the router can handle cross-agent follow-ups
    memory_context = ""
    if memory is not None:
        ctx = memory.context_for_prompt()
        if ctx and ctx != "No prior context.":
            memory_context = f"\n\nSESSION CONTEXT (use this to understand follow-ups and user preferences):\n{ctx}"

    raw = re.sub(r"```json|```", "", await generate_with_fallback(
        f"{SYSTEM_PROMPT}{history_text}{memory_context}\n\nUser message: {user_text}"
    )).strip()

    if not raw:
        return [{"intent": "GENERAL", "query": user_text}]
    try:
        data = json.loads(raw)
        return data.get("steps", [{"intent": "GENERAL", "query": user_text}])
    except json.JSONDecodeError:
        return [{"intent": "GENERAL", "query": user_text}]