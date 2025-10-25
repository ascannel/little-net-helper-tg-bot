import json
from abc import ABC, abstractmethod
from bot.handlers.handler_status import HandlerStatus

class Handler(ABC):
    @abstractmethod
    def canHandle(self, update: dict, state: str = "", data: dict | None = None) -> bool:
        pass

    @abstractmethod
    def handle(self, update: dict, state: str = "", data: dict | None = None) -> HandlerStatus:
        """
        return options:
        - true signal for dispatchr to continue processing;
        - false - signal for dispatcher to stop processing
        """
        pass
