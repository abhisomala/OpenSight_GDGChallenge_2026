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
        import time
        proc = subprocess.Popen([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--new-window",
            "--window-size=720,900",
            "--window-position=720,0",
            "https://calendar.google.com"
        ])
        while not result_holder.get("close"):
            time.sleep(0.5)
        proc.terminate()
    except Exception as e:
        print(f"[calendar] browser error: {e}")


async def run_calendar_agent(query: str) -> str:
    global _active_browser

    parse_prompt = f"""
Extract calendar event details from this request: "{query}"
Respond ONLY with valid JSON. No extra text, no markdown.

If the user wants to CREATE or ADD or SCHEDULE an event, respond with:
{{"action": "create", "title": "event title here", "date": "YYYY-MM-DD", "time": "HH:MM", "duration_hours": 1}}

If the user wants to LIST, CHECK, or SEE their events, respond with:
{{"action": "list"}}

Today's date is: {datetime.date.today()}
Tomorrow is: {datetime.date.today() + datetime.timedelta(days=1)}
"""

    try:
        raw = re.sub(r"```json|```", "", await generate_with_fallback(parse_prompt)).strip()
        print(f"[calendar] parsed: {raw}")
        details = json.loads(raw)
    except Exception as e:
        print(f"[calendar] parse error: {e}")
        return "Sorry, I couldn't understand that calendar request. Try saying something like 'schedule a meeting tomorrow at 2pm'."

    # open browser
    result_holder = {"close": False}
    _active_browser = result_holder
    threading.Thread(target=_open_calendar_browser, args=(result_holder,), daemon=True).start()

    try:
        service = get_calendar_service()
    except Exception as e:
        print(f"[calendar] service error: {e}")
        return "I couldn't connect to Google Calendar. Make sure you're authenticated."

    if details.get("action") == "create":
        try:
            date_str = details.get("date", str(datetime.date.today()))
            time_str = details.get("time", "09:00")
            title = details.get("title", "New Event")
            duration = details.get("duration_hours", 1)

            start_dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + datetime.timedelta(hours=duration)

            event = {
                'summary': title,
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/New_York'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/New_York'},
            }
            service.events().insert(calendarId='primary', body=event).execute()

            # format time nicely for speech
            spoken_time = start_dt.strftime("%-I:%M %p")
            spoken_date = start_dt.strftime("%B %d")
            return f"Done. {title} on {spoken_date} at {spoken_time}."

        except Exception as e:
            print(f"[calendar] create error: {e}")
            return "I ran into an issue creating that event. Try again."

    else:
        try:
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

        except Exception as e:
            print(f"[calendar] list error: {e}")
            return "I couldn't fetch your calendar events. Try again."