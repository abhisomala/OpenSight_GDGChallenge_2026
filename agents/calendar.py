"""Read and create Google Calendar events from natural-language requests."""
import os
import asyncio
import datetime
import json
import re
import threading
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from playwright.sync_api import sync_playwright
from agents.router import generate_with_fallback
from dotenv import load_dotenv
import browser_manager

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/calendar']

# Configurable timezone — set USER_TIMEZONE in .env to override.
TZ = os.getenv("USER_TIMEZONE", "America/New_York")


def close_active_browser() -> None:
    """No-op stub kept for import compatibility with server.py.

    Calendar browser closing is now handled via browser_manager.register()
    inside _launch_calendar_browser, so browser_manager.close_all() covers it.
    """
    pass


def get_calendar_service():
    """Build an authenticated Google Calendar service client (synchronous)."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Google technology: Google Calendar API.
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)


def _launch_calendar_browser(holder: dict) -> None:
    """Open Google Calendar in a Playwright Chromium window, registered with browser_manager."""
    try:
        # Snapshot before launch so _find_chromium_hwnd can detect the new window.
        pre_launch = browser_manager.snapshot_chromium_hwnds()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=720,900",
                "--window-position=720,0",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            context = browser.new_context(viewport={"width": 720, "height": 900})
            page = context.new_page()

            def _close():
                holder["close"] = True

            browser_manager.register(_close)

            try:
                page.goto("https://calendar.google.com", wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            hwnd = browser_manager._find_chromium_hwnd(timeout=6.0, seen_before=pre_launch)
            if hwnd:
                browser_manager.set_browser_hwnd(hwnd)
                browser_manager.focus_browser()

            while not holder.get("close"):
                page.wait_for_timeout(500)
            browser.close()
    except Exception as e:
        print(f"[calendar] browser error: {e}")
    finally:
        holder["done"] = True


def _format_spoken_time(dt: datetime.datetime) -> str:
    """Format a datetime for natural speech — cross-platform, no leading zero."""
    return dt.strftime("%I:%M %p").lstrip("0")


async def run_calendar_agent(query: str, memory=None) -> str:
    """Parse a calendar request and create or list events."""

    mem_context_block = ""
    if memory is not None:
        ctx = memory.context_for_prompt()
        if ctx and ctx != "No prior context.":
            mem_context_block = (
                f"\n\nSESSION CONTEXT (use this to resolve references like "
                f"'it', 'that', 'the supplement'):\n{ctx}\n"
            )

    parse_prompt = f"""
Extract calendar event details from this request: "{query}"
Respond ONLY with valid JSON. No extra text, no markdown.
{mem_context_block}
If the user wants to CREATE or ADD or SCHEDULE an event, respond with:
{{"action": "create", "title": "event title here", "date": "YYYY-MM-DD", "time": "HH:MM", "duration_hours": 1}}

If the user wants to LIST, CHECK, or SEE their events, respond with:
{{"action": "list"}}

Today's date is: {datetime.date.today()}
Tomorrow is: {datetime.date.today() + datetime.timedelta(days=1)}
"""

    try:
        raw = re.sub(r"```json|```", "", await generate_with_fallback(parse_prompt)).strip()
        details = json.loads(raw)
    except Exception:
        print("[calendar] parse error")
        return "Sorry, I couldn't understand that calendar request. Try saying something like 'schedule a meeting tomorrow at 2pm'."

    holder: dict = {"close": False, "done": False}
    threading.Thread(target=_launch_calendar_browser, args=(holder,), daemon=True).start()

    loop = asyncio.get_running_loop()
    try:
        service = await loop.run_in_executor(None, get_calendar_service)
    except Exception:
        print("[calendar] service error")
        return "I couldn't connect to Google Calendar. Make sure you're authenticated."

    if details.get("action") == "create":
        try:
            date_str = details.get("date", str(datetime.date.today()))
            time_str = details.get("time", "09:00")
            title = details.get("title", "New Event")
            duration = details.get("duration_hours", 1)

            start_dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + datetime.timedelta(hours=duration)

            event_body = {
                'summary': title,
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': TZ},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': TZ},
            }

            await loop.run_in_executor(
                None,
                lambda: service.events().insert(calendarId='primary', body=event_body).execute(),
            )

            spoken_time = _format_spoken_time(start_dt)
            spoken_date = start_dt.strftime("%B %d")
            response = f"Done. {title} on {spoken_date} at {spoken_time}."
            if memory is not None:
                memory.set_result("calendar", response)
                memory.add_turn("assistant", response, agent="calendar")
            return response

        except Exception:
            print("[calendar] create error")
            return "I ran into an issue creating that event. Try again."

    else:
        try:
            now = datetime.datetime.utcnow().isoformat() + 'Z'

            events_result = await loop.run_in_executor(
                None,
                lambda: service.events().list(
                    calendarId='primary',
                    timeMin=now,
                    maxResults=5,
                    singleEvents=True,
                    orderBy='startTime',
                ).execute(),
            )
            events = events_result.get('items', [])

            if not events:
                response = "You have no upcoming events."
                if memory is not None:
                    memory.set_result("calendar", response)
                    memory.add_turn("assistant", response, agent="calendar")
                return response

            response = "Here are your next events. "
            for e in events:
                start = e['start'].get('dateTime', e['start'].get('date'))
                if 'T' in start:
                    dt = datetime.datetime.fromisoformat(start)
                    end = e['end'].get('dateTime', '')
                    end_dt = datetime.datetime.fromisoformat(end) if end and 'T' in end else None
                    formatted = f"{dt.strftime('%B %d')} at {_format_spoken_time(dt)}"
                    if end_dt:
                        formatted += f" to {_format_spoken_time(end_dt)}"
                else:
                    formatted = datetime.datetime.strptime(start, "%Y-%m-%d").strftime("%B %d")
                response += f"{e['summary']} on {formatted}. "

            if memory is not None:
                memory.set_result("calendar", response)
                memory.add_turn("assistant", response, agent="calendar")
            return response

        except Exception:
            print("[calendar] list error")
            return "I couldn't fetch your calendar events. Try again."