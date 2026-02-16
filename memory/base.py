from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class VectorStoreBase(ABC):

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        
    @abstractmethod
    def create_col(self, name, vector_size, distance):
        """Create a new collection."""
        pass

    @abstractmethod
    def insert(self, name, vectors, payloads=None, ids=None):
        """Insert vectors into a collection."""
        pass

    @abstractmethod
    def search(self, name, query, limit=5, filters=None):
        """Search for similar vectors."""
        pass

    @abstractmethod
    def delete(self, name, vector_id):
        """Delete a vector by ID."""
        pass

    @abstractmethod
    def update(self, name, vector_id, vector=None, payload=None):
        """Update a vector and its payload."""
        pass

    @abstractmethod
    def get(self, name, vector_id):
        """Retrieve a vector by ID."""
        pass

    @abstractmethod
    def list_cols(self):
        """List all collections."""
        pass

    @abstractmethod
    def delete_col(self, name):
        """Delete a collection."""
        pass

    @abstractmethod
    def col_info(self, name):
        """Get information about a collection."""
        pass


class EmbeddingBase(ABC):
    """Initialized a base embedding class

    :param config: Embedding configuration option class, defaults to None
    :type config: Optional[BaseEmbedderConfig], optional
    """

    def __init__(self):
        pass

    @abstractmethod
    async def embed(self, text):
        """
        Get the embedding for the given text.

        Args:
            text (str): The text to embed.

        Returns:
            list: The embedding vector.
        """
        pass


class LLMBase(ABC):
    def __init__(self):
        pass

    @abstractmethod
    async def generate_response(self,
                                messages: List[Dict[str, str]],
                                tools: Optional[List[Dict]] = None,
                                tool_choice: str = "auto",
                                functions: Optional[List] = None,
                                function_call: Optional[str] = None
                                ):
        """
        Generate a response based on the given messages.

        Args:
            messages (list): List of message dicts containing 'role' and 'content'.

        Returns:
            str: The generated response.
        """
        pass


class MemoryBase(ABC):

    @abstractmethod
    async def add(
        self,
        data: str,
        user_name=None,
        user_id=None,
        agent_id=None,
        run_id=None,
        metadata=None,
        filters=None,
        prompt=None,
    ):
        pass

    @abstractmethod
    async def search(
        self, query, user_name=None, user_id=None, agent_id=None, run_id=None, limit=100, filters=None
    ):
        pass


    @abstractmethod
    def get(self, memory_id):
        """
        Retrieve a memory by ID.

        Args:
            memory_id (str): ID of the memory to retrieve.

        Returns:
            dict: Retrieved memory.
        """
        pass

    @abstractmethod
    def get_all(self):
        """
        List all memories.

        Returns:
            list: List of all memories.
        """
        pass

    @abstractmethod
    def update(self, memory_id, data):
        """
        Update a memory by ID.

        Args:
            memory_id (str): ID of the memory to update.
            data (dict): Data to update the memory with.

        Returns:
            dict: Updated memory.
        """
        pass

    @abstractmethod
    def delete(self, memory_id):
        """
        Delete a memory by ID.

        Args:
            memory_id (str): ID of the memory to delete.
        """
        pass


    @abstractmethod       
    def delete_all(self, user_name=None, user_id=None, agent_id=None, run_id=None):
        pass


    @abstractmethod
    def history(self, memory_id):
        """
        Get the history of changes for a memory by ID.

        Args:
            memory_id (str): ID of the memory to get history for.

        Returns:
            list: List of changes for the memory.
        """
        pass

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def chat(self, query):
        pass
