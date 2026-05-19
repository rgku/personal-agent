import datetime as dt
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path
from zoneinfo import available_timezones

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from .config import settings
from .orchestrator import Orchestrator
from .memory.profile import ProfileManager
from .agents.calendar import CalendarAgent
from .agents.notes import NotesAgent
from .agents.reminders import ReminderAgent
from .agents.shopping import ShoppingAgent, get_all_user_ids
from .agents.todos import TodoAgent
from .agents.habits import HabitsAgent

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PID_FILE = PROJECT_ROOT / "data" / "bot.pid"

_orchestrators: dict[int, Orchestrator] = {}

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton("📝 Notas"),
            KeyboardButton("⏰ Lembretes"),
            KeyboardButton("🛒 Compras"),
        ],
        [
            KeyboardButton("📋 Hoje"),
            KeyboardButton("🏃 Habitos"),
            KeyboardButton("📤 Exportar"),
        ],
        [KeyboardButton("🌐 Pesquisar"), KeyboardButton("📅 Calendario")],
    ],
    resize_keyboard=True,
)

ONBOARD_NAME, ONBOARD_TZ, ONBOARD_LANG = range(3)


def _orch(uid: int) -> Orchestrator:
    if uid not in _orchestrators:
        _orchestrators[uid] = Orchestrator(str(uid))
    return _orchestrators[uid]


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    mgr = ProfileManager(uid)
    p = mgr.get()

    if p.name is None or p.timezone == "UTC" and not _has_custom_tz(p):
        await update.message.reply_text(
            "Ola\\! Bem\\-vindo ao teu assistente pessoal\\. Vou conhecer\\-te melhor\\.\n\n"
            "Como te chamas\\?",
            parse_mode="MarkdownV2",
        )
        return ONBOARD_NAME

    await update.message.reply_text(
        f"Ola de volta, {_escape(p.name or '')}\\! \n\n"
        "📝 *Notas* \\- criar, pesquisar, organizar\n"
        "⏰ *Lembretes* \\- agenda com hora marcada\n"
        "🛒 *Compras* \\- listas de compras\n"
        "🌐 *Pesquisa* \\- pesquisar na web\n"
        "🏃 *Habitos* \\- tracking diario\n"
        "📅 *Calendario* \\- Google Calendar\n\n"
        "/help \\- todos os comandos",
        parse_mode="MarkdownV2",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


def _has_custom_tz(p) -> bool:
    return p.updated_at != "" and p.updated_at != p.created_at


async def onboard_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    mgr = ProfileManager(uid)
    p = mgr.get()
    p.name = update.message.text.strip()
    mgr.save(p)
    await update.message.reply_text(
        f"Prazer, {_escape(p.name or '')}\\! Qual o teu fuso horario\\?\n"
        "Ex: Europe/Lisbon, America/Sao_Paulo, Europe/London",
        parse_mode="MarkdownV2",
    )
    return ONBOARD_TZ


async def onboard_tz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    tz = update.message.text.strip()
    if tz not in available_timezones():
        await update.message.reply_text(
            "Fuso invalido\\. Tenta: Europe/Lisbon, America/Sao_Paulo...",
            parse_mode="MarkdownV2",
        )
        return ONBOARD_TZ

    mgr = ProfileManager(uid)
    p = mgr.get()
    p.timezone = tz
    mgr.save(p)
    await update.message.reply_text(
        "Perfeito\\! E qual a tua lingua\\? (pt / en)",
        parse_mode="MarkdownV2",
    )
    return ONBOARD_LANG


async def onboard_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    lang = update.message.text.strip().lower()[:2]
    if lang not in ("pt", "en"):
        lang = "pt"

    mgr = ProfileManager(uid)
    p = mgr.get()
    p.language = lang
    p.updated_at = ""
    mgr.save(p)

    await update.message.reply_text(
        f"Pronto, {_escape(p.name or '')}\\! 🎉\n\n"
        "📝 *Notas* \\- criar, pesquisar, organizar\n"
        "⏰ *Lembretes* \\- agenda com hora marcada\n"
        "🛒 *Compras* \\- listas de compras\n"
        "🌐 *Pesquisa* \\- pesquisar na web\n"
        "🏃 *Habitos* \\- tracking diario\n"
        "📅 *Calendario* \\- Google Calendar\n\n"
        "/help \\- todos os comandos",
        parse_mode="MarkdownV2",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def onboard_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Onboarding cancelado\\. /start para recomecar\\.",
        parse_mode="MarkdownV2",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Comandos*\n"
        "/start \\- Iniciar\n"
        "/help \\- Ajuda\n"
        "/profile \\- Ver perfil\n"
        "/reset \\- Reiniciar conversa\n"
        "/hoje \\- Agenda de hoje\n"
        "/cal \\- Eventos do calendario\n"
        "/cal\\_auth \\- Conectar Google Calendar\n"
        "/cal\\_desconectar \\- Desconectar\n"
        "/export \\- Exportar dados\n"
        "/update \\- Atualizar via git\n"
        "/restart \\- Reiniciar bot\n\n"
        "Ou fala comigo naturalmente\\!",
        parse_mode="MarkdownV2",
    )


async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    mgr = ProfileManager(uid)
    p = mgr.get()

    lines = ["*Perfil*"]
    if p.name:
        lines.append(f"Nome: {_escape(p.name)}")
    if p.language:
        lines.append(f"Lingua: {_escape(p.language)}")
    if p.timezone:
        lines.append(f"Fuso: {_escape(p.timezone)}")
    if p.email:
        lines.append(f"Email: {_escape(p.email)}")
    if p.preferences:
        prefs = ", ".join(
            f"{_escape(k)}: {_escape(v)}" for k, v in p.preferences.items()
        )
        lines.append(f"Preferencias: {prefs}")
    if p.frequent_contacts:
        lines.append(f"Contactos: {', '.join(_escape(c) for c in p.frequent_contacts)}")

    if len(lines) == 1:
        lines.append("_Ainda vazio\\. Fala comigo para eu te conhecer\\._")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="MarkdownV2",
    )


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _orch(uid).reset()
    await update.message.reply_text("Conversa reiniciada\\.")


