"""Python implementation of a Tinode chatbot."""
# Test account for Tinoe
# homeclaw_user:password
# pengshilei:232410
# shileipeng:232410
# Tinode home server: http://200.69.21.246:6060

# For compatibility between python 2 and 3
from __future__ import print_function
import asyncio
from pathlib import Path
import argparse
import base64
from concurrent import futures
from datetime import datetime
import json
import os
import platform
import threading
import importlib.metadata
import httpx
try:
    import Queue as queue
except ImportError:
    import queue
import random
import signal
import sys
import time

import grpc
from google.protobuf.json_format import MessageToDict

# Import generated grpc modules
from tinode_grpc import pb
from tinode_grpc import pbx
from pydub import AudioSegment
from pydub.playback import play

# Import for Channel
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel
from dotenv import dotenv_values
import yaml
from os import getenv
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from base.util import Util
from base.BaseChannel import ChannelMetadata, BaseChannel
from base.base import PromptRequest, AsyncResponse, ChannelType, ContentType

channel_app: FastAPI = FastAPI() 

# For compatibility with python2
if sys.version_info[0] >= 3:
    unicode = str

APP_NAME = "Tinode HomeClaw Channel"
APP_VERSION = "1.2.2"
try:
    LIB_VERSION = importlib.metadata.version("tinode_grpc")
except importlib.metadata.PackageNotFoundError:
    LIB_VERSION = "0.0.0"

MAX_LOG_LEN = 64
# User ID of the current user (the account the channel is logged in as)
botUID = None
# If True, process messages even when from_user_id == botUID (same account, e.g. mobile + channel). Set TINODE_ALLOW_SAME_USER=1 in env to enable.
ALLOW_SAME_USER = os.environ.get("TINODE_ALLOW_SAME_USER", "").strip().lower() in ("1", "true", "yes")

# Dictionary which contains lambdas to be executed when server response is received
onCompletion = {}

# Connection state tracking
connection_state = {
    'connected': False,
    'reconnect_attempts': 0,
    'last_connection_time': None,
    'connected_since': None,  # time when current connection started (for periodic re-login)
    'connection_error': None,
    'stream': None,
    'channel': None
}

# Reconnection configuration
RECONNECT_CONFIG = {
    'max_attempts': 10,
    'initial_delay': 1,  # seconds
    'max_delay': 60,     # seconds
    'backoff_factor': 2,
    'health_check_interval': 30,   # seconds
    'idle_timeout': 0,   # seconds; 0 = disabled — never force reconnect due to idle (reconnect only when stream actually ends)
    'keepalive_interval': 45,      # seconds; send hello to Tinode server so it doesn't close the connection (many servers timeout at 60s)
    'relogin_interval': 86400,     # seconds; 0 = disabled. If > 0, proactively reconnect (and thus re-login) after this many seconds (e.g. 86400 = 24h) to refresh session
}

# This is needed for gRPC ssl to work correctly.
os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"

def log(*args):
    print(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], *args)

# Add bundle for future execution
def add_future(tid, bundle):
    onCompletion[tid] = bundle

# Shorten long strings for logging.
def clip_long_string(obj):
    if isinstance(obj, unicode) or isinstance(obj, str):
        if len(obj) > MAX_LOG_LEN:
            return '<' + str(len(obj)) + ' bytes: ' + obj[:12] + '...' + obj[-12:] + '>'
        return obj
    elif isinstance(obj, (list, tuple)):
        return [clip_long_string(item) for item in obj]
    elif isinstance(obj, dict):
        return dict((key, clip_long_string(val)) for key, val in obj.items())
    else:
        return obj

def to_json(msg):
    return json.dumps(clip_long_string(MessageToDict(msg)))

# Resolve or reject the future
def exec_future(tid, code, text, params):
    bundle = onCompletion.get(tid)
    if bundle != None:
        del onCompletion[tid]
        try:
            if code >= 200 and code < 400:
                arg = bundle.get('arg')
                bundle.get('onsuccess')(arg, params)
            else:
                log("Error: {} {} ({})".format(code, text, tid))
                onerror = bundle.get('onerror')
                if onerror:
                    onerror(bundle.get('arg'), {'code': code, 'text': text})
        except Exception as err:
            log("Error handling server response", err)

# Channel instance for message loop to call Core (set in Channel.work())
_tinode_channel = None

# List of active subscriptions
subscriptions = {}
def add_subscription(topic):
    subscriptions[topic] = True

def del_subscription(topic):
    subscriptions.pop(topic, None)

def subscription_failed(topic, errcode):
    if topic == 'me':
        # Failed 'me' subscription means the bot is disfunctional.
        if errcode.get('code') == 502:
            # Cluster unreachable. Break the loop and retry in a few seconds.
            log("Server cluster unreachable, triggering reconnection")
            connection_state['connected'] = False
            connection_state['connection_error'] = f"Cluster unreachable (502)"
            client_post(None)
        else:
            log(f"Critical subscription failure: {errcode}")
            exit(1)

def login_error(unused, errcode):
    # Check for 409 "already authenticated".
    if errcode.get('code') != 409:
        exit(1)

def server_version(params):
    if params == None:
        return
    log("Server:", params['build'].decode('ascii'), params['ver'].decode('ascii'))

def next_id():
    next_id.tid += 1
    return str(next_id.tid)
next_id.tid = 100

class Plugin(pbx.PluginServicer):
    def Account(self, acc_event, context):
        action = None
        if acc_event.action == pb.CREATE:
            action = "created"
            # TODO: subscribe to the new user.

        elif acc_event.action == pb.UPDATE:
            action = "updated"
        elif acc_event.action == pb.DELETE:
            action = "deleted"
        else:
            action = "unknown"

        #log("Account", action, ":", acc_event.user_id, acc_event.public)
        logger.debug(f"Account {action}: {acc_event.user_id} {acc_event.public}")

        return pb.Unused()
    
queue_out = queue.Queue()

def client_generate():
    while True:
        msg = queue_out.get()
        if msg == None:
            return
        logger.debug(f"out: {to_json(msg)}")
        log("out:", to_json(msg))
        yield msg

def client_post(msg):
    queue_out.put(msg)

def client_reset():
    # Drain the queue
    try:
        while queue_out.get(False) != None:
            pass
    except queue.Empty:
        pass

def hello():
    tid = next_id()
    add_future(tid, {
        'onsuccess': lambda unused, params: server_version(params),
    })
    return pb.ClientMsg(hi=pb.ClientHi(id=tid, user_agent=APP_NAME + "/" + APP_VERSION + " (" +
        platform.system() + "/" + platform.release() + "); gRPC-python/" + LIB_VERSION,
        ver=LIB_VERSION, lang="EN"))

def login(cookie_file_name, scheme, secret):
    tid = next_id()
    add_future(tid, {
        'arg': cookie_file_name,
        'onsuccess': lambda fname, params: on_login(fname, params),
        'onerror': lambda unused, errcode: login_error(unused, errcode),
    })
    return pb.ClientMsg(login=pb.ClientLogin(id=tid, scheme=scheme, secret=secret))

def subscribe(topic, since_seq_id=None):
    """Subscribe to topic. If since_seq_id is set (e.g. from pres.seq_id when what=MSG), request message data so server sends {data}."""
    tid = next_id()
    add_future(tid, {
        'arg': topic,
        'onsuccess': lambda topicName, unused: add_subscription(topicName),
        'onerror': lambda topicName, errcode: subscription_failed(topicName, errcode),
    })
    if since_seq_id is not None and since_seq_id > 0:
        try:
            get_opts = pb.GetOpts(since_id=since_seq_id, limit=20)
            get_query = pb.GetQuery(what="data", data=get_opts)
            return pb.ClientMsg(sub=pb.ClientSub(id=tid, topic=topic, get_query=get_query))
        except (AttributeError, TypeError) as e:
            logger.warning("Tinode: subscribe with get_query not available (%s), subscribing without requesting data", e)
    return pb.ClientMsg(sub=pb.ClientSub(id=tid, topic=topic))

def leave(topic):
    tid = next_id()
    add_future(tid, {
        'arg': topic,
        'onsuccess': lambda topicName, unused: del_subscription(topicName)
    })
    return pb.ClientMsg(leave=pb.ClientLeave(id=tid, topic=topic))

def publish(topic, text):
    tid = next_id()
    return pb.ClientMsg(pub=pb.ClientPub(id=tid, topic=topic, no_echo=True,
        head={"auto": json.dumps(True).encode('utf-8')}, content=json.dumps(text).encode('utf-8')))

def note_read(topic, seq):
    
    return pb.ClientMsg(note=pb.ClientNote(topic=topic, what=pb.READ, seq_id=seq))

def init_server(listen):
    # Launch plugin server: accept connection(s) from the Tinode server.
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pbx.add_PluginServicer_to_server(Plugin(), server)
    server.add_insecure_port(listen)
    server.start()

    log("Plugin server running at '"+listen+"'")

    return server

def init_client(addr, schema, secret, cookie_file_name, secure, ssl_host):
    """Initialize client connection with proper state management"""
    try:
        log("Connecting to", "secure" if secure else "", "server at", addr,
            "SNI="+ssl_host if ssl_host else "")

        channel = None
        # gRPC keepalive: ping every 30s so Tinode/server doesn't close the connection (many time out at 60s)
        grpc_keepalive_ms = 30000
        grpc_keepalive_timeout_ms = 60000
        if secure:
            opts = (("grpc.ssl_target_name_override", ssl_host), ('grpc.keepalive_time_ms', grpc_keepalive_ms), ('grpc.keepalive_timeout_ms', grpc_keepalive_timeout_ms),) if ssl_host else None
            channel = grpc.secure_channel(addr, grpc.ssl_channel_credentials(), opts)
        else:
            opts = (('grpc.keepalive_time_ms', grpc_keepalive_ms), ('grpc.keepalive_timeout_ms', grpc_keepalive_timeout_ms),)
            channel = grpc.insecure_channel(addr, opts)

        # Store channel for later cleanup
        connection_state['channel'] = channel

        # Call the server
        stream = pbx.NodeStub(channel).MessageLoop(client_generate())
        connection_state['stream'] = stream

        # Session initialization sequence: {hi}, {login}, {sub topic='me'}
        client_post(hello())
        client_post(login(cookie_file_name, schema, secret))
        
        # Start the keepalive thread
        start_keepalive_thread()
        
        # Start the health monitor thread
        start_health_monitor_thread()
        
        # Update connection state
        update_connection_state(True)
        
        return stream
        
    except Exception as e:
        error_msg = f"Failed to initialize client: {str(e)}"
        log(error_msg)
        update_connection_state(False, error_msg)
        return None

def keepalive_task():
    """Send hello periodically so Tinode server does not close the connection."""
    interval = RECONNECT_CONFIG.get('keepalive_interval', 90)
    while True:
        try:
            time.sleep(interval)
            log("Sending keepalive hello message")
            client_post(hello())
        except Exception as e:
            log("Error in keepalive task:", e)

def start_keepalive_thread():
    """Start the keepalive thread if not already running"""
    # Check if keepalive thread is already running
    for thread in threading.enumerate():
        if thread.name == "keepalive_thread":
            log("Keepalive thread already running")
            return
    
    # Create and start the keepalive thread
    keepalive_thread = threading.Thread(target=keepalive_task, name="keepalive_thread")
    keepalive_thread.daemon = True  # Make the thread daemon so it exits when the main program exits
    keepalive_thread.start()
    log("Keepalive thread started")

def connection_health_monitor():
    """Monitor connection health and trigger reconnection if needed"""
    while True:
        try:
            time.sleep(RECONNECT_CONFIG['health_check_interval'])
            
            if not connection_state['connected']:
                log("Connection health check: not connected")
                continue
                
            # Optional: reconnect only if no server message for a very long time. idle_timeout=0 disables (recommended).
            idle_timeout = RECONNECT_CONFIG.get('idle_timeout', 0)
            if idle_timeout > 0 and connection_state['last_connection_time']:
                idle_time = time.time() - connection_state['last_connection_time']
                if idle_time > idle_timeout:
                    log(f"Connection idle for {idle_time:.1f}s (>{idle_timeout}s), triggering reconnection")
                    update_connection_state(False, "Connection idle timeout")
                    client_post(None)
            
            # Optional: periodic re-login (reconnect so we run hello + login + subscribe again; refreshes session/cookie).
            relogin = RECONNECT_CONFIG.get('relogin_interval', 0)
            if relogin > 0 and connection_state.get('connected_since'):
                uptime = time.time() - connection_state['connected_since']
                if uptime >= relogin:
                    log(f"Periodic re-login after {uptime:.0f}s (interval={relogin}s), triggering reconnect")
                    update_connection_state(False, "Periodic re-login")
                    client_post(None)
                    
        except Exception as e:
            log(f"Error in connection health monitor: {e}")

def start_health_monitor_thread():
    """Start the connection health monitoring thread"""
    # Check if health monitor thread is already running
    for thread in threading.enumerate():
        if thread.name == "health_monitor_thread":
            log("Health monitor thread already running")
            return
    
    # Create and start the health monitor thread
    health_thread = threading.Thread(target=connection_health_monitor, name="health_monitor_thread")
    health_thread.daemon = True
    health_thread.start()
    log("Health monitor thread started")

def update_connection_state(connected: bool, error: str = None):
    """Update connection state and log changes"""
    if connection_state['connected'] != connected:
        connection_state['connected'] = connected
        connection_state['connection_error'] = error
        if connected:
            connection_state['last_connection_time'] = time.time()
            connection_state['connected_since'] = time.time()
            connection_state['reconnect_attempts'] = 0
            log("Connection established successfully")
        else:
            connection_state['connected_since'] = None
            log(f"Connection lost: {error if error else 'Unknown error'}")

def calculate_reconnect_delay():
    """Calculate exponential backoff delay for reconnection"""
    attempts = connection_state['reconnect_attempts']
    if attempts == 0:
        return RECONNECT_CONFIG['initial_delay']
    
    delay = RECONNECT_CONFIG['initial_delay'] * (RECONNECT_CONFIG['backoff_factor'] ** attempts)
    return min(delay, RECONNECT_CONFIG['max_delay'])

def reset_connection_state():
    """Reset connection state for fresh connection attempt"""
    connection_state['connected'] = False
    connection_state['connection_error'] = None
    connection_state['connected_since'] = None
    connection_state['stream'] = None
    connection_state['channel'] = None

