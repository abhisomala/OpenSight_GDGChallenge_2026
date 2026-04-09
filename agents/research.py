import os
from serpapi import GoogleSearch
from google import genai as genai2
from dotenv import load_dotenv

load_dotenv()

async def run_research_agent(query: str) -> str:
    params = {
        "engine": "google_scholar",
        "q": query,
        "api_key": os.getenv("SERPAPI_KEY"),
        "num": 5
    }

    search = GoogleSearch(params)
    results = search.get_dict()
    papers = results.get("organic_results", [])

    if not papers:
        return f"I couldn't find academic papers on {query}. Try being more specific."

    context = "\n\n".join([
        f"Title: {p.get('title')}\nSummary: {p.get('snippet', 'No summary available')}"
        for p in papers[:5]
    ])

    client = genai2.Client(api_key=os.getenv("GEMINI_API_KEY"))
    summary_prompt = f"""
    A user asked: "{query}"
    Here are academic papers found on this topic:
    {context}

    Give a clear, spoken-friendly 3-4 sentence summary mentioning 2-3 specific papers by name.
    Keep it conversational — it will be read aloud.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=summary_prompt
    )
    return response.text.strip()