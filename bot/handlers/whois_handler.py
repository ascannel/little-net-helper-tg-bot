# bot/handlers/whois_handler.py
from __future__ import annotations

import ipaddress
import re

from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus
from bot import telegram_client, db_client
from bot.net_tools import whois as whois_tool

WHOIS_WAIT_TARGET = "WHOIS_WAIT_TARGET"
WHOIS_RUNNING = "WHOIS_RUNNING"

def _is_valid_domain(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) > 253:
        return False
    if s.endswith("."):
        s = s[:-1]
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    return bool(re.fullmatch(rf"(?:{label}\.)+{label}", s))

def _is_valid_public_ipv4(s: str) -> bool:
    try:
        ip = ipaddress.ip_address((s or "").strip())
        return (
            ip.version == 4 and
            not ip.is_private and not ip.is_loopback and not ip.is_link_local and
            not ip.is_multicast and not ip.is_reserved
        )
    except Exception:
        return False

def _validate(text: str) -> tuple[bool, str | None]:
    t = (text or "").strip()
    if not t:
        return False, "пустая строка"
    if _is_valid_public_ipv4(t):
        return True, None
    if _is_valid_domain(t):
        return True, None
    return False, "ожидается публичный IPv4 или домен (FQDN)"

def _prompt_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Ввести заново", "callback_data": "whois:start"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

def _result_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Повторить", "callback_data": "whois:repeat"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

class MessageWhois(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        if "callback_query" in update:
            d = (update["callback_query"].get("data") or "")
            return d.startswith("whois:")
        if "message" in update and "text" in update["message"]:
            telegram_id = update["message"]["from"]["id"]
            user = db_client.getUser(telegram_id)
            st = (user.get("state") if user else "") or ""
            return st in (WHOIS_WAIT_TARGET, WHOIS_RUNNING)
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        # если RUNNING — вежливо отвечаем и ждём завершения
        def _busy(chat_id: int):
            telegram_client.sendMessage(chat_id=chat_id, text="⏳ Выполняю предыдущий WHOIS. Подождите, пожалуйста…")

        # CALLBACKS
        if "callback_query" in update:
            cq = update["callback_query"]
            from_id = cq["from"]["id"]
            chat_id = cq["message"]["chat"]["id"]
            message_id = cq["message"]["message_id"]
            d = (cq.get("data") or "")
            telegram_client.answerCallbackQuery(cq["id"])

            if d == "whois:start":
                db_client.setUserState(from_id, WHOIS_WAIT_TARGET)
                telegram_client.editMessageText(
                    chat_id=chat_id, message_id=message_id,
                    text="Введите домен (FQDN) или публичный IPv4:",
                )
                return HandlerStatus.STOP

            if d == "whois:repeat":
                # new target
                db_client.setUserState(from_id, WHOIS_WAIT_TARGET)
                telegram_client.editMessageText(
                    chat_id=chat_id, message_id=message_id,
                    text="Введите домен (FQDN) или публичный IPv4:",
                    reply_markup=_prompt_kb(),
                )
                return HandlerStatus.STOP
        # TEXT INPUT
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]

            st = (db_client.getUser(user_id) or {}).get("state") or ""
            if st == WHOIS_RUNNING:
                _busy(chat_id)
                return HandlerStatus.STOP

            target = (msg["text"] or "").strip()
            ok, why = _validate(target)
            if not ok:
                telegram_client.sendMessage(chat_id=chat_id, text=f"Некорректный ввод: {why}", reply_markup=_prompt_kb())
                db_client.setUserState(user_id, WHOIS_WAIT_TARGET)
                return HandlerStatus.STOP

            # RUNNING + плейсхолдер
            db_client.setUserState(user_id, WHOIS_RUNNING)
            telegram_client.sendChatAction(chat_id, "typing")
            placeholder = telegram_client.sendMessage(
                chat_id=chat_id, text=f"⏳ WHOIS `{target}`…", parse_mode="Markdown"
            )
            ph_id = placeholder["message_id"]

            res = whois_tool.lookup(target, timeout=8.0)
            text = _format_result(res)

            # сохранить цель для Повторить
            user = db_client.getUser(user_id) or {"data": {}}
            data_obj = user.get("data") or {}
            if not isinstance(data_obj, dict):
                data_obj = {}
            data_obj["whois_last_target"] = target
            db_client.setUserData(user_id, data_obj)

            db_client.setUserState(user_id, "")  # выходим из RUNNING

            ok2 = telegram_client.safe_edit_message_text(
                chat_id=chat_id, message_id=ph_id,
                text=text, parse_mode="Markdown", reply_markup=_result_kb()
            )
            if not ok2:
                telegram_client.sendMessage(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=_result_kb())
            return HandlerStatus.STOP

        return HandlerStatus.CONTINUE


def _format_result(res: whois_tool.WhoisResult) -> str:
    if not res.ok:
        return f"WHOIS `{res.target}`\n❌ {res.error or 'ошибка'}"

    head = f"WHOIS `{res.target}`"
    lines = [head] + res.summary_lines

    # Добавим укороченный RAW блок, чтобы не выбежать за лимит 4096
    if res.raw_text:
        snippet = _trim(res.raw_text, limit=1800)
        if snippet:
            lines += ["", "```", snippet, "```"]

    return "\n".join(lines)


def _trim(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n…(truncated)"
