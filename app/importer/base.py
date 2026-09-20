from abc import ABC, abstractmethod
from typing import List, Generator
from app.services.messages import NormalizedMessage

class HistorySourceAdapter(ABC):
    @abstractmethod
    def parse_messages(self, source_path: str) -> Generator[NormalizedMessage, None, None]:
        """Yield NormalizedMessage objects from the given source file."""
        pass
