from abc import ABC
from typing import Optional, ClassVar, Dict, Any
from pydantic import BaseModel, Field, model_validator, field_validator
import os

from base.util import Util
memory_dir = Util().data_path()

class MemoryItem(BaseModel):
    id: str = Field(..., description="The unique identifier for the text data")
    memory: str = Field(
        ..., description="The memory deduced from the text data"
    )  # TODO After prompt changes from platform, update this
    hash: Optional[str] = Field(None, description="The hash of the memory")
    # The metadata value can be anything and not just string. Fix it
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata for the text data"
    )
    score: Optional[float] = Field(
        None, description="The score associated with the text data"
    )
    created_at: Optional[str] = Field(
        None, description="The timestamp when the memory was created"
    )
    updated_at: Optional[str] = Field(
        None, description="The timestamp when the memory was updated"
    )


class MemoryConfig(BaseModel):
    history_db_path: str = Field(
        description="Path to the history database",
        default=os.path.join(memory_dir, "memory.db"),
    )
