import ipaddress
import re

from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus
from bot import telegram_client, db_client
from bot.net_tools import ping as ping_tool

PING_WAIT_STATE = "PING_WAIT_TARGET"
PING_RUNNING_STATE = "PING_RUNNING"

def _is_valid_host(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    try:
        ip = ipaddress.ip_address(s)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
        return ip.version == 4  # IPv4-only для ping 
    except ValueError:
        pass
    if len(s) > 253:
        return False
    if s.endswith("."):
        s = s[:-1]
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    return bool(re.fullmatch(rf"(?:{label}\.)+{label}", s))

class MessagePing(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        # callbacks
        if "callback_query" in update:
            d = (update["callback_query"].get("data") or "")
            return d in ("ping:start", "ping:repeat")
        # ожидание адреса
        if "message" in update and "text" in update["message"]:
            telegram_id = update["message"]["from"]["id"]
            user = db_client.getUser(telegram_id)
            st = (user.get("state") if user else "") or ""
            return st in (PING_WAIT_STATE, PING_RUNNING_STATE)
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        # если сейчас RUNNING — вежливо сообщаем и выходим
        def _busy_reply(chat_id: int):
            telegram_client.sendMessage(chat_id=chat_id, text="⏳ Выполняю предыдущий пинг. Подождите, пожалуйста…")

        # CALLBACKS
        if "callback_query" in update:
            cq = update["callback_query"]
            from_id = cq["from"]["id"]
            chat_id = cq["message"]["chat"]["id"]
            message_id = cq["message"]["message_id"]
            d = (cq.get("data") or "")
            telegram_client.answerCallbackQuery(cq["id"])

            if d == "ping:start":
                db_client.setUserState(from_id, PING_WAIT_STATE)
                db_client.setUserData(from_id, {})
                # просим ввод
                telegram_client.editMessageText(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Введите IPv4-адрес или домен (публичный):",
                )
                return HandlerStatus.STOP

            if d == "ping:repeat":
                db_client.setUserState(from_id, PING_WAIT_STATE)
                # очищаем прошлую цель
                user = db_client.getUser(from_id) or {"data": {}}
                data_obj = user.get("data") or {}
                if isinstance(data_obj, dict) and "last_ping_target" in data_obj:
                    data_obj.pop("last_ping_target", None)
                    db_client.setUserData(from_id, data_obj)
                telegram_client.editMessageText(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Введите IPv4-адрес или домен (публичный):",
                )
                return HandlerStatus.STOP

        # TEXT INPUT
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            st = (db_client.getUser(user_id) or {}).get("state") or ""

            if st == PING_RUNNING_STATE:
                _busy_reply(chat_id)
                return HandlerStatus.STOP

            target = (msg["text"] or "").strip()
            if not _is_valid_host(target):
                telegram_client.sendMessage(
                    chat_id=chat_id,
                    text="Некорректный адрес.\nПример: `8.8.8.8` или `example.com`",
                    parse_mode="Markdown",
                )
                db_client.setUserState(user_id, PING_WAIT_STATE)
                return HandlerStatus.STOP

            # сохраняем, включаем RUNNING, показываем плейсхолдер
            user = db_client.getUser(user_id) or {"data": {}}
            data_obj = user.get("data") or {}
            if not isinstance(data_obj, dict):
                data_obj = {}
            data_obj["last_ping_target"] = target
            db_client.setUserData(user_id, data_obj)
            db_client.setUserState(user_id, PING_RUNNING_STATE)

            telegram_client.sendChatAction(chat_id, "typing")
            placeholder = telegram_client.sendMessage(
                chat_id=chat_id, text=f"⏳ Пингую `{target}`…", parse_mode="Markdown"
            )
            ph_id = placeholder["message_id"]

            res = ping_tool.run(target, count=10, deadline_s=20, per_reply_timeout_s=2)
            text = _format_ping_result(target, res)
            ok = telegram_client.safe_edit_message_text(
                chat_id=chat_id, message_id=ph_id,
                text=text, reply_markup=_result_kb(), parse_mode="Markdown"
            )
            if not ok:
                telegram_client.sendMessage(chat_id=chat_id, text=text, reply_markup=_result_kb(), parse_mode="Markdown")

            db_client.setUserState(user_id, "")
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

def _result_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Повторить", "callback_data": "ping:repeat"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }
