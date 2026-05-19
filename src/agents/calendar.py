import json
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone as tz
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import dateparser
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import BaseAgent
from ..config import settings
from ..memory.profile import ProfileManager

UTC = tz.utc

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_DIR = Path(settings.data_dir) / "cal_tokens"

_cal_flows: dict[str, Flow] = {}
_cal_flow_users: dict[str, str] = {}
_cal_flow_ts: dict[str, float] = {}

OAUTH_FLOW_TTL = 600


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _init_token_dir():
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_expired_flows():
    now = time.time()
    expired = [s for s, ts in _cal_flow_ts.items() if now - ts > OAUTH_FLOW_TTL]
    for s in expired:
        _cal_flows.pop(s, None)
        _cal_flow_users.pop(s, None)
        _cal_flow_ts.pop(s, None)


class _OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code and state and state in _cal_flows:
            flow = _cal_flows.pop(state)
            user_id = _cal_flow_users.pop(state, None)
            _cal_flow_ts.pop(state, None)
            try:
                flow.fetch_token(code=code)
                CalendarAgent._persist_creds(user_id, flow.credentials)
                self._respond(
                    200,
                    "Autorizacao concluida! Podes fechar esta pagina e voltar ao Telegram.",
                )
            except Exception as e:
                self._respond(400, f"Erro ao trocar codigo: {e}")
        else:
            self._respond(400, "Pedido invalido ou expirado.")

    def _respond(self, status_code: int, msg: str):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
            f"<h2>{msg}</h2>"
            "<p>Volta ao Telegram.</p>"
            "</body></html>"
        )
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def _run_oauth_server():
    server = HTTPServer(("127.0.0.1", 8080), _OAuthHandler)
    server.serve_forever()


def start_oauth_server():
    t = threading.Thread(target=_run_oauth_server, daemon=True)
    t.start()


class CalendarAgent(BaseAgent):
    name = "calendar"
    description = (
        "Google Calendar integration. List today's events, week events, "
        "or create new events. Calls with list_today, list_week, list, create."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id
        _init_token_dir()
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
        _cleanup_expired_flows()
        flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
        flow.redirect_uri = settings.google_redirect_uri
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        _cal_flows[state] = flow
        _cal_flow_users[state] = user_id
        _cal_flow_ts[state] = time.time()
        return auth_url

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
