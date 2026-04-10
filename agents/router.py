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
- RESEARCH: finding academic papers or studies on a topic
- GENERAL: anything else, answer conversationally

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


def _looks_like_shopping_followup(user_text: str, history: list, shopping_memory: dict | None) -> bool:
    text = (user_text or "").strip().lower()
    if not text:
        return False

    has_recent_options = bool((shopping_memory or {}).get("last_results"))
    if not has_recent_options:
        # Fallback: detect recent option-style assistant response.
        for turn in (history or []):
            assistant = (turn.get("assistant") or "").lower()
            if "option 1:" in assistant:
                has_recent_options = True
                break

    if not has_recent_options:
        return False

    followup_markers = [
        r"\boption\s*\d+\b",
        r"\b(first|second|third|1st|2nd|3rd)\b",
        r"\b(click|open|buy|select|choose)\b",
        r"\b(that one|this one|the first one|the second one|the third one)\b",
        r"\btell me more\b",
        r"\bmore about\b",
    ]
    return any(re.search(pattern, text) for pattern in followup_markers)


async def plan_intent(user_text: str, history: list | None = None, shopping_memory: dict | None = None) -> list:
    # Deterministic override for short follow-ups like "option 2".
    if _looks_like_shopping_followup(user_text, history or [], shopping_memory):
        return [{"intent": "SHOPPING", "query": user_text}]

    history_text = ""
    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    raw = re.sub(r"```json|```", "", await generate_with_fallback(
        f"{SYSTEM_PROMPT}{history_text}\n\nUser message: {user_text}"
    )).strip()

    if not raw:
        return [{"intent": "GENERAL", "query": user_text}]
    try:
        data = json.loads(raw)
        return data.get("steps", [{"intent": "GENERAL", "query": user_text}])
    except json.JSONDecodeError:
        return [{"intent": "GENERAL", "query": user_text}]