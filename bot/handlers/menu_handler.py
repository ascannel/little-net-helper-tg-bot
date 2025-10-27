from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus
from bot import telegram_client, db_client

MAIN_MENU_KB = {
    "inline_keyboard": [
        [{"text": "🔁 Ping (ICMP)", "callback_data": "ping:start"}],
        [{"text": "🔎 DNS (nslookup)", "callback_data": "dns:start"}],
        [{"text": "❓ WHOIS", "callback_data": "whois:start"}],
        [{"text": "🔐 TLS info", "callback_data": "tls:start"}], 
        [{"text": "🧭 My IP", "callback_data": "myip:start"}],
    ]
}

class MessageMenu(Handler):
    def canHandle(self, update: dict) -> bool:
        # /start или /menu в личке; либо callback "menu"
        if "message" in update and "text" in update["message"]:
            txt = (update["message"]["text"] or "").strip()
            return txt in ("/start", "/menu")
        if "callback_query" in update:
            return update["callback_query"].get("data") == "menu"
        return False

    def handle(self, update: dict, state: str = "", data=None) -> HandlerStatus:
        if "callback_query" in update:
            cq = update["callback_query"]
            telegram_client.answerCallbackQuery(cq["id"])

            chat_id = cq["message"]["chat"]["id"]
            message_id = cq["message"]["message_id"]
            telegram_client.editMessageText(
                chat_id=chat_id,
                message_id=message_id,
                text="Выберите действие:",
                reply_markup=MAIN_MENU_KB,
            )
        else:
            chat_id = update["message"]["chat"]["id"]
            telegram_client.sendMessage(
                chat_id=chat_id,
                text="Выберите действие:",
                reply_markup=MAIN_MENU_KB,
            )

        # сброс состояния
        if "message" in update:
            telegram_id = update["message"]["from"]["id"]
        else:
            telegram_id = update["callback_query"]["from"]["id"]
        db_client.setUserState(telegram_id, "")
        db_client.setUserData(telegram_id, {})
        return HandlerStatus.STOP