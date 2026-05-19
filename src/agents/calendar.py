import json
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

import dateparser
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import BaseAgent
from ..config import settings
from ..memory.profile import ProfileManager

UTC = tz.utc

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar",
]

TOKEN_DIR = Path(settings.data_dir) / "cal_tokens"

_device_flows: dict[str, dict] = {}


def _request_device_code() -> dict:
    data = json.dumps(
        {
            "client_id": settings.google_client_id,
            "scope": " ".join(SCOPES),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/device/code",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"Google device code error {e.code}: {body}"
        )


def _poll_for_token(device_code: str, user_id: str, interval: int, timeout: int = 300):
    data = json.dumps(
        {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
    ).encode("utf-8")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(interval)
        try:
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read())
            creds = Credentials(
                token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=SCOPES,
            )
            tp = TOKEN_DIR / f"{user_id}.json"
            tp.parent.mkdir(parents=True, exist_ok=True)
            with open(tp, "w") as f:
                json.dump(json.loads(creds.to_json()), f)
            print(f"[Calendar] Token saved for user {user_id}")
            _device_flows.pop(device_code, None)
            return
        except urllib.error.HTTPError as e:
            if e.code == 400:
                body = json.loads(e.read())
                err = body.get("error", "")
                if err == "slow_down":
                    interval += 5
                elif err in ("access_denied", "expired_token"):
                    _device_flows.pop(device_code, None)
                    return
            else:
                body = e.read().decode("utf-8", errors="ignore")
                print(f"[Calendar] Token poll error {e.code}: {body}")
                _device_flows.pop(device_code, None)
                return
        except Exception as e:
            print(f"[Calendar] Token poll unexpected error: {e}")
            _device_flows.pop(device_code, None)
            return
    _device_flows.pop(device_code, None)


class CalendarAgent(BaseAgent):
    name = "calendar"
    description = (
        "Google Calendar integration. List today's events, week events, "
        "or create new events. Calls with list_today, list_week, list, create."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        self._token_path = TOKEN_DIR / f"{user_id}.json"

    def _is_authed(self) -> bool:
        if not self._token_path.exists():
            return False
        try:
            return self._get_creds() is not None
        except Exception:
            return False

    def _get_creds(self):
        if not self._token_path.exists():
            return None
        with open(self._token_path) as f:
            creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._save_creds(creds)
                except Exception:
                    return None
            else:
                return None
        return creds

    def _save_creds(self, creds: Credentials):
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._token_path, "w") as f:
            json.dump(json.loads(creds.to_json()), f)

    def _get_service(self):
        creds = self._get_creds()
        if creds is None:
            return None
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @staticmethod
    def start_auth(user_id: str) -> str:
        if not settings.google_client_id or not settings.google_client_secret:
            raise RuntimeError(
                "GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nao configurados no .env"
            )
        try:
            device_info = _request_device_code()
        except Exception as e:
            raise RuntimeError(f"Erro ao contactar Google: {e}")

        device_code = device_info["device_code"]
        user_code = device_info["user_code"]
        verification_url = device_info.get(
            "verification_url", "https://www.google.com/device"
        )
        interval = device_info.get("interval", 5)

        _device_flows[device_code] = {"user_id": user_id}

        t = threading.Thread(
            target=_poll_for_token,
            args=(device_code, user_id, interval),
            daemon=True,
        )
        t.start()

        return (
            "Passo 1: Abre este link no teu browser:\n"
            f"{verification_url}\n\n"
            f"Passo 2: Insere este codigo:\n"
            f"{user_code}\n\n"
            "Depois de autorizares, o calendario fica ligado automaticamente."
        )

    @staticmethod
    def _persist_creds(user_id: str, creds: Credentials):
        tp = TOKEN_DIR / f"{user_id}.json"
        tp.parent.mkdir(parents=True, exist_ok=True)
        with open(tp, "w") as f:
            json.dump(json.loads(creds.to_json()), f)

    @staticmethod
    def is_connected(user_id: str) -> bool:
        return CalendarAgent(user_id)._is_authed()

    @staticmethod
    def disconnect(user_id: str):
        tp = TOKEN_DIR / f"{user_id}.json"
        if tp.exists():
            tp.unlink()

    @classmethod
    def get_events_for_range(
        cls, user_id: str, start: datetime, end: datetime
    ) -> list[dict]:
        agent = cls(user_id)
        svc = agent._get_service()
        if not svc:
            return []
        try:
            result = (
                svc.events()
                .list(
                    calendarId="primary",
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = []
            for event in result.get("items", []):
                start_info = event["start"].get(
                    "dateTime", event["start"].get("date", "")
                )
                end_info = event["end"].get("dateTime", event["end"].get("date", ""))
                events.append(
                    {
                        "id": event.get("id"),
                        "summary": event.get("summary", ""),
                        "start": start_info,
                        "end": end_info,
                        "description": event.get("description", ""),
                    }
                )
            return events
        except Exception:
            return []

    async def execute(self, action: str, params: dict) -> dict:
        fn = getattr(self, f"_handle_{action}", None)
        if fn is None:
            return {"error": f"Unknown action: {action}"}
        return fn(params)

    def _handle_list_today(self, p: dict) -> dict:
        svc = self._get_service()
        if not svc:
            return {
                "error": "Google Calendar nao conectado. Usa /cal_auth para conectar."
            }
        now = datetime.now(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._fetch_events(svc, start, end)

    def _handle_list_week(self, p: dict) -> dict:
        svc = self._get_service()
        if not svc:
            return {
                "error": "Google Calendar nao conectado. Usa /cal_auth para conectar."
            }
        now = datetime.now(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return self._fetch_events(svc, start, end)

    def _handle_list(self, p: dict) -> dict:
        return self._handle_list_week(p)

    def _handle_create(self, p: dict) -> dict:
        svc = self._get_service()
        if not svc:
            return {
                "error": "Google Calendar nao conectado. Usa /cal_auth para conectar."
            }
        summary = p.get("summary", "")
        start_str = p.get("start", "")
        end_str = p.get("end", "")
        description = p.get("description", "")
        if not summary or not start_str:
            return {"error": "summary e start sao obrigatorios"}

        profile = ProfileManager(self.user_id).get()
        user_tz = profile.timezone or "UTC"

        settings_dp = {"PREFER_DATES_FROM": "future", "TIMEZONE": user_tz}
        start_dt = dateparser.parse(start_str, settings=settings_dp)
        end_dt = dateparser.parse(end_str, settings=settings_dp) if end_str else None

        if start_dt is None:
            return {"error": f"Nao consegui interpretar a data: {start_str}"}

        event = {
            "summary": summary,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": user_tz,
            },
            "end": {
                "dateTime": end_dt.isoformat()
                if end_dt
                else (start_dt + timedelta(hours=1)).isoformat(),
                "timeZone": user_tz,
            },
        }
        if description:
            event["description"] = description

        try:
            created = svc.events().insert(calendarId="primary", body=event).execute()
            return {"status": "created", "id": created.get("id"), "summary": summary}
        except HttpError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}

    def _fetch_events(self, svc, start: datetime, end: datetime) -> dict:
        try:
            result = (
                svc.events()
                .list(
                    calendarId="primary",
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = []
            for event in result.get("items", []):
                start_info = event["start"].get(
                    "dateTime", event["start"].get("date", "")
                )
                end_info = event["end"].get("dateTime", event["end"].get("date", ""))
                events.append(
                    {
                        "id": event.get("id"),
                        "summary": event.get("summary", ""),
                        "start": start_info,
                        "end": end_info,
                        "description": event.get("description", ""),
                    }
                )
            return {"status": "ok", "count": len(events), "events": events}
        except HttpError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}

    def get_tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list_today", "list_week", "list", "create"],
                            "description": "Action: list_today (eventos de hoje), list_week (esta semana), list (semana), create (criar evento)",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Titulo do evento (para create)",
                        },
                        "start": {
                            "type": "string",
                            "description": "Inicio do evento, linguagem natural (ex: 'amanha as 14:00') ou ISO (para create)",
                        },
                        "end": {
                            "type": "string",
                            "description": "Fim do evento, linguagem natural ou ISO (para create)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Descricao do evento (opcional, para create)",
                        },
                    },
                    "required": ["action"],
                },
            },
        }
