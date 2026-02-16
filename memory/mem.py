import hashlib
import json
import re
import uuid
import pytz
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
# Ensure the project root is in the PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.util import (
    ADD_MEMORY_TOOL,
    DELETE_MEMORY_TOOL,
    UPDATE_MEMORY_TOOL,
)
from memory.prompts import MEMORY_DEDUCTION_PROMPT, MEMORY_GRAPH_EXTRACT_PROMPT
#from memory.prompts import MEMORY_PREPROCESSING_PROMPT
from memory.base import MemoryBase, VectorStoreBase, EmbeddingBase, LLMBase

#from memory.setup import setup_config
from memory.util import get_update_memory_messages, get_add_memory_messages
from memory.storage import SQLiteManager
from memory.configs import MemoryItem, MemoryConfig
from loguru import logger
from base.util import Util


# Setup user config
#setup_config()


class Memory(MemoryBase):
    def __init__(self, embedding_model: EmbeddingBase=None, vector_store: VectorStoreBase=None,
                 llm: LLMBase=None, graph_store=None):
        self.config = MemoryConfig()
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.llm = llm
        # Optional graph store (Kuzu/Neo4j). Used in Step 2 for entity/relation extraction. None = no-op.
        self.graph_store = graph_store

        self.db = SQLiteManager(db_path=self.config.history_db_path)
        self.collection_name = self.vector_store.collection_name

    async def add(
        self,
        data,
        user_name=None,
        user_id=None,
        agent_id=None,
        run_id=None,
        metadata=None,
        filters=None,
        prompt=None,
    ):
        """
        Create a new memory.

        Args:
            data (str): Data to store in the memory.
            user_name (str, optional): Name of the user creating the memory. Defaults to None.
            user_id (str, optional): ID of the user creating the memory. Defaults to None.
            agent_id (str, optional): ID of the agent creating the memory. Defaults to None.
            run_id (str, optional): ID of the run creating the memory. Defaults to None.
            metadata (dict, optional): Metadata to store with the memory. Defaults to None.
            filters (dict, optional): Filters to apply to the search. Defaults to None.
            prompt (str, optional): Prompt to use for memory deduction. Defaults to None.

        Returns:
            str: ID of the created memory.
        """
        if metadata is None:
            metadata = {}
        logger.debug(f"#########Data send to embedding: {data}#########")

        filters = filters or {}
        if user_name:
            filters["user_name"] = metadata["user_name"] = user_name
        if user_id:
            filters["user_id"] = metadata["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = metadata["agent_id"] = agent_id
        if run_id:
            filters["run_id"] = metadata["run_id"] = run_id

        ret = []

        # The commented code is using tool calls to add or update memory, but it is not working properly for many models. ignore it for now.
        '''
        if not prompt:
            prompt = MEMORY_DEDUCTION_PROMPT.format(user_input=data, metadata=metadata)
        logger.debug(f"Memory Deduction Prompt: {prompt}")
        extracted_memories = await self.llm.generate_response(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at deducing facts, preferences and memories from unstructured text.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        logger.debug(f"Extracted memories: {extracted_memories}\n")
        
        embedding_result = await self.embedding_model.embed(data)
        existing_memories = self.vector_store.search(
            query=embedding_result,
            limit=5,
            filters=filters,
        )
        logger.debug(f"Total existing memories: {len(existing_memories)}")
        messages = []
        
        # If find some similar exiting memories, using prompt to check whether they need to be updated or just 
        # need to add the new memory
        if len(existing_memories) > 0:
            existing_memories = [
                MemoryItem(
                    id=mem.id,
                    score=mem.score,
                    metadata=mem.payload,
                    memory=mem.payload["data"],
                )
                for mem in existing_memories
            ]
            serialized_existing_memories = [
                item.model_dump(include={"id", "memory", "score"})
                for item in existing_memories
            ]
            messages = get_update_memory_messages(
                serialized_existing_memories, data
            )

            logger.debug(f"Memory selection function call Messages: {messages}")
            tools = [ADD_MEMORY_TOOL, UPDATE_MEMORY_TOOL]
            response = await self.llm.generate_response(messages=messages, tools=tools)
            tool_calls = response["tool_calls"]
            logger.debug(f"Response with tool calls: {response}")

            if tool_calls:
                # Create a new memory
                available_functions = {
                    "add_memory": self._create_memory_tool,
                    "update_memory": self._update_memory_tool
                }
                for tool_call in tool_calls:
                    function_name = tool_call["name"]
                    if function_name not in available_functions:
                        continue
                    function_to_call = available_functions[function_name]
                    function_args = {'data': data}
                    #function_args = tool_call["arguments"]
                    logger.debug(
                        f"[openai_func] func: {function_name}, args: {function_args}"
                    )

                    # Pass metadata to the function if it requires it
                    function_args["metadata"] = metadata
                    function_result = await function_to_call(**function_args)

                    # Fetch the memory_id from the response
                    ret.append(
                        {
                            "id": function_result,
                            "event": function_name.replace("_memory", ""),
                            "data": function_args.get("data"),
                        }
                    )
                    logger.debug(f"Memory saved!")
                    return ret
        '''
        # If there is no similar memories, just add the new memory
        # If the LLM didn't return tool_call, just add the new memory
        function_result = await self._create_memory_tool(data, metadata)
        ret.append(
            {
                "id": function_result,
                "event": "add",
                "data": data,
            },
        )
        # Step 2: optional graph — extract entities/relations using main LLM and write to graph store
        if getattr(self, "graph_store", None) is not None:
            try:
                await self._extract_and_store_graph(function_result, data)
            except Exception as e:
                logger.debug("Graph extraction skipped or failed: %s", e)
        return ret

    def get(self, memory_id):
        """
        Retrieve a memory by ID.

        Args:
            memory_id (str): ID of the memory to retrieve.

        Returns:
            dict: Retrieved memory.
        """
        memory = self.vector_store.get(vector_id=memory_id)
        if not memory:
            return None

        filters = {
            key: memory.payload[key]
            for key in ["user_name", "user_id", "agent_id", "run_id"]
            if memory.payload.get(key)
        }

        # Prepare base memory item
        memory_item = MemoryItem(
            id=memory.id,
            memory=memory.payload["data"],
            hash=memory.payload.get("hash"),
            created_at=memory.payload.get("created_at"),
            updated_at=memory.payload.get("updated_at"),
        ).model_dump(exclude={"score"})

        # Add metadata if there are additional keys
        excluded_keys = {
            "user_name",
            "user_id",
            "agent_id",
            "run_id",
            "hash",
            "data",
            "created_at",
            "updated_at",
        }
        additional_metadata = {
            k: v for k, v in memory.payload.items() if k not in excluded_keys
        }
        if additional_metadata:
            memory_item["metadata"] = additional_metadata

        result = {**memory_item, **filters}

        return result

    def get_all(self, user_name=None, user_id=None, agent_id=None, run_id=None, limit=100):
        """
        List all memories.

        Returns:
            list: List of all memories.
        """
        filters = {}
        if user_name:
            filters["user_name"] = user_name
        if user_id:
            filters["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = agent_id
        if run_id:
            filters["run_id"] = run_id

        memories = self.vector_store.list(filters=filters, limit=limit)

        excluded_keys = {
            "user_name",
            "user_id",
            "agent_id",
            "run_id",
            "hash",
            "data",
            "created_at",
            "updated_at",
        }
        return [
            {
                **MemoryItem(
                    id=mem.id,
                    memory=mem.payload["data"],
                    hash=mem.payload.get("hash"),
                    created_at=mem.payload.get("created_at"),
                    updated_at=mem.payload.get("updated_at"),
                ).model_dump(exclude={"score"}),
                **{
                    key: mem.payload[key]
                    for key in ["user_name", "user_id", "agent_id", "run_id"]
                    if key in mem.payload
                },
                **(
                    {
                        "metadata": {
                            k: v
                            for k, v in mem.payload.items()
                            if k not in excluded_keys
                        }
                    }
                    if any(k for k in mem.payload if k not in excluded_keys)
                    else {}
                ),
            }
            for mem in memories[0]
        ]

    async def search(
        self, query, user_name=None, user_id=None, agent_id=None, run_id=None, limit=100, filters=None
    ):
        """
        Search for memories.

        Args:
            query (str): Query to search for.
            user_name (str, optional): Name of the user to search for. Defaults to None.
            user_id (str, optional): ID of the user to search for. Defaults to None.
            agent_id (str, optional): ID of the agent to search for. Defaults to None.
            run_id (str, optional): ID of the run to search for. Defaults to None.
            limit (int, optional): Limit the number of results. Defaults to 100.
            filters (dict, optional): Filters to apply to the search. Defaults to None.

        Returns:
            list: List of search results.
        """
        filters = filters or {}
        if user_name:
            filters["user_name"] = user_name
        if user_id:
            filters["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = agent_id
        if run_id:
            filters["run_id"] = run_id

        '''
        prompt = MEMORY_PREPROCESSING_PROMPT
        prompt = prompt.format(text = query.lower())
        messages = []
        messages = [{"role": "system", "content": prompt}] 
        logger.debug("Search Memory Preprocessing using LLM")
        result = await Util().openai_chat_completion(messages=messages)
        logger.debug(f"Search Memory Preprocessing: {query}")
        
        embedding_result = None
        if result:
            logger.debug(f"Search Memory Preprocessed: {result}")
            embedding_result = await self.embedding_model.embed(result) 
        else:
            embedding_result = await self.embedding_model.embed(query)
        '''
        embedding_result = await self.embedding_model.embed(query.lower())
        memories = self.vector_store.search(
            query=embedding_result, limit=limit, filters=filters
        )

        excluded_keys = {
            "user_name",
            "user_id",
            "agent_id",
            "run_id",
            "hash",
            "data",
            "created_at",
            "updated_at",
        }

        for mem in list(memories):
            if mem.score > 0.9:
                memories.remove(mem)

        def _mem_to_item(mem):
            return {
                **MemoryItem(
                    id=mem.id,
                    memory=mem.payload["data"],
                    hash=mem.payload.get("hash"),
                    created_at=mem.payload.get("created_at"),
                    updated_at=mem.payload.get("updated_at"),
                    score=mem.score,
                ).model_dump(),
                **{
                    key: mem.payload[key]
                    for key in ["user_name", "user_id", "agent_id", "run_id"]
                    if key in mem.payload
                },
                **(
                    {
                        "metadata": {
                            k: v
                            for k, v in mem.payload.items()
                            if k not in excluded_keys
                        }
                    }
                    if any(k for k in mem.payload if k not in excluded_keys)
                    else {}
                ),
            }

        result = [_mem_to_item(mem) for mem in memories]

        # Step 3: graph-aware expansion — add related memories via entity graph (1-hop)
        graph = getattr(self, "graph_store", None)
        if graph is not None and result:
            seen_ids = {r["id"] for r in result}
            graph_expand_top = 3
            graph_expand_max = 5
            added = 0
            for item in result[:graph_expand_top]:
                if added >= graph_expand_max:
                    break
                memory_id = item.get("id")
                if not memory_id:
                    continue
                try:
                    node_ids = graph.get_nodes_by_memory_id(memory_id)
                    for node_id in node_ids:
                        if added >= graph_expand_max:
                            break
                        neighbors = graph.get_neighbors(node_id, limit=10)
                        for nb in neighbors:
                            mid = nb.get("memory_id") if isinstance(nb, dict) else None
                            if not mid or mid in seen_ids:
                                continue
                            seen_ids.add(mid)
                            extra = self.vector_store.get(vector_id=mid)
                            if extra is None or not getattr(extra, "payload", None):
                                continue
                            if "data" not in extra.payload:
                                continue
                            if filters and any(extra.payload.get(k) != v for k, v in filters.items()):
                                continue
                            result.append(
                                _mem_to_item(SimpleNamespace(id=mid, payload=extra.payload, score=0.5))
                            )
                            added += 1
                except Exception as e:
                    logger.debug("Graph expansion: %s", e)
            if added:
                logger.debug("Graph-aware search added %d related memories", added)

        return result

    def update(self, memory_id, data):
        """
        Update a memory by ID.

        Args:
            memory_id (str): ID of the memory to update.
            data (dict): Data to update the memory with.

        Returns:
            dict: Updated memory.
        """
        self._update_memory_tool(memory_id, data)
        return {"message": "Memory updated successfully!"}

    def delete(self, memory_id):
        """
        Delete a memory by ID.

        Args:
            memory_id (str): ID of the memory to delete.
        """
        self._delete_memory_tool(memory_id)
        return {"message": "Memory deleted successfully!"}

    def delete_all(self, user_name=None, user_id=None, agent_id=None, run_id=None):
        """
        Delete all memories.

        Args:
            user_name (str, optional): Name of the user to delete memories for. Defaults to None.
            user_id (str, optional): ID of the user to delete memories for. Defaults to None.
            agent_id (str, optional): ID of the agent to delete memories for. Defaults to None.
            run_id (str, optional): ID of the run to delete memories for. Defaults to None.
        """
        filters = {}
        if user_name:
            filters["user_name"] = user_name
        if user_id:
            filters["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = agent_id
        if run_id:
            filters["run_id"] = run_id

        if not filters:
            raise ValueError(
                "At least one filter is required to delete all memories. If you want to delete all memories, use the `reset()` method."
            )

        memories = self.vector_store.list(filters=filters)[0]
        for memory in memories:
            self._delete_memory_tool(memory.id)
        return {"message": "Memories deleted successfully!"}

    def history(self, memory_id):
        """
        Get the history of changes for a memory by ID.

        Args:
            memory_id (str): ID of the memory to get history for.

        Returns:
            list: List of changes for the memory.
        """
        return self.db.get_history(memory_id)

    async def _create_memory_tool(self, data, metadata=None):
        '''
        prompt = MEMORY_PREPROCESSING_PROMPT
        prompt = prompt.format(text = data.lower())
        messages = []
        messages = [{"role": "system", "content": prompt}] 
        logger.debug("Add Memory Preprocessing using LLM")
        result = await Util().openai_chat_completion(messages=messages)
        embeddings = None
        logger.debug(f"Add Memory Preprocessing: {data}")
        if result:
            logger.debug(f"Add Memory Preprocessed: {result}")
            embeddings = await self.embedding_model.embed(result)
        else:
            embeddings = await self.embedding_model.embed(data)
        '''
        embeddings = await self.embedding_model.embed(data.lower())
        memory_id = str(uuid.uuid4())
        metadata = metadata or {}
        metadata["data"] = data
        metadata["hash"] = hashlib.md5(data.encode()).hexdigest()
        metadata["created_at"] = datetime.now(pytz.timezone("US/Pacific")).isoformat()

        self.vector_store.insert(
            vectors=[embeddings],
            ids=[memory_id],
            payloads=[metadata],
        )
        self.db.add_history(
            memory_id, None, data, "ADD", created_at=metadata["created_at"]
        )
        logger.debug(f"#####Created memory with {memory_id}, old_memory=None, memory={data}####")
        return memory_id

    async def _extract_and_store_graph(self, memory_id: str, data: str) -> None:
        """
        Extract entities and relations from memory text using the main LLM, then write to graph store.
        Uses Util().openai_chat_completion() (same model as chat). No separate model required.
        """
        graph = getattr(self, "graph_store", None)
        if graph is None:
            return
        text = (data or "").strip()[:2000]
        if not text:
            return
        prompt = MEMORY_GRAPH_EXTRACT_PROMPT.format(text=text)
        messages = [
            {"role": "system", "content": "You output only valid JSON. No explanation or markdown."},
            {"role": "user", "content": prompt},
        ]
        response = await Util().openai_chat_completion(messages=messages)
        if not response or not isinstance(response, str):
            return
        payload = self._parse_graph_json(response)
        if not payload:
            return
        entities = payload.get("entities") or []
        relations = payload.get("relations") or []
        try:
            graph.init_schema()
        except Exception:
            pass
        seen: set = set()
        for e in entities:
            if not isinstance(e, dict):
                continue
            eid = (e.get("id") or e.get("name") or "").strip()
            if not eid or eid in seen:
                continue
            seen.add(eid)
            graph.add_node(
                eid,
                "Entity",
                {
                    "name": (e.get("name") or eid),
                    "type": (e.get("type") or "thing"),
                    "memory_id": memory_id,
                },
            )
        for r in relations:
            if not isinstance(r, dict):
                continue
            from_id = (r.get("from") or r.get("from_id") or "").strip()
            to_id = (r.get("to") or r.get("to_id") or "").strip()
            label = (r.get("label") or "RELATES_TO").strip() or "RELATES_TO"
            if from_id and to_id and from_id in seen and to_id in seen:
                graph.add_edge(from_id, to_id, label)
        logger.debug("Graph extraction stored for memory_id=%s (%d entities, %d relations)", memory_id, len(entities), len(relations))

    def _parse_graph_json(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON object from LLM response (strip markdown code block if present)."""
        s = (response or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
        if m:
            s = m.group(1).strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    async def _update_memory_tool(self, memory_id, data, metadata=None):
        logger.debug(f"Updating memory with {memory_id} with {data}")
        existing_memory = self.vector_store.get(vector_id=memory_id)
        if existing_memory is None:
            await self._create_memory_tool(data, metadata)
            return

        logger.debug(f"Existing memory: {existing_memory}")
        prev_value = existing_memory.payload.get("data")

        new_metadata = metadata or {}
        new_metadata["data"] = data
        new_metadata["hash"] = existing_memory.payload.get("hash")
        new_metadata["created_at"] = existing_memory.payload.get("created_at")
        new_metadata["updated_at"] = datetime.now(
            pytz.timezone("US/Pacific")
        ).isoformat()

        if "user_name" in existing_memory.payload:
            new_metadata["user_name"] = existing_memory.payload["user_name"]
        if "user_id" in existing_memory.payload:
            new_metadata["user_id"] = existing_memory.payload["user_id"]
        if "agent_id" in existing_memory.payload:
            new_metadata["agent_id"] = existing_memory.payload["agent_id"]
        if "run_id" in existing_memory.payload:
            new_metadata["run_id"] = existing_memory.payload["run_id"]


        embeddings = await self.embedding_model.embed(data)
        self.vector_store.update(
            vector_id=memory_id,
            vector=embeddings,
            payload=new_metadata,
        )

        # Add history
        self.db.add_history(
            memory_id,
            prev_value,
            data,
            "UPDATE",
            created_at=new_metadata["created_at"],
            updated_at=new_metadata["updated_at"],
        )
        logger.debug(f"Updated memory with {memory_id}, old memory={prev_value}, memory={data}")

    def _delete_memory_tool(self, memory_id):
        logger.debug(f"Deleting memory with {memory_id=}")
        existing_memory = self.vector_store.get(vector_id=memory_id)
        prev_value = existing_memory.payload["data"]
        self.vector_store.delete(vector_id=memory_id)
        self.db.add_history(memory_id, prev_value, None, "DELETE", is_deleted=1)
        logger.debug(f"Deleted memory with {memory_id}, memory={prev_value}")

    def reset(self):
        """
        Reset the memory store.
        """
        self.vector_store.delete_col()
        self.db.reset()
        if getattr(self, "graph_store", None) is not None:
            try:
                self.graph_store.reset()
            except Exception as e:
                logger.debug("Graph store reset: %s", e)
        logger.debug("Reset memory store")

    def chat(self, query):
        raise NotImplementedError("Chat function not implemented yet.")