async def update_bot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("A atualizar... \u23f3")
    try:
        result = subprocess.run(
            ["git", "pull"], capture_output=True, text=True, cwd=str(PROJECT_ROOT)
        )
        out = (result.stdout.strip() or result.stderr.strip() or "sem alteracoes")[:500]
        import re as _re

        out = _re.sub(r"https://[^@\s]+@", "https://[redacted]@", out)
        await update.message.reply_text(f"git pull: {out}")
        pip_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                "requirements.txt",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        if pip_result.returncode != 0:
            await update.message.reply_text(
                f"pip install falhou: {pip_result.stderr[:300]}"
            )
            return
        await update.message.reply_text("A reiniciar... \U0001f504")
        _clean_pid()
        os._exit(42)
    except Exception:
        traceback.print_exc()
        await update.message.reply_text("Erro ao atualizar. Ve os logs.")


async def restart_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("A reiniciar... \U0001f504")
    _clean_pid()
    os._exit(42)


async def hoje_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    now = dt.datetime.now(dt.timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    today_reminders = ReminderAgent.get_for_day_range(
        uid, f"{today_str}T00:00", f"{today_str}T23:59"
    )
    shop = ShoppingAgent.get_pending_summary_for(uid)
    todos_list = TodoAgent.get_pending_for(uid)
    habits_list = HabitsAgent.get_pending_for(uid)
    cal_events = CalendarAgent.get_events_for_range(
        uid,
        now.replace(hour=0, minute=0, second=0, microsecond=0),
        now.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1),
    )

    lines = [f"\u2600\ufe0f *Hoje, {now.strftime('%d/%m')}*"]
    lines.append("\n\U0001f4cb *Lembretes:*")
    if today_reminders:
        for t in today_reminders:
            ts = t["trigger_at"][11:16] if "T" in t["trigger_at"] else t["trigger_at"]
            lines.append(f"  \u2022 {ts} \\- {_escape(t['message'])}")
    else:
        lines.append("  _Sem lembretes_")

    if todos_list:
        lines.append("\n\U0001f4dd *Tarefas:*")
        for t in todos_list:
            icon = {
                "high": "\\\U0001f534",
                "medium": "\\\U0001f7e1",
                "low": "\\\U0001f7e2",
            }.get(t["priority"], "")
            lines.append(f"  \u2022 {icon} {_escape(t['title'])}")

    if habits_list:
        lines.append("\n\U0001f3c3 *Habitos:*")
        for h in habits_list:
            done = "\\\u2705" if h["today_status"] == "done" else "\\\u274c"
            target = f" \\({_escape(h['target'])}\\)" if h.get("target") else ""
            lines.append(
                f"  {done} {_escape(h['name'])}{target} \\- streak {h['streak']}"
            )

    if cal_events:
        lines.append("\n📅 *Agenda:*")
        for e in cal_events:
            s = e["start"]
            if "T" in s:
                time = s[11:16]
                lines.append(f"  • {time} — {_escape(e['summary'])}")
            else:
                lines.append(f"  • {_escape(e['summary'])}")

    if shop:
        lines.append("\n\U0001f6d2 *Compras:*")
        for s in shop:
            qty = f" \\({s['quantity']}\\)" if s.get("quantity") else ""
            lines.append(f"  \u2022 {_escape(s['item'])}{qty}")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


