import os
import json
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
You are a router for a voice assistant called OpenSight.
Given a user message, classify it into exactly one of these categories...
...
Keep all responses under 3 sentences. Be direct and concise.
"""

async def plan_intent(user_text: str) -> list:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{SYSTEM_PROMPT}\n\nUser message: {user_text}"
    )
    raw = re.sub(r"```json|```", "", response.text.strip()).strip()
    if not raw:
        return [{"intent": "GENERAL", "query": user_text}]
    try:
        data = json.loads(raw)
        return data.get("steps", [{"intent": "GENERAL", "query": user_text}])
    except json.JSONDecodeError:
        return [{"intent": "GENERAL", "query": user_text}]