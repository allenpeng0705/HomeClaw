# Codeium Chat Conversation

Note: _This is purely the output of the chat conversation and does not contain any raw data, codebase snippets, etc. used to generate the output._

**User** _at 9:12 am, Jul 31, 2024_



---

**Codeium** _at 9:12 am, Jul 31, 2024_

Creating a plugin framework in Python involves defining a structure that allows plugins to be dynamically discovered, loaded, and used by the main application. Below is a basic example of how you can create a simple plugin framework using Python:

### Step 1: Define a Plugin Channel

Create a base class or channel that all plugins should inherit from. This ensures that all plugins follow a common protocol.

```python
# plugin_channel.py
class PluginChannel:
    def initialize(self):
        """Initialize the plugin"""
        raise NotImplementedError

    def run(self, *args, **kwargs):
        """Run the plugin"""
        raise NotImplementedError
```

### Step 2: Create a Plugin Manager

The plugin manager will handle discovering and loading plugins.

```python
# plugin_manager.py
import importlib
import os

class PluginManager:
    def __init__(self, plugin_folder):
        self.plugin_folder = plugin_folder
        self.plugins = []

    def discover_plugins(self):
        for file in os.listdir(self.plugin_folder):
            if file.endswith(".py") and file != "__init__.py":
                module_name = file[:-3]
                module = importlib.import_module(f"{self.plugin_folder}.{module_name}")
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, PluginChannel) and attribute is not PluginChannel:
                        self.plugins.append(attribute())

    def initialize_plugins(self):
        for plugin in self.plugins:
            plugin.initialize()

    def run_plugins(self, *args, **kwargs):
        results = []
        for plugin in self.plugins:
            results.append(plugin.run(*args, **kwargs))
        return results
```

### Step 3: Implement Plugins

Implement plugins that inherit from the base channel.

```python
# plugins/hello_plugin.py
from plugin_channel import PluginChannel

class HelloPlugin(PluginChannel):
    def initialize(self):
        logger.debug("HelloPlugin initialized")

    def run(self, *args, **kwargs):
        logger.debug("HelloPlugin running")
        return "Hello from HelloPlugin"
```

### Step 4: Use the Plugin Framework

Discover and use the plugins in your main application.

```python
# main.py
from plugin_manager import PluginManager

if __name__ == "__main__":
    manager = PluginManager("plugins")
    manager.discover_plugins()
    manager.initialize_plugins()
    results = manager.run_plugins()
    for result in results:
        logger.debug(result)
```

### Directory Structure

```
your_project/
│
├── plugin_channel.py
├── plugin_manager.py
├── main.py
└── plugins/
    └── hello_plugin.py
```

### Running the Example

1. Make sure your `plugins` directory contains the `hello_plugin.py`.
2. Run `main.py` to see the plugin framework in action.

This is a basic example to get you started. Depending on your needs, you might want to add more advanced features like dynamic reloading, configuration management, error handling, etc.

_Context Items Read (35):_

- settings.gradle.kts `pluginManagement {`
- plugin-bot.ts `/**`
- 3rd_round_nsm_windows.md `### Helper Module`
- README.md `The plugins are name...`
- requirements.txt `loguru`
- gguf.py `# This file left for...`
- package.json `{`
- regex_to_grammar.py `import json, subproc...`
- package.json `{`
- package.json `{`
- package.json `{`
- hot-import-bot.js `/**`
- build.gradle.kts `dependencies {`
- package.json `{`
- distributed_system.md `- test-backend-ops.c...`
- README.md `# BLESSED TWINS BOT`
- build.gradle.kts `plugins {`
- build.gradle.kts `plugins {`
- Package.swift `// swift-tools-versi...`
- documentloader_service.py `_text_splitter = Rec...`
- 2nd_round_with_process_manager.md `if __name__ == "__ma...`
- ggml-rpc.cpp ``
- 1st_round_system_framework_code.md `if __name__ == "__ma...`
- llama.cpp ``
- build.gradle.kts `// Top-level build f...`
- package_win.spec `# -*- mode: python ;...`
- requirements-convert_legacy_llama.txt `numpy~=1.26.4`
- json_schema_to_grammar.py `#!/usr/bin/env pytho...`
- build.gradle.kts `dependencies {`
- package_mac.spec `# -*- mode: python ;...`
- convert_llama_ggml_to_gguf.py `#!/usr/bin/env pytho...`
- README.md `When I code customiz...`
- on-message.js `////////////////////...`
- MainActivity.kt `package com.example....`
- eval-callback.cpp `#include "common.h"`


---

**User** _at 9:16 am, Jul 31, 2024_



---

**Codeium** _at 9:17 am, Jul 31, 2024_

To allow plugins to register themselves with the plugin manager, you can modify the plugin manager and the plugin channel to include a registration mechanism. Here's how you can achieve this:

### Step 1: Update the Plugin Channel

Add a registration method to the plugin channel.

```python
# plugin_channel.py
class PluginChannel:
    def initialize(self):
        """Initialize the plugin"""
        raise NotImplementedError

    def run(self, *args, **kwargs):
        """Run the plugin"""
        raise NotImplementedError

    @classmethod
    def register(cls, manager):
        """Register the plugin with the manager"""
        manager.register_plugin(cls)
```

### Step 2: Update the Plugin Manager

Add a method to register plugins.

```python
# plugin_manager.py
import importlib
import os

class PluginManager:
    def __init__(self, plugin_folder):
        self.plugin_folder = plugin_folder
        self.plugins = []

    def register_plugin(self, plugin_cls):
        """Register a plugin class"""
        self.plugins.append(plugin_cls())

    def discover_plugins(self):
        for file in os.listdir(self.plugin_folder):
            if file.endswith(".py") and file != "__init__.py":
                module_name = file[:-3]
                module = importlib.import_module(f"{self.plugin_folder}.{module_name}")
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, PluginChannel) and attribute is not PluginChannel:
                        attribute.register(self)  # Register the plugin

    def initialize_plugins(self):
        for plugin in self.plugins:
            plugin.initialize()

    def run_plugins(self, *args, **kwargs):
        results = []
        for plugin in self.plugins:
            results.append(plugin.run(*args, **kwargs))
        return results
```

### Step 3: Update Plugins to Register Themselves

Ensure each plugin calls the `register` method during module import.