def get_connection_status():
    """Get current connection status information"""
    return {
        'connected': connection_state['connected'],
        'reconnect_attempts': connection_state['reconnect_attempts'],
        'last_connection_time': connection_state['last_connection_time'],
        'connection_error': connection_state['connection_error'],
        'uptime': time.time() - connection_state['last_connection_time'] if connection_state['last_connection_time'] else 0
    }


def client_message_loop(stream):
    """Enhanced message loop with connection monitoring and error handling"""
    try:
        log("Starting message loop")
        update_connection_state(True)
        
        # Read server responses
        for msg in stream:
            connection_state['last_connection_time'] = time.time()
            log(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], "in:", to_json(msg))

            if msg.HasField("ctrl"):
                # Run code on command completion
                exec_future(msg.ctrl.id, msg.ctrl.code, msg.ctrl.text, msg.ctrl.params)
                
                # Check for connection-related errors
                if msg.ctrl.code >= 500 and msg.ctrl.code < 600:
                    log(f"Server error detected: {msg.ctrl.code} - {msg.ctrl.text}")
                    if msg.ctrl.code == 502:  # Cluster unreachable
                        update_connection_state(False, f"Cluster unreachable (502)")
                        return  # Exit loop to trigger reconnection

            elif msg.HasField("data"):
                log("Message Data:", msg.data)
                log("message from:", msg.data.from_user_id)
                
                encoded_content = msg.data.content
                # If encoded_content is bytes, decode it to get the string representation
                if isinstance(encoded_content, bytes):
                    encoded_content = encoded_content.decode('utf-8')

                data_type = 'text'
                subtype = ''
                content_dict = None
                # Parse the JSON string into a Python dictionary
                try:
                    # Attempt to parse the JSON string
                    content_dict = json.loads(encoded_content)
                    
                    # Access the MIME type
                    mime_type = content_dict["ent"][0]["data"]["mime"]
                    parts = mime_type.split('/')
                    data_type = parts[0]
                    subtype = parts[1] if len(parts) > 1 else None
                except Exception as err:
                    # Plain text or other non-JSON content — treat as text
                    logger.debug("Message content is plain text (not JSON)")
                    data_type = 'text'
                    subtype = ''
                

                # Protection against the bot talking to self from another session (unless ALLOW_SAME_USER).
                from_id = msg.data.from_user_id or ""
                skip_self = (from_id == botUID) and not ALLOW_SAME_USER
                log("Tinode: from_user_id=%s botUID=%s skip_self=%s allow_same_user=%s" % (from_id, botUID, skip_self, ALLOW_SAME_USER))
                if skip_self:
                    log("Tinode: skipping (message from bot's account). Use a different Tinode account on mobile, or set TINODE_ALLOW_SAME_USER=1.")
                if not skip_self:
                    # Respond to message.
                    # Mark received message as read
                    client_post(note_read(msg.data.topic, msg.data.seq_id))
                    # Insert a small delay to prevent accidental DoS self-attack.
                    time.sleep(0.1)
                    # Forward to Core and reply via process_message_queue when response arrives
                    if data_type == 'text':
                        encoded_content = msg.data.content
                        if isinstance(encoded_content, bytes):
                            encoded_content = encoded_content.decode('utf-8')
                        log("Message content:", encoded_content)
                        text_content = encoded_content if isinstance(encoded_content, str) else encoded_content.decode('utf-8')
                        msg_id = str(msg.data.seq_id)
                        if _tinode_channel is not None:
                            core_url = Util().get_channels_core_url()
                            log("Tinode: sending text to Core at", core_url + "/process", "(msg_id=%s, topic=%s)" % (msg_id, msg.data.topic))
                            logger.info(f"Tinode: sending text to Core at {core_url}/process (msg_id={msg_id}, topic={msg.data.topic})")
                            _tinode_channel.chats[msg_id] = msg.data.topic
                            request = PromptRequest(
                                request_id=msg_id,
                                channel_name=_tinode_channel.metadata.name if _tinode_channel else 'tinode',
                                request_metadata={'sender': msg.data.topic, 'msg_id': msg_id, 'channel': 'tinode'},
                                channelType=ChannelType.IM,
                                user_name=msg.data.topic,
                                app_id='tinode',
                                user_id='tinode:' + msg.data.topic,
                                contentType=ContentType.TEXT,
                                text=text_content,
                                action='respond',
                                host=_tinode_channel.metadata.host if _tinode_channel else 0,
                                port=_tinode_channel.metadata.port if _tinode_channel else 0,
                                images=[],
                                videos=[],
                                audios=[],
                                files=None,
                                timestamp=datetime.now().timestamp(),
                            )
                            try:
                                _tinode_channel.syncTransferTocore(request=request)
                            except Exception as e:
                                logger.exception(f"Tinode: syncTransferTocore failed: {e}")
                        else:
                            log("Tinode: _tinode_channel is None, echoing message (not sending to Core). Start channel with: python -m channels.run tinode")
                            logger.warning("Tinode: _tinode_channel is None, echoing message (not sending to Core). Is the channel started via Channel.work()?")
                            client_post(publish(msg.data.topic, text_content))
                    elif data_type == 'image':
                        # Build data URL and send to Core with TEXTWITHIMAGE
                        try:
                            b64_val = content_dict['ent'][0]['data']['val']
                            mime = content_dict['ent'][0]['data'].get('mime', 'image/png')
                            data_url = f"data:{mime};base64,{b64_val}"
                            msg_id = str(msg.data.seq_id)
                            if _tinode_channel is not None:
                                _tinode_channel.chats[msg_id] = msg.data.topic
                            request = PromptRequest(
                                request_id=msg_id,
                                channel_name=_tinode_channel.metadata.name if _tinode_channel else 'tinode',
                                request_metadata={'sender': msg.data.topic, 'msg_id': msg_id, 'channel': 'tinode'},
                                channelType=ChannelType.IM,
                                user_name=msg.data.topic,
                                app_id='tinode',
                                user_id='tinode:' + msg.data.topic,
                                contentType=ContentType.TEXTWITHIMAGE,
                                text='User sent an image',
                                action='respond',
                                host=_tinode_channel.metadata.host if _tinode_channel else 0,
                                port=_tinode_channel.metadata.port if _tinode_channel else 0,
                                images=[data_url],
                                videos=[],
                                audios=[],
                                files=None,
                                timestamp=datetime.now().timestamp(),
                            )
                            if _tinode_channel is not None:
                                _tinode_channel.syncTransferTocore(request=request)
                            else:
                                client_post(publish(msg.data.topic, 'Image received'))
                        except Exception as err:
                            log("Error handling image: %s" % err)
                            client_post(publish(msg.data.topic, 'Image received'))
                    elif data_type == 'audio':
                        try:
                            b64_val = content_dict.get('ent', [{}])[0].get('data', {}).get('val')
                            if b64_val:
                                audio_bytes = base64.b64decode(b64_val)
                                root = Path(__file__).resolve().parent.parent.parent
                                docs_dir = root / "channels" / "tinode" / "docs"
                                docs_dir.mkdir(parents=True, exist_ok=True)
                                ext = (subtype or 'bin').split(';')[0].strip() or 'bin'
                                filename = docs_dir / f"audio_{msg.data.seq_id}_{int(time.time())}.{ext}"
                                filename.write_bytes(audio_bytes)
                                msg_id = str(msg.data.seq_id)
                                if _tinode_channel is not None:
                                    _tinode_channel.chats[msg_id] = msg.data.topic
                                    request = PromptRequest(
                                        request_id=msg_id,
                                        channel_name=_tinode_channel.metadata.name,
                                        request_metadata={'sender': msg.data.topic, 'msg_id': msg_id, 'channel': 'tinode'},
                                        channelType=ChannelType.IM,
                                        user_name=msg.data.topic,
                                        app_id='tinode',
                                        user_id='tinode:' + msg.data.topic,
                                        contentType=ContentType.AUDIO,
                                        text='User sent audio',
                                        action='respond',
                                        host=getattr(_tinode_channel, 'metadata', None) and _tinode_channel.metadata.host or 0,
                                        port=getattr(_tinode_channel, 'metadata', None) and _tinode_channel.metadata.port or 0,
                                        images=[],
                                        videos=[],
                                        audios=[str(filename.resolve())],
                                        files=None,
                                        timestamp=datetime.now().timestamp(),
                                    )
                                    _tinode_channel.syncTransferTocore(request=request)
                                else:
                                    client_post(publish(msg.data.topic, 'Audio received'))
                        except Exception as err:
                            log("Error handling audio: %s" % err)
                            client_post(publish(msg.data.topic, 'Audio received'))
                    elif data_type == 'video':
                        try:
                            b64_val = content_dict.get('ent', [{}])[0].get('data', {}).get('val')
                            if b64_val:
                                video_bytes = base64.b64decode(b64_val)
                                root = Path(__file__).resolve().parent.parent.parent
                                docs_dir = root / "channels" / "tinode" / "docs"
                                docs_dir.mkdir(parents=True, exist_ok=True)
                                ext = (subtype or 'mp4').split(';')[0].strip() or 'mp4'
                                filename = docs_dir / f"video_{msg.data.seq_id}_{int(time.time())}.{ext}"
                                filename.write_bytes(video_bytes)
                                msg_id = str(msg.data.seq_id)
                                if _tinode_channel is not None:
                                    _tinode_channel.chats[msg_id] = msg.data.topic
                                    request = PromptRequest(
                                        request_id=msg_id,
                                        channel_name=_tinode_channel.metadata.name,
                                        request_metadata={'sender': msg.data.topic, 'msg_id': msg_id, 'channel': 'tinode'},
                                        channelType=ChannelType.IM,
                                        user_name=msg.data.topic,
                                        app_id='tinode',
                                        user_id='tinode:' + msg.data.topic,
                                        contentType=ContentType.VIDEO,
                                        text='User sent video',
                                        action='respond',
                                        host=getattr(_tinode_channel.metadata, 'host', 0),
                                        port=getattr(_tinode_channel.metadata, 'port', 0),
                                        images=[],
                                        videos=[str(filename.resolve())],
                                        audios=[],
                                        files=None,
                                        timestamp=datetime.now().timestamp(),
                                    )
                                    _tinode_channel.syncTransferTocore(request=request)
                                else:
                                    client_post(publish(msg.data.topic, 'Video received'))
                        except Exception as err:
                            log("Error handling video: %s" % err)
                            client_post(publish(msg.data.topic, 'Video received'))
                    else:
                        # file / application / other: save to docs and send as files
                        try:
                            b64_val = content_dict.get('ent', [{}])[0].get('data', {}).get('val')
                            if b64_val:
                                raw = base64.b64decode(b64_val)
                                root = Path(__file__).resolve().parent.parent.parent
                                docs_dir = root / "channels" / "tinode" / "docs"
                                docs_dir.mkdir(parents=True, exist_ok=True)
                                ext = (subtype or 'bin').split(';')[0].strip() or 'bin'
                                filename = docs_dir / f"file_{msg.data.seq_id}_{int(time.time())}.{ext}"
                                filename.write_bytes(raw)
                                msg_id = str(msg.data.seq_id)
                                if _tinode_channel is not None:
                                    _tinode_channel.chats[msg_id] = msg.data.topic
                                    request = PromptRequest(
                                        request_id=msg_id,
                                        channel_name=_tinode_channel.metadata.name,
                                        request_metadata={'sender': msg.data.topic, 'msg_id': msg_id, 'channel': 'tinode'},
                                        channelType=ChannelType.IM,
                                        user_name=msg.data.topic,
                                        app_id='tinode',
                                        user_id='tinode:' + msg.data.topic,
                                        contentType=ContentType.TEXT,
                                        text='User sent a file',
                                        action='respond',
                                        host=getattr(_tinode_channel.metadata, 'host', 0),
                                        port=getattr(_tinode_channel.metadata, 'port', 0),
                                        images=[],
                                        videos=[],
                                        audios=[],
                                        files=[str(filename.resolve())],
                                        timestamp=datetime.now().timestamp(),
                                    )
                                    _tinode_channel.syncTransferTocore(request=request)
                                else:
                                    client_post(publish(msg.data.topic, 'File received'))
                        except Exception as err:
                            log("Error handling file: %s" % err)
                            client_post(publish(msg.data.topic, 'File received'))

            elif msg.HasField("pres"):
                # log("presence:", msg.pres.topic, msg.pres.what)
                # Wait for peers to appear online and subscribe to their topics.
                # For MSG we must request message data (get_query) so the server sends {data} with content.
                if msg.pres.topic == 'me':
                    if (msg.pres.what == pb.ServerPres.ON or msg.pres.what == pb.ServerPres.MSG) \
                            and subscriptions.get(msg.pres.src) == None:
                        seq_id = msg.pres.seq_id if msg.pres.what == pb.ServerPres.MSG else None
                        client_post(subscribe(msg.pres.src, since_seq_id=seq_id))
                    elif msg.pres.what == pb.ServerPres.OFF and subscriptions.get(msg.pres.src) != None:
                        client_post(leave(msg.pres.src))
                        #pass
            else:
                # Ignore everything else
                pass

    except grpc._channel._Rendezvous as err:
        error_msg = f"gRPC connection error: {err}"
        log(error_msg)
        update_connection_state(False, error_msg)
    except grpc.RpcError as err:
        error_msg = f"gRPC RPC error: {err.code()} - {err.details()}"
        log(error_msg)
        update_connection_state(False, error_msg)
    except Exception as err:
        error_msg = f"Unexpected error in message loop: {str(err)}"
        log(error_msg)
        update_connection_state(False, error_msg)

def read_auth_cookie(cookie_file_name):
    """Read authentication token from a file"""
    cookie = open(cookie_file_name, 'r')
    params = json.load(cookie)
    cookie.close()
    schema = params.get("schema")
    secret = None
    if schema == None:
        return None, None
    if schema == 'token':
        secret = base64.b64decode(params.get('secret').encode('utf-8'))
    else:
        secret = params.get('secret').encode('utf-8')
    return schema, secret

def on_login(cookie_file_name, params):
    global botUID
    
    """Handle successful login and save authentication token"""
    if params == None or cookie_file_name == None:
        return

    if 'user' in params:
        botUID = params['user'].decode("ascii")[1:-1]
        log(f"Successfully logged in as user: {botUID}")
        log("Tinode channel (bot) is logged in as this account. Messages from this user id are ignored unless you set TINODE_ALLOW_SAME_USER=1 (or use a different account on the mobile app).")
        
        # Update connection state on successful login
        update_connection_state(True, None)

    # Subscribe to 'me' topic after successful login
    client_post(subscribe('me'))

    # Protobuf map 'params' is not a python object or dictionary. Convert it.
    nice = {'schema': 'token'}
    for key_in in params:
        if key_in == 'token':
            key_out = 'secret'
        else:
            key_out = key_in
        nice[key_out] = json.loads(params[key_in].decode('utf-8'))

    try:
        cookie = open(cookie_file_name, 'w')
        json.dump(nice, cookie)
        cookie.close()
        log("Authentication cookie saved successfully")
    except Exception as err:
        log("Failed to save authentication cookie", err)

