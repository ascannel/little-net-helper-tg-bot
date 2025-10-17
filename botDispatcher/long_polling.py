from botDispatcher.dispatcher import Dispatcher
import botDispatcher.telegram_client
import time

def startLongPolling(dispatcher: Dispatcher) -> None:
        nextUpdateOffset = 0
        while True:
            updates = botDispatcher.telegram_client.getUpdates(offset=nextUpdateOffset)
            for update in updates:
                nextUpdateOffset = max(nextUpdateOffset, update["update_id"]+1)
                dispatcher.dispatch(update)
                print(".", end="")
            time.sleep(1)