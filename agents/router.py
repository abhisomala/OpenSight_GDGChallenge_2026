"""Route user intent with Gemini and coordinate cross-agent handoffs."""
import os
import asyncio
import json
import re
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from dotenv import load_dotenv

load_dotenv()
# Disable the SDK's built-in retry. By default google-genai retries 429 with
# exponential backoff via tenacity, which causes a quota-blocked call to
# consume our full 15s timeout before we can fall through to the next model.
# attempts=1 means one attempt total, no retries — 429 surfaces in ~100ms.
_NO_RETRY_HTTP_OPTIONS = genai_types.HttpOptions(
    retry_options=genai_types.HttpRetryOptions(attempts=1),
)
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=_NO_RETRY_HTTP_OPTIONS,
)  # Google technology: Gemini API

# Primary model is read from GEMINI_MODEL env, defaulting to the current GA Flash.
# All fallback IDs are GA per ai.google.dev/gemini-api/docs/models — no preview aliases
# (e.g. gemini-flash-latest) and no retired 1.5/2.0 models.
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

_FALLBACK_CHAIN = [
    "gemini-3.5-flash",       # frontier GA Flash — agentic/coding optimized
    "gemini-3.1-flash-lite",  # frontier-class lite, lower cost, separate quota
    "gemini-2.5-flash",       # prior-gen Flash, separate quota bucket
    "gemini-2.5-flash-lite",  # prior-gen lite, cheapest GA
]

# Put PRIMARY_MODEL first, dedupe while preserving order so an override still
# benefits from the rest of the chain on quota errors.
MODELS = [PRIMARY_MODEL] + [m for m in _FALLBACK_CHAIN if m != PRIMARY_MODEL]

