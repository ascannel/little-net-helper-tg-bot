from __future__ import annotations

import ipaddress
import re

from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus
from bot import telegram_client, db_client
from bot.net_tools import tls as tls_tool

TLS_WAIT_TARGET = "TLS_WAIT_TARGET"
TLS_RUNNING = "TLS_RUNNING"

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

def _is_valid_domain(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) > 253:
        return False
    if s.endswith("."):
        s = s[:-1]
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    return bool(re.fullmatch(rf"(?:{label}\.)+{label}", s))

def _parse_target(text: str) -> tuple[bool, str | None, int | None, str | None]:
    """
    Возвращает (ok, host, port, why)
    Форматы: host | host:port
    """
    t = (text or "").strip()
    if not t:
        return False, None, None, "пустая строка"

    # IPv6 не поддерживаем в MVP
    if t.count(":") >= 2:
        return False, None, None, "IPv6 не поддерживается"

    host, port = t, 443
    if ":" in t:
        host, p = t.rsplit(":", 1)
        if not p.isdigit():
            return False, None, None, "порт должен быть числом"
        port = int(p)
        if not (1 <= port <= 65535):
            return False, None, None, "порт вне диапазона 1–65535"

    if _is_valid_public_ipv4(host) or _is_valid_domain(host):
        return True, host, port, None

    return False, None, None, "ожидается домен (FQDN) или публичный IPv4"

def _prompt_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Ввести заново", "callback_data": "tls:start"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

def _result_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Повторить", "callback_data": "tls:repeat"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

class MessageTLS(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        if "callback_query" in update:
            d = (update["callback_query"].get("data") or "")
            return d.startswith("tls:")
        if "message" in update and "text" in update["message"]:
            telegram_id = update["message"]["from"]["id"]
            user = db_client.getUser(telegram_id)
            st = (user.get("state") if user else "") or ""
            return st in (TLS_WAIT_TARGET, TLS_RUNNING)
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        def _busy(chat_id: int):
            telegram_client.sendMessage(chat_id=chat_id, text="⏳ Выполняю предыдущий TLS-запрос. Подождите, пожалуйста…")

        # CALLBACKS
        if "callback_query" in update:
            cq = update["callback_query"]
            from_id = cq["from"]["id"]
            chat_id = cq["message"]["chat"]["id"]
            message_id = cq["message"]["message_id"]
            d = (cq.get("data") or "")
            telegram_client.answerCallbackQuery(cq["id"])

            if d == "tls:start":
                db_client.setUserState(from_id, TLS_WAIT_TARGET)
                telegram_client.editMessageText(
                    chat_id=chat_id, message_id=message_id,
                    text="Введите `host[:port]` (по умолчанию 443):",
                    parse_mode="Markdown",
                )
                return HandlerStatus.STOP

            if d == "tls:repeat":
                # теперь "Повторить" просит новый host[:port]
                db_client.setUserState(from_id, TLS_WAIT_TARGET)
                telegram_client.editMessageText(
                    chat_id=chat_id, message_id=message_id,
                    text="Введите `host[:port]` (по умолчанию 443):",
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
            if st == TLS_RUNNING:
                _busy(chat_id)
                return HandlerStatus.STOP

            ok, host, port, why = _parse_target(msg["text"])
            if not ok:
                telegram_client.sendMessage(chat_id=chat_id, text=f"Некорректный ввод: {why}", reply_markup=_prompt_kb())
                db_client.setUserState(user_id, TLS_WAIT_TARGET)
                return HandlerStatus.STOP

            db_client.setUserState(user_id, TLS_RUNNING)
            telegram_client.sendChatAction(chat_id, "typing")
            placeholder = telegram_client.sendMessage(
                chat_id=chat_id, text=f"⏳ TLS `{host}:{port}`…", parse_mode="Markdown"
            )
            ph_id = placeholder["message_id"]

            info = tls_tool.fetch(host, port, timeout=7.0)
            text = _format_tls(info)

            # context
            user = db_client.getUser(user_id) or {"data": {}}
            data_obj = user.get("data") or {}
            if not isinstance(data_obj, dict):
                data_obj = {}
            data_obj["tls_last_host"] = host
            data_obj["tls_last_port"] = port
            db_client.setUserData(user_id, data_obj)
            db_client.setUserState(user_id, "")

            ok2 = telegram_client.safe_edit_message_text(
                chat_id=chat_id, message_id=ph_id,
                text=text, parse_mode="Markdown", reply_markup=_result_kb()
            )
            if not ok2:
                telegram_client.sendMessage(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=_result_kb())
            return HandlerStatus.STOP

        return HandlerStatus.CONTINUE

def _format_tls(info: tls_tool.TlsInfo) -> str:
    if not info.ok:
        return f"TLS `{info.host}:{info.port}`\n❌ {info.error or 'ошибка'}"

    lines = [f"TLS `{info.host}:{info.port}`"]
    if info.protocol:
        lines.append(f"Protocol: {info.protocol}")
    if info.cipher:
        lines.append(f"Cipher: {info.cipher}")

    if info.subject_cn:
        lines.append(f"Subject CN: `{info.subject_cn}`")

    if info.hostname_ok is not None:
        lines.append("Hostname match: " + ("✅" if info.hostname_ok else "⚠️ mismatch"))

    if info.issuer_cn:
        lines.append(f"Issuer: `{info.issuer_cn}`")
    elif info.issuer_full:
        lines.append(f"Issuer: `{info.issuer_full}`")

    if info.serial:
        short_serial = info.serial[:32] + ("…" if len(info.serial or "") > 32 else "")
        lines.append(f"Serial: `{short_serial}`")

    if info.not_before or info.not_after:
        span = f"{info.not_before or '?'} → {info.not_after or '?'}"
        if info.days_left is not None:
            span += f"  (D-{info.days_left})"
        lines.append(f"Validity: {span}")

    if info.san:
        show = info.san[:10]
        lines.append("SAN: " + ", ".join(f"`{x}`" for x in show) + (" …" if len(info.san) > 10 else ""))

    if info.ocsp_urls:
        lines.append("OCSP: " + ", ".join(info.ocsp_urls[:2]) + (" …" if len(info.ocsp_urls) > 2 else ""))
    if info.ca_issuers:
        lines.append("CA Issuers: " + ", ".join(info.ca_issuers[:2]) + (" …" if len(info.ca_issuers) > 2 else ""))

    return "\n".join(lines)
