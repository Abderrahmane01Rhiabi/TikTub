#!/usr/bin/env python3
"""
Channel Setup and Authentication
================================
Authenticate and manage YouTube channels for the automation system
"""

import os
import sys
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]

class ChannelSetup:
    def __init__(self):
        self.channels_dir = Path('channels')
        self.load_channel_config()
    
    def load_channel_config(self):
        """Load channel configuration"""
        config_file = self.channels_dir / 'channel_config.json'
        if config_file.exists():
            with open(config_file, 'r') as f:
                self.channels = json.load(f)
        else:
            self.channels = {}
    
    def authenticate_channel(self, channel_name):
        """Authenticate a specific channel"""
        channel_dir = self.channels_dir / channel_name
        creds_file = channel_dir / 'credentials.json'
        token_file = channel_dir / 'token.json'
        
        if not creds_file.exists():
            print(f"❌ No credentials.json found for {channel_name}")
            return False
        
        creds = None
        
        # Load existing token
        if token_file.exists() and token_file.stat().st_size > 0:
            try:
                creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            except ValueError:
                print(f"🗑️ Invalid token file for {channel_name}, removing...")
                token_file.unlink()
                creds = None
        
        # If no valid credentials, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print(f"🔄 Refreshing token for {channel_name}...")
                creds.refresh(Request())
            else:
                print(f"🔐 Starting authentication for {channel_name}...")
                print(f"📱 Opening browser for Google authentication...")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_file), SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
        
        # Test the authentication
        try:
            youtube = build('youtube', 'v3', credentials=creds)
            request = youtube.channels().list(part="snippet", mine=True)
            response = request.execute()
            
            if response['items']:
                channel_info = response['items'][0]['snippet']
                print(f"✅ {channel_name} authenticated successfully!")
                print(f"   📺 Channel: {channel_info['title']}")
                print(f"   🆔 ID: {response['items'][0]['id']}")
                return True
            else:
                print(f"❌ No channel found for {channel_name}")
                return False
                
        except Exception as e:
            print(f"❌ Authentication failed for {channel_name}: {e}")
            return False
    
    def show_channel_status(self):
        """Show status of all channels"""
        print("📺 CHANNEL STATUS:")
        print("="*50)
        
        for channel_name, config in self.channels.items():
            channel_dir = self.channels_dir / channel_name
            token_file = channel_dir / 'token.json'
            creds_file = channel_dir / 'credentials.json'
            
            print(f"\n🔸 {config['display_name']} ({channel_name})")
            print(f"   📝 {config.get('description', 'No description')}")
            
            if not creds_file.exists():
                print("   ❌ No credentials.json")
            elif not token_file.exists():
                print("   🔑 Needs authentication")
            else:
                # Check if token is valid
                try:
                    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
                    if creds and creds.valid:
                        print("   ✅ Authenticated & Ready")
                    else:
                        print("   🔄 Token expired - needs refresh")
                except:
                    print("   ❌ Invalid token")
    
    def setup_all_channels(self):
        """Setup all channels"""
        print("🚀 SETTING UP ALL CHANNELS")
        print("="*40)
        
        for channel_name in self.channels.keys():
            print(f"\n📺 Setting up {channel_name}...")
            self.authenticate_channel(channel_name)
    
    def interactive_setup(self):
        """Interactive channel setup"""
        while True:
            print("\n🔧 CHANNEL MANAGEMENT")
            print("="*30)
            print()
            
            self.show_channel_status()
            
            print("\n📋 OPTIONS:")
            print("1. 🔑 Authenticate specific channel")
            print("2. 🚀 Setup all channels")
            print("3. 📊 Show channel status")
            print("4. ❌ Exit")
            
            choice = input("\nChoice (1-4): ").strip()
            
            if choice == '1':
                print("\n📺 Available Channels:")
                channels = list(self.channels.keys())
                for i, channel in enumerate(channels, 1):
                    print(f"   {i}. {channel}")
                
                try:
                    channel_input = input("\nSelect channel number: ").strip()
                    channel_choice = int(channel_input) - 1
                    print(f"DEBUG: Input='{channel_input}', Choice={channel_choice}, Channels={len(channels)}")
                    
                    if 0 <= channel_choice < len(channels):
                        channel_name = channels[channel_choice]
                        print(f"✅ Selected: {channel_name}")
                        self.authenticate_channel(channel_name)
                    else:
                        print(f"❌ Invalid choice: {channel_choice + 1} (valid range: 1-{len(channels)})")
                except ValueError as e:
                    print(f"❌ Please enter a valid number. Error: {e}")
            
            elif choice == '2':
                self.setup_all_channels()
            
            elif choice == '3':
                continue  # Will show status at top of loop
            
            elif choice == '4':
                print("👋 Goodbye!")
                break
            
            else:
                print("❌ Invalid choice")

def main():
    setup = ChannelSetup()
    setup.interactive_setup()

if __name__ == "__main__":
    main()
