import asyncio
import json
from typing import Optional
from abc import ABC, abstractmethod
import aiohttp
import requests
import sys
from pathlib import Path
from base.util import Util
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.base import EmbeddingBase
from loguru import logger


class LlamaCppEmbedding(EmbeddingBase):
    def __init__(self):
        super().__init__()

    async def embed(self, text):
        """
        Get the embedding for the given text using OpenAI.

        Args:
            text (str): The text to embed.

        Returns:
            list: The embedding vector.
        """
        try:
            return await Util().embedding(text)
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None

# Example usage
if __name__ == "__main__":
    embedder = LlamaCppEmbedding()
    embedding_vector = asyncio.run(embedder.embed("Your sample text here"))
    logger.debug(embedding_vector)
    logger.debug(len(embedding_vector))