async def export_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    mgr = ProfileManager(uid)
    p = mgr.get()
    now = dt.datetime.now(dt.timezone.utc).strftime("%d/%m/%Y %H:%M")

    lines = [f"# Personal Agent Export — {now}\n"]
    lines.append(
        f"## Perfil\nNome: {p.name or '-'} | Fuso: {p.timezone} | Lingua: {p.language}\n"
    )

    notes = NotesAgent(uid)._handle_list({})
    lines.append("## Notas")
    if notes.get("notes"):
        for n in notes["notes"]:
            lines.append(f"- {n['title']}: {n.get('snippet', '')}")
    else:
        lines.append("_vazio_\n")

    rem = ReminderAgent(uid)._handle_list({})
    lines.append("\n## Lembretes (ativos)")
    if rem.get("reminders"):
        for r in rem["reminders"]:
            if not r.get("notified"):
                lines.append(f"- {r['trigger_at']} | {r['message']}")
    else:
        lines.append("_vazio_\n")

    td = TodoAgent(uid)._handle_list({})
    lines.append("\n## Tarefas (pendentes)")
    if td.get("todos"):
        for t in td["todos"]:
            lines.append(f"- [{t['priority'].upper()}] {t['title']}")
    else:
        lines.append("_vazio_\n")

    shop = ShoppingAgent.get_pending_summary_for(uid)
    lines.append("\n## Compras (pendentes)")
    if shop:
        for s in shop:
            qty = f" ({s['quantity']})" if s.get("quantity") else ""
            lines.append(f"- {s['item']}{qty} [{s['list_name']}]")
    else:
        lines.append("_vazio_\n")

    hab = HabitsAgent(uid)._handle_status({})
    lines.append("\n## Habitos")
    if hab.get("habits"):
        for h in hab["habits"]:
            fire = "🔥" * min(h["streak"], 5)
            lines.append(
                f"- {h['name']}: streak {h['streak']} {fire} | best {h['best_streak']}"
            )
    else:
        lines.append("_vazio_")

    import io

    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
    buf.name = f"export_{now.replace('/', '-').replace(':', '-').replace(' ', '_')}.md"
    await update.message.reply_document(buf)


async def cal_auth_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    try:
        auth_msg = CalendarAgent.start_auth(uid)
    except RuntimeError as e:
        await update.message.reply_text(str(e))
        return
    await update.message.reply_text(auth_msg)


