import bot.db_client
from bot.handlers.handler import Handler
from bot.handlers.handler_status import HandlerStatus

class UpdateDB(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        return True

    def handle(self, update: dict, state: str = "", data: dict | None = None) -> HandlerStatus:
        bot.db_client.persistUpdates([update])
        return HandlerStatus.CONTINUE