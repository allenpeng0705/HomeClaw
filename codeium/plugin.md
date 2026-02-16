from fastapi import FastAPI
import uvicorn

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []

    def discover_plugins(self):
        # Discover and load plugins dynamically
        # Example: using importlib to import plugins from a specific directory

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.name}

        uvicorn.run(plugin.app, host="127.0.0.1", port=8000)

    def kill_plugin(self, plugin):
        # Stop the web server for the specified plugin

    def register_plugin(self, plugin):
        # Register the plugin with the manager

# Example Plugin class
class Plugin:
    def __init__(self, name):
        self.name = name
        self.app = None

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Create and register plugins
plugin1 = Plugin("Plugin 1")
plugin2 = Plugin("Plugin 2")
plugin_manager.register_plugin(plugin1)
plugin_manager.register_plugin(plugin2)

# Launch and kill plugins
plugin_manager.launch_plugin(plugin1)

from fastapi import FastAPI
import uvicorn

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []

    def discover_plugins(self):
        # Discover and load plugins dynamically
        # Example: using importlib to import plugins from a specific directory

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.name}

        uvicorn.run(plugin.app, host="127.0.0.1", port=8000)

    def kill_plugin(self, plugin):
        # Stop the web server for the specified plugin

    def register_plugin(self, plugin):
        # Register the plugin with the manager

# Example Plugin class
class Plugin:
    def __init__(self, name):
        self.name = name
        self.app = None

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Create and register plugins
plugin1 = Plugin("Plugin 1")
plugin2 = Plugin("Plugin 2")
plugin_manager.register_plugin(plugin1)
plugin_manager.register_plugin(plugin2)

# Launch and kill plugins
plugin_manager.launch_plugin(plugin1)


import os
import yaml

# Plugin Manager class
class PluginManager:
    def __init__(self):
        self.plugins = []

    def discover_plugins(self):
        plugins_dir = "plugins"
        for folder_name in os.listdir(plugins_dir):
            plugin_folder = os.path.join(plugins_dir, folder_name)
            if os.path.isdir(plugin_folder):
                config_file = os.path.join(plugin_folder, "config.yml")
                if os.path.exists(config_file):
                    with open(config_file) as file:
                        config = yaml.safe_load(file)
                        plugin = Plugin(config.get("name", "Unknown"))
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.name}

        uvicorn.run(plugin.app, host="127.0.0.1", port=8000)

    def kill_plugin(self, plugin):
        if plugin.app:
            # Stop the web server for the specified plugin
            # You can implement the logic to stop the uvicorn server for the plugin

    def register_plugin(self, plugin):
        self.plugins.append(plugin)

# Example Plugin class
class Plugin:
    def __init__(self, name):
        self.name = name
        self.app = None

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch and kill plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# To kill a plugin, you can call kill_plugin with the specific plugin instance
# plugin_manager.kill_plugin(plugin_instance)

import signal

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
                        plugin = Plugin(config.get("name", "Unknown"))
                        self.register_plugin(plugin)

    def launch_plugin(self, plugin):
        plugin.app = FastAPI()

        @plugin.app.get("/")
        def read_root():
            return {"Plugin": plugin.name}

        process = uvicorn.run(plugin.app, host="127.0.0.1", port=8000, log_level="error", access_log=False)
        self.running_processes.append(process)

    def kill_plugin(self, plugin):
        if plugin.app:
            for process in self.running_processes:
                if plugin.name in process.name():
                    process.kill()

    def kill_all_plugins(self):
        for process in self.running_processes:
            process.kill()

    def register_plugin(self, plugin):
        self.plugins.append(plugin)

# Example Plugin class
class Plugin:
    def __init__(self, name):
        self.name = name
        self.app = None

# Signal handler for CTRL+C
def signal_handler(signal, frame):
    plugin_manager.kill_all_plugins()
    sys.exit(0)

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch and kill plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# Register signal handler for CTRL+C
signal.signal(signal.SIGINT, signal_handler)


import signal
import sys

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

# Signal handler for CTRL+C
def signal_handler(signal, frame):
    plugin_manager.kill_all_plugins()
    sys.exit(0)

# Usage
plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# Launch and kill plugins
for plugin in plugin_manager.plugins:
    plugin_manager.launch_plugin(plugin)

# Register signal handler for CTRL+C
signal.signal(signal.SIGINT, signal_handler)


# Launching and monitoring plugins