async def cal_events_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not CalendarAgent.is_connected(uid):
        await update.message.reply_text(
            "Nao conectado ao Google Calendar\\. Usa /cal_auth primeiro\\.",
            parse_mode="MarkdownV2",
        )
        return

    now = dt.datetime.now(dt.timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=7)
    events = CalendarAgent.get_events_for_range(uid, start, end)

    if not events:
        await update.message.reply_text("Nenhum evento nos proximos 7 dias\\.")
        return

    lines = ["📅 *Proximos eventos:*"]
    for e in events:
        s = e["start"]
        if "T" in s:
            day = s[:10]
            time = s[11:16]
            lines.append(f"  • {day} {time} — {_escape(e['summary'])}")
        else:
            lines.append(f"  • {s} (todo dia) — {_escape(e['summary'])}")
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


async def cal_desconectar_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    CalendarAgent.disconnect(uid)
    await update.message.reply_text("Desconectado do Google Calendar\\.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    if not text or len(text) > 4000:
        await update.message.reply_text("Mensagem muito longa. Tenta algo mais curto.")
        return
    try:
        reply = await _orch(uid).process(text)
        await update.message.reply_text(reply)
    except Exception:
        traceback.print_exc()
        await update.message.reply_text("Ocorreu um erro. Tenta novamente.")


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Audio em breve \\(Fase 5\\)\\.",
        parse_mode="MarkdownV2",
    )


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    import telegram.error

    err = ctx.error
    if isinstance(err, telegram.error.Conflict):
        print("FATAL: Another bot instance is polling. Shutting down.")
        _clean_pid()
        os._exit(0)
    print(f"Error: {err}")
    traceback.print_exception(err)


