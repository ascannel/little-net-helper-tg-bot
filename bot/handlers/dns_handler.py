from __future__ import annotations

import ipaddress
import re
from typing import Tuple

from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus
from bot import telegram_client, db_client
from bot.net_tools import dns as dns_tool

DNS_WAIT_TARGET = "DNS_WAIT_TARGET"
DNS_RUNNING = "DNS_RUNNING"

DNS_TYPES = ("A", "AAAA", "CNAME", "MX", "TXT", "NS", "PTR")

def _is_valid_domain(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) > 253:
        return False
    if s.endswith("."):
        s = s[:-1]
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    return bool(re.fullmatch(rf"(?:{label}\.)+{label}", s))

def _is_valid_ipv4(s: str) -> bool:
    try:
        ip = ipaddress.ip_address(s.strip())
        return ip.version == 4 and (not ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_multicast and not ip.is_reserved)
    except Exception:
        return False

def _validate_input(rrtype: str, text: str) -> Tuple[bool, str | None]:
    t = (text or "").strip()
    if not t:
        return False, "пустая строка"
    if rrtype == "PTR":
        if not _is_valid_ipv4(t):
            return False, "ожидается публичный IPv4 для PTR (пример: 8.8.8.8)"
        return True, None
    if not _is_valid_domain(t):
        return False, "ожидается домен (FQDN), например: example.com"
    return True, None

def _type_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "A", "callback_data": "dns:type:A"},
             {"text": "AAAA", "callback_data": "dns:type:AAAA"},
             {"text": "CNAME", "callback_data": "dns:type:CNAME"}],
            [{"text": "MX", "callback_data": "dns:type:MX"},
             {"text": "TXT", "callback_data": "dns:type:TXT"},
             {"text": "NS", "callback_data": "dns:type:NS"}],
            [{"text": "PTR", "callback_data": "dns:type:PTR"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

def _prompt_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🧾 Сменить тип", "callback_data": "dns:choose_type"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

def _result_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Повторить", "callback_data": "dns:repeat"}],
            [{"text": "🧾 Сменить тип", "callback_data": "dns:choose_type"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

class MessageDNS(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        if "callback_query" in update:
            d = (update["callback_query"].get("data") or "")
            return d.startswith("dns:")
        if "message" in update and "text" in update["message"]:
            telegram_id = update["message"]["from"]["id"]
            user = db_client.getUser(telegram_id)
            st = (user.get("state") if user else "") or ""
            return st in (DNS_WAIT_TARGET, DNS_RUNNING)
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        # если RUNNING — “занято”
        def _busy(chat_id: int):
            telegram_client.sendMessage(chat_id=chat_id, text="⏳ Выполняю предыдущий DNS-запрос. Подождите, пожалуйста…")

        if "callback_query" in update:
            cq = update["callback_query"]
            from_id = cq["from"]["id"]
            chat_id = cq["message"]["chat"]["id"]
            message_id = cq["message"]["message_id"]
            d = (cq.get("data") or "")
            telegram_client.answerCallbackQuery(cq["id"])

            if d in ("dns:start", "dns:choose_type"):
                user = db_client.getUser(from_id) or {"data": {}}
                data_obj = user.get("data") or {}
                if not isinstance(data_obj, dict):
                    data_obj = {}
                data_obj.pop("dns_type", None)
                db_client.setUserData(from_id, data_obj)
                db_client.setUserState(from_id, "")
                telegram_client.editMessageText(
                    chat_id=chat_id, message_id=message_id,
                    text="Выберите тип DNS-записи:", reply_markup=_type_kb()
                )
                return HandlerStatus.STOP

            if d.startswith("dns:type:"):
                rrtype = d.split(":")[-1].upper()
                if rrtype not in DNS_TYPES:
                    rrtype = "A"
                user = db_client.getUser(from_id) or {"data": {}}
                data_obj = user.get("data") or {}
                if not isinstance(data_obj, dict):
                    data_obj = {}
                data_obj["dns_type"] = rrtype
                db_client.setUserData(from_id, data_obj)
                db_client.setUserState(from_id, DNS_WAIT_TARGET)
                prompt = "Введите домен (FQDN), например: `example.com`"
                if rrtype == "PTR":
                    prompt = "Введите публичный IPv4 для PTR, например: `8.8.8.8`"
                telegram_client.editMessageText(
                    chat_id=chat_id, message_id=message_id,
                    text=prompt, parse_mode="Markdown", reply_markup=_prompt_kb()
                )
                return HandlerStatus.STOP

            if d == "dns:repeat":
                # теперь "Повторить" просит новую цель для текущего типа
                user = db_client.getUser(from_id)
                data_obj = (user.get("data") if user else {}) or {}
                if not isinstance(data_obj, dict):
                    data_obj = {}
                rrtype = (data_obj.get("dns_type") or "A").upper()
                db_client.setUserState(from_id, DNS_WAIT_TARGET)
                prompt = "Введите домен (FQDN), например: `example.com`"
                if rrtype == "PTR":
                    prompt = "Введите публичный IPv4 для PTR, например: `8.8.8.8`"
                telegram_client.editMessageText(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=prompt,
                    parse_mode="Markdown",
                    reply_markup=_prompt_kb(),
                )
                return HandlerStatus.STOP

        # TEXT INPUT
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            st = (db_client.getUser(user_id) or {}).get("state") or ""
            if st == DNS_RUNNING:
                _busy(chat_id)
                return HandlerStatus.STOP

            user = db_client.getUser(user_id)
            data_obj = (user.get("data") if user else {}) or {}
            if not isinstance(data_obj, dict):
                data_obj = {}
            rrtype = (data_obj.get("dns_type") or "A").upper()

            target = (msg["text"] or "").strip()
            ok, why = _validate_input(rrtype, target)
            if not ok:
                telegram_client.sendMessage(chat_id=chat_id, text=f"Некорректный ввод: {why}", reply_markup=_prompt_kb())
                db_client.setUserState(user_id, DNS_WAIT_TARGET)
                return HandlerStatus.STOP

            # RUNNING + плейсхолдер (новое сообщение)
            db_client.setUserState(user_id, DNS_RUNNING)
            telegram_client.sendChatAction(chat_id, "typing")
            placeholder = telegram_client.sendMessage(
                chat_id=chat_id, text=f"⏳ DNS `{rrtype}` для `{target}`…", parse_mode="Markdown"
            )
            ph_id = placeholder["message_id"]

            res = dns_tool.lookup(target, rrtype, timeout=4.0)
            text = _format_dns_result(target, rrtype, res)

            # сохранить контекст для "Повторить"
            data_obj["dns_last_target"] = target
            data_obj["dns_type"] = rrtype
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

def _format_dns_result(target: str, rrtype: str, res: dns_tool.DnsResult) -> str:
    head = f"DNS `{rrtype}` для `{target}`"
    if not res.ok:
        err = res.error or "ошибка"
        return f"{head}\n❌ {err}"
    lines = [head]
    if res.cname and rrtype != "CNAME":
        lines.append(f"↪ CNAME: `{res.cname}`")
    if res.answers:
        lines.append("```\n" + "\n".join(
            f"{a.value}" + (f"  (TTL {a.ttl})" if a.ttl is not None else "")
            for a in res.answers[:50]
        ) + "\n```")
        if len(res.answers) > 50:
            lines.append(f"…и ещё {len(res.answers)-50} записей")
    else:
        lines.append("Нет ответов (No answer)")
    return "\n".join(lines)
