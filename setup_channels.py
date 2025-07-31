#!/usr/bin/env python3
"""
🏗️ Channel Setup Wizard - Multi-Channel YouTube Support
Interactive setup tool for managing multiple YouTube channels.
"""

import os
import sys
import json
from channel_manager import ChannelManager

def print_header():
    """Print setup wizard header"""
    print("🏗️  MULTI-CHANNEL SETUP WIZARD")
    print("=" * 50)
    print("Setup and manage multiple YouTube channels")
    print("Each channel needs its own OAuth credentials")
    print("=" * 50)

def show_main_menu():
    """Show main menu options"""
    print("\n📋 CHANNEL MANAGEMENT OPTIONS:")
    print("1. 📺 List all channels")
    print("2. ➕ Add new channel")
    print("3. 🔧 Configure existing channel")
    print("4. 🗑️  Delete channel")
    print("5. 🔄 Migrate single-channel setup")
    print("6. ❓ Help & Instructions")
    print("0. 🚪 Exit")

def list_channels(manager: ChannelManager):
    """List all configured channels"""
    channels = manager.list_channels()
    
    if not channels:
        print("\n❌ No channels configured yet")
        print("Use option 2 to add your first channel")
        return
        
    print(f"\n📺 CONFIGURED CHANNELS ({len(channels)})")
    print("=" * 60)
    
    for channel in channels:
        status_icon = "✅" if channel["ready"] else "❌"
        print(f"\n{status_icon} {channel['display_name']}")
        print(f"   📁 Name: {channel['name']}")
        print(f"   📝 Description: {channel['description'] or 'No description'}")
        print(f"   🔑 Credentials: {'✅ Found' if channel['has_credentials'] else '❌ Missing'}")
        print(f"   🎟️  Token: {'✅ Found' if channel['has_token'] else '⚠️  Will be generated on first use'}")
        
        if not channel['ready']:
            credentials_path, _ = manager.get_channel_paths(channel['name'])
            print(f"   🚨 Missing: {credentials_path}")

def add_new_channel(manager: ChannelManager):
    """Add a new channel interactively"""
    print("\n➕ ADD NEW CHANNEL")
    print("=" * 30)
    
    try:
        # Get channel details
        print("Channel name (used internally, no spaces):")
        print("Examples: gaming_channel, anime_clips, main_channel")
        channel_name = input("Channel name: ").strip().lower()
        
        if not channel_name:
            print("❌ Channel name cannot be empty")
            return
            
        print("\nDisplay name (shown in menus):")
        display_name = input("Display name: ").strip()
        
        if not display_name:
            display_name = channel_name.replace("_", " ").title()
            
        print("\nDescription (optional):")
        description = input("Description: ").strip()
        
        # Create channel
        if manager.add_channel(channel_name, display_name, description):
            print("\n🎉 CHANNEL CREATED SUCCESSFULLY!")
            show_oauth_instructions(channel_name)
        
    except KeyboardInterrupt:
        print("\n❌ Channel creation cancelled")

def show_oauth_instructions(channel_name: str):
    """Show OAuth setup instructions for a channel"""
    print(f"\n🔑 OAUTH SETUP INSTRUCTIONS for '{channel_name}'")
    print("=" * 60)
    print("1. Go to Google Cloud Console: https://console.cloud.google.com/")
    print("2. Create a new project or select existing one")
    print("3. Enable YouTube Data API v3")
    print("4. Create OAuth 2.0 Client ID credentials")
    print("5. Download the credentials JSON file")
    print(f"6. Rename it to 'credentials.json'")
    print(f"7. Place it in: channels/{channel_name}/credentials.json")
    print("\n⚠️  IMPORTANT: Each channel needs its own OAuth credentials!")
    print("You cannot use the same credentials.json for multiple channels.")
    
    print(f"\n📁 Expected file location:")
    print(f"   channels/{channel_name}/credentials.json")

def configure_channel(manager: ChannelManager):
    """Configure an existing channel"""
    channels = manager.list_channels()
    
    if not channels:
        print("\n❌ No channels to configure. Add a channel first.")
        return
        
    print("\n🔧 CONFIGURE CHANNEL")
    print("=" * 30)
    
    # Show channels
    for i, channel in enumerate(channels):
        status = "✅ Ready" if channel["ready"] else "❌ Needs setup"
        print(f"{i+1}. {channel['display_name']} - {status}")
    
    try:
        choice = input("\nSelect channel to configure (number): ").strip()
        if not choice.isdigit():
            print("❌ Invalid selection")
            return
            
        idx = int(choice) - 1
        if not (0 <= idx < len(channels)):
            print("❌ Invalid selection")
            return
            
        channel = channels[idx]
        show_channel_config(manager, channel)
        
    except KeyboardInterrupt:
        print("\n❌ Configuration cancelled")

def show_channel_config(manager: ChannelManager, channel):
    """Show detailed channel configuration"""
    print(f"\n🔧 CONFIGURING: {channel['display_name']}")
    print("=" * 40)
    
    credentials_path, token_path = manager.get_channel_paths(channel['name'])
    
    print(f"📁 Channel Directory: channels/{channel['name']}/")
    print(f"🔑 Credentials: {credentials_path}")
    print(f"   Status: {'✅ Found' if channel['has_credentials'] else '❌ Missing'}")
    print(f"🎟️  Token: {token_path}")  
    print(f"   Status: {'✅ Found' if channel['has_token'] else '⚠️  Will be auto-generated'}")
    
    if not channel['has_credentials']:
        print(f"\n🚨 ACTION REQUIRED:")
        print(f"1. Download OAuth credentials from Google Cloud Console")
        print(f"2. Save as: {credentials_path}")
        show_oauth_instructions(channel['name'])
    else:
        print(f"\n✅ Channel is ready to use!")
        
        if not channel['has_token']:
            print("🔄 Token will be generated automatically on first use")
            print("   (You'll need to authorize in browser)")

def delete_channel(manager: ChannelManager):
    """Delete a channel with confirmation"""
    channels = manager.list_channels()
    
    if not channels:
        print("\n❌ No channels to delete")
        return
        
    # Filter out default channel
    deletable_channels = [c for c in channels if c['name'] != 'default']
    
    if not deletable_channels:
        print("\n❌ No deletable channels (default channel cannot be deleted)")
        return
        
    print("\n🗑️  DELETE CHANNEL")
    print("=" * 30)
    print("⚠️  WARNING: This will permanently delete the channel and its credentials!")
    
    for i, channel in enumerate(deletable_channels):
        print(f"{i+1}. {channel['display_name']}")
    
    try:
        choice = input("\nSelect channel to DELETE (number): ").strip()
        if not choice.isdigit():
            print("❌ Invalid selection")
            return
            
        idx = int(choice) - 1
        if not (0 <= idx < len(deletable_channels)):
            print("❌ Invalid selection")
            return
            
        channel = deletable_channels[idx]
        
        # Double confirmation
        confirm = input(f"\nAre you SURE you want to delete '{channel['display_name']}'? (type 'DELETE'): ")
        if confirm != "DELETE":
            print("❌ Deletion cancelled")
            return
            
        manager.delete_channel(channel['name'])
        
    except KeyboardInterrupt:
        print("\n❌ Deletion cancelled")

def migrate_single_channel(manager: ChannelManager):
    """Migrate existing single-channel setup"""
    print("\n🔄 MIGRATE SINGLE-CHANNEL SETUP")
    print("=" * 40)
    
    # Check if already migrated
    if os.path.exists("channels"):
        print("✅ Multi-channel setup already exists")
        return
        
    # Check for existing credentials
    has_credentials = os.path.exists("credentials.json")
    has_token = os.path.exists("token.json")
    
    if not has_credentials and not has_token:
        print("❌ No existing credentials found to migrate")
        print("Use option 2 to add a new channel instead")
        return
        
    print("Found existing single-channel setup:")
    print(f"🔑 credentials.json: {'✅ Found' if has_credentials else '❌ Missing'}")
    print(f"🎟️  token.json: {'✅ Found' if has_token else '❌ Missing'}")
    
    confirm = input("\nMigrate to multi-channel setup? (y/n): ").lower().strip()
    if confirm != 'y':
        print("❌ Migration cancelled")
        return
        
    # Trigger migration
    manager.ensure_channels_structure()
    print("✅ Migration completed!")
    print("Your existing setup is now available as 'Default Channel'")

def show_help():
    """Show help and instructions"""
    print("\n❓ HELP & INSTRUCTIONS")
    print("=" * 40)
    print("🎯 MULTI-CHANNEL SUPPORT:")
    print("- Upload to different YouTube channels")
    print("- Each channel needs separate OAuth credentials")
    print("- Switch channels during upload process")
    print("")
    print("🔑 OAUTH SETUP:")
    print("1. Each channel needs its own Google Cloud project")
    print("2. Or use same project with different OAuth clients")
    print("3. Download credentials.json for each channel")
    print("4. Place in channels/CHANNEL_NAME/credentials.json")
    print("")
    print("📁 FILE STRUCTURE:")
    print("channels/")
    print("├── default/            # Your main channel")
    print("│   ├── credentials.json")
    print("│   └── token.json")
    print("├── gaming_channel/     # Gaming content")
    print("│   ├── credentials.json")
    print("│   └── token.json")
    print("└── channel_config.json # Channel metadata")
    print("")
    print("🚀 USAGE:")
    print("- Run youtube_uploader.py to select channel")
    print("- Run batch_processor.py for batch uploads")
    print("- System will ask which channel to use")

def main():
    """Main setup wizard"""
    print_header()
    
    manager = ChannelManager()
    
    while True:
        show_main_menu()
        
        try:
            choice = input("\nSelect option (0-6): ").strip()
            
            if choice == "0":
                print("👋 Goodbye!")
                break
            elif choice == "1":
                list_channels(manager)
            elif choice == "2":
                add_new_channel(manager)
            elif choice == "3":
                configure_channel(manager)
            elif choice == "4":
                delete_channel(manager)
            elif choice == "5":
                migrate_single_channel(manager)
            elif choice == "6":
                show_help()
            else:
                print("❌ Invalid option. Please select 0-6.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()
