from __future__ import annotations
import json
import traceback

from littleNetHelper.handlers.handler import Handler
from littleNetHelper.handlers.handler_status import HandlerStatus
from littleNetHelper.db_client import getUser

class Dispatcher:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def _get_telegram_id_from_update(self, update: dict) -> int | None:
        if "message" in update:
            return update["message"]["from"]["id"]
        if "callback_query" in update:
            return update["callback_query"]["from"]["id"]
        return None

    def addHandlers(self, *handlers: Handler) -> None:
        self._handlers.extend(handlers)

    def dispatch(self, update: dict) -> None:
        telegram_id = self._get_telegram_id_from_update(update)
        user = getUser(telegram_id) if telegram_id else None
        state = (user.get("state") if user else "") or ""
        data_raw = user.get("data") if user else None
        try:
            user_data = json.loads(data_raw) if isinstance(data_raw, str) and data_raw else (data_raw or {})
        except Exception:
            user_data = {}

        for handler in self._handlers:
            if handler.canHandle(update):
                try:
                    res = handler.handle(update, state, user_data)
                except Exception:
                    traceback.print_exc()
                    break

                if res is False or res == HandlerStatus.STOP:
                    break