def build_app() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_error_handler(error_handler)

    onboarding = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ONBOARD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_name)
            ],
            ONBOARD_TZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_tz)],
            ONBOARD_LANG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_lang)
            ],
        },
        fallbacks=[CommandHandler("cancel", onboard_cancel)],
    )
    app.add_handler(onboarding)

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("update", update_bot))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("hoje", hoje_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("cal_auth", cal_auth_cmd))
    app.add_handler(CommandHandler("cal", cal_events_cmd))
    app.add_handler(CommandHandler("cal_desconectar", cal_desconectar_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    return app


def setup_jobs(app: Application):
    async def check_reminders(ctx: ContextTypes.DEFAULT_TYPE):
        due = ReminderAgent.get_due()
        for r in due:
            try:
                await ctx.bot.send_message(
                    chat_id=int(r["user_id"]),
                    text=f"\u23f0 *Lembrete*\n{_escape(r['message'])}",
                    parse_mode="MarkdownV2",
                )
            except Exception:
                traceback.print_exc()
            ReminderAgent.mark_notified(r["id"])

    async def daily_briefing(ctx: ContextTypes.DEFAULT_TYPE):
        now = dt.datetime.now(dt.timezone.utc)
        today = now.date()
        weekday = today.weekday()

        if weekday == 6:
            monday = today + dt.timedelta(days=1)
        else:
            monday = today - dt.timedelta(days=weekday)
        sunday = monday + dt.timedelta(days=6)

        for uid in get_all_user_ids():
            try:
                week_start = monday.strftime("%Y-%m-%dT00:00")
                week_end = (sunday + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00")
                week_reminders = ReminderAgent.get_for_day_range(
                    uid, week_start, week_end
                )
                shop = ShoppingAgent.get_pending_summary_for(uid)
                todos_list = TodoAgent.get_pending_for(uid)
                habits_list = HabitsAgent.get_pending_for(uid)

                cal_start = dt.datetime.combine(
                    monday, dt.time.min, tzinfo=dt.timezone.utc
                )
                cal_end = dt.datetime.combine(
                    sunday + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc
                )
                cal_events = CalendarAgent.get_events_for_range(uid, cal_start, cal_end)

                by_day: dict[str, list[dict]] = {}
                for r in week_reminders:
                    d = (
                        r["trigger_at"][:10]
                        if "T" in r["trigger_at"]
                        else r["trigger_at"]
                    )
                    by_day.setdefault(d, []).append(r)

                cal_by_day: dict[str, list[dict]] = {}
                for e in cal_events:
                    s = e["start"]
                    d = s[:10] if "T" in s else s
                    cal_by_day.setdefault(d, []).append(e)

                lines = [f"\u2600\ufe0f *Bom dia\\!* {now.strftime('%d/%m/%Y')}\n"]
                days_pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

                for i in range(7):
                    d = monday + dt.timedelta(days=i)
                    d_key = d.strftime("%Y-%m-%d")
                    entries = by_day.get(d_key, [])
                    cal_entries = cal_by_day.get(d_key, [])
                    marker = " \\(hoje\\)" if d == today else ""
                    lines.append(
                        f"\U0001f539 *{days_pt[i]} {d.strftime('%d/%m')}*{marker}"
                    )

                    if entries:
                        for e in entries:
                            ts = (
                                e["trigger_at"][11:16]
                                if "T" in e["trigger_at"]
                                else e["trigger_at"]
                            )
                            lines.append(f"    \u2022 {ts} \\- {_escape(e['message'])}")

                    if cal_entries:
                        for ce in cal_entries:
                            s = ce["start"]
                            if "T" in s:
                                ts = s[11:16]
                                lines.append(
                                    f"    📅 {ts} \\- {_escape(ce['summary'])}"
                                )
                            else:
                                lines.append(f"    📅 {_escape(ce['summary'])}")

                    if not entries and not cal_entries:
                        lines.append("    _\\-\\-_")

                if todos_list:
                    lines.append("\n\U0001f4dd *Tarefas pendentes:*")
                    for t in todos_list:
                        icon = {
                            "high": "\\\U0001f534",
                            "medium": "\\\U0001f7e1",
                            "low": "\\\U0001f7e2",
                        }.get(t["priority"], "")
                        status = {"in_progress": " \\(em curso\\)"}.get(
                            t.get("status", ""), ""
                        )
                        lines.append(f"  \u2022 {icon} {_escape(t['title'])}{status}")

                if habits_list:
                    lines.append("\n\U0001f3c3 *Habitos:*")
                    for h in habits_list:
                        done = "\\\u2705" if h["today_status"] == "done" else "\\\u274c"
                        target = (
                            f" \\({_escape(h['target'])}\\)" if h.get("target") else ""
                        )
                        fire = (
                            "\\\U0001f525" * min(h.get("streak", 0), 3)
                            if h.get("streak", 0) > 1
                            else ""
                        )
                        lines.append(f"  {done} {_escape(h['name'])}{target} {fire}")

                if shop:
                    lines.append("\n\U0001f6d2 *Compras pendentes:*")
                    for s in shop:
                        qty = (
                            f" \\({_escape(s['quantity'])}\\)"
                            if s.get("quantity")
                            else ""
                        )
                        lines.append(
                            f"  \u2022 {_escape(s['item'])}{qty} _\\({_escape(s['list_name'])}\\)_"
                        )

                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text="\n".join(lines),
                    parse_mode="MarkdownV2",
                )
            except Exception:
                traceback.print_exc()

    async def proactive_habits(ctx: ContextTypes.DEFAULT_TYPE):
        for uid, pending_habits in HabitsAgent.get_users_with_pending():
            try:
                names = ", ".join(_escape(h["name"]) for h in pending_habits)
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"\U0001f3c3 *Check\\-in de habitos\\!*\n"
                    f"Ainda nao registaste hoje: {names}\\.\n"
                    f"Ja fizeste? Ainda vais fazer?",
                    parse_mode="MarkdownV2",
                )
            except Exception:
                traceback.print_exc()

    app.job_queue.run_repeating(check_reminders, interval=30, first=10)
    app.job_queue.run_daily(
        daily_briefing,
        time=dt.time(hour=7, minute=0, tzinfo=dt.timezone.utc),
    )
    app.job_queue.run_daily(
        proactive_habits,
        time=dt.time(hour=20, minute=0, tzinfo=dt.timezone.utc),
    )


def _clean_pid():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def _escape(text: str) -> str:
    """Escape MarkdownV2 special characters. Input must be raw, not pre-escaped."""
    text = text.replace("\\", "\\\\")
    for ch in "_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
