import os
import json
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
You are a planner for a voice assistant called OpenSight.
Given a user message, determine if it requires one or multiple steps to complete.

Available agents:
- SHOPPING: finding, comparing, or buying products on Amazon
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
"""

async def plan_intent(user_text: str) -> list:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{SYSTEM_PROMPT}\n\nUser message: {user_text}"
    )
    raw = re.sub(r"```json|```", "", response.text.strip()).strip()
    data = json.loads(raw)
    return data.get("steps", [])