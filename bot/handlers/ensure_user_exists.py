from bot.db_client import ensureUserExists
from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus


class EnsureUserExists(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        return "message" in update and "from" in update["message"]

    def handle(self, update: dict, state: str = "", data: dict | None = None) -> HandlerStatus:
        telegram_id = update["message"]["from"]["id"]
        ensureUserExists(telegram_id)
        return HandlerStatus.CONTINUE