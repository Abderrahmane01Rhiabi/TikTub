#!/usr/bin/env python3
"""
🎯 Channel Manager - Multi-Channel YouTube Support
Manages multiple YouTube channels with individual credentials and configurations.
"""

import os
import json
from typing import Dict, List, Optional

class ChannelManager:
    def __init__(self):
        self.channels_dir = "channels"
        self.config_file = os.path.join(self.channels_dir, "channel_config.json")
        self.ensure_channels_structure()

    def ensure_channels_structure(self):
        """Create channels directory structure if it doesn't exist"""
        if not os.path.exists(self.channels_dir):
            os.makedirs(self.channels_dir)
            
        # Create default channel from existing credentials if they exist
        if not os.path.exists(self.config_file) and (
            os.path.exists("credentials.json") or os.path.exists("token.json")
        ):
            self.migrate_default_channel()

    def migrate_default_channel(self):
        """Migrate existing single-channel setup to default channel"""
        default_dir = os.path.join(self.channels_dir, "default")
        os.makedirs(default_dir, exist_ok=True)
        
        # Move existing credentials to default channel
        if os.path.exists("credentials.json"):
            import shutil
            shutil.copy2("credentials.json", os.path.join(default_dir, "credentials.json"))
            print("✅ Migrated credentials.json to channels/default/")
            
        if os.path.exists("token.json"):
            import shutil
            shutil.copy2("token.json", os.path.join(default_dir, "token.json"))
            print("✅ Migrated token.json to channels/default/")
        
        # Create initial config
        config = {
            "default": {
                "display_name": "Default Channel",
                "description": "Your main YouTube channel",
                "created_at": "2025-07-30",
                "active": True
            }
        }
        self.save_config(config)

    def get_config(self) -> Dict:
        """Load channel configuration"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_config(self, config: Dict):
        """Save channel configuration"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def add_channel(self, channel_name: str, display_name: str, description: str = "") -> bool:
        """Add a new channel"""
        if not channel_name.replace("_", "").replace("-", "").isalnum():
            print("❌ Channel name must contain only letters, numbers, hyphens, and underscores")
            return False

        channel_dir = os.path.join(self.channels_dir, channel_name)
        if os.path.exists(channel_dir):
            print(f"❌ Channel '{channel_name}' already exists")
            return False

        # Create channel directory + per-channel URLs folder
        os.makedirs(channel_dir, exist_ok=True)
        os.makedirs(os.path.join(channel_dir, "urls_input"), exist_ok=True)

        # Update config
        config = self.get_config()
        config[channel_name] = {
            "display_name": display_name,
            "description": description,
            "created_at": "2025-07-30",
            "active": True
        }
        self.save_config(config)

        # Create a default AI/scheduling profile for this channel
        self.save_channel_profile(channel_name, self.get_default_profile(display_name))

        print(f"✅ Channel '{display_name}' created successfully!")
        print(f"📁 Directory: {channel_dir}")
        print(f"🔑 Place your credentials.json and token.json in this directory")
        print(f"🧠 Edit {os.path.join(channel_dir, 'profile.json')} to customize AI style")
        return True

    def get_default_profile(self, display_name: str) -> Dict:
        """Default profile.json content for a freshly created channel"""
        return {
            "display_name": display_name,
            "analysis_mode": "vision",  # "vision", "audio", "vision+audio", or "native_video"
            "ai_style_prompt": "",
            "language_hint": "en",
            "preferred_days": [],
            "preferred_hours": [],
            # Purely informational — which Google account to log into when
            # connecting this channel. Never used to authenticate anything.
            "google_account_email": ""
        }

    def get_profile_path(self, channel_name: str) -> str:
        return os.path.join(self.channels_dir, channel_name, "profile.json")

    def get_background_path(self, channel_name: str) -> Optional[str]:
        """Path to the channel's default background image, if one exists"""
        for ext in ("jpg", "jpeg", "png"):
            path = os.path.join(self.channels_dir, channel_name, f"background.{ext}")
            if os.path.exists(path):
                return path
        return None

    def get_channel_profile(self, channel_name: str) -> Dict:
        """Load a channel's AI/scheduling profile, creating a default one if missing"""
        profile_path = self.get_profile_path(channel_name)
        if not os.path.exists(profile_path):
            info = self.get_config().get(channel_name, {})
            default_profile = self.get_default_profile(info.get("display_name", channel_name))
            self.save_channel_profile(channel_name, default_profile)
            return default_profile

        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_channel_profile(self, channel_name: str, profile: Dict):
        """Save a channel's AI/scheduling profile"""
        channel_dir = os.path.join(self.channels_dir, channel_name)
        os.makedirs(channel_dir, exist_ok=True)
        with open(self.get_profile_path(channel_name), 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

    def get_urls_input_dir(self, channel_name: str) -> str:
        """Path to a channel's own urls_input/ folder, created on demand"""
        path = os.path.join(self.channels_dir, channel_name, "urls_input")
        os.makedirs(path, exist_ok=True)
        return path

    def get_assets_dirs(self, channel_name: str) -> Dict[str, str]:
        """Paths to a channel's generative-pipeline asset pools (background loop
        videos and background music), created on demand. The user drops files
        into these folders manually — nothing here is fetched from an API."""
        backgrounds = os.path.join(self.channels_dir, channel_name, "assets", "backgrounds")
        music = os.path.join(self.channels_dir, channel_name, "assets", "music")
        os.makedirs(backgrounds, exist_ok=True)
        os.makedirs(music, exist_ok=True)
        return {"backgrounds": backgrounds, "music": music}

    def list_channels(self) -> List[Dict]:
        """List all available channels"""
        config = self.get_config()
        channels = []
        
        for channel_name, channel_info in config.items():
            channel_dir = os.path.join(self.channels_dir, channel_name)
            has_credentials = os.path.exists(os.path.join(channel_dir, "credentials.json"))
            has_token = os.path.exists(os.path.join(channel_dir, "token.json"))
            profile = self.get_channel_profile(channel_name)

            channels.append({
                "name": channel_name,
                "display_name": channel_info.get("display_name", channel_name),
                "description": channel_info.get("description", ""),
                "active": channel_info.get("active", True),
                "has_credentials": has_credentials,
                "has_token": has_token,
                "ready": has_credentials,  # Ready if has credentials (token can be generated)
                "analysis_mode": profile.get("analysis_mode", "vision"),
                "has_ai_style": bool(profile.get("ai_style_prompt")),
                "has_background": self.get_background_path(channel_name) is not None,
                "google_account_email": profile.get("google_account_email", ""),
                "generation_mode": profile.get("generation_mode", False)
            })
            
        return channels

    def get_channel_paths(self, channel_name: str) -> tuple:
        """Get credentials and token paths for a channel"""
        # Check if using old single-channel setup
        if not os.path.exists(self.channels_dir):
            return "credentials.json", "token.json"
            
        # Multi-channel setup
        channel_dir = os.path.join(self.channels_dir, channel_name)
        credentials_path = os.path.join(channel_dir, "credentials.json")
        token_path = os.path.join(channel_dir, "token.json")
        
        # If requesting "default" but it doesn't exist, try to find the first available channel
        if channel_name == "default" and not os.path.exists(channel_dir):
            config = self.get_config()
            if config:
                # Use the first available channel as fallback
                first_channel = list(config.keys())[0]
                channel_dir = os.path.join(self.channels_dir, first_channel)
                credentials_path = os.path.join(channel_dir, "credentials.json")
                token_path = os.path.join(channel_dir, "token.json")
        
        return credentials_path, token_path

    def channel_exists(self, channel_name: str) -> bool:
        """Check if a channel exists"""
        config = self.get_config()
        return channel_name in config

    def get_channel_info(self, channel_name: str) -> Optional[Dict]:
        """Get detailed channel information"""
        config = self.get_config()
        if channel_name not in config:
            return None
            
        info = config[channel_name].copy()
        credentials_path, token_path = self.get_channel_paths(channel_name)
        info.update({
            "name": channel_name,
            "has_credentials": os.path.exists(credentials_path),
            "has_token": os.path.exists(token_path),
            "credentials_path": credentials_path,
            "token_path": token_path
        })
        
        return info

    def delete_channel(self, channel_name: str) -> bool:
        """Delete a channel (with confirmation)"""
        if channel_name == "default":
            print("❌ Cannot delete the default channel")
            return False
            
        config = self.get_config()
        if channel_name not in config:
            print(f"❌ Channel '{channel_name}' not found")
            return False
            
        # Remove from config
        del config[channel_name]
        self.save_config(config)
        
        # Remove directory
        channel_dir = os.path.join(self.channels_dir, channel_name)
        if os.path.exists(channel_dir):
            import shutil
            shutil.rmtree(channel_dir)
            
        print(f"✅ Channel '{channel_name}' deleted successfully")
        return True

    def select_channel_interactive(self) -> Optional[str]:
        """Interactive channel selection"""
        channels = self.list_channels()
        
        if not channels:
            print("❌ No channels found. Run setup_channels.py to create channels.")
            return None
            
        if len(channels) == 1:
            return channels[0]["name"]
            
        print("\n📺 Available Channels:")
        print("=" * 50)
        
        ready_channels = []
        for i, channel in enumerate(channels):
            status = "✅ Ready" if channel["ready"] else "❌ Missing credentials"
            print(f"{i+1}. {channel['display_name']} ({channel['name']}) - {status}")
            if channel["description"]:
                print(f"   📝 {channel['description']}")
            if channel["ready"]:
                ready_channels.append(i+1)
        
        if not ready_channels:
            print("\n❌ No channels have credentials configured!")
            print("Run setup_channels.py to configure your channels.")
            return None
            
        print("\n" + "=" * 50)
        try:
            while True:
                choice = input("Select channel number: ").strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(channels):
                        selected = channels[idx]
                        if selected["ready"]:
                            print(f"✅ Selected: {selected['display_name']}")
                            return selected["name"]
                        else:
                            print("❌ Selected channel doesn't have credentials configured!")
                    else:
                        print("❌ Invalid selection")
                else:
                    print("❌ Please enter a number")
        except KeyboardInterrupt:
            print("\n👋 Selection cancelled")
            return None

def main():
    """Test channel manager functionality"""
    manager = ChannelManager()
    
    print("🎯 Channel Manager Test")
    print("=" * 30)
    
    channels = manager.list_channels()
    if channels:
        print(f"Found {len(channels)} channels:")
        for channel in channels:
            status = "✅" if channel["ready"] else "❌"
            print(f"  {status} {channel['display_name']} ({channel['name']})")
    else:
        print("No channels configured")

if __name__ == "__main__":
    main()
