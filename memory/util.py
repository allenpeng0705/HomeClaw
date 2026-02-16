ADD_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "add_memory",
        "description": "Add a memory",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Data to add to memory"}
            },
            "required": ["data"],
        },
    },
}

UPDATE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "update_memory",
        "description": "Update memory provided ID and data",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "memory_id of the memory to update",
                },
                "data": {
                    "type": "string",
                    "description": "Updated data for the memory",
                },
            },
            "required": ["memory_id", "data"],
        },
    },
}

DELETE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_memory",
        "description": "Delete memory by memory_id",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "memory_id of the memory to delete",
                }
            },
            "required": ["memory_id"],
        },
    },
}

from memory.prompts import UPDATE_MEMORY_PROMPT, ADD_MEMORY_PROMPT
def get_update_memory_prompt(existing_memories, memory, template=UPDATE_MEMORY_PROMPT):
    return template.format(existing_memories=existing_memories, memory=memory)


def get_update_memory_messages(existing_memories, memory):
    return [
        {
            "role": "user",
            "content": get_update_memory_prompt(existing_memories, memory),
        },
    ]

def get_add_memory_prompt(memory, template=ADD_MEMORY_PROMPT):
    return template.format(memory=memory)


def get_add_memory_messages(memory):
    return [
        {
            "role": "user",
            "content": get_add_memory_prompt(memory),
        },
    ]

