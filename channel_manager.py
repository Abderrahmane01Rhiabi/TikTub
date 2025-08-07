#!/usr/bin/env python3
"""
Simple Channel Manager for Multi-Channel Support
"""

import os
from pathlib import Path

class ChannelManager:
    """Simple channel manager for multi-channel YouTube authentication"""
    
    def __init__(self):
        self.base_dir = Path("channels")
        
    def get_channel_paths(self, channel_name="default"):
        """Get credentials and token paths for a channel"""
        if channel_name == "default":
            # Fallback to single-channel mode
            return "credentials.json", "token.json"
        
        # Multi-channel mode
        channel_dir = self.base_dir / channel_name
        credentials_path = channel_dir / "credentials.json"
        token_path = channel_dir / "token.json"
        
        return str(credentials_path), str(token_path)
    
    def list_channels(self):
        """List available channels"""
        channels = []
        if not self.base_dir.exists():
            return channels
            
        for item in self.base_dir.iterdir():
            if item.is_dir():
                credentials_file = item / "credentials.json"
                if credentials_file.exists():
                    channels.append(item.name)
        
        return channels
