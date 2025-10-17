import botDispatcher.telegram_client
from botDispatcher.handler import Handler

class MessageText(Handler):
    def canHandle(self, update: dict) -> bool:
        return "message" in update and "text" in update["message"]

    def handle(self, update: dict) -> bool:
        botDispatcher.telegram_client.sendMessage(
            chat_id=update["message"]["chat"]["id"],
            text=update["message"]["text"],\
        )
        return False
