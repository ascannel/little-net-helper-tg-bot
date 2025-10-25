from bot.long_polling import startLongPolling
from bot.handlers.db_handler import UpdateDB
from bot.dispatcher import Dispatcher
from bot.handlers import getHandlers

if __name__ == "__main__":
    try:
        dispatcher = Dispatcher()
        dispatcher.addHandlers(*getHandlers())
        startLongPolling(dispatcher)
    except KeyboardInterrupt:
        print("\nbb")