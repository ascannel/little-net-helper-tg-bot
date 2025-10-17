from botDispatcher.handler import Handler

class Dispatcher:
    def __init__(self) -> None:
        self._handlers : list[Handler] = []

    def addHandler(self, *handlers: Handler) -> None:
        for handler in handlers:
            self._handlers.append(handler)

    def dispatch(self, update: dict) -> None:
        for handler in self._handlers:
            if handler.canHandle(update):
                signal = handler.handle(update)
                if not signal:
                    break