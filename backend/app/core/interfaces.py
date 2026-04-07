from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IEmbeddingService(ABC):
    @abstractmethod
    async def get_embedding_async(self, text: str) -> List[float]:
        pass

class IVectorSearch(ABC):
    @abstractmethod
    def search_sync(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        pass
        
    @abstractmethod
    async def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def upsert_sync(self, id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
        pass
    @abstractmethod
    def initialize(self) -> bool:
        pass        
        pass

class IAudioPipeline(ABC):
    @abstractmethod
    async def process_audio(self, audio_data: bytes) -> str:
        pass

class IDatabase(ABC):
    @abstractmethod
    def get_collection(self, name: str) -> Any:
        pass

    @abstractmethod
    def is_degraded(self) -> bool:
        pass

    @abstractmethod
    def connect(self) -> None:
        pass
        
    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

class ICacheService(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass
