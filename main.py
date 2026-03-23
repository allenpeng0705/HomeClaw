import json
import os
import re
import signal
import sys
import threading
import webbrowser
from time import sleep

# Ensure project root is on path so "import core" works when started from another cwd.
_project_root = os.path.abspath(os.path.normpath(os.path.dirname(os.path.abspath(__file__))))
if _project_root and _project_root not in sys.path:
    sys.path.insert(0, _project_root)
# Cognee is vendored in vendor/cognee; add it so "import cognee" finds vendor/cognee/cognee.
_vendor_cognee = os.path.join(_project_root, "vendor", "cognee")
if os.path.isdir(_vendor_cognee) and _vendor_cognee not in sys.path:
    sys.path.insert(0, _vendor_cognee)

# LiteLLM: use local model cost map only (avoids "Failed to fetch remote model cost map... timed out" warning when offline/slow).
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# Apply Instructor/litellm patch before any code imports instructor or cognee (fixes cognify "coroutine not callable" with local LLM).
try:
    from memory.instructor_patch import apply_instructor_patch_for_local_llm
    apply_instructor_patch_for_local_llm()
except Exception:
    pass

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


def run_peer_invite_create(ttl_seconds: int = 900) -> None:
    """POST /api/peer/invite/create on local Core (requires Core running and auth key from core.yml if auth_enabled)."""
    if not os.path.isfile(core_config_file_path):
        print("Config not found:", core_config_file_path)
        return
    cfg = read_config(core_config_file_path)
    port = int(cfg.get("port", 9000) or 9000)
    host = (cfg.get("host") or "127.0.0.1").strip()
    connect_host = "127.0.0.1" if host in ("0.0.0.0", "::", "[::]") else host
    url = f"http://{connect_host}:{port}/api/peer/invite/create"
    headers = {"Content-Type": "application/json"}
    if bool(cfg.get("auth_enabled", False)):
        ak = (cfg.get("auth_api_key") or "").strip()
        if ak:
            headers["X-API-Key"] = ak
    try:
        r = requests.post(url, json={"ttl_seconds": int(ttl_seconds)}, headers=headers, timeout=30)
        print(r.status_code, r.text)
    except Exception as e:
        print("Request failed:", e)


def run_peer_import(file_path: str, api_key_env: str = "") -> None:
    """Merge a peer entry from JSON/YAML (e.g. saved invite-consume response) into config/peers.yml."""
    from base.peer_registry import merge_peer_entry, peer_dict_from_import_payload

    path = os.path.abspath(os.path.expanduser(file_path.strip()))
    if not os.path.isfile(path):
        print("File not found:", path)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        if path.lower().endswith(".json"):
            data = json.loads(raw_text)
        else:
            data = yaml.safe_load(raw_text)
    except Exception as e:
        print("Failed to read config:", e)
        sys.exit(2)
    peer = peer_dict_from_import_payload(data)
    if not peer:
        print("No peer object found: need top-level 'peer' { ... } or flat instance_id + base_url + inbound_user_id")
        sys.exit(2)
    if (api_key_env or "").strip():
        peer["api_key_env"] = api_key_env.strip()
    ok, msg = merge_peer_entry(peer)
    print(msg)
    if not ok:
        sys.exit(1)


def run_peer_list() -> None:
    """Print configured peers from config/peers.yml as JSON."""
    from base.peer_registry import load_peers_list

    print(json.dumps(load_peers_list(), indent=2, ensure_ascii=False))


