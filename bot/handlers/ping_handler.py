import ipaddress
import re

from littleNetHelper.handlers.handler import Handler
from littleNetHelper.handlers.handler_status import HandlerStatus
from littleNetHelper import telegram_client, db_client
from littleNetHelper.net_tools import ping as ping_tool

PING_WAIT_STATE = "PING_WAIT_TARGET"

def _validate_host(text: str) -> tuple[bool, str | None]:
    s = (text or "").strip()
    if not s:
        return False, "пустая строка"
    # IPv4?
    ipv4_like = bool(re.fullmatch(r"\d+(?:\.\d+){3}", s))
    try:
        ip = ipaddress.ip_address(s)
        if ip.version == 4:
            if ip.is_private:
                return False, "приватный диапазон (RFC1918) не допускается"
            if ip.is_loopback:
                return False, "loopback-адрес (127.0.0.0/8) не допускается"
            if ip.is_link_local:
                return False, "link-local адрес не допускается"
            if ip.is_multicast or ip.is_reserved:
                return False, "служебный диапазон не допускается"
            return True, None
        else:
            return False, "ожидается IPv4 или домен (IPv6 сейчас не поддержан)"
    except ValueError:
        if ipv4_like:
            return False, "некорректный IPv4-адрес"
    # домен (FQDN)
    if len(s) > 253:
        return False, "домен слишком длинный (>253)"
    if s.endswith("."):
        s = s[:-1]
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    if not re.fullmatch(rf"(?:{label}\.)+{label}", s):
        return False, "некорректное доменное имя (ожидается FQDN вида example.com)"
    return True, None

class MessagePing(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        # 1) callback "ping:start" / "ping:repeat"
        if "callback_query" in update:
            d = update["callback_query"].get("data") or ""
            return d in ("ping:start", "ping:repeat")
        # 2) текст в состоянии ожидания цели
        if "message" in update and "text" in update["message"]:
            telegram_id = update["message"]["from"]["id"]
            user = db_client.getUser(telegram_id)
            st = (user.get("state") if user else "") or ""
            return st == PING_WAIT_STATE
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        # CASE A: кнопки
        if "callback_query" in update:
            cq = update["callback_query"]
            from_id = cq["from"]["id"]
            chat_id = cq["message"]["chat"]["id"]
            message_id = cq["message"]["message_id"]
            d = cq.get("data")
            telegram_client.answerCallbackQuery(cq["id"])

            if d == "ping:start":
                db_client.setUserState(from_id, PING_WAIT_STATE)
                db_client.setUserData(from_id, {})  # сбросим прошлую цель
                telegram_client.editMessageText(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Введите IPv4-адрес или домен (публичный):",
                    reply_markup=_prompt_kb(),
                )
                return HandlerStatus.STOP

            if d == "ping:repeat":
                user = db_client.getUser(from_id)
                data_obj = (user.get("data") if user else {}) or {}
                if not isinstance(data_obj, dict):
                    # страховка: вдруг в БД строка
                    try:
                        import json
                        data_obj = json.loads(data_obj) if data_obj else {}
                    except Exception:
                        data_obj = {}
                last = data_obj.get("last_ping_target")
                if not last:
                    telegram_client.editMessageText(
                        chat_id=chat_id,
                        message_id=message_id,
                        text="Нет предыдущей цели. Введите IPv4-адрес или домен:",
                        reply_markup=_prompt_kb(),
                    )
                    db_client.setUserState(from_id, PING_WAIT_STATE)
                    return HandlerStatus.STOP

                res = ping_tool.run(last, count=10, deadline_s=20, per_reply_timeout_s=2)
                text = _format_ping_result(last, res)
                telegram_client.editMessageText(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=_result_kb(),
                    parse_mode="Markdown",
                )
                return HandlerStatus.STOP

        # CASE B: введён адрес
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            target = (msg["text"] or "").strip()

            ok, why = _validate_host(target)
            if not ok:
                telegram_client.sendMessage(
                    chat_id=chat_id,
                    text=f"Некорректный адрес: {why}\n\nПример: `8.8.8.8` или `example.com`",
                    parse_mode="Markdown",
                    reply_markup=_prompt_kb(),
                )
                # остаёмся в состоянии ожидания цели
                db_client.setUserState(user_id, PING_WAIT_STATE)
                return HandlerStatus.STOP

            # сохраняем цель (гарантируем dict)
            user = db_client.getUser(user_id) or {"data": {}}
            data_obj = user.get("data") or {}
            if not isinstance(data_obj, dict):
                try:
                    import json
                    data_obj = json.loads(data_obj) if data_obj else {}
                except Exception:
                    data_obj = {}
            data_obj["last_ping_target"] = target
            db_client.setUserData(user_id, data_obj)
            db_client.setUserState(user_id, "")  # выходим из режима ввода

            # пинг и ответ
            res = ping_tool.run(target, count=10, deadline_s=20, per_reply_timeout_s=2)
            text = _format_ping_result(target, res)
            telegram_client.sendMessage(
                chat_id=chat_id,
                text=text,
                reply_markup=_result_kb(),
                parse_mode="Markdown",
            )
            return HandlerStatus.STOP

        return HandlerStatus.CONTINUE

def _format_ping_result(target: str, res: ping_tool.PingResult) -> str:
    if not res.ok and res.received == 0:
        return (
            f"Ping `{target}` (10 пакетов)\n"
            f"❌ недоступно, потери {res.loss_pct:.0f}%\n\n"
            f"```\n{res.raw_tail}\n```"
        )
    lines = [
        f"Ping `{target}` (10 пакетов)",
        f"📨 передано: {res.transmitted}, получено: {res.received}, потери: {res.loss_pct:.0f}%",
    ]
    if res.avg_ms is not None:
        lines.append(
            f"⏱️ rtt (мс): min {res.min_ms:.2f} | avg {res.avg_ms:.2f} | max {res.max_ms:.2f} | σ {res.stddev_ms:.2f}"
        )
    lines += ["", "```", res.raw_tail, "```"]
    return "\n".join(lines)

def _prompt_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Ввести заново", "callback_data": "ping:start"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }

def _result_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Повторить", "callback_data": "ping:repeat"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }
