import streamlit as st
import requests
import json
import time
import websocket
import threading
from datetime import datetime
import pandas as pd

# API endpoint URLs
API_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "token" not in st.session_state:
    st.session_state.token = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "username" not in st.session_state:
    st.session_state.username = None

if "current_channel" not in st.session_state:
    st.session_state.current_channel = None

if "channels" not in st.session_state:
    st.session_state.channels = []

if "messages" not in st.session_state:
    st.session_state.messages = {}

if "ws" not in st.session_state:
    st.session_state.ws = None

if "users" not in st.session_state:
    st.session_state.users = []

if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False

if "ws_connecting" not in st.session_state:
    st.session_state.ws_connecting = False

# Helper functions
def api_request(endpoint, method="GET", data=None, token=None):
    """Make a request to the API"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    if method == "GET":
        response = requests.get(f"{API_URL}/{endpoint}", headers=headers)
    elif method == "POST":
        response = requests.post(f"{API_URL}/{endpoint}", json=data, headers=headers)
    
    return response

def signup(username, password):
    """Sign up a new user"""
    try:
        response = api_request(
            "signup", 
            method="POST", 
            data={"username": username, "password": password}
        )
        if response.status_code == 200:
            st.success("Signup successful! You can now log in.")
            return True
        else:
            st.error(f"Signup failed: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Error during signup: {str(e)}")
        return False

def login(username, password):
    """Log in a user"""
    try:
        response = requests.post(
            f"{API_URL}/login",
            data={"username": username, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.token = data["access_token"]
            st.session_state.authenticated = True
            st.session_state.username = username
            
            # Get user info
            user_info = get_user_info()
            if user_info:
                st.session_state.user_id = user_info["id"]
            
            # Load channels
            load_channels()
            
            # Load users
            load_users()
            
            return True
        else:
            st.error(f"Login failed: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Error during login: {str(e)}")
        return False

def get_user_info():
    """Get current user info from channels list"""
    try:
        response = api_request("channels", token=st.session_state.token)
        if response.status_code == 200:
            # Find the user in the members list
            for channel in response.json():
                for member in channel["members"]:
                    if member["username"] == st.session_state.username:
                        return member
        return None
    except Exception as e:
        st.error(f"Error getting user info: {str(e)}")
        return None

def load_channels():
    """Load user's channels"""
    try:
        response = api_request("channels", token=st.session_state.token)
        if response.status_code == 200:
            st.session_state.channels = response.json()
            
            # Initialize messages dict for each channel
            for channel in st.session_state.channels:
                if channel["id"] not in st.session_state.messages:
                    st.session_state.messages[channel["id"]] = []
            
            return True
        else:
            st.error(f"Failed to load channels: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Error loading channels: {str(e)}")
        return False

def load_users():
    """Load all users"""
    try:
        response = api_request("users", token=st.session_state.token)
        if response.status_code == 200:
            st.session_state.users = response.json()
            return True
        else:
            st.error(f"Failed to load users: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Error loading users: {str(e)}")
        return False

def load_messages(channel_id):
    """Load messages for a channel"""
    try:
        response = api_request(f"messages?channel_id={channel_id}", token=st.session_state.token)
        if response.status_code == 200:
            # Sort messages by creation time
            messages = response.json()
            messages.sort(key=lambda m: m["created_at"])
            st.session_state.messages[channel_id] = messages
            
            # Mark messages as read
            api_request(f"messages/read?channel_id={channel_id}", method="POST", token=st.session_state.token)
            
            return True
        else:
            st.error(f"Failed to load messages: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Error loading messages: {str(e)}")
        return False

def create_direct_channel(user_id):
    """Create a direct message channel with another user"""
    try:
        response = api_request(
            f"channels/direct?user_id={user_id}", 
            method="POST", 
            token=st.session_state.token
        )
        if response.status_code == 200:
            # Reload channels
            load_channels()
            # Switch to the new channel
            channel_data = response.json()
            st.session_state.current_channel = channel_data["id"]
            # Load messages
            load_messages(channel_data["id"])
            return True
        else:
            st.error(f"Failed to create channel: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Error creating channel: {str(e)}")
        return False

def create_group_channel(name, member_ids):
    """Create a group channel"""
    try:
        # Convert any None values to actual numbers if needed
        valid_member_ids = [int(member_id) for member_id in member_ids if member_id is not None]
        
        response = api_request(
            "channels/group", 
            method="POST", 
            data={
                "name": name,
                "type": "group",
                "member_ids": valid_member_ids
            },
            token=st.session_state.token
        )
        if response.status_code == 200:
            # Reload channels
            load_channels()
            # Switch to the new channel
            channel_data = response.json()
            st.session_state.current_channel = channel_data["id"]
            # Load messages for the new channel
            load_messages(channel_data["id"])
            # Connect WebSocket for the new channel
            connect_websocket(channel_data["id"])
            return True
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            st.error(f"Failed to create group: {error_detail}")
            return False
    except Exception as e:
        st.error(f"Error creating group: {str(e)}")
        return False

def send_message(channel_id, content):
    """Send a message via WebSocket"""
    if not st.session_state.ws or not hasattr(st.session_state.ws, 'sock') or not st.session_state.ws.sock or not st.session_state.ws.sock.connected:
        # Try to reconnect
        connect_websocket(channel_id)
        time.sleep(1)  # Give it a moment to connect
        
    # Check again after potential reconnection
    if st.session_state.ws and hasattr(st.session_state.ws, 'sock') and st.session_state.ws.sock and st.session_state.ws.sock.connected:
        message = {
            "content": content,
            "channel_id": channel_id
        }
        try:
            st.session_state.ws.send(json.dumps(message))
            return True
        except Exception as e:
            st.error(f"Error sending message: {str(e)}")
            # Reconnect on error
            connect_websocket(channel_id)
            return False
    else:
        st.error("WebSocket not connected. Trying to reconnect...")
        # Try once more
        connect_websocket(channel_id)
        return False

def connect_websocket(channel_id):
    """Connect to WebSocket for a channel"""
    try:
        # Close existing connection if any
        close_websocket()
        
        # Create WebSocket connection
        ws_endpoint = f"{WS_URL}/ws/chat?token={st.session_state.token}&channel_id={channel_id}"
        
        # Initialize connection status
        st.session_state.ws_connected = False
        st.session_state.ws_connecting = True
        
        # Create a local variable to track connection state that's accessible in threads
        # This avoids accessing st.session_state from background threads
        connecting = True
        
        # Setup WebSocket
        ws = websocket.WebSocketApp(
            ws_endpoint,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Start WebSocket connection in a background thread
        def run_websocket():
            nonlocal connecting  # Use a local variable instead of session state
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                try:
                    if not ws.sock or not ws.sock.connected:
                        ws.run_forever(ping_interval=30, ping_timeout=10)
                    
                    # If we get here, the WebSocket was closed intentionally
                    if not connecting:  # Use local variable instead of session state
                        break
                        
                    # Only increment retry count for errors, not intentional closes
                    retry_count += 1
                    time.sleep(min(retry_count * 2, 10))  # Exponential backoff
                except Exception as e:
                    # Log error but continue retrying
                    print(f"WebSocket error in thread: {str(e)}")
                    retry_count += 1
                    time.sleep(min(retry_count * 2, 10))
            
            # We can't update session state from a background thread in Streamlit
            # So we don't set session state here
        
        thread = threading.Thread(target=run_websocket)
        thread.daemon = True
        thread.start()
        
        # Store WebSocket connection
        st.session_state.ws = ws
        
        # Wait a bit for connection to establish before returning
        time.sleep(2)
        return True
    except Exception as e:
        st.error(f"Error connecting to WebSocket: {str(e)}")
        st.session_state.ws = None
        st.session_state.ws_connected = False
        st.session_state.ws_connecting = False
        return False

def close_websocket():
    """Close WebSocket connection"""
    if st.session_state.ws:
        # Mark that we're intentionally closing
        st.session_state.ws_connecting = False
        # Close the connection
        try:
            st.session_state.ws.close()
        except:
            pass
        st.session_state.ws = None
        st.session_state.ws_connected = False

def on_open(ws):
    """Handle WebSocket open event"""
    # We can't set session state directly from WebSocket callbacks
    # So we'll just print a message here
    print("WebSocket connection opened")
    # The main thread will need to check connection status another way

def on_message(ws, message):
    """Handle incoming WebSocket messages"""
    try:
        data = json.loads(message)
        message_type = data.get("message_type")
        
        if message_type == "message":
            # Add message to session state
            msg_data = data.get("data")
            channel_id = msg_data.get("channel_id")
            
            # Make sure the channel exists in messages dict
            if channel_id not in st.session_state.messages:
                st.session_state.messages[channel_id] = []
                
            # Add message to channel
            st.session_state.messages[channel_id].append(msg_data)
            
            # Queue a rerun
            # We can't call st.experimental_rerun() directly from a thread
            # But we can set a flag that the main thread can check
            st.session_state.new_message = True
            
        elif message_type == "connection_status" and data.get("data", {}).get("status") == "connected":
            # When we get a connection confirmation from the server
            print("WebSocket confirmed connected")
            
        elif message_type == "notification":
            # Handle notification (user joined/left)
            # We can't show a toast from a background thread
            print(f"Notification: {data.get('data')}")
            st.session_state.notification = data.get("data")
            
    except Exception as e:
        print(f"Error handling WebSocket message: {str(e)}")

def on_error(ws, error):
    """Handle WebSocket errors"""
    st.error(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_reason):
    """Handle WebSocket closure"""
    pass

def format_timestamp(timestamp_str):
    """Format timestamp for display"""
    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    return dt.strftime("%H:%M")

def logout():
    """Log out the user"""
    # Close WebSocket connection
    close_websocket()
    
    # Clear session state
    st.session_state.authenticated = False
    st.session_state.token = None
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.current_channel = None
    st.session_state.channels = []
    st.session_state.messages = {}
    st.session_state.users = []
    
    # Rerun to refresh UI
    st.experimental_rerun()

# Main UI
st.title("Real-time Chat App")

if not st.session_state.authenticated:
    # Login / Signup tabs
    tab1, tab2 = st.tabs(["Login", "Signup"])
    
    with tab1:
        st.subheader("Login")
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login", key="login_button"):
            if login_username and login_password:
                login(login_username, login_password)
            else:
                st.warning("Please enter username and password")
    
    with tab2:
        st.subheader("Sign Up")
        signup_username = st.text_input("Username", key="signup_username")
        signup_password = st.text_input("Password", type="password", key="signup_password")
        
        if st.button("Sign Up", key="signup_button"):
            if signup_username and signup_password:
                signup(signup_username, signup_password)
            else:
                st.warning("Please enter username and password")
else:
    # Chat interface
    st.sidebar.subheader(f"Welcome, {st.session_state.username}!")
    
    # Logout button
    if st.sidebar.button("Logout"):
        logout()
    
    # Create new direct message
    st.sidebar.subheader("New Direct Message")
    user_options = [f"{user['username']} (ID: {user['id']})" for user in st.session_state.users 
                   if user['id'] != st.session_state.user_id]
    selected_user = st.sidebar.selectbox("Select User", [""] + user_options)
    
    if selected_user and st.sidebar.button("Start Chat"):
        user_id = int(selected_user.split("ID: ")[1].strip(")"))
        create_direct_channel(user_id)
    
    # Create new group chat
    st.sidebar.subheader("New Group Chat")
    group_name = st.sidebar.text_input("Group Name")
    
    # Multi-select for users
    user_options = {user['id']: user['username'] for user in st.session_state.users 
                   if user['id'] != st.session_state.user_id}
    selected_users = st.sidebar.multiselect("Select Members", options=list(user_options.keys()), 
                                           format_func=lambda x: user_options[x])
    
    if group_name and selected_users and st.sidebar.button("Create Group"):
        # Add current user to the group
        member_ids = selected_users + [st.session_state.user_id]
        create_group_channel(group_name, member_ids)
    
    # Channel list
    st.sidebar.subheader("Your Channels")
    
    # Extract channel options
    channel_options = []
    for channel in st.session_state.channels:
        if channel["type"] == "direct":
            # For direct messages, show the other person's name
            other_user = next((m for m in channel["members"] if m["id"] != st.session_state.user_id), None)
            name = f"DM: {other_user['username']}" if other_user else channel["name"]
        else:
            name = channel["name"]
        channel_options.append((channel["id"], name))
    
    # Create channel selection radio buttons
    if channel_options:
        channel_ids = [c[0] for c in channel_options]
        channel_names = [c[1] for c in channel_options]
        
        selected_index = 0
        if st.session_state.current_channel in channel_ids:
            selected_index = channel_ids.index(st.session_state.current_channel)
            
        selected_channel_name = st.sidebar.radio("Select Channel", channel_names, index=selected_index)
        selected_channel_id = channel_ids[channel_names.index(selected_channel_name)]
        
        # Update current channel if changed
        if st.session_state.current_channel != selected_channel_id:
            st.session_state.current_channel = selected_channel_id
            # Load messages for the selected channel
            load_messages(selected_channel_id)
            # Connect to WebSocket for this channel
            connect_websocket(selected_channel_id)
        elif not hasattr(st.session_state, 'ws_connected') or not st.session_state.ws_connected:
            # Ensure WebSocket is connected for the current channel
            connect_websocket(selected_channel_id)
    
    # Chat area
    if st.session_state.current_channel:
        # Find channel info
        channel = next((c for c in st.session_state.channels if c["id"] == st.session_state.current_channel), None)
        
        if channel:
            # Display channel name
            if channel["type"] == "direct":
                other_user = next((m for m in channel["members"] if m["id"] != st.session_state.user_id), None)
                st.header(f"Chat with {other_user['username']}" if other_user else channel["name"])
            else:
                st.header(f"Group: {channel['name']}")
            
            # Display chat messages
            if st.session_state.current_channel in st.session_state.messages:
                messages = st.session_state.messages[st.session_state.current_channel]
                
                # Create a container for chat messages
                chat_container = st.container()
                
                # Display messages
                with chat_container:
                    for msg in messages:
                        # Find sender username
                        sender = next((u for u in st.session_state.users if u["id"] == msg["sender_id"]), None)
                        sender_name = sender["username"] if sender else f"User {msg['sender_id']}"
                        
                        # Format timestamp
                        time_str = format_timestamp(msg["created_at"])
                        
                        # Determine if message is from current user
                        is_me = msg["sender_id"] == st.session_state.user_id
                        
                        # Display message with different styles for own/others' messages
                        if is_me:
                            st.markdown(f"""
                            <div style="display:flex;justify-content:flex-end;margin-bottom:10px;">
                                <div style="background-color:#1e88e5;color:white;padding:8px 12px;border-radius:15px;max-width:70%;">
                                    {msg["content"]}
                                    <div style="font-size:0.7em;text-align:right;margin-top:2px;">{time_str}</div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div style="display:flex;justify-content:flex-start;margin-bottom:10px;">
                                <div style="background-color:#f0f0f0;color:black;padding:8px 12px;border-radius:15px;max-width:70%;">
                                    <div style="font-size:0.8em;font-weight:bold;margin-bottom:2px;">{sender_name}</div>
                                    {msg["content"]}
                                    <div style="font-size:0.7em;text-align:right;margin-top:2px;">{time_str}</div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
            
            # Message input - use a form with a callback to handle the message sending
            with st.form(key="message_form", clear_on_submit=True):
                message = st.text_input("Type your message", key="message_input")
                submit = st.form_submit_button("Send")
                
                if submit and message:
                    if send_message(st.session_state.current_channel, message):
                        # The form's clear_on_submit=True will handle clearing the input
                        pass
        else:
            st.warning("Channel not found")
    else:
        st.info("Select a channel or create a new conversation")
        st.info("Select a channel or create a new conversation")

# Add this at the end of your app, after all the UI rendering:
# Check for new messages that came in via WebSocket
if hasattr(st.session_state, "new_message") and st.session_state.new_message:
    st.session_state.new_message = False
    st.experimental_rerun()

# Check for notifications
if hasattr(st.session_state, "notification") and st.session_state.notification:
    notification = st.session_state.notification
    st.session_state.notification = None
    st.toast(notification)
