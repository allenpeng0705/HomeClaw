from asyncio import subprocess
import multiprocessing
import os
import asyncio
from pathlib import Path
from subprocess import PIPE, Popen
import sys
import threading
from time import sleep
from typing import Dict, List
import uvicorn
import signal
from loguru import logger  # Ensure you import the logger appropriately

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import base
from base.util import Util
from base.base import LLM, Server
#from llm.llamaCppPython import LlamaCppPython
from llm.litellmService import LiteLLMService
from llm.llama_cpp_platform import (
    resolve_llama_server,
    FOLDER_WIN_CUDA,
    FOLDER_LINUX_CUDA,
)

class LLMServiceManager:
    
    _instance = None
    _lock = threading.Lock() 

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(LLMServiceManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance
        
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.llama_cpp_processes = []
            self.apps: List[asyncio.Task] = []
            self.llms: List[LLM] = []
            #self.llm_to_app: Dict[str, asyncio.Task] = {}
            self.gather_task: asyncio.Task = None
            #self.litellm_server_task = None
        
        
    async def start_llama_cpp_process(self, cmd: str, name:str, host:str, port:str):
        """
        Start an LLM process asynchronously and record its details.
        """
        try:
            #process = Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process = await asyncio.to_thread(Popen, cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # shell=True is not necessary here, as we're passing the command as a list of strings.
            # This is safer, as it prevents shell injection attacks.
            
            self.llama_cpp_processes.append({
                'name': name,
                'process': process,
                'host': host,
                'port': port,
            })
            logger.debug(f"Started LLM process on {host}:{port} with PID {process.pid}")
            return process
        except Exception as e:
            logger.error(f"Failed to start LLM process on {host}:{port}: {e}")
            return None


    def stop_llama_cpp_process(self, name:str):
        """
        Stop a specific LLM process asynchronously.
        """
        try:
            for process_info in self.llama_cpp_processes:
                if process_info['name'] == name:
                    process_info['process'].terminate()
                    #await asyncio.to_thread(process_info['process'].wait)
                    self.llama_cpp_processes.remove(process_info)
                    logger.debug(f"Stopped LLM process on {process_info['host']}:{process_info['port']}")
                    return
        except Exception as e:
            logger.error(f"Failed to stop LLM process on {process_info['host']}:{process_info['port']}: {e}")


    def stop_all_llama_cpp_processes(self):
        """
        Stop all LLM processes.
        """
        for process_info in list(self.llama_cpp_processes):
            self.stop_llama_cpp_process(process_info['name'])
        self.llama_cpp_processes = []


    def get_llama_cpp_processes(self):
        """
        Get the list of all running LLM processes.
        """
        return self.llama_cpp_processes
    
    
    def get_llama_cpp_process_names(self):
        """
        Get the list of names of all running LLM processes.
        """
        return [process_info['name'] for process_info in self.llama_cpp_processes]

    def start_async_coroutine(self, coroutine):
        """Function to run the coroutine in a new event loop."""
        def run(loop, coroutine):
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coroutine)
        
        # Create a new event loop
        new_loop = asyncio.new_event_loop()
        # Create and start a new Thread with the loop and coroutine
        t = threading.Thread(target=run, args=(new_loop, coroutine))
        t.start()
        #t.join() 
    
    def _llama_cpp_opts(self):
        """Read llama.cpp server options from config/core.yml (llama_cpp section)."""
        opts = getattr(Util().get_core_metadata(), "llama_cpp", None) or {}
        return opts

    def start_llama_cpp_server(self, name: str, host: str, port: int, model_path: str,
                              ctx_size: str = None, predict: str = None, temp: str = None,
                              threads: str = None, n_gpu_layers: str = None,
                              chat_format: str = None, verbose: str = None, function_calling: bool = True, pooling: bool = False,
                              mmproj_path: str = None, lora_paths: List[str] = None, lora_base_path: str = None,
                              opts_override: Dict = None):
        """
        Start llama.cpp server. Parameters not passed are read from config/core.yml under llama_cpp.
        When opts_override is set (e.g. llama_cpp.embedding), it is merged over base llama_cpp opts.
        For vision models: pass mmproj_path (full path to projector .gguf).
        For LoRA: pass lora_paths (list of full paths; one or more adapters) and optionally lora_base_path.
        """
        opts = dict(self._llama_cpp_opts())
        if opts_override:
            opts.update(opts_override)

        def _str(v):
            return str(v) if v is not None else None

        ctx_size = _str(ctx_size) or _str(opts.get("ctx_size")) or ("0" if pooling else "32768")
        predict = _str(predict) or _str(opts.get("predict")) or "8192"
        temp = _str(temp) or _str(opts.get("temp")) or "0.8"
        threads = _str(threads) or _str(opts.get("threads")) or "8"
        n_gpu_layers = _str(n_gpu_layers) or _str(opts.get("n_gpu_layers")) or "99"
        verbose = verbose if verbose is not None else opts.get("verbose", False)
        repeat_penalty = _str(opts.get("repeat_penalty")) or "1.5"
        if chat_format is None:
            chat_format = opts.get("chat_format")
        if function_calling and opts.get("function_calling") is False:
            function_calling = False

        logger.debug(f"model path {model_path}")
        thread_num = multiprocessing.cpu_count()
        model_sub_path = os.path.normpath(model_path)
        full_model_path = os.path.join(Util().models_path(), model_sub_path)
        logger.debug(f"Full model path: {full_model_path}")

        root_path = Util().root_path()
        exe_path, folder = resolve_llama_server(root_path)
        if exe_path is None or folder is None:
            logger.error(
                "llama-server not found. Put the binary in llama.cpp-master/<platform>/ (mac, win_cpu, win_cuda, linux_cpu, linux_cuda). See llama.cpp-master/README.md"
            )
            return
        use_gpu = folder in (FOLDER_WIN_CUDA, FOLDER_LINUX_CUDA)
        threads_val = threads if (thread_num is None or thread_num > 8) else str(thread_num)

        cmd_list = [
            str(exe_path),
            "-m", full_model_path,
            "--ctx-size", ctx_size,
            "--predict", predict,
            "--temp", temp,
            "--threads", threads_val,
            "--host", host,
            "--port", str(port),
        ]
        if mmproj_path:
            if os.path.isfile(mmproj_path):
                cmd_list.extend(["--mmproj", mmproj_path])
                logger.info("Vision model: llama.cpp server started with --mmproj {}", mmproj_path)
            else:
                logger.warning(
                    "mmproj file not found ({}), llama.cpp server will start WITHOUT vision. "
                    "Put the mmproj .gguf in the model path or fix the mmproj path in config/core.yml.",
                    mmproj_path,
                )
        lora_list = lora_paths if isinstance(lora_paths, list) else ([lora_paths] if lora_paths else [])
        for lp in lora_list:
            if lp and os.path.isfile(lp):
                cmd_list.extend(["--lora", lp])
        if lora_list and lora_base_path and os.path.isfile(lora_base_path):
            cmd_list.extend(["--lora-base", lora_base_path])
        if lora_list:
            logger.debug("LoRA: paths={}, lora_base={}", lora_list, lora_base_path)
        if verbose not in (False, "false", "False"):
            cmd_list.append("--verbose")
        if not pooling:
            cmd_list.extend(["--repeat-penalty", repeat_penalty])
        if function_calling:
            cmd_list.append("--jinja")
            logger.debug("Function calling is enabled.")
        if pooling:
            cmd_list.extend(["--embedding", "--pooling", "cls", "-ub", "8192"])
            logger.debug("Pooling is enabled.")
        if chat_format:
            cmd_list.extend(["--chat_format", str(chat_format)])
        if use_gpu:
            cmd_list.extend(["--n-gpu-layers", n_gpu_layers])

        try:
            logger.debug("llama.cpp server: {} (folder: {}), cmd: {}", exe_path, folder, " ".join(cmd_list))
            process = Popen(cmd_list, stdout=PIPE, stderr=PIPE)
            self.llama_cpp_processes.append({
                'name': name,
                'process': process,
                'host': host,
                'port': port,
            })
            logger.debug(
                "Started LLM process on {}:{} with PID {} (folder: {}), model: {}",
                host, port, process.pid, folder, os.path.basename(full_model_path),
            )
        except asyncio.CancelledError:
            logger.debug("Shutting down the daemon.")
        except Exception as e:
            logger.exception("Failed to start llama.cpp server: {}", e)
            

    def run_embedding_llm(self):
        try:
            embedding_model_path, llm_name, llm_type, host, port = Util().embedding_llm()
            
            if llm_name in self.llms:
                logger.debug(f"LLM {llm_name} is already running")
                return

            if llm_type == 'local':
                entry, _ = Util()._get_model_entry(Util().get_core_metadata().embedding_llm)
                mmproj_path, lora_paths, lora_base_path = (None, [], None)
                if entry:
                    mmproj_path, lora_paths, lora_base_path = self._resolve_local_extra_paths(entry)
                llama_cpp = getattr(Util().get_core_metadata(), "llama_cpp", None) or {}
                embedding_opts = llama_cpp.get("embedding") if isinstance(llama_cpp, dict) else None
                if not isinstance(embedding_opts, dict):
                    embedding_opts = {}
                # ctx_size: use embedding.ctx_size if set, else 0 so llama.cpp uses the model's native n_ctx
                emb_ctx = embedding_opts.get("ctx_size")
                ctx_size = str(emb_ctx) if emb_ctx is not None else "0"
                self.start_llama_cpp_server(
                    llm_name, host, port, embedding_model_path,
                    ctx_size=ctx_size, function_calling=False, pooling=True,
                    mmproj_path=mmproj_path, lora_paths=lora_paths or None, lora_base_path=lora_base_path,
                    opts_override=embedding_opts,
                )
            elif llm_type == 'litellm':
                pass
            self.llms.append(llm_name)
            logger.debug("Running Embedding services!")
        except asyncio.CancelledError:
            logger.debug("LLM for embeddingwas cancelled.")
        
            
    def _resolve_local_extra_paths(self, entry: Dict) -> tuple:
        """Resolve mmproj, lora, lora_base from local_models entry. lora can be string or array. Returns (mmproj_path, lora_paths_list, lora_base_path)."""
        models_base = Util().models_path()
        mmproj = (entry.get("mmproj") or "").strip() if isinstance(entry.get("mmproj"), str) else ""
        mmproj_path = os.path.join(models_base, os.path.normpath(mmproj)) if mmproj else None
        lora_raw = entry.get("lora")
        if isinstance(lora_raw, list):
            lora_paths = [os.path.join(models_base, os.path.normpath(str(p).strip())) for p in lora_raw if str(p).strip()]
        elif isinstance(lora_raw, str) and lora_raw.strip():
            lora_paths = [os.path.join(models_base, os.path.normpath(lora_raw.strip()))]
        else:
            lora_paths = []
        lora_base = (entry.get("lora_base") or "").strip() if isinstance(entry.get("lora_base"), str) else ""
        lora_base_path = os.path.join(models_base, os.path.normpath(lora_base)) if lora_base else None
        return mmproj_path, lora_paths, lora_base_path

    def run_main_llm(self, pooling:bool = False):
        llm_path,  llm_name, llm_type, host, port = Util().main_llm()

        if llm_name in self.llms:
            logger.debug(f"LLM {llm_name} is already running")
            return

        if llm_type == 'local':
            entry, _ = Util()._get_model_entry(Util().get_core_metadata().main_llm)
            mmproj_path, lora_paths, lora_base_path = (None, [], None)
            if entry:
                mmproj_path, lora_paths, lora_base_path = self._resolve_local_extra_paths(entry)
            self.start_llama_cpp_server(
                llm_name, host, port, llm_path, pooling=pooling,
                mmproj_path=mmproj_path, lora_paths=lora_paths or None, lora_base_path=lora_base_path,
            )
            self.llms.append(llm_name)      
            #self.apps.append(self.start_llama_cpp_server(name, host, port, path))
            logger.debug(f"Running Main LLM Server {llm_name} on {host}:{port}")
        elif llm_type == 'litellm':
            self.run_litellm_service()
            self.llms.append(llm_name)
            logger.debug(f"Running Main LLM Server {llm_name} on {host}:{port}")

    def run_classifier_llm(self):
        """When main_llm_mode == 'mix' and hybrid_router.slm.enabled, start the classifier model on its port (same mechanism as main LLM)."""
        meta = Util().get_core_metadata()
        mode = (getattr(meta, "main_llm_mode", None) or "").strip().lower()
        if mode != "mix":
            return
        hr = getattr(meta, "hybrid_router", None) or {}
        if not isinstance(hr, dict):
            return
        slm = hr.get("slm")
        if not isinstance(slm, dict) or not slm.get("enabled"):
            return
        model_ref = (slm.get("model") or "").strip()
        if not model_ref:
            return
        entry, mtype = Util()._get_model_entry(model_ref)
        if entry is None or mtype != "local":
            logger.debug("Classifier LLM: model ref {} not found or not local, skipping.", model_ref)
            return
        _, raw_id = Util()._parse_model_ref(model_ref)
        name = raw_id or model_ref
        if name in self.llms:
            logger.debug("Classifier LLM {} is already running", name)
            return
        host = entry.get("host", "127.0.0.1")
        port = int(entry.get("port", 5089))
        path_rel = (entry.get("path") or "").strip()
        if not path_rel:
            logger.warning("Classifier LLM entry has no path, skipping.")
            return
        models_base = Util().models_path()
        full_path = os.path.join(models_base, os.path.normpath(path_rel))
        if not os.path.isfile(full_path):
            logger.warning("Classifier model file not found: {}, skipping start. Put the GGUF in the models folder.", full_path)
            return
        mmproj_path, lora_paths, lora_base_path = self._resolve_local_extra_paths(entry)
        self.start_llama_cpp_server(
            name, host, port, path_rel, pooling=False,
            mmproj_path=mmproj_path, lora_paths=lora_paths or None, lora_base_path=lora_base_path,
        )
        self.llms.append(name)
        logger.debug("Running classifier LLM {} on {}:{}", name, host, port)

    '''       
    async def start_llama_cpp_python(self, host, port, model_path, 
                                     chat_format='chatml-function-calling', 
                                     embedding=False, verbose=False, n_gpu_layers=99, n_ctx=2048):
        # Initialize the LLM service
        llm_service = LlamaCppPython()
        llm_service.initialize_llm(model_path, chat_format=chat_format, 
                                   embedding=embedding, verbose=verbose, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx)

        # Run the FastAPI app
        if host == '127.0.0.1' or host == 'localhost':
            host = '0.0.0.0'
        config = uvicorn.Config(llm_service.app, host=host, port=port, log_level="info")
        server = Server(config)
        logger.debug(f"Running Llama.cpp.python on {host}:{port}, model is {model_path}")
        try:
            await server.serve()
            logger.debug("LLM from llama.cpp.python server done.")
        except asyncio.CancelledError:
            logger.debug("LLM from llama.cpp.python was cancelled.")


    def run_llama_cpp_python_llm(self, name: str, chat_format='chatml-function-calling', 
                                     embedding=False, verbose=False, n_gpu_layers=99, n_ctx=2048):
        try:
            llm = Util().get_llm(name)
            name = llm.name
            host = llm.host
            port = llm.port
            path = llm.path
            
            if llm in self.llms:
                logger.debug(f"LLM {name} is already running")
                return None
            
            # Initialize and start the Uvicorn server for the LLM service
            server_task = asyncio.create_task(self.start_llama_cpp_python(host, port, path,chat_format=chat_format, 
                                    embedding=embedding, verbose=verbose, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx))
            #self.apps.append(server_task)
            self.llm_to_app[name] = server_task
            self.llms.append(llm)
            #self.apps.append(self.start_llama_cpp_server(name, host, port, path))
            logger.debug(f"Running LLM Server {path} on {host}:{port}")
            return server_task
        except asyncio.CancelledError:
            logger.debug("LLM from llama.cpp.python was cancelled.")
            # Handle any cleanup if necessary
    '''   

       
    async def start_litellm_service(self):
        try:
            # Initialize the LLM service
            litellm_service = LiteLLMService()
            _, model, type, host, port = llm = Util().main_llm()
            # Run the FastAPI app
            if host == '127.0.0.1' or host == 'localhost':
                host = '0.0.0.0'
            config = uvicorn.Config(litellm_service.app, host=host, port=port, log_level="info")
            server = Server(config)
            logger.debug(f"Running litellm on {host}:{port}, model is {model}")
            try:
                await server.serve()
            except asyncio.CancelledError:
                logger.debug("LLM from liteLLM was cancelled.")
        except Exception as e:
            logger.error(f"Unexpected error in start_litellm_service: {e}")

        
        
    def run_litellm_service(self):
        try:
            _, model, type, host, port = Util().main_llm()
            logger.debug(f"Try to run LLM Server {model} on {host}:{port}")
            if model in self.llms:
                logger.debug(f"LLM {model} is already running")
                return None
            
            coroutine = self.start_litellm_service()
            self.start_async_coroutine(coroutine)
            #self.litellm_server_task = asyncio.create_task(self.start_litellm_service())

            #self.llm_to_app[name] = server_task
            logger.debug(f"Running litellm Service {model} on {host}:{port}")
        except asyncio.CancelledError:
            logger.debug("LLM from litellm service was cancelled.")


    

    def main_llm(self):
        return Util().main_llm()

    def embedding_llm(self):
        return Util().embedding_llm()
    
    async def add_and_start_new_app(self, app):
        logger.debug("Adding app.")
        if not asyncio.iscoroutinefunction(app) and not isinstance(app, asyncio.Task):
            raise ValueError("App must be a coroutine function or asyncio.Task")

        if asyncio.iscoroutinefunction(app):
            task = asyncio.create_task(app())
        elif isinstance(app, asyncio.Task):
            task = app
        else:
            raise ValueError("Invalid app type")

        self.apps.append(task)
        
        try:
            result = await task
            logger.debug(f"New app completed with result: {result}")
        except asyncio.CancelledError:
            logger.debug(f"New app cancelled successfully.")
        except Exception as e:
            logger.error(f"Exception in new app: {e}")
            
  
    async def start_all_apps(self):
        #await asyncio.gather(*self.apps)
        #for app in self.apps:
        try:
            logger.debug("Starting all apps.")
            if len(self.apps) > 0:
                self.gather_task = asyncio.gather(*self.apps, return_exceptions=True)
                await self.gather_task
    
        except asyncio.CancelledError:
            logger.debug("Gathering task was cancelled.")
        except Exception as e:
            logger.exception(e)
   
            
    # if you run some LLMs after the start_all_apps(), you can call this function
    # This function will gather self.apps again
    async def restart_all_apps(self):
        try:
            logger.debug("Restarting all apps.")
            # Cancel the current gather task
            if self.gather_task and not self.gather_task.done():
                self.gather_task.cancel()
            
            #start all the apps again
            await self.start_all_apps()
        except asyncio.CancelledError:
            logger.debug("All the apps were cancelled.")
        except Exception as e:
            logger.error(f"Unexpected error in restart_all_apps: {e}")
        
    
    def stop_all_apps(self):
        """
        Stop all running apps.
        """
        try:
            logger.debug("LLM Service Stopping all apps...")
            if len(self.apps) == 0:
                return
            for app in self.apps:
                app.cancel()
            self.apps = []
            # Because all the apps are in unicorn server, when Ctrl + C is pressed, it will exit all the apps.
            logger.debug("All apps have been stopped.")
        except asyncio.CancelledError:
            logger.debug("All the apps were cancelled.")
        except Exception as e:
            logger.error(f"Unexpected error in stop_all_apps: {e}")
     
        
    def exit_gracefully(self, signum, frame):
        try:
            logger.debug("LLM Service CTRL+C received, shutting down...")
            # End the main thread
            #asyncio.run(self.stop_all_llama_cpp_processes())
            self.stop_all_llama_cpp_processes()
            self.stop_all_apps()
            sys.exit(0)
        except asyncio.CancelledError:
            logger.debug("All the apps were cancelled.")
        except Exception as e:
            logger.error(f"Unexpected error in stop_all_apps: {e}")
        
    
    def __enter__(self):
        if threading.current_thread() == threading.main_thread():
            try:
                #logger.debug("channel initializing..., register the ctrl+c signal handler")
                signal.signal(signal.SIGINT, self.exit_gracefully)
                signal.signal(signal.SIGTERM, self.exit_gracefully)
            except Exception as e:
                # It's a good practice to at least log the exception
                # logger.error(f"Error setting signal handlers: {e}")
                pass

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass
        
    # This funciton is for testing    
    def run(self):
        try:
            self.run_embedding_llm()
            self.run_main_llm()
            self.run_classifier_llm()
        except Exception as e:
            logger.exception(f"Unexpected error in run: {e}")

            
    
if __name__ == "__main__":   
    try:
        llm_manager = LLMServiceManager()
        llm_manager.run()
        #asyncio.run(llm_manager.run())
    except KeyboardInterrupt:
        logger.debug("Ctrl+C received, shutting down...")
        # End the main thread
        llm_manager.stop_all_llama_cpp_processes()
        #llm_manager.stop_all_apps()
    except Exception as e:
        logger.exception(e)