import os
import re
import signal
import sys
import threading
import webbrowser
from time import sleep
import httpx
from loguru import logger
import requests
import argparse

import yaml

from base.util import Util
from core import core


path = os.path.join(Util().root_path(), 'config')
core_config_file_path = os.path.join(path, 'core.yml')
user_config_file_path = os.path.join(path, 'user.yml')


def run_onboard():
    """Interactive onboarding: walk through workspace_dir, LLM, channels, skills; update core.yml."""
    if not os.path.isfile(core_config_file_path):
        print("Config not found:", core_config_file_path)
        return
    config = read_config(core_config_file_path)
    root = Util().root_path()
    print("HomeClaw onboarding — update core config (press Enter to keep current).\n")
    # workspace_dir
    current = config.get("workspace_dir") or "config/workspace"
    val = input(f"Workspace directory [{current}]: ").strip()
    if val:
        config["workspace_dir"] = val
    # main_llm
    local_models = config.get("local_models") or []
    cloud_models = config.get("cloud_models") or []
    llm_opts = [f"local_models/{m['id']}" for m in local_models if m.get("id")] + [f"cloud_models/{m['id']}" for m in cloud_models if m.get("id")]
    current_llm = config.get("main_llm") or ""
    if llm_opts:
        print("Available main LLM refs:")
        for i, ref in enumerate(llm_opts, 1):
            print(f"  {i}. {ref}")
        choice = input(f"Main LLM (1-{len(llm_opts)}) or Enter to keep [{current_llm}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(llm_opts):
            config["main_llm"] = llm_opts[int(choice) - 1]
    # embedding_llm
    if llm_opts:
        current_emb = config.get("embedding_llm") or ""
        choice = input(f"Embedding LLM (1-{len(llm_opts)}) or Enter to keep [{current_emb}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(llm_opts):
            config["embedding_llm"] = llm_opts[int(choice) - 1]
    # use_skills (default True; always on)
    current_skills = config.get("use_skills", True)
    val = input(f"Enable skills (y/n) [{'y' if current_skills else 'n'}]: ").strip().lower()
    if val in ("y", "yes"):
        config["use_skills"] = True
    elif val in ("n", "no"):
        config["use_skills"] = False
    if config.get("use_skills", True):
        current_sd = config.get("skills_dir") or "skills"
        val = input(f"Skills directory [{current_sd}]: ").strip()
        if val:
            config["skills_dir"] = val
    # use_tools (default True; always on)
    current_tools = config.get("use_tools", True)
    val = input(f"Enable tool layer (y/n) [{'y' if current_tools else 'n'}]: ").strip().lower()
    if val in ("y", "yes"):
        config["use_tools"] = True
    elif val in ("n", "no"):
        config["use_tools"] = False
    Util().update_yaml_preserving_comments(core_config_file_path, config)
    print("Config saved. Run 'python -m main doctor' to check connectivity, or 'python -m main start' to start.")


def run_doctor():
    """Check config, connectivity, and LLM reachability; report issues."""
    issues = []
    ok = []
    root = Util().root_path()
    if not os.path.isfile(core_config_file_path):
        issues.append("core.yml not found at " + core_config_file_path)
        for s in issues:
            print("Issue:", s)
        return
    try:
        config = read_config(core_config_file_path)
    except Exception as e:
        issues.append("Failed to load core.yml: " + str(e))
        for s in issues:
            print("Issue:", s)
        return
    ok.append("core.yml loaded")
    # workspace_dir
    ws_dir = config.get("workspace_dir") or "config/workspace"
    ws_path = os.path.join(root, ws_dir) if not os.path.isabs(ws_dir) else ws_dir
    if os.path.isdir(ws_path):
        ok.append("workspace_dir exists: " + ws_dir)
    else:
        issues.append("workspace_dir missing or not a directory: " + ws_dir)
    # skills_dir (skills always on)
    if config.get("use_skills", True):
        sd = config.get("skills_dir") or "skills"
        sd_path = os.path.join(root, sd) if not os.path.isabs(sd) else sd
        if os.path.isdir(sd_path):
            ok.append("skills_dir exists: " + sd)
        else:
            issues.append("skills_dir missing or not a directory: " + sd)
    # LLM connectivity (requires Util().get_core_metadata() to be loaded)
    try:
        meta = Util().get_core_metadata()
        # If main or embedding is local (llama.cpp), check that llama-server binary is findable (project folder or PATH)
        main_type = Util()._effective_main_llm_type()
        emb_type = Util()._effective_embedding_llm_type()
        if main_type == "local" or emb_type == "local":
            try:
                from llm.llama_cpp_platform import resolve_llama_server
                exe_path, folder = resolve_llama_server(root)
                if exe_path is not None:
                    if folder == "path":
                        ok.append("llama-server found on PATH (e.g. winget/brew/nix)")
                    else:
                        ok.append("llama-server found: llama.cpp-master/{}/".format(folder))
                else:
                    issues.append(
                        "llama-server not found. Use Guide step 4: copy binary into llama.cpp-master/<platform>/ "
                        "or install via winget/brew/nix so it is on PATH (see https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md)"
                    )
            except Exception as e:
                issues.append("llama-server check failed: " + str(e))
        main_ok = Util().check_main_model_server_health(timeout=10)
        if main_ok:
            ok.append("main_llm reachable: " + (meta.main_llm or ""))
        else:
            issues.append("main_llm not reachable (health check failed): " + (meta.main_llm or ""))
        emb_ok = Util().check_embedding_model_server_health(timeout=10)
        if emb_ok:
            ok.append("embedding_llm reachable: " + (meta.embedding_llm or ""))
        else:
            issues.append("embedding_llm not reachable (health check failed): " + (meta.embedding_llm or ""))
    except Exception as e:
        issues.append("LLM health check error: " + str(e))
    print("Doctor report:")
    for s in ok:
        print("  OK:", s)
    for s in issues:
        print("  Issue:", s)
    if not issues:
        print("All checks passed.")


def read_config(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    return config


def _safe_shutdown_config():
    """Return (shutdown_url, host, port) for Core shutdown/ready. Never raises; uses defaults on any error."""
    try:
        if not os.path.isfile(core_config_file_path):
            return ("http://127.0.0.1:9000/shutdown", "127.0.0.1", 9000)
        cfg = read_config(core_config_file_path)
        port = int(cfg.get("port", 9000) or 9000)
        host = (cfg.get("host") or "0.0.0.0").strip()
        shutdown_host = "127.0.0.1" if host == "0.0.0.0" else host
        return (f"http://{shutdown_host}:{port}/shutdown", shutdown_host, port)
    except Exception:
        return ("http://127.0.0.1:9000/shutdown", "127.0.0.1", 9000)


def _has_public_connect_config():
    """True if core_public_url or pinggy.token is set (so we can show QR/connect). Never raises."""
    try:
        if not os.path.isfile(core_config_file_path):
            return False
        cfg = read_config(core_config_file_path)
        if (cfg.get("core_public_url") or "").strip():
            return True
        pinggy_cfg = cfg.get("pinggy") or {}
        if (pinggy_cfg.get("token") or "").strip():
            return True
        return False
    except Exception:
        return False

def write_config(file_path, config):
    with open(file_path, 'w', encoding='utf-8') as file:
        yaml.safe_dump(config, file, default_flow_style=False, sort_keys=False)
        
def get_core_config():
    core_config = read_config(core_config_file_path)
    name = core_config['name']
    host = core_config['host']
    port = core_config['port']
    mode = core_config['mode']
    main_llm = core_config.get('main_llm', '')
    embedding_llm = core_config.get('embedding_llm', '')
    local_models = core_config.get('local_models') or []
    cloud_models = core_config.get('cloud_models') or []
    llm_options = [f"local_models/{m['id']}" for m in local_models if m.get('id')] + [f"cloud_models/{m['id']}" for m in cloud_models if m.get('id')]
    if not llm_options and (main_llm or embedding_llm):
        llm_options = [x for x in [main_llm, embedding_llm] if x]
    return (name, host, port, mode, main_llm, embedding_llm, llm_options)


def update_core_config(host, port, mode, main_llm, embedding_llm):
    Util().update_yaml_preserving_comments(core_config_file_path, {
        'host': host,
        'port': port,
        'mode': mode,
        'main_llm': main_llm,
        'embedding_llm': embedding_llm,
    })
    return "Configuration updated successfully!"


def account_exists():
    # Implement logic to check for an existing account
    # Return True if account exists, False otherwise
    homeclaw_account = Util().get_homeclaw_account()
    email = homeclaw_account.email_user
    password = homeclaw_account.email_pass
    if email and len(email) > 0 and password and len(password) > 0:
        #logger.debug(f"Account exists: {email}")
        return True
    else:
        #logger.debug("Account does not exist")
        return False

def register_user():
    email_inputted = False
    email = None
    verified_email = None
    while not email_inputted:
        email = input("Enter your email address for receiving verification code(输入一个有效的邮件地址，用来接收验证码):\n")
        if not is_valid_email(email):
            print("Invalid email format. Please enter a valid email address.(输入一个有效的邮件地址，用来接收验证码)\n")
            continue
        verified_email = input("Enter your email address again for verification(再次输入你的邮件地址): ")
        if email != verified_email:
            print("Emails do not match. Please try again.(两次输入的邮件地址不一致，请重新输入)")
            continue

        email_inputted = True

    ret, text = send_verification_code(email)
    if not ret:
        print(text)
        return False
    print(text)
    for i in range(3):
        code = input("Enter the verification code you received(输入你收到的验证码): ")
        print("Verifying(验证)...")
        ret, text = create_account(email, code)
        if not ret:
            print("Verification failed. Please try again.(验证失败，请重试)")
            continue
        print(text)
        return True


# Function to check email format
def is_valid_email(email_addr):
    # Simple regex for validating an email address
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if re.fullmatch(regex, email_addr):
        return True
    else:
        return False

def send_verification_code(email):
    # First, verify the email format
    if not is_valid_email(email):
        return False, "Invalid email format. Please enter a valid email address.(输入一个有效的邮件地址，用来接收验证码)"
    
    # URL of the API endpoint
    url = "http://mail.homeclaw.ai:3000/send_verification"
    
    # Data to be sent in the request
    data = {
        'email': email
    }
    
    # Headers, if required (e.g., API keys, Content-Type)
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        # Sending a POST request to the endpoint
        response = requests.post(url, json=data, headers=headers)
        #logger.debug(f"Response code: {response.status_code} - {response.text}")
        if response.status_code == 200:
            #logger.debug(f"Sending verification code to {email}")
            return True, "Verification code sent to your email.(验证码已发送到你的邮箱)"
        else:
            # Handle different response codes accordingly
            return False,  "Failed to send verification code.(发送验证码失败)"
    except Exception as e:
        #logger.debug(f"An error occurred: {e}")
        return False, "An error occurred while sending the verification code.(发送验证码时发生错误)"

def create_account(email, code):
    # URL of the API endpoint
    url = "http://mail.homeclaw.ai:3000/create_user"
    
    # Data to be sent in the request, using the provided email and code
    data = {
        "email": email,
        "verificationCode": code
    }
    
    # Headers specifying that the request body is JSON
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        # Sending a POST request to the endpoint
        response = requests.post(url, json=data, headers=headers)
        
        # Check the response status code to determine if the request was successful
        if response.status_code == 200 or response.status_code == 201:
            # Assuming a successful response code means the account was created successfully
            #logger.debug(f"Account created for ) {response.json()['user']['email']}, {response.json()['user']['password']}")

            homeclaw_account = Util().get_homeclaw_account()
            homeclaw_account.email_user = response.json()['user']['email']
            homeclaw_account.email_pass = response.json()['user']['password']
            Util().email_account = homeclaw_account
            Util().save_homeclaw_account()
            return True, "Account created successfully. Welcome to HomeClaw!（账户创建成功，欢迎使用HomeClaw！）"
        else:
            # If the response code is not 200, assume verification failed
            return False, "Verification failed. Please try again.（验证失败，请重试）"
    except Exception as e:
        # Catch any exceptions that occur during the request and report them
        return False, f"An error occurred(发生错误): {e}"


def _ollama_llm_path():
    """Path to llm config file (e.g. config/llm.yml). Uses core.yml llm_config_file if set."""
    try:
        core_cfg = read_config(core_config_file_path)
        llm_file = (core_cfg.get("llm_config_file") or "").strip() or "llm.yml"
        if os.path.isabs(llm_file):
            return llm_file
        return os.path.join(path, llm_file)
    except Exception:
        return os.path.join(path, "llm.yml")


def run_ollama_list(host: str, port: int):
    """Print Ollama models from GET /api/tags. Never raises."""
    from llm import ollama_client
    models = ollama_client.list_models(host=host, port=port)
    if not models:
        print("No models found (is Ollama running at {}:{}?).".format(host, port))
        return
    print("Ollama models ({}:{}):".format(host, port))
    for m in models:
        name = m.get("name") or m.get("model") or ""
        size = m.get("size")
        size_str = "{} MB".format(round(size / (1024 * 1024))) if isinstance(size, (int, float)) else ""
        print("  {}  {}".format(name, size_str).strip())


def run_ollama_pull(model_name: str, host: str, port: int):
    """Pull model via POST /api/pull. Never raises."""
    from llm import ollama_client
    print("Pulling {} from {}:{}...".format(model_name, host, port))
    def on_status(chunk):
        s = chunk.get("status") or ""
        if s:
            print("  {}".format(s))
    ok = ollama_client.pull_model(model_name, host=host, port=port, on_status=on_status)
    if ok:
        print("Done.")
    else:
        print("Pull failed or timed out (check Ollama is running).")


def run_ollama_set_main(model_name: str):
    """Ensure local_models has an Ollama entry for model_name, set main_llm_local and main_llm_mode to local. Never raises."""
    from llm import ollama_client
    model_name = (model_name or "").strip()
    if not model_name:
        print("Usage: python -m main ollama set-main <model_name>")
        return
    llm_path = _ollama_llm_path()
    if not os.path.isfile(llm_path):
        print("llm config not found: {} (create it or set main_llm in core.yml).".format(llm_path))
        return
    try:
        meta = Util().get_core_metadata()
        host, port = ollama_client.get_default_host_port(meta)
    except Exception:
        host, port = ollama_client.DEFAULT_OLLAMA_HOST, ollama_client.DEFAULT_OLLAMA_PORT
    entry_id = ollama_client.sanitize_ollama_id(model_name)
    entry = {
        "id": entry_id,
        "type": "ollama",
        "alias": model_name,
        "path": model_name,
        "host": host,
        "port": port,
        "capabilities": ["Chat"],
    }
    try:
        llm_data = read_config(llm_path)
    except Exception:
        llm_data = {}
    local_models = list(llm_data.get("local_models") or [])
    found = False
    for i, m in enumerate(local_models):
        if isinstance(m, dict) and m.get("id") == entry_id:
            local_models[i] = entry
            found = True
            break
    if not found:
        local_models.append(entry)
    updates = {
        "local_models": local_models,
        "main_llm_local": "local_models/{}".format(entry_id),
        "main_llm_mode": "local",
    }
    try:
        Util().update_yaml_preserving_comments(llm_path, updates)
        print("Set main_llm_local to local_models/{} (Ollama {}). Restart Core to use.".format(entry_id, model_name))
    except Exception as e:
        logger.warning("Failed to write {}: {}", llm_path, e)
        print("Failed to update config: {}.".format(e))


def run_core() -> threading.Thread:
    """Start the same Core as core/core.py (core.main) in a background thread.
    So `python -m main start` and `python core/core.py` both run the same Core server."""
    thread = threading.Thread(target=core.main, daemon=True)
    thread.start()
    return thread


def run_portal(open_browser=True):
    """Start the Portal server (config and onboarding). Bind 127.0.0.1 only. Optionally open browser when ready. Ctrl+C to stop."""
    try:
        import uvicorn
        from portal.app import app
        from portal.config import get_host, get_port
    except Exception as e:
        logger.exception("Failed to load Portal: %s", e)
        sys.exit(1)
    host = get_host()
    port = get_port()
    base_url = "http://{}:{}".format(host, port)
    ready_url = base_url + "/ready"

    def open_browser_when_ready():
        if not open_browser:
            return
        for _ in range(30):
            try:
                r = httpx.get(ready_url, timeout=1.0)
                if r is not None and r.status_code == 200:
                    try:
                        webbrowser.open(base_url)
                        print("Opened browser to {}\n".format(base_url))
                    except Exception:
                        print("Portal: {}\n".format(base_url))
                    break
            except Exception:
                pass
            sleep(0.5)

    print("Starting HomeClaw Portal at {}\n".format(base_url))
    # Run uvicorn in main thread so Ctrl+C shuts down cleanly; browser opener in background.
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\nPortal stopped.")


def start(open_browser=True):
    """Start Core only. Optionally open the launcher page (/ui) with WebChat and Control UI links. Ctrl+C to stop.
    All logic is defensive: config/HTTP/browser failures never crash; shutdown is always attempted on exit."""
    shutdown_url, shutdown_host, core_port = _safe_shutdown_config()
    ui_url = f"http://{shutdown_host}:{core_port}/ui"
    ready_url = f"http://{shutdown_host}:{core_port}/ready"

    def _do_shutdown():
        try:
            httpx.get(shutdown_url, timeout=2.0)
        except Exception:
            pass

    def shutdown_on_signal(signum, frame):
        try:
            print("\nShutting down... (Ctrl+C) 正在关闭...")
            _do_shutdown()
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)

    try:
        signal.signal(signal.SIGINT, shutdown_on_signal)
    except Exception:
        pass

    core_thread = None
    try:
        core_thread = run_core()
        if core_thread is None:
            logger.error("run_core() returned None")
            sys.exit(1)
        print("Starting HomeClaw Core... (启动 HomeClaw Core...)\n")
        max_wait_s = 90
        poll_interval_s = 3
        ready = False
        for elapsed in range(0, max_wait_s, poll_interval_s):
            try:
                r = httpx.get(ready_url, timeout=2.0)
                if r is not None and r.status_code == 200:
                    ready = True
                    print(f"Core running at http://{shutdown_host}:{core_port}")
                    print("Use Companion app or channels to chat. Press Ctrl+C to stop.\n")
                    break
            except Exception:
                pass
            if elapsed + poll_interval_s < max_wait_s:
                try:
                    sleep(poll_interval_s)
                except Exception:
                    pass
        if not ready:
            print(f"Core starting (or check {ready_url})\n")
        # Only open browser when core_public_url or pinggy.token is set (so we don't pop up QR/connect when neither is set)
        if open_browser and _has_public_connect_config():
            try:
                webbrowser.open(ui_url)
                print(f"Opened launcher (WebChat / Control UI): {ui_url}\n")
            except Exception:
                try:
                    print(f"Launcher: {ui_url}\n")
                except Exception:
                    pass
        if core_thread is not None:
            try:
                core_thread.join()
            except Exception:
                pass
    except Exception as e:
        logger.exception(e)
        try:
            _do_shutdown()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HomeClaw — local-first AI assistant")
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "onboard", "doctor", "ollama", "portal"],
        help="start (default): run Core; onboard: wizard; doctor: check config; ollama: list/pull/set-main Ollama models; portal: run Portal server (config and onboarding)",
    )
    parser.add_argument(
        "ollama_action",
        nargs="?",
        help="ollama subcommand: list, pull <name>, set-main <name>",
    )
    parser.add_argument(
        "ollama_name",
        nargs="?",
        help="Ollama model name (for pull and set-main)",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="do not open the browser when starting Core or Portal",
    )
    args = parser.parse_args()
    try:
        if args.command == "ollama":
            from llm import ollama_client
            action = (args.ollama_action or "list").strip().lower()
            meta = None
            try:
                meta = Util().get_core_metadata()
            except Exception:
                pass
            host, port = ollama_client.get_default_host_port(meta)
            if action == "list":
                run_ollama_list(host, port)
            elif action == "pull":
                name = (args.ollama_name or "").strip()
                if not name:
                    print("Usage: python -m main ollama pull <model_name>")
                else:
                    run_ollama_pull(name, host, port)
            elif action == "set-main":
                name = (args.ollama_name or "").strip()
                run_ollama_set_main(name)
            else:
                print("Usage: python -m main ollama {list|pull <name>|set-main <name>}")
        elif args.command == "portal":
            run_portal(open_browser=not args.no_open_browser)
        elif args.command == "onboard":
            run_onboard()
        elif args.command == "doctor":
            run_doctor()
        else:
            start(open_browser=not args.no_open_browser)
    except KeyboardInterrupt:
        try:
            print("\nShutting down... (Ctrl+C) 正在关闭...")
            shutdown_url, _, _ = _safe_shutdown_config()
            try:
                httpx.get(shutdown_url, timeout=2.0)
            except Exception:
                pass
        except Exception:
            pass
        try:
            sys.exit(0)
        except Exception:
            os._exit(0)
    except Exception as e:
        logger.exception(e)
        sys.exit(1)