def run_peer_invite_accept(
    peer_base_url: str,
    invite_id: str,
    token: str,
    my_instance_id: str = "",
    my_display_name: str = "",
) -> None:
    """POST /api/peer/invite/consume on the peer Core (no API key; invite token is the secret)."""
    url = peer_base_url.rstrip("/") + "/api/peer/invite/consume"
    body = {
        "invite_id": invite_id.strip(),
        "invite_token": token.strip(),
        "instance_id": (my_instance_id or "").strip(),
        "display_name": (my_display_name or "").strip(),
        "initiator_base_url": "",
        "initiator_inbound_user_id": "",
    }
    try:
        from base.peer_registry import load_instance_identity

        ident = load_instance_identity()
        body["initiator_base_url"] = (ident.get("public_base_url") or "").strip().rstrip("/")
        body["initiator_inbound_user_id"] = (ident.get("pairing_inbound_user_id") or "").strip()
        if not body["instance_id"]:
            body["instance_id"] = (ident.get("instance_id") or "").strip()
        if not body["display_name"]:
            body["display_name"] = (ident.get("display_name") or "").strip()
    except Exception:
        pass
    try:
        r = requests.post(url, json=body, timeout=30)
        print(r.status_code, r.text)
    except Exception as e:
        print("Request failed:", e)


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
        # external_skills_dir (optional; e.g. for converted OpenClaw skills)
        ext_sd = (config.get("external_skills_dir") or "").strip()
        if ext_sd:
            ext_path = os.path.join(root, ext_sd) if not os.path.isabs(ext_sd) else ext_sd
            if os.path.isdir(ext_path):
                ok.append("external_skills_dir exists: " + ext_sd)
        # Optional: ClawHub CLI for OpenClaw skills search/install
        try:
            from base.clawhub_integration import clawhub_available
            if clawhub_available():
                ok.append("clawhub CLI found on PATH (OpenClaw skills search/install)")
            else:
                ok.append("clawhub CLI not found (optional; install OpenClaw/ClawHub to search & import skills)")
        except Exception:
            ok.append("clawhub CLI check skipped (optional)")
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
    # Optional multi-instance peer files (config/instance_identity.yml, config/peers.yml)
    try:
        from base.peer_registry import (
            INSTANCE_IDENTITY_FILENAME,
            PEERS_FILENAME,
            load_instance_identity,
            load_peers_list,
        )

        cfg_dir = path
        id_path = os.path.join(cfg_dir, INSTANCE_IDENTITY_FILENAME)
        if os.path.isfile(id_path):
            ident = load_instance_identity(cfg_dir)
            if (ident.get("instance_id") or "").strip():
                ok.append("instance_identity.yml: instance_id=" + (ident.get("instance_id") or "").strip())
            else:
                issues.append(
                    "instance_identity.yml exists but instance_id is empty "
                    "(set a stable id for pairing / peer_call)"
                )
        else:
            ok.append("instance_identity.yml absent (optional; see config/instance_identity.yml.example)")
        peers_path = os.path.join(cfg_dir, PEERS_FILENAME)
        if os.path.isfile(peers_path):
            plist = load_peers_list(cfg_dir)
            if plist:
                ok.append("peers.yml: {} peer(s) configured".format(len(plist)))
                for p in plist:
                    pid = (p.get("instance_id") or "?").strip()
                    if not (p.get("inbound_user_id") or "").strip():
                        issues.append("peers.yml peer '{}': inbound_user_id missing".format(pid))
                    envn = (p.get("api_key_env") or "").strip()
                    if envn and not (os.environ.get(envn) or "").strip():
                        issues.append(
                            "peers.yml peer '{}': api_key_env {} is not set in the environment".format(pid, envn)
                        )
                any_https = any(
                    str((p.get("base_url") or "")).strip().lower().startswith("https:")
                    for p in plist
                )
                if any_https:
                    pub = ""
                    if os.path.isfile(id_path):
                        pub = (load_instance_identity(cfg_dir).get("public_base_url") or "").strip()
                    if not pub:
                        issues.append(
                            "peers.yml: peer(s) use https:// but instance_identity.yml has no public_base_url "
                            "(set public_base_url so pairing returns a stable URL for peer_call / peers.yml)"
                        )
            else:
                ok.append("peers.yml present but peers list is empty")
        else:
            ok.append("peers.yml absent (optional; see config/peers.yml.example)")
    except Exception as e:
        issues.append("Peer / instance identity check failed: " + str(e))
    # Federated user messaging: peer_instance_id on friends requires federation_enabled
    try:
        if not bool(config.get("federation_enabled", False)):
            warned = False
            for u in Util().get_users() or []:
                for f in getattr(u, "friends", None) or []:
                    if (getattr(f, "peer_instance_id", None) or "").strip():
                        issues.append(
                            "Federation: a user friend has peer_instance_id but federation_enabled is false in core.yml "
                            "(enable federation or remove peer_instance_id)."
                        )
                        warned = True
                        break
                if warned:
                    break
    except Exception as e:
        issues.append("Federation friend check failed: " + str(e))
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


def _run_core_capture_exception(exc_holder):
    """Run core.main() and store any exception in exc_holder (e.g. a list) so the main thread can report it."""
    try:
        core.main()
    except BaseException as e:
        exc_holder.append(e)


def run_core() -> threading.Thread:
    """Start the same Core as core/core.py (core.main) in a background thread.
    So `python -m main start` and `python core/core.py` both run the same Core server.
    If Core exits with an exception, it is stored and reported after join()."""
    exc_holder = []
    thread = threading.Thread(target=_run_core_capture_exception, args=(exc_holder,), daemon=True)
    thread._exc_holder = exc_holder
    thread.start()
    return thread