```python
# plugins/hello_plugin.py
from plugin_channel import PluginChannel

class HelloPlugin(PluginChannel):
    def initialize(self):
        logger.debug("HelloPlugin initialized")

    def run(self, *args, **kwargs):
        logger.debug("HelloPlugin running")
        return "Hello from HelloPlugin"

# Register the plugin with the plugin manager


from fastapi import FastAPI

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []
        self.running_processes = []

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config)
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.metadata["name"]}

        process = uvicorn.run(plugin.app, host="127.0.0.1", port=8000, log_level="error", access_log=False)
        self.running_processes.append(process)

    def kill_plugin(self, plugin):
        if plugin.app:
            for process in self.running_processes:
                if plugin.metadata["name"] in process.name():
                    process.kill()

    def restart_plugin(self, plugin):
        self.kill_plugin(plugin)
        self.running_processes.remove(plugin.app)
        self.plugins.remove(plugin)
        self.launch_plugin(plugin)

    def kill_all_plugins(self):
        for process in self.running_processes:
            process.kill()

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        logger.debug(f"Registered plugin: {plugin.metadata['name']}")

# Example Plugin class
class Plugin:
    def __init__(self, metadata):
        self.metadata = metadata
        self.app = None

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

# Signal handler for CTRL+C
def signal_handler(signal, frame):
    plugin_manager.kill_all_plugins()
    sys.exit(0)

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch and monitor plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# Register signal handler for CTRL+C
signal.signal(signal.SIGINT, signal_handler)


# Add read host and port from .env
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []
        self.running_processes = []

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config)
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.metadata["name"]}

        host = os.getenv("PLUGIN_HOST", "127.0.0.1")
        port = int(os.getenv("PLUGIN_PORT", 8000))
        process = uvicorn.run(plugin.app, host=host, port=port, log_level="error", access_log=False)
        self.running_processes.append(process)

    def kill_plugin(self, plugin):
        if plugin.app:
            for process in self.running_processes:
                if plugin.metadata["name"] in process.name():
                    process.kill()

    def restart_plugin(self, plugin):
        self.kill_plugin(plugin)
        self.running_processes.remove(plugin.app)
        self.plugins.remove(plugin)
        self.launch_plugin(plugin)

    def kill_all_plugins(self):
        for process in self.running_processes:
            process.kill()

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        logger.debug(f"Registered plugin: {plugin.metadata['name']}")

# Example Plugin class
class Plugin:
    def __init__(self, metadata):
        self.metadata = metadata
        self.app = None

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

# Signal handler for CTRL+C
def signal_handler(signal, frame):
    plugin_manager.kill_all_plugins()
    sys.exit(0)

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch and monitor plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# Register signal handler for CTRL+C
signal.signal(signal.SIGINT, signal_handler)


# add start remote plugin
import socket
import pickle
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []
        self.running_processes = []

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config)
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.metadata["name"]}

        host = os.getenv("PLUGIN_HOST", "127.0.0.1")
        port = int(os.getenv("PLUGIN_PORT", 8000))
        process = uvicorn.run(plugin.app, host=host, port=port, log_level="error", access_log=False)
        self.running_processes.append(process)

    def start_remote_plugin(self, remote_host, remote_port):
        # Connect to remote plugin
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((remote_host, remote_port))
            data = pickle.dumps({"command": "start"})
            s.sendall(data)

            response = s.recv(1024)
            if response == b"Started":
                logger.debug("Remote plugin started successfully.")
            else:
                logger.debug("Failed to start remote plugin.")

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        logger.debug(f"Registered plugin: {plugin.metadata['name']}")

# Example Plugin class
class Plugin:
    def __init__(self, metadata):
        self.metadata = metadata
        self.app = None

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch local plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# Start a remote plugin
remote_host = "remote_plugin_host"
remote_port = 8001
plugin_manager.start_remote_plugin(remote_host, remote_port)


# Add the stop plugin and the required functions in plugin class
import socket
import pickle
import os
import yaml
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []
        self.running_processes = []

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config)
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.metadata["name"]}

        host = os.getenv("PLUGIN_HOST", "127.0.0.1")
        port = int(os.getenv("PLUGIN_PORT", 8000)
        process = uvicorn.run(plugin.app, host=host, port=port, log_level="error", access_log=False)
        self.running_processes.append(process)

    def start_remote_plugin(self, remote_host, remote_port):
        # Connect to remote plugin and send start command
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((remote_host, remote_port))
            data = pickle.dumps({"command": "start"})
            s.sendall(data)

            response = s.recv(1024)
            if response == b"Started":
                logger.debug("Remote plugin started successfully.")
            else:
                logger.debug("Failed to start remote plugin.")

    def stop_remote_plugin(self, remote_host, remote_port):
        # Connect to remote plugin and send stop command
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((remote_host, remote_port))
            data = pickle.dumps({"command": "stop"})
            s.sendall(data)

            response = s.recv(1024)
            if response == b"Stopped":
                logger.debug("Remote plugin stopped successfully.")
            else:
                logger.debug("Failed to stop remote plugin.")

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        logger.debug(f"Registered plugin: {plugin.metadata['name']}")

# Example Plugin class
class Plugin:
    def __init__(self, metadata):
        self.metadata = metadata
        self.app = FastAPI()

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

        @self.app.get("/stop")
        def stop_plugin():
            return {"message": "Stopping plugin"}
            # Add logic here to stop the plugin

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch local plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# Start a remote plugin
remote_host = "remote_plugin_host"
remote_port = 8001
plugin_manager.start_remote_plugin(remote_host, remote_port)

# Stop a remote plugin
plugin_manager.stop_remote_plugin(remote_host, remote_port)

# managert check the remote plugin automatically
import socket
import pickle
import os
import yaml
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []
        self.running_processes = []
        self.manager_host = os.getenv("MANAGER_HOST")
        self.manager_port = int(os.getenv("MANAGER_PORT"))

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config)
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.metadata["name"]}

        host = plugin.metadata.get("host", "127.0.0.1")
        port = int(plugin.metadata.get("port", 8000))
        process = uvicorn.run(plugin.app, host=host, port=port, log_level="error", access_log=False)
        self.running_processes.append(process)

    def start_plugins_based_on_location(self):
        for plugin in self.plugins:
            plugin_host = plugin.metadata.get("host")
            if plugin_host == self.manager_host:
                self.launch_plugin(plugin)
            else:
                self.start_remote_plugin(plugin_host, plugin.metadata.get("port"))

    def start_remote_plugin(self, remote_host, remote_port):
        # Connect to remote plugin and send start command
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((remote_host, remote_port))
            data = pickle.dumps({"command": "start"})
            s.sendall(data)

            response = s.recv(1024)
            if response == b"Started":
                logger.debug(f"Remote plugin at {remote_host}:{remote_port} started successfully.")
            else:
                logger.debug(f"Failed to start remote plugin at {remote_host}:{remote_port}.")

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        logger.debug(f"Registered plugin: {plugin.metadata['name']}")

# Example Plugin class
class Plugin:
    def __init__(self, metadata):
        self.metadata = metadata
        self.app = FastAPI()

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()
plugin_manager.start_plugins_based_on_location()


# 

import socket
import pickle
import os
import yaml
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []
        self.running_processes = []
        self.manager_host = os.getenv("MANAGER_HOST")
        self.manager_port = int(os.getenv("MANAGER_PORT"))

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config, self)
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.metadata["name"]}

        host = plugin.metadata.get("host", "127.0.0.1")
        port = int(plugin.metadata.get("port", 8000))
        process = uvicorn.run(plugin.app, host=host, port=port, log_level="error", access_log=False)
        self.running_processes.append(process)

    def send_command_to_plugin(self, plugin_host, plugin_port, command):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((plugin_host, plugin_port))
            data = pickle.dumps({"command": command})
            s.sendall(data)

    def start_plugins_based_on_location(self):
        for plugin in self.plugins:
            plugin_host = plugin.metadata.get("host")
            if plugin_host == self.manager_host:
                self.launch_plugin(plugin)
            else:
                self.send_command_to_plugin(plugin_host, plugin.metadata.get("port"), "start")

    def stop_plugins_based_on_location(self):
        for plugin in self.plugins:
            plugin_host = plugin.metadata.get("host")
            if plugin_host != self.manager_host:
                self.send_command_to_plugin(plugin_host, plugin.metadata.get("port"), "stop")

    def register_plugin(self, plugin):
        self.plugins.append(plugin)
        logger.debug(f"Registered plugin: {plugin.metadata['name']}")

# Plugin class
class Plugin:
    def __init__(self, metadata, manager):
        self.metadata = metadata
        self.app = FastAPI()
        self.plugin_manager = manager

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

        @self.app.get("/stop")
        def stop_plugin():
            return self.stop_plugin()

    def stop_plugin(self):
        # Add logic here to stop the plugin
        return {"message": "Stopping plugin"}

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()
plugin_manager.start_plugins_based_on_location()

# Stop remote plugins
plugin_manager.stop_plugins_based_on_location()

#### Plugin with socket
# Plugin class
class Plugin:
    def __init__(self, metadata, manager):
        self.metadata = metadata
        self.app = FastAPI()
        self.plugin_manager = manager

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

        @self.app.get("/stop")
        def stop_plugin():
            return self.stop_plugin()

    def stop_plugin(self):
        # Add logic here to stop the plugin
        return {"message": "Stopping plugin"}

    def stop_plugin_with_socket_data(self, data):
        # Process the socket data to determine if the plugin should stop
        if data == b"Stop":
            # Add logic here to stop the plugin
            return {"message": "Stopping plugin"}
        else:
            return {"message": "Invalid command"}

# Plugin Manager class
class PluginManager:
    # Other methods remain the same

    def stop_plugins_based_on_location(self):
        for plugin in self.plugins:
            plugin_host = plugin.metadata.get("host")
            if plugin_host != self.manager_host:
                self.send_command_to_plugin(plugin_host, plugin.metadata.get("port"), "stop")

    def send_stop_command_to_plugin(self, plugin_host, plugin_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((plugin_host, plugin_port))
            data = pickle.dumps({"command": "stop"})
            s.sendall(data)

            response = s.recv(1024)
            if response:
                response_data = pickle.loads(response)
                result = plugin.stop_plugin_with_socket_data(response_data)
                logger.debug(result)

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()
plugin_manager.start_plugins_based_on_location()

# Stop remote plugins
plugin_manager.stop_plugins_based_on_location()
In this updated code snippet, I've added the stop_plugin_with_socket_data method to the Plugin class. This method processes the data received from the socket to determine if the plugin should stop. If the data is "Stop", the plugin stops; otherwise, it returns an "Invalid command" message.

Additionally, the PluginManager class now includes the send_stop_command_to_plugin method, which sends a "stop" command to a plugin via a socket connection. After sending the command, it receives a response and calls the stop_plugin_with_socket_data method in the Plugin class to handle stopping the plugin based on the received data.

With these updates, the stop endpoint in the Plugin class can now accept socket data from the manager to determine whether the plugin should stop.



But where is the socket in plugin class?

Copy
# Plugin class
class Plugin:
    def __init__(self, metadata, manager):
        self.metadata = metadata
        self.app = FastAPI()
        self.plugin_manager = manager
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(("0.0.0.0", self.metadata["port"]))  # Bind to the plugin's port
        self.server_socket.listen(1)
        logger.debug(f"Plugin {self.metadata['name']} listening on port {self.metadata['port']}")

        @self.app.get("/info")
        def get_info():
            return self.metadata

        @self.app.get("/status")
        def get_status():
            return {"status": "OK"}

        @self.app.get("/stop")
        def stop_plugin():
            return self.stop_plugin()

    def stop_plugin(self):
        # Add logic here to stop the plugin
        return {"message": "Stopping plugin"}

    def handle_socket_data(self):
        while True:
            client_socket, address = self.server_socket.accept()
            data = client_socket.recv(1024)
            if data:
                response = self.stop_plugin_with_socket_data(data)
                client_socket.send(response)

    def stop_plugin_with_socket_data(self, data):
        # Process the socket data to determine if the plugin should stop
        if data == b"Stop":
            # Add logic here to stop the plugin
            return pickle.dumps({"message": "Stopping plugin"})
        else:
            return pickle.dumps({"message": "Invalid command"})


# Plugin manager manage the remote plugin.
# PluginManager class
class PluginManager:
    # Other methods remain the same

    def start_remote_plugin(self, plugin):
        plugin_host = plugin.metadata.get("host")
        plugin_port = plugin.metadata.get("port")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((plugin_host, plugin_port))
                data = pickle.dumps({"command": "start"})
                s.sendall(data)
                response = s.recv(1024)
                if response:
                    response_data = pickle.loads(response)
                    if response_data.get("status") == "started":
                        logger.debug(f"Remote plugin {plugin.metadata['name']} started successfully.")
                    else:
                        logger.debug(f"Failed to start remote plugin {plugin.metadata['name']}.")
        except ConnectionRefusedError:
            logger.debug(f"Connection to remote plugin {plugin.metadata['name']} at {plugin_host}:{plugin_port} failed.")

    def check_and_restart_remote_plugins(self):
        for plugin in self.plugins:
            plugin_host = plugin.metadata.get("host")
            plugin_port = plugin.metadata.get("port")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((plugin_host, plugin_port))
            except ConnectionRefusedError:
                logger.debug(f"Remote plugin {plugin.metadata['name']} at {plugin_host}:{plugin_port} is down. Restarting...")
                self.start_remote_plugin(plugin)

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()
plugin_manager.start_plugins_based_on_location()

# Check and restart remote plugins if they are down
plugin_manager.check_and_restart_remote_plugins()