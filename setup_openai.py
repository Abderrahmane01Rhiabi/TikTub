#!/usr/bin/env python3
"""
OpenAI Setup Assistant - Interactive setup for OpenAI API
========================================================
Helps users configure OpenAI API key and test the connection
"""

import os
import json
from openai_ai_generator import OpenAIGenerator

def setup_openai_api():
    """Interactive OpenAI API setup"""
    print("🤖 OpenAI API Setup Assistant")
    print("=" * 50)
    
    print("\n📋 What you'll need:")
    print("• OpenAI API key from https://platform.openai.com/api-keys")
    print("• Credit card for billing (Pay-as-you-go)")
    print("• Estimated cost: $0.01-0.05 per video analysis")
    
    print("\n💰 OpenAI Pricing (GPT-4o-mini):")
    print("• Input: $0.15 per 1M tokens")
    print("• Output: $0.60 per 1M tokens") 
    print("• Vision: $0.002890 per image")
    print("• Estimated: ~$0.01-0.05 per video")
    
    # Get API key
    api_key = input("\n🔑 Enter your OpenAI API key: ").strip()
    
    if not api_key:
        print("❌ No API key provided. Exiting...")
        return False
    
    # Test the API key
    print("\n🔄 Testing OpenAI API connection...")
    
    try:
        generator = OpenAIGenerator(api_key)
        
        if generator.test_api_connection():
            print("✅ OpenAI API connection successful!")
            
            # Save API key to .env file
            save_api_key(api_key)
            
            # Test with sample analysis
            test_choice = input("\n🧪 Would you like to test with a sample video analysis? (y/n): ").lower()
            if test_choice == 'y':
                test_with_sample_video(generator)
            
            print("\n🎉 OpenAI setup complete!")
            print("\n📖 Usage Guide:")
            print("• Your system will now try: Gemini → OpenAI → Local AI")
            print("• OpenAI provides excellent content detection")
            print("• Monitor usage at: https://platform.openai.com/usage")
            print("• Set usage limits to control costs")
            
            return True
            
        else:
            print("❌ OpenAI API connection failed!")
            print("• Check your API key")
            print("• Ensure you have credits available")
            print("• Visit: https://platform.openai.com/account/billing")
            return False
            
    except Exception as e:
        print(f"❌ OpenAI setup failed: {e}")
        return False

def save_api_key(api_key: str):
    """Save API key to .env file"""
    try:
        # Read existing .env file
        env_content = ""
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                env_content = f.read()
        
        # Check if OPENAI_API_KEY already exists
        lines = env_content.split('\n')
        updated = False
        
        for i, line in enumerate(lines):
            if line.startswith('OPENAI_API_KEY='):
                lines[i] = f'OPENAI_API_KEY={api_key}'
                updated = True
                break
        
        # If not found, add it
        if not updated:
            if env_content and not env_content.endswith('\n'):
                env_content += '\n'
            env_content += f'OPENAI_API_KEY={api_key}\n'
        else:
            env_content = '\n'.join(lines)
        
        # Write back to .env file
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("✅ API key saved to .env file")
        
    except Exception as e:
        print(f"⚠️ Could not save API key to .env: {e}")
        print(f"💡 Please manually add this to your .env file:")
        print(f"OPENAI_API_KEY={api_key}")

def test_with_sample_video(generator: OpenAIGenerator):
    """Test OpenAI with a sample video analysis"""
    print("\n🧪 Testing OpenAI with sample content...")
    
    # Simulate a video analysis (without actual video file)
    try:
        # Test text-only analysis first
        sample_prompt = """
Analyze this TikTok content: A funny gaming moment where a player makes an epic fail in Fortnite.

Respond with JSON:
{
  "category": "gaming",
  "emotion": "funny",
  "specific_content": {
    "game": "Fortnite",
    "content_type": "epic fail"
  },
  "viral_potential": 8
}
"""
        
        result = generator.call_openai_api(sample_prompt)
        
        if "error" not in result:
            print("✅ Sample analysis successful!")
            print(f"📊 Category: {result.get('category', 'N/A')}")
            print(f"🎮 Game detected: {result.get('specific_content', {}).get('game', 'N/A')}")
            print(f"⚡ Viral potential: {result.get('viral_potential', 'N/A')}/10")
        else:
            print(f"⚠️ Sample analysis failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"⚠️ Sample test failed: {e}")

def show_usage_tips():
    """Show OpenAI usage tips and cost management"""
    print("\n💡 OpenAI Usage Tips:")
    print("=" * 30)
    print("• Set monthly usage limits in OpenAI dashboard")
    print("• Monitor costs regularly")
    print("• OpenAI is more expensive but very accurate")
    print("• Use for important content when quality matters")

    print("\n🔧 Integration Info:")
    print("• OpenAI integrates automatically with your existing system")
    print("• Fallback order: Gemini → OpenAI → Local AI")
    print("• You can configure preferred provider in ai_tags_generator.py")
    
    print("\n📚 Useful Links:")
    print("• OpenAI Dashboard: https://platform.openai.com/")
    print("• Usage & Billing: https://platform.openai.com/account/billing")
    print("• API Documentation: https://platform.openai.com/docs")

if __name__ == "__main__":
    print("🚀 Welcome to OpenAI API Setup!")
    print("This will add OpenAI GPT-4 Vision to your TikTub system.")
    
    # Check if already configured
    if os.getenv('OPENAI_API_KEY'):
        print("✅ OpenAI API key already configured!")
        choice = input("🔄 Do you want to reconfigure? (y/n): ").lower()
        if choice != 'y':
            show_usage_tips()
            exit(0)
    
    # Run setup
    if setup_openai_api():
        show_usage_tips()
    else:
        print("\n❌ Setup failed. Please try again.")
        print("💡 Need help? Check the OpenAI documentation or contact support.")
