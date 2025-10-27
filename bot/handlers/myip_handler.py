# bot/handlers/myip_handler.py
from __future__ import annotations

from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus
from bot import telegram_client, db_client
from bot.net_tools import myip as myip_tool

MYIP_RUNNING = "MYIP_RUNNING"


def _result_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔁 Повторить", "callback_data": "myip:repeat"}],
            [{"text": "🏠 Меню", "callback_data": "menu"}],
        ]
    }


class MessageMyIP(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        if "callback_query" in update:
            d = (update["callback_query"].get("data") or "")
            return d.startswith("myip:")
        if "message" in update and "text" in update["message"]:
            # перехватываем любые сообщения, пока идёт запрос
            telegram_id = update["message"]["from"]["id"]
            user = db_client.getUser(telegram_id)
            st = (user.get("state") if user else "") or ""
            return st == MYIP_RUNNING
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        def _busy(chat_id: int):
            telegram_client.sendMessage(chat_id=chat_id, text="⏳ Определяю внешний IP. Подождите, пожалуйста…")

        # Если пользователь что-то написал, пока мы «заняты»
        if "message" in update and "text" in update["message"]:
            chat_id = update["message"]["chat"]["id"]
            _busy(chat_id)
            return HandlerStatus.STOP

        # CALLBACKS
        cq = update["callback_query"]
        from_id = cq["from"]["id"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        d = (cq.get("data") or "")
        telegram_client.answerCallbackQuery(cq["id"])

        if d in ("myip:start", "myip:repeat"):
            db_client.setUserState(from_id, MYIP_RUNNING)
            telegram_client.sendChatAction(chat_id, "typing")
            # показываем плейсхолдер и потом редактируем
            telegram_client.safe_edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text="⏳ Определяю внешний IP…"
            )

            res = myip_tool.lookup_v4(timeout=4.0)
            if res.ok and res.ip:
                text = f"Внешний IP этого бота: `{res.ip}`"
            else:
                text = f"Не удалось определить внешний IP: {res.error or 'ошибка'}"

            ok = telegram_client.safe_edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text, parse_mode="Markdown", reply_markup=_result_kb()
            )
            if not ok:
                telegram_client.sendMessage(
                    chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=_result_kb()
                )
            db_client.setUserState(from_id, "")
            return HandlerStatus.STOP

        return HandlerStatus.CONTINUE
