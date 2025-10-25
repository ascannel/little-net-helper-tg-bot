from littleNetHelper.long_polling import startLongPolling
from littleNetHelper.handlers.db_handler import UpdateDB
from littleNetHelper.dispatcher import Dispatcher
from littleNetHelper.handlers import getHandlers

if __name__ == "__main__":
    try:
        dispatcher = Dispatcher()
        dispatcher.addHandlers(*getHandlers())
        startLongPolling(dispatcher)
    except KeyboardInterrupt:
        print("\nbb")