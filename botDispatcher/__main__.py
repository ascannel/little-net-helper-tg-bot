from botDispatcher.handlers.echo import MessageText
from botDispatcher.handlers.picture import MessagePhoto
from botDispatcher.long_polling import startLongPolling
from botDispatcher.handlers.db_handler import UpdateDB
from botDispatcher.dispatcher import Dispatcher

if __name__ == "__main__":
    try:
        dispatcher = Dispatcher()
        dispatcher.addHandler(UpdateDB())
        dispatcher.addHandler(MessageText())
        dispatcher.addHandler(MessagePhoto())
        startLongPolling(dispatcher)
    except KeyboardInterrupt:
        print("\nbb")