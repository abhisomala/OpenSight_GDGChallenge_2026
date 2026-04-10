import os
import datetime
import json
import re
import threading
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from agents.router import generate_with_fallback
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/calendar']

_active_browser: dict | None = None

def close_active_browser():
    global _active_browser
    if _active_browser:
        _active_browser["close"] = True
        _active_browser = None

def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)


def _open_calendar_browser(result_holder: dict) -> None:
    try:
        import subprocess
        subprocess.Popen([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--new-window",
            "--window-size=680,780",
            "--window-position=720,60",
            "https://calendar.google.com"
        ])
        # stay alive until agent switches
        while not result_holder.get("close"):
            import time
            time.sleep(0.5)
    except Exception as e:
        print(f"[calendar] browser error: {e}")


async def run_calendar_agent(query: str) -> str:
    global _active_browser

    parse_prompt = f"""
    Extract calendar event details from this request: "{query}"
    Respond ONLY with JSON:
    {{
      "action": "create" or "list",
      "title": "event title if creating",
      "date": "YYYY-MM-DD if creating",
      "time": "HH:MM if creating (24hr)",
      "duration_hours": 1
    }}
    Use today's date as reference: {datetime.date.today()}
    """
    raw = re.sub(r"```json|```", "", await generate_with_fallback(parse_prompt)).strip()
    details = json.loads(raw)

    service = get_calendar_service()

    # open Google Calendar browser in background
    result_holder = {"close": False}
    _active_browser = result_holder
    threading.Thread(
        target=_open_calendar_browser,
        args=(result_holder,),
        daemon=True,
    ).start()

    if details.get("action") == "create":
        start_dt = datetime.datetime.strptime(
            f"{details['date']} {details.get('time', '09:00')}", "%Y-%m-%d %H:%M"
        )
        end_dt = start_dt + datetime.timedelta(hours=details.get("duration_hours", 1))

        event = {
            'summary': details.get('title', 'New Event'),
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/New_York'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/New_York'},
        }
        service.events().insert(calendarId='primary', body=event).execute()
        return f"Done! Created '{details.get('title')}' on {details['date']} at {details.get('time', '9 AM')}."

    else:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now, maxResults=5,
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        if not events:
            return "You have no upcoming events."
        response = "Here are your next events. "
        for e in events:
            start = e['start'].get('dateTime', e['start'].get('date'))
            if 'T' in start:
                dt = datetime.datetime.fromisoformat(start)
                end = e['end'].get('dateTime', '')
                end_dt = datetime.datetime.fromisoformat(end) if end and 'T' in end else None
                formatted = dt.strftime("%B %d at %-I:%M %p")
                if end_dt:
                    formatted += end_dt.strftime(" to %-I:%M %p")
            else:
                formatted = datetime.datetime.strptime(start, "%Y-%m-%d").strftime("%B %d")
            response += f"{e['summary']} on {formatted}. "
        return response