import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
import litellm
from litellm import (
    acompletion,
    aembedding,
    aimage_generation,
    EmbeddingResponse,
    ImageResponse,
)
from base.util import Util
from base.base import ChatRequest, EmbeddingRequest, ImageGenerationRequest
from contextlib import asynccontextmanager

# Drop unsupported params per provider (latest LiteLLM: https://github.com/BerriAI/litellm)
litellm.drop_params = True


def _response_to_dict(obj: Any) -> dict:
    """Serialize LiteLLM response (Pydantic v2 model_dump or to_json)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if hasattr(obj, "to_json"):
        return json.loads(obj.to_json())
    return dict(obj)


class LiteLLMService:
    
    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        #await register_with_core()
        logger.debug("LiteLLM service lifespan started!")
        yield
        logger.debug("LiteLLM service lifespan end!")
        try:
            # Do some deinitialization
            pass
        except:
            pass
    
    def __init__(self):
        self.app = FastAPI()
        self.num_retries = 2
        self.max_tokens = 2048
        self._setup_routes()
        Util().set_api_key_for_llm()
        #os.environ["OPENAI_API_KEY"] = "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"
 
    def _setup_routes(self):
        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            body = await request.body()
            # Log errors clearly; truncate body if large (e.g. base64 image) to avoid log flood
            body_preview = body[:500].decode("utf-8", errors="replace") + ("..." if len(body) > 500 else "") if body else ""
            logger.error("Validation error: {} | detail: {} | body preview: {}", exc, exc.errors(), body_preview)
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors(), "body": exc.body},
            ) 
    

        @self.app.post("/v1/chat/completions")
        async def chat_completion(request: ChatRequest):
            try:
                model = request.model
                messages = request.messages
                stream = request.stream or False

                kwargs = {
                    "model": model,
                    "messages": messages,
                    "num_retries": self.num_retries,
                    "max_tokens": request.max_tokens or self.max_tokens,
                    "stream": stream,
                }
                # Optional params (LiteLLM drops unsupported via drop_params=True)
                if request.response_format is not None:
                    kwargs["response_format"] = request.response_format
                if request.timeout is not None:
                    kwargs["timeout"] = request.timeout
                if request.tools is not None:
                    kwargs["tools"] = request.tools
                if request.tool_choice is not None:
                    kwargs["tool_choice"] = request.tool_choice
                if request.parallel_tool_calls is not None:
                    kwargs["parallel_tool_calls"] = request.parallel_tool_calls
                if request.temperature is not None:
                    kwargs["temperature"] = request.temperature
                if request.presence_penalty is not None:
                    kwargs["presence_penalty"] = request.presence_penalty
                if request.frequency_penalty is not None:
                    kwargs["frequency_penalty"] = request.frequency_penalty
                if request.seed is not None:
                    kwargs["seed"] = request.seed
                if request.logit_bias is not None:
                    kwargs["logit_bias"] = request.logit_bias
                if request.top_p is not None:
                    kwargs["top_p"] = request.top_p
                if request.n is not None:
                    kwargs["n"] = request.n
                if request.stream_options is not None:
                    kwargs["stream_options"] = request.stream_options
                if request.logprobs is not None:
                    kwargs["logprobs"] = request.logprobs
                if request.top_logprobs is not None:
                    kwargs["top_logprobs"] = request.top_logprobs
                if request.function_call is not None:
                    kwargs["function_call"] = request.function_call
                if request.functions is not None:
                    kwargs["functions"] = request.functions
                if request.extra_body:
                    kwargs["extra_body"] = request.extra_body
                if request.base_url is not None:
                    kwargs["api_base"] = request.base_url
                if request.api_key is not None:
                    kwargs["api_key"] = request.api_key
                if request.api_version is not None:
                    kwargs["api_version"] = request.api_version

                response = await acompletion(**kwargs)

                logger.debug("Response from LiteLLM: {}", type(response).__name__)
                if not stream:
                    return JSONResponse(content=_response_to_dict(response))
                # Async streaming: collect chunks then rebuild (per LiteLLM docs)
                chunks = []
                async for chunk in response:
                    chunks.append(chunk)
                resp = litellm.stream_chunk_builder(chunks, messages=messages)
                return JSONResponse(content=_response_to_dict(resp))
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})            


        @self.app.post("/v1/embeddings")
        async def embedding(request: EmbeddingRequest):
            try:
                kwargs = {
                    "model": request.model,
                    "input": request.input,
                    "timeout": request.timeout,
                }
                if request.input_type is not None:
                    kwargs["input_type"] = request.input_type
                if request.dimensions is not None:
                    kwargs["dimensions"] = request.dimensions
                if request.api_base is not None:
                    kwargs["api_base"] = request.api_base
                if request.api_version is not None:
                    kwargs["api_version"] = request.api_version
                if request.api_key is not None:
                    kwargs["api_key"] = request.api_key
                if request.api_type is not None:
                    kwargs["api_type"] = request.api_type

                response: EmbeddingResponse = await aembedding(**kwargs)
                # OpenAI-format: {"object": "list", "data": [{"embedding": [...]}, ...]}
                return JSONResponse(content=_response_to_dict(response))
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})
            
            
        @self.app.post("/v1/image_generation")
        async def image_generation(request: ImageGenerationRequest):
            try:
                kwargs = {
                    "prompt": request.prompt,
                    "model": request.model,
                    "timeout": request.timeout,
                }
                if request.n is not None:
                    kwargs["n"] = request.n
                if request.quality is not None:
                    kwargs["quality"] = request.quality
                if request.response_format is not None:
                    kwargs["response_format"] = request.response_format
                if request.size is not None:
                    kwargs["size"] = request.size
                if request.style is not None:
                    kwargs["style"] = request.style
                if request.api_base is not None:
                    kwargs["api_base"] = request.api_base
                if request.api_version is not None:
                    kwargs["api_version"] = request.api_version
                if request.api_key is not None:
                    kwargs["api_key"] = request.api_key

                response: ImageResponse = await aimage_generation(**kwargs)
                return JSONResponse(content=_response_to_dict(response))
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})    