SYSTEM_PROMPT = """
You are a planner for a voice assistant called OpenSight.
Given a user message, determine if it requires one or multiple steps to complete.

Available agents:
- SHOPPING: finding, comparing, buying, or searching for products on Amazon. Only use SHOPPING when the user wants to buy or find a purchasable product. Never use SHOPPING for academic research queries. Always preserve price constraints exactly as stated by the user (e.g. "under $800", "less than $500").
- CALENDAR: scheduling, booking, checking or creating Google Calendar events
- RESEARCH: finding academic papers or studies on a topic. ALWAYS use RESEARCH if the word "research", "papers", "studies", or "articles" appears in the query — never route these to SHOPPING. Also use RESEARCH for any follow-up questions about papers that were previously mentioned, such as asking about authors, methodology, findings, or details of a specific paper.
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

# ── Follow-up pattern matchers ─────────────────────────────────────────────────

RESEARCH_FOLLOWUP_PATTERN = re.compile(
    r"\b(author|who wrote|who made|first paper|second paper|that paper|the paper|"
    r"tell me more|methodology|findings|published|journal|when was)\b",
    re.IGNORECASE,
)

# Matches open/select actions that include explicit paper/study/research words,
# used to let research followup win over shopping followup when both contexts active.
RESEARCH_EXPLICIT_PATTERN = re.compile(
    r"\b(paper|study|studies|research|journal|that research|the research|"
    r"first paper|second paper|that study|the study)\b",
    re.IGNORECASE,
)

SHOPPING_FOLLOWUP_PATTERN = re.compile(
    r"\b(open|click|buy|select|choose|pick|option|option\s*\d+|first|second|third|1st|2nd|3rd|"
    r"that one|this one|the first one|the second one|the third one|repeat|tell me more|more about)\b",
    re.IGNORECASE,
)

SHOPPING_INTENT_PATTERN = re.compile(
    r"\b(find|get|buy|order|search|look for|shop|show me|recommend|suggest|pick)\b.{0,30}"
    r"\b(on amazon|supplement|product|pill|capsule|tablet|powder|oil|cream|gear|device|gadget|book|item|something|one|result|option)\b"
    r"|\b(on amazon|under \$|less than \$|for under|buy me|order me)\b",
    re.IGNORECASE,
)

PRODUCT_CONTEXT_PATTERN = re.compile(
    r"\b(ingredient|ingredients|nutrition|calories|allergen|contain|made of|what.s in|"
    r"what is in|how much|serving|protein|carb|fat|sugar|sodium|fiber|review|rating|how many star)\b",
    re.IGNORECASE,
)

GENERAL_KNOWLEDGE_PATTERN = re.compile(
    r"^(what\b|how\b|why\b|who\b|when\b|where\b|which\b|"
    r"tell me (about|more|how)|"
    r"explain|describe|define)",
    re.IGNORECASE,
)

EXPLICIT_RESEARCH_TRIGGER = re.compile(
    r"\b(find.{0,10}research|find.{0,10}papers|find.{0,10}studies|"
    r"research on|papers on|studies on|articles on|look up.{0,10}research)\b",
    re.IGNORECASE,
)

PRONOUN_RESEARCH_PATTERN = re.compile(
    r'\b(find|search|look up|get)\b.{0,20}\b(research|papers|studies|articles)\b'
    r'.{0,20}\b(on\s+)?(that|it|this)\b',
    re.IGNORECASE,
)

# Exclude "where can I find/buy/get X" from knowledge question override
# Exclude "where can I find/buy/get X" from knowledge question override
_WHERE_SHOPPING_RE = re.compile(
    r'^where\b.{0,40}\b(find|buy|get|order|purchase|shop for)\b',
    re.IGNORECASE,
)

def _has_recent_research_context(history: list | None, memory=None) -> bool:
    """Check history AND memory for a recent research result."""
    if memory is not None and memory.entities.get("product_hint"):
        return True
    if not history:
        return False
    for turn in history[-3:]:
        assistant_text = str(turn.get("assistant", "")).lower()
        if any(phrase in assistant_text for phrase in [
            "research", "paper", "study", "journal", "published", "authors",
            "got two papers", "found one paper", "i found",
        ]):
            return True
    return False


def _has_recent_shopping_context(history: list | None, shopping_memory: dict | None = None) -> bool:
    """Check history AND shopping_memory for a recent Amazon result."""
    if shopping_memory and shopping_memory.get("last_results"):
        return True
    if not history:
        return False
    for turn in history[-3:]:
        assistant_text = str(turn.get("assistant", "")).lower()
        if any(phrase in assistant_text for phrase in [
            "option", "found", "amazon", "$", "which one", "opening",
            "i found", "two options", "three options", "got two", "got three",
            "for $", "at $", "going for",
        ]):
            return True
    return False


# ── Gemini helpers ─────────────────────────────────────────────────────────────

def _is_quota_error(exc: BaseException) -> bool:
    """True if exc is a 429 / RESOURCE_EXHAUSTED from Gemini, regardless of wrapping."""
    if isinstance(exc, genai_errors.ClientError):
        if getattr(exc, "code", None) == 429:
            return True
        if getattr(exc, "status", None) == "RESOURCE_EXHAUSTED":
            return True
    msg = str(exc)
    return "RESOURCE_EXHAUSTED" in msg or "429" in msg


async def generate_with_fallback(contents: str) -> str:
    """Generate text with Gemini via thread executor to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    for model in MODELS:
        try:
            # client.models.generate_content is synchronous — run in executor
            # so it doesn't stall the FastAPI event loop on every query.
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda m=model: client.models.generate_content(model=m, contents=contents),
                ),
                timeout=15.0,
            )
            return response.text.strip()
        except asyncio.TimeoutError:
            print(f"[gemini] {model} timed out after 15s, trying next...")
        except Exception as e:
            # Quota / rate-limit: skip to next model immediately, do not log noisily.
            if _is_quota_error(e):
                print(f"[gemini] {model} quota-blocked (429), trying next...")
                continue
            print(f"[gemini] {model} failed: {e}, trying next...")
    raise Exception("All Gemini models unavailable")


async def extract_preferences(query: str, memory) -> None:
    """Extract and store preferences from a user query."""
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
        raw = re.sub(r"```json|```", "", await generate_with_fallback(prompt)).strip()
        prefs = json.loads(raw)
        new_prefs: dict = {}
        if prefs.get("budget") is not None:
            new_prefs["budget"] = prefs["budget"]
        if prefs.get("allergies"):
            existing = memory.preferences.get("allergies", [])
            new_prefs["allergies"] = list(set(existing + prefs["allergies"]))
        if prefs.get("diet"):
            diet = prefs["diet"]
            if isinstance(diet, str):
                diet = [diet]
            existing = memory.preferences.get("diet", [])
            new_prefs["diet"] = list(set(existing + diet))
        if new_prefs:
            memory.update_preferences(new_prefs)
        topics = prefs.get("topics") or []
        # setdefault prevents KeyError if memory.entities was initialized without "topics"
        memory.entities.setdefault("topics", [])
        existing_topics = set(memory.entities["topics"])
        for t in topics:
            if t and t not in existing_topics:
                memory.entities["topics"].append(t)
                existing_topics.add(t)
    except Exception as e:
        print(f"[router] preference extraction skipped: {e}")


# ── Main planner ───────────────────────────────────────────────────────────────

async def plan_intent(
    user_text: str,
    history: list | None = None,
    memory=None,
    shopping_memory: dict | None = None,
) -> list:
    """Plan one or more agent steps for a user message."""
    history = history or []

    # ── product context question on an open Amazon page → GENERAL ──
    
    if PRODUCT_CONTEXT_PATTERN.search(user_text) and _has_recent_shopping_context(history, shopping_memory):
        last_product = ""
        if shopping_memory and shopping_memory.get("last_results"):
            last_product = shopping_memory["last_results"][0].get("title", "")
        enriched = f"{user_text} [context: user is looking at {last_product}]" if last_product else user_text
        return [{"intent": "GENERAL", "query": enriched}]

    # ── knowledge question override → GENERAL regardless of context ──
    # Runs BEFORE shopping checks so "what causes X" / "which Y" never
    # accidentally matches SHOPPING_FOLLOWUP_PATTERN (e.g. "first" in "in the first place")
    if (
        GENERAL_KNOWLEDGE_PATTERN.search(user_text)
        and not EXPLICIT_RESEARCH_TRIGGER.search(user_text)
        and not re.search(r'\b(research|papers|studies|articles|paper|study)\b', user_text, re.IGNORECASE)
        and not RESEARCH_FOLLOWUP_PATTERN.search(user_text)
        and not _WHERE_SHOPPING_RE.search(user_text)
    ):
        return [{"intent": "GENERAL", "query": user_text}]

    # ── research followup wins over shopping followup when research words are present ──
    if _has_recent_research_context(history, memory) and RESEARCH_FOLLOWUP_PATTERN.search(user_text):
        last_research = ""
        for turn in reversed(history):
            if any(phrase in turn.get("assistant", "").lower() for phrase in
                   ["paper", "study", "research", "journal"]):
                last_research = turn.get("assistant", "")
                break
        enriched_query = f"{user_text} [context: {last_research}]" if last_research else user_text
        return [{"intent": "RESEARCH", "query": enriched_query}]

    # ── shopping follow-up: skip if query contains explicit paper/research words ──
    if (
        _has_recent_shopping_context(history, shopping_memory)
        and SHOPPING_FOLLOWUP_PATTERN.search(user_text)
        and not RESEARCH_EXPLICIT_PATTERN.search(user_text)
    ):
        return [{"intent": "SHOPPING", "query": user_text}]

    # ── cross-agent: research → shopping handoff ──
    if _has_recent_research_context(history, memory) and SHOPPING_INTENT_PATTERN.search(user_text):
        product_hint = ""
        if memory is not None:
            product_hint = memory.entities.get("product_hint", "")

        if product_hint:
            price_match = re.search(
                r"(under \$[\d]+|less than \$[\d]+|below \$[\d]+|under [\d]+|for under \$[\d]+)",
                user_text, re.IGNORECASE
            )
            price_clause = f" {price_match.group(0)}" if price_match else ""
            enriched_query = f"{product_hint}{price_clause}"
            return [{"intent": "SHOPPING", "query": enriched_query}]
        else:
            return [{"intent": "SHOPPING", "query": user_text}]
    # ── GENERAL→RESEARCH pronoun resolution ──
    
  
    if PRONOUN_RESEARCH_PATTERN.search(user_text) and memory is not None:
        last_topic = memory.entities.get("last_general_topic", "")
        if last_topic:
            enriched_query = re.sub(
                r'\b(that|it|this)\b', last_topic, user_text, flags=re.IGNORECASE
            )
            return [{"intent": "RESEARCH", "query": enriched_query}]

    # ── general Gemini routing ──
    if memory is not None:
        await extract_preferences(user_text, memory)

    history_text = ""

    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

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

  