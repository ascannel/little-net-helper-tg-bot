import botDispatcher.db_client
from botDispatcher.handler import Handler


class UpdateDB(Handler):
    def canHandle(self, update: dict) -> bool:
        return True

    def handle(self, update: dict) -> bool:
        botDispatcher.db_client.persistUpdates([update])
        return True