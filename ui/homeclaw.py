import os
from pathlib import Path
import re
import subprocess
from time import sleep
from fastapi import FastAPI, Depends, Request
from fastapi.responses import RedirectResponse
import uvicorn
import requests
import yaml
import sys
import gradio as gr
from loguru import logger
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from base.util import Util

app = FastAPI()

Util().setup_logging("ui", "dev")

path = os.path.join(Util().root_path(), 'config')
config_file_path = os.path.join(path, 'core.yml')
user_config_file_path = os.path.join(path, 'user.yml')

def read_config(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    return config

def write_config(file_path, config):
    with open(file_path, 'w', encoding='utf-8') as file:
        yaml.safe_dump(config, file, default_flow_style=False, sort_keys=False)

def _llm_options_from_core(core_config):
    local = core_config.get('local_models') or []
    cloud = core_config.get('cloud_models') or []
    return [f"local_models/{m['id']}" for m in local if m.get('id')] + [f"cloud_models/{m['id']}" for m in cloud if m.get('id')]
        
def get_config():
    core_config = read_config(config_file_path)
    name = core_config['name']
    host = core_config['host']
    port = core_config['port']
    mode = core_config['mode']
    main_llm = core_config.get('main_llm', '')
    embedding_llm = core_config.get('embedding_llm', '')
    llm_options = _llm_options_from_core(core_config)
    if not llm_options and (main_llm or embedding_llm):
        llm_options = [x for x in [main_llm, embedding_llm] if x]
    return (name, host, port, mode, main_llm, embedding_llm, llm_options)

def update_config(host, port, mode, main_llm, embedding_llm):
    Util().update_yaml_preserving_comments(config_file_path, {
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
        logger.debug(f"Account exists: {email}")
        return True
    else:
        logger.debug("Account does not exist")
        return False

# Function to check email format
def is_valid_email(email):
    # Simple regex for validating an email address
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if re.fullmatch(regex, email):
        return True
    else:
        return False

def send_verification_code(email):
    # First, verify the email format
    if not is_valid_email(email):
        return "Invalid email format. Please enter a valid email address."
    
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
        logger.debug(f"Response code: {response.status_code} - {response.text}")
        if response.status_code == 200:
            logger.debug(f"Sending verification code to {email}")
            return "Verification code sent to your email."
        else:
            # Handle different response codes accordingly
            return "Failed to send verification code."
    except Exception as e:
        logger.debug(f"An error occurred: {e}")
        return "An error occurred while sending the verification code."

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
        
        # Check the response code to determine if the request was successful
        if response.status_code == 200 or response.status_code == 201:
            # Assuming a successful response code means the account was created successfully
            logger.debug(f"Account created for {response.json()['user']['email']}, {response.json()['user']['password']}")

            homeclaw_account = Util().get_homeclaw_account()
            homeclaw_account.email_user = response.json()['user']['email']
            homeclaw_account.email_pass = response.json()['user']['password']
            Util().email_account = homeclaw_account
            Util().save_homeclaw_account()
            return "Account created successfully. Welcome to HomeClaw!"
        else:
            # If the response code is not 200, assume verification failed
            return "Verification failed. Please try again."
    except Exception as e:
        # Catch any exceptions that occur during the request and report them
        return f"An error occurred: {e}"
    
def after_verification_callback(email, code):
    #nonlocal account_created
    logger.debug(f"Received email: {email} and code: {code}")
    response = create_account(email, code)
    if "Account created successfully" in response:
        # Hide demo UI and show main UI
        return "Account created successfully", 'Please click <a href="http://127.0.0.1:8000/portal" target="_blank">here</a> to go to the portal.'
    return "Verification failed. Please check your details and try again.",  "Check the email address and verification code and try again."

def render_login_ui():
    with gr.Blocks() as login_ui:
        email = gr.Textbox(label="Email")
        send_code_btn = gr.Button("Send Verification Code")
        code = gr.Textbox(label="Verification Code")
        verify_btn = gr.Button("Verify and Create Account")
        text_output = gr.Textbox(label="Output", lines=2, interactive=False)
        output = gr.HTML()  # Use HTML component for output capable of executing JavaScript

        send_code_btn.click(fn=send_verification_code, inputs=email, outputs=[text_output])
        #verify_btn.click(fn=after_verification_callback, inputs=[email, code], outputs=[output])
        verify_btn.click(fn=after_verification_callback, inputs=[email, code], outputs=[text_output, output])
    return login_ui


def render_main_ui(visible=False):
    core_config = read_config(config_file_path)
    llm_options = _llm_options_from_core(core_config)
    channels = []

    root = Util().root_path()
    channels_path = os.path.join(root, 'channels')
    for folder in os.listdir(channels_path):
        channel_path = os.path.join(channels_path, folder, 'channel.py')
        if os.path.isfile(channel_path):
            channels.append(folder)

    def start_core():
        root = Util().root_path()
        core_path = os.path.join(root, 'core', 'core.py')
        subprocess.Popen(["python", core_path])

    def start_channels():
        root = Util().root_path()
        channels_path = os.path.join(root, 'channels')
        for folder in os.listdir(channels_path):
            channel_path = os.path.join(channels_path, folder, 'channel.py')
            if os.path.isfile(channel_path):
                subprocess.Popen(["python", channel_path])

    def start_channel(selected_channel):
        subprocess.Popen(["python", os.path.join(channels_path, selected_channel, "channel.py")])

    def start_all():
        start_core()
        sleep(10)
        start_channels()

    with gr.Blocks(visible=visible) as main_ui:
        with gr.Tabs():
            with gr.Tab("Portal"):
                selected_channel = gr.Dropdown(label="Select Channel", choices=channels)
                start_core_button = gr.Button("Start core")
                #start_channels_button = gr.Button("Start Channels")
                start_channel_button = gr.Button("Start Selected Channel")
                #start_all_button = gr.Button("Start All")

                start_core_button.click(fn=start_core, inputs=[], outputs=[])
                #start_channels_button.click(fn=start_channels, inputs=[], outputs=[])
                start_channel_button.click(fn=start_channel, inputs=[selected_channel], outputs=[])
                #start_all_button.click(fn=start_all, inputs=[], outputs=[])

            with gr.Tab("Core Configuration"):
                with gr.Row():
                    with gr.Column():
                        name = gr.Textbox(label="Name", interactive=False)
                        host = gr.Textbox(label="Host")
                        port = gr.Number(label="Port")
                        mode = gr.Dropdown(label="Mode", choices=["dev", "production"])
                        main_llm = gr.Dropdown(label="Main LLM", choices=llm_options)
                        embedding_llm = gr.Dropdown(label="Embedding LLM", choices=llm_options)

                update_button = gr.Button("Update Configuration")
                output = gr.Textbox(label="Result:", interactive=False)

                update_button.click(
                    fn=update_config,
                    inputs=[host, port, mode, main_llm, embedding_llm],
                    outputs=output
                )

                def load_initial_values():
                    values = get_config()
                    return values[0], values[1], values[2], values[3], values[4], values[5], values[6]

                main_ui.load(fn=load_initial_values, outputs=[name, host, port, mode, main_llm, embedding_llm])

            with gr.Tab("Manage LLMs"):
                llm_list = gr.Dropdown(label="LLM List", choices=llm_options, value=llm_options[0] if llm_options else None)
                llm_name = gr.Textbox(label="LLM Name (id)")
                llm_type = gr.Dropdown(label="LLM Type", choices=["local", "litellm"])
                llm_alias = gr.Textbox(label="LLM Alias")
                llm_path = gr.Textbox(label="LLM Path")
                llm_description = gr.Textbox(label="LLM Description")
                llm_languages = gr.Textbox(label="LLM Languages")
                llm_introduction = gr.Textbox(label="LLM Introduction")
                llm_capabilities = gr.Textbox(label="LLM Capabilities")
                llm_host = gr.Textbox(label="LLM Host")
                llm_port = gr.Number(label="LLM Port")
                llm_parameters = gr.Textbox(label="LLM Parameters")

                def load_llm_list():
                    core_config = read_config(config_file_path)
                    options = _llm_options_from_core(core_config)
                    if not options:
                        return ("", "local", "", "", "", "", "", "", "", 0, "")
                    return load_llm_metadata(options[0])

                def load_llm_metadata(sel_id):
                    if not sel_id:
                        return ("", "local", "", "", "", "", "", "", "", 0, "")
                    core_config = read_config(config_file_path)
                    raw_id = sel_id
                    if sel_id.startswith("local_models/"):
                        raw_id = sel_id[len("local_models/"):]
                    elif sel_id.startswith("cloud_models/"):
                        raw_id = sel_id[len("cloud_models/"):]
                    for m in (core_config.get('local_models') or []):
                        if m.get('id') == raw_id:
                            return (
                                sel_id, "local", m.get('alias', ''),
                                m.get('path', ''), '', '', '',
                                str(m.get('capabilities', [])),
                                m.get('host', ''), m.get('port', 0),
                                str(m.get('parameters', {}))
                            )
                    for m in (core_config.get('cloud_models') or []):
                        if m.get('id') == raw_id:
                            return (
                                sel_id, "litellm", m.get('alias', ''),
                                m.get('path', ''), '', '', '',
                                str(m.get('capabilities', [])),
                                m.get('host', ''), m.get('port', 0),
                                str(m.get('api_key_name', ''))
                            )
                    return (sel_id, "local", "", "", "", "", "", "", "", 0, "")

                main_ui.load(
                    fn=load_llm_list,
                    outputs=[llm_name, llm_type, llm_alias, llm_path, llm_description, llm_languages, llm_introduction, llm_capabilities, llm_host, llm_port, llm_parameters]
                )
                llm_list.change(
                    fn=load_llm_metadata,
                    inputs=[llm_list],
                    outputs=[llm_name, llm_type, llm_alias, llm_path, llm_description, llm_languages, llm_introduction, llm_capabilities, llm_host, llm_port, llm_parameters]
                )

            with gr.Tab("Manage Users"):
                user_config = read_config(user_config_file_path)
                user_list = user_config['users']
                user_names = [user['name'] for user in user_list]
                selected_user = gr.Dropdown(label="Select User", choices=user_names, value=user_names[0])

                def display_user_info(selected_user):
                    for user in user_list:
                        if user['name'] == selected_user:
                            return user

                user_name = gr.Textbox(label="Name")
                user_email = gr.Textbox(label="Email")
                user_im = gr.Textbox(label="IM")
                user_phone = gr.Textbox(label="Phone")
                user_permissions = gr.Textbox(label="Permissions")

                def update_user_info(selected_user):
                    user = display_user_info(selected_user)
                    return user['name'], user['email'], user['im'], user['phone'], user['permissions']

                selected_user.change(
                    fn=update_user_info,
                    inputs=[selected_user],
                    outputs=[user_name, user_email, user_im, user_phone, user_permissions]
                )

                def load_initial_user_info():
                    user = display_user_info(user_names[0])
                    return user['name'], user['email'], user['im'], user['phone'], user['permissions']

                main_ui.load(
                    fn=load_initial_user_info,
                    outputs=[user_name, user_email, user_im, user_phone, user_permissions]
                )

                user_name.readonly = True
                user_email.readonly = True
                user_im.readonly = True
                user_phone.readonly = True
                user_permissions.readonly = True

    return main_ui

login_app = render_login_ui()
main_app = render_main_ui()
    
app = gr.mount_gradio_app(app, login_app, path="/login") 
app = gr.mount_gradio_app(app, main_app, path="/portal") 
  
    
@app.get('/')
def public(existed: bool = Depends(account_exists)):
    if existed:
        return RedirectResponse(url='/portal')
    else:
        return RedirectResponse(url='/login')
  

if __name__ == '__main__':
    # Call the function to launch the app
    uvicorn.run(app)
    #uvicorn.run(app, host="0.0.0.0", port=10000)