def run_portal(open_browser=True):
    """Start the Portal server (config and onboarding). Bind host from PORTAL_HOST (default 0.0.0.0). Optionally open browser when ready. Ctrl+C to stop."""
    # Ensure project root is first on path so portal imports work from any cwd.
    _root = os.path.abspath(os.path.normpath(os.path.dirname(os.path.abspath(__file__))))
    if _root and (not sys.path or sys.path[0] != _root):
        sys.path.insert(0, _root)
    try:
        import uvicorn
        from portal.app import app
        from portal.config import get_host, get_port
    except Exception as e:
        logger.exception("Failed to load Portal: {}", e)
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
            # Give Core time to release the port so restart or Slack channel can bind/reach 9000
            sleep(2)
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
        # Use join(timeout) in a loop so the main thread periodically returns to Python and can run
        # the Ctrl+C handler. An infinite join() would block the main thread in a C-level wait, so
        # the signal handler would never run (e.g. when Core is blocked on vision LLM).
        if core_thread is not None:
            try:
                while core_thread.is_alive():
                    core_thread.join(timeout=1.0)
            except Exception:
                pass
            exc_holder = getattr(core_thread, "_exc_holder", None)
            if exc_holder and len(exc_holder) > 0:
                err = exc_holder[0]
                print("\nCore exited with an error:", file=sys.stderr)
                try:
                    import traceback
                    traceback.print_exception(type(err), err, err.__traceback__, file=sys.stderr)
                except Exception:
                    print(err, file=sys.stderr)
                print("Check logs/core_debug.log for the full error if Core had started logging.", file=sys.stderr)
                try:
                    _do_shutdown()
                except Exception:
                    pass
                sys.exit(1)
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
        choices=["start", "onboard", "doctor", "ollama", "portal", "skills", "peer"],
        help="start (default): run Core; onboard: wizard; doctor: check config; peer: multi-instance CLI (invite-create, invite-accept, import, list); ollama: …; portal: …; skills: ClawHub",
    )
    parser.add_argument(
        "ollama_action",
        nargs="?",
        help="ollama subcommand: list, pull <name>, set-main <name>. For skills: search <query...> | install <skill[@version]> [--dry-run] [--with-deps]",
    )
    parser.add_argument(
        "ollama_name",
        nargs="?",
        help="Ollama model name (for pull and set-main). For skills: first argument (query token or skill id).",
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Extra args for subcommands (e.g. skills search query words...).",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="do not open the browser when starting Core or Portal",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Limit for skills search results (skills command only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only (skills install only): runs clawhub install --dry-run; does not convert.",
    )
    parser.add_argument(
        "--with-deps",
        action="store_true",
        help="Install with dependencies (skills install only).",
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
        elif args.command == "peer":
            sub = (args.ollama_action or "").strip().lower()
            extra = list(args.extra or [])
            if sub == "invite-create":
                ttl = 900
                if extra:
                    try:
                        ttl = max(60, min(int(str(extra[0]).strip()), 86400))
                    except (TypeError, ValueError):
                        print("Invalid ttl_seconds; using 900")
                run_peer_invite_create(ttl_seconds=ttl)
            elif sub == "invite-accept":
                if len(extra) < 3:
                    print(
                        "Usage: python -m main peer invite-accept <peer_base_url> <invite_id> <token> "
                        "[my_instance_id] [my_display_name]"
                    )
                    sys.exit(2)
                run_peer_invite_accept(
                    extra[0].strip(),
                    extra[1].strip(),
                    extra[2].strip(),
                    extra[3].strip() if len(extra) > 3 else "",
                    extra[4].strip() if len(extra) > 4 else "",
                )
            elif sub == "import":
                if not extra:
                    print("Usage: python -m main peer import <file.json_or_yml> [api_key_env_name]")
                    sys.exit(2)
                run_peer_import(extra[0], api_key_env=extra[1].strip() if len(extra) > 1 else "")
            elif sub == "list":
                run_peer_list()
            else:
                print(
                    "Usage:\n"
                    "  python -m main peer invite-create [ttl_seconds]\n"
                    "  python -m main peer invite-accept <peer_base_url> <invite_id> <token> "
                    "[my_instance_id] [my_display_name]\n"
                    "  python -m main peer import <file.json_or_yml> [api_key_env_name]\n"
                    "  python -m main peer list\n"
                    "Core must be running for invite-create. invite-accept calls the peer's /api/peer/invite/consume. "
                    "Save invite-accept JSON to a file and run peer import to merge into config/peers.yml."
                )
                sys.exit(2)
        elif args.command == "skills":
            from pathlib import Path
            from base.clawhub_integration import clawhub_available, clawhub_search, clawhub_install_and_convert
            from base.skills import remove_skill_folder

            action = (args.ollama_action or "").strip().lower()
            if not action:
                print("Usage: python -m main skills search <query...>\n       python -m main skills install <skill[@version]> [--dry-run] [--with-deps]\n       python -m main skills remove <folder-name>")
                sys.exit(2)
            if action == "remove":
                folder = (args.ollama_name or "").strip()
                if not folder and args.extra:
                    folder = str(args.extra[0]).strip()
                if not folder:
                    print("Usage: python -m main skills remove <folder-name>")
                    sys.exit(2)
                try:
                    meta = Util().get_core_metadata()
                    skills_dir = (getattr(meta, "skills_dir", None) or "skills").strip() or "skills"
                    ext_dir = (getattr(meta, "external_skills_dir", None) or "external_skills").strip()
                    extra_dirs = getattr(meta, "skills_extra_dirs", None) or []
                    if not isinstance(extra_dirs, list):
                        extra_dirs = []
                except Exception:
                    skills_dir, ext_dir, extra_dirs = "skills", "external_skills", []
                root = Path(Util().root_path()).resolve()
                out = remove_skill_folder(folder, root, skills_dir, ext_dir, extra_dirs)
                if out.get("removed"):
                    print(f"Removed skill: {folder}")
                    sys.exit(0)
                print(out.get("error") or "Remove failed")
                sys.exit(1)
            if not clawhub_available():
                print("clawhub not found on PATH. Install OpenClaw/ClawHub first, then try again.")
                sys.exit(2)
            if action == "search":
                tokens = []
                if args.ollama_name:
                    tokens.append(str(args.ollama_name))
                if args.extra:
                    tokens.extend([t for t in args.extra if t and not str(t).startswith("-")])
                query = " ".join(tokens).strip()
                results, raw = clawhub_search(query, limit=args.limit)
                if raw.error and not raw.ok:
                    print(f"Search failed: {raw.error}")
                    if raw.stderr:
                        print(raw.stderr.strip()[:1000])
                    sys.exit(1)
                if not results:
                    print("No results.")
                    sys.exit(0)
                print(f"Found {len(results)} result(s):")
                for row in results[: max(1, min(50, int(args.limit) if args.limit else 20))]:
                    sid = row.get("id") or ""
                    desc = (row.get("description") or "").strip()
                    print(f"  {sid}  {desc}".rstrip())
                sys.exit(0)
            if action == "install":
                spec = (args.ollama_name or "").strip()
                if not spec and args.extra:
                    spec = str(args.extra[0]).strip()
                if not spec:
                    print("Usage: python -m main skills install <skill[@version]>")
                    sys.exit(2)
                try:
                    meta = Util().get_core_metadata()
                    ext_dir = (getattr(meta, "external_skills_dir", None) or "external_skills").strip() or "external_skills"
                    download_dir = (getattr(meta, "clawhub_download_dir", None) or "downloads").strip() or "downloads"
                except Exception:
                    ext_dir = "external_skills"
                    download_dir = "downloads"
                home_root = Path(Util().root_path()).resolve()
                out = clawhub_install_and_convert(
                    skill_spec=spec,
                    skill_id_hint=None,
                    homeclaw_root=home_root,
                    external_skills_dir=ext_dir,
                    clawhub_download_dir=download_dir,
                    dry_run=bool(args.dry_run),
                    with_deps=bool(args.with_deps),
                )
                if args.dry_run:
                    print("Install dry-run:")
                    print((out.get("install") or {}).get("stdout") or "")
                    sys.exit(0 if out.get("ok") else 1)
                if not out.get("ok"):
                    err = out.get("error") or ((out.get("convert") or {}).get("error")) or ((out.get("install") or {}).get("error")) or "Install/convert failed"
                    print(str(err))
                    sys.exit(1)
                convert = out.get("convert") or {}
                print(f"Installed & converted: {spec}")
                print(f"  Output: {convert.get('output')}")
                # Skills vector store is off by default; new skills are registered when Core restarts (if vector search enabled).
                sys.exit(0)
            print("Usage: python -m main skills search <query...> | install <skill[@version]> | remove <folder-name>")
            sys.exit(2)
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
