from littleNetHelper.db_client import ensureUserExists
from littleNetHelper.handlers.handler import Handler
from littleNetHelper.handlers.handler_status import HandlerStatus


class EnsureUserExists(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        return "message" in update and "from" in update["message"]

    def handle(self, update: dict, state: str = "", data: dict | None = None) -> HandlerStatus:
        telegram_id = update["message"]["from"]["id"]
        ensureUserExists(telegram_id)
        return HandlerStatus.CONTINUE