import logging
import time
import traceback

from bot.dispatcher import Dispatcher
import bot.telegram_client

def startLongPolling(dispatcher: Dispatcher) -> None:
    next_offset = 0
    while True:
        try:
            updates = bot.telegram_client.getUpdates(
                offset=next_offset, timeout=50, limit=100
            )
        except Exception as e:
            logging.warning("getUpdates failed: %s", e)
            time.sleep(2)
            continue
        for upd in updates:
            next_offset = max(next_offset, upd["update_id"] + 1)
            try:
                dispatcher.dispatch(upd)
            except Exception:
                traceback.print_exc()
                pass