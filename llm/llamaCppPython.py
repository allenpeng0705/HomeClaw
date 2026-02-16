'''
from http.client import HTTPResponse
import os
from types import FrameType
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from llama_cpp import Llama, LlamaGrammar
from loguru import logger
from base.util import Util
from base.base import ChatRequest, EmbeddingRequest
from contextlib import asynccontextmanager

class LlamaCppPython:
    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        #await register_with_core()
        logger.debug("LLamaCppPython service lifespan started!")
        yield
        #self.uvicorn_server.should_exit = True
        logger.debug("LLamaCppPython service lifespan end!")
        try:
            # Do some deinitialization
            pass
        except:
            pass
        
        
    def __init__(self):
        self.app = FastAPI()
        self.llm = None
        self.embedding = False
        self._setup_routes()
    
    
    def initialize_llm(self, model_path, chat_format='chatml-function-calling', embedding=False, verbose=False, n_gpu_layers=99, n_ctx=2048):
        full_path = os.path.join(Util().models_path(), model_path)
        self.embedding = embedding
        if n_gpu_layers != 0:    
            self.llm = Llama(model_path = full_path, 
                            n_gpu_layers = n_gpu_layers, 
                            n_ctx = n_ctx, 
                            chat_format = chat_format, 
                            verbose = verbose,  
                            embedding = embedding,
                            )
        else:
            self.llm = Llama(model_path = full_path, 
                            n_ctx = n_ctx, 
                            chat_format = chat_format, 
                            verbose = verbose,  
                            embedding = embedding,
                            )

    
    def _setup_routes(self):
        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            logger.error(f"Validation error: {exc} for request: {await request.body()}")
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors(), "body": exc.body},
            ) 
    

        @self.app.post("/v1/chat/completions")
        async def chat_completion(request: ChatRequest):
            try:
                grammar: LlamaGrammar = None
                if request.extra_body is not None and "grammar" in request.extra_body:
                    grammar = LlamaGrammar.from_string(request.extra_body["grammar"])
                result = self.llm.create_chat_completion_openai_v1(messages=request.messages, 
                                                                     tools=request.tools, 
                                                                     tool_choice=request.tool_choice,
                                                                     temperature=0.2,
                                                                     repeat_penalty=1.2,
                                                                     grammar=grammar
                                                                     )
                json_result = result.to_json()
                return JSONResponse(content=json_result, media_type="application/json")
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})            


        # This embedding function always give word embedding, not sentence embedding, deprecated!
        @self.app.post("/v1/embeddings")
        async def embedding(request: EmbeddingRequest):
            try:
                embeddings = self.llm.embed(request.input) # List[str]
                return embeddings #List[List[float]]
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})
            
            
    def __exit__(self, exc_type, exc_value, traceback):
        self.llm = None
'''