import littleNetHelper.db_client
from littleNetHelper.handlers.handler import Handler
from littleNetHelper.handlers.handler_status import HandlerStatus

class UpdateDB(Handler):
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        return True

    def handle(self, update: dict, state: str = "", data: dict | None = None) -> HandlerStatus:
        littleNetHelper.db_client.persistUpdates([update])
        return HandlerStatus.CONTINUE