def run(args):
    """Enhanced run function with robust reconnection logic"""
    schema = None
    secret = None

    if args.login_token:
        """Use token to login"""
        schema = 'token'
        secret = args.login_token.encode('ascii')
        log("Logging in with token", args.login_token)

    elif args.login_basic:
        """Use username:password"""
        schema = 'basic'
        secret = args.login_basic.encode('utf-8')
        log("Logging in with login:password", args.login_basic)

    else:
        """Try reading the cookie file"""
        try:
            schema, secret = read_auth_cookie(args.login_cookie)
            log("Logging in with cookie file", args.login_cookie)
        except Exception as err:
            log("Failed to read authentication cookie", err)

    if schema:
        # Start Plugin server
        server = init_server(args.listen)
        
        # Initialize client connection
        stream = None
        
        # Run with robust reconnection logic
        while True:
            try:
                if not connection_state['connected']:
                    # Calculate reconnection delay
                    if connection_state['reconnect_attempts'] > 0:
                        delay = calculate_reconnect_delay()
                        log(f"Waiting {delay} seconds before reconnection attempt {connection_state['reconnect_attempts']}")
                        time.sleep(delay)
                    
                    # Reset connection state for new attempt
                    reset_connection_state()
                    
                    log(f"Attempting connection (attempt {connection_state['reconnect_attempts'] + 1})")
                    stream = init_client(args.host, schema, secret, args.login_cookie, args.ssl, args.ssl_host)
                    
                    if stream is None:
                        connection_state['reconnect_attempts'] += 1
                        if connection_state['reconnect_attempts'] >= RECONNECT_CONFIG['max_attempts']:
                            log("Maximum reconnection attempts reached, exiting")
                            break
                        continue
                    
                    connection_state['reconnect_attempts'] += 1
                
                # Run message loop (this will block until connection is lost)
                log("Connection established, starting message loop")
                client_message_loop(stream)
                
                # If we get here, connection was lost
                log("Connection lost, preparing for reconnection")
                
            except KeyboardInterrupt:
                log("Received interrupt signal, shutting down")
                break
            except Exception as e:
                error_msg = f"Unexpected error in main loop: {str(e)}"
                log(error_msg)
                update_connection_state(False, error_msg)
                
                if connection_state['reconnect_attempts'] >= RECONNECT_CONFIG['max_attempts']:
                    log("Maximum reconnection attempts reached, exiting")
                    break
            
            # Reset client before next connection attempt
            client_reset()
            
        # Graceful shutdown
        log("Shutting down gracefully")
        if server:
            server.stop(None)
        if connection_state['stream']:
            connection_state['stream'].cancel()

    else:
        log("Error: authentication scheme not defined")
    
class Channel(BaseChannel):
    def __init__(self, metadata: ChannelMetadata):
        super().__init__(metadata=metadata, app=channel_app)

        self.message_queue = asyncio.Queue()
        self.message_queue_task = None
        self.chats = {}
        
    # def handle_message(self, client: NewClient, message: MessageEv):
    #     try:
    #         #send receipt otherwise we keep receiving the same message over and over
    #         content = message.Message.conversation or message.Message.extendedTextMessage.text
    #         sender = message.Info.MessageSource.Sender.User
    #         msg_id = message.Info.ID
    #         chat = message.Info.MessageSource.Chat
    #         self.chats[msg_id] =  chat

    #         # Extract data from request
    #         im_name = 'whatsapp'
    #         sender = 'whatsapp:' + sender
    #         logger.debug(f"whatsapp Received message from {sender}: {content}")

    #         text = ''
    #         action = ''
    #         if content.startswith('+') or content.startswith('+'):
    #             action = 'store'
    #             text = content[1:]
    #         elif content.startswith('?') or content.startswith('？'):
    #             action = 'retrieve'
    #             text =content[1:]
    #         else:
    #             action = 'respond'
    #             text = content

    #         request = PromptRequest(
    #             request_id= msg_id,
    #             channel_name= self.metadata.name,
    #             request_metadata={'sender': sender, 'msg_id': msg_id, 'channel': 'whatsapp'},
    #             channelType=ChannelType.IM.value,
    #             user_name= sender,
    #             app_id= im_name,
    #             user_id= sender, # The wechaty will return like wechat:shileipeng
    #             contentType=ContentType.TEXT.value,
    #             text= text,
    #             action=action,
    #             host= self.metadata.host,
    #             port= self.metadata.port,
    #             images=[],
    #             videos=[],
    #             audios=[],
    #             timestamp= datetime.now().timestamp()
    #         )

    #         # Call handle_message with the extracted data
    #         self.syncTransferTocore(request=request)

    #     except Exception as e:
    #         logger.exception(e)
    #         return {"message": "System Internal Error", "response": "Sorry, something went wrong. Please try again later."}         
    


    async def process_message_queue(self):
        while True:
            try:
                response: AsyncResponse = await self.message_queue.get()
                logger.debug(f"Got response: {response} from message queue")
                request_id = getattr(response, "request_id", "")
                response_data = getattr(response, "response_data", {}) or {}
                request_metadata = getattr(response, "request_metadata", None) or {}
                to = request_metadata.get("sender") or request_metadata.get("topic")
                msg_id_raw = request_metadata.get("msg_id")
                msg_id = str(msg_id_raw) if msg_id_raw is not None else None
                if not msg_id:
                    logger.warning("Tinode: response missing request_metadata.msg_id, cannot route to topic")
                    self.message_queue.task_done()
                    continue
                if "text" in response_data:
                    text = response_data["text"]
                    chat = self.chats.pop(msg_id, None)
                    if chat is None:
                        logger.warning("Tinode: no topic for msg_id=%s (chats had %s), response not sent to app", msg_id, list(self.chats.keys())[:5])
                    else:
                        try:
                            client_post(publish(chat, text))
                            logger.info("Tinode: sent response to topic %s (msg_id=%s)", chat, msg_id)
                        except Exception as e:
                            logger.error("Tinode: error sending to Tinode: %s", e)
                else:
                    logger.debug("Tinode: response has no 'text' in response_data")
                self.message_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception("Tinode: error processing message queue: %s", e)


    def initialize(self):
        logger.debug("Tinode Channel initializing...")
        self.message_queue_task = asyncio.create_task(self.process_message_queue())
        
        # Add connection status endpoint
        @self.app.get("/connection_status")
        def get_connection_status_endpoint():
            """Get current Tinode connection status"""
            return get_connection_status()
        
        super().initialize()
        

    def stop(self):
        # do some deinitialization here
        super().stop()
        self.message_queue_task.cancel()
        logger.debug("Tinode Channel is stopping!")
        
        
    async def handle_async_response(self, response: AsyncResponse):
        rid = getattr(response, "request_id", "?")
        meta = getattr(response, "request_metadata", None) or {}
        logger.info("Tinode: received response from Core request_id=%s sender=%s msg_id=%s", rid, meta.get("sender"), meta.get("msg_id"))
        logger.debug("Put response: %s into message queue", response)
        await self.message_queue.put(response) 

    def stop(self):
        super().stop()
        
    def work(self):
        global _tinode_channel
        _tinode_channel = self
        random.seed()

        purpose = "Tino, Tinode's chatbot."
        log(purpose)
        parser = argparse.ArgumentParser(description=purpose)
        parser.add_argument('--host', default='200.69.21.246:16060', help='address of Tinode server gRPC endpoint')
        parser.add_argument('--ssl', action='store_true', help='use SSL to connect to the server')
        parser.add_argument('--ssl-host', help='SSL host name to use instead of default (useful for connecting to localhost)')
        parser.add_argument('--listen', default='0.0.0.0:40051', help='address to listen on for incoming Plugin API calls')
        parser.add_argument('--login-basic', default='homeclaw_user:password',help='login using basic authentication username:password')
        parser.add_argument('--login-token', help='login using token authentication')
        parser.add_argument('--login-cookie', default='.tn-cookie', help='read credentials from the provided cookie file')
        args = parser.parse_args()

        run(args)
                
                        
shutdown_url = ""
def main():
    random.seed()

    try:
        root = Util().channels_path()
        config_path = os.path.join(root, 'tinode', 'config.yml')
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            metadata = ChannelMetadata(**config)
            global shutdown_url
            host = metadata.host
            if host == '0.0.0.0':
                host = '127.0.0.1'
            shutdown_url = "http://" + host + ":" + str(metadata.port) + "/shutdown"

        with Channel(metadata=metadata) as channel:
            # Create a thread to run channel.work()
            work_thread = threading.Thread(target=channel.work)
            work_thread.daemon = True  # Make the thread daemon so it exits when the main program exits
            work_thread.start()
            
            # Run the async event loop in the main thread
            asyncio.run(channel.run())
    except Exception as e:
        logger.exception(e)
        
def suicide():
    try:
        global shutdown_url
        httpx.get(shutdown_url)
    except Exception as e:
        logger.exception(e)


if __name__ == '__main__':
    """Parse command-line arguments. Extract server host name, listen address, authentication scheme"""
    main()
 
