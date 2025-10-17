from abc import ABC, abstractmethod

class Handler(ABC):
    @abstractmethod
    def canHandle(self, update: dict) -> bool: ...

    @abstractmethod
    def handle(self, update: dict) -> bool:
        """
        return options:
        - true signal for dispatchr to continue processing;
        - false - signal for dispatcher to stop processing
        """
        pass
