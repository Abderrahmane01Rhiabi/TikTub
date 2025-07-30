#!/usr/bin/env python3
"""
Gemini AI Setup - Configuration script for Google Gemini API
===========================================================
Helps you set up and test Gemini AI integration
"""

import os
import json
from gemini_ai_generator import GeminiAIGenerator

def setup_gemini_api():
    """Interactive setup for Gemini API"""
    print("🤖 GEMINI AI SETUP FOR TIKTUB")
    print("=" * 50)
    
    print("\n📋 STEP 1: Get your FREE Gemini API key")
    print("1. Go to: https://aistudio.google.com/app/apikey")
    print("2. Click 'Create API Key'")
    print("3. Copy your API key")
    print("\n💰 Pricing: FREE tier includes:")
    print("   • 15 requests per minute")
    print("   • 1,500 requests per day")
    print("   • ~$0.075 per 1M tokens (very cheap!)")
    
    # Get API key from user
    print("\n🔑 Enter your Gemini API key:")
    api_key = input().strip()
    
    if not api_key:
        print("❌ No API key provided. Exiting...")
        return False
    
    # Test the API key
    print("\n🧪 Testing API connection...")
    try:
        ai = GeminiAIGenerator(api_key)
        if ai.test_api_connection():
            print("✅ API connection successful!")
            
            # Save to environment file
            save_api_key(api_key)
            
            # Test with a sample video if available
            test_with_sample_video(ai)
            
            print("\n✅ SETUP COMPLETE!")
            print("🎯 Your TikTub system now has advanced AI capabilities:")
            print("   • Intelligent video analysis")
            print("   • Optimized title generation")
            print("   • SEO-friendly descriptions")
            print("   • Smart tag recommendations")
            
            return True
        else:
            print("❌ API connection failed. Please check your API key.")
            return False
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False

def save_api_key(api_key: str):
    """Save API key to config file"""
    try:
        # Create .env file
        with open('.env', 'w') as f:
            f.write(f"GEMINI_API_KEY={api_key}\n")
        
        # Update config.yaml if it exists
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                import yaml
                config = yaml.safe_load(f)
            
            if 'ai' not in config:
                config['ai'] = {}
            config['ai']['gemini_api_key'] = api_key
            
            with open('config.yaml', 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
        
        print("✅ API key saved to .env and config.yaml")
    except Exception as e:
        print(f"⚠️ Could not save API key: {e}")

def test_with_sample_video(ai: GeminiAIGenerator):
    """Test AI with a sample video if available"""
    # Look for any processed video
    processed_dir = "processed_videos"
    if os.path.exists(processed_dir):
        videos = [f for f in os.listdir(processed_dir) if f.endswith('.mp4')]
        if videos:
            sample_video = os.path.join(processed_dir, videos[0])
            print(f"\n🎬 Testing with sample video: {videos[0]}")
            
            try:
                result = ai.generate_ai_data(sample_video, "Sample TikTok Video")
                
                print(f"✅ AI Analysis Results:")
                print(f"   📝 Title: {result['ai_title']}")
                print(f"   📂 Category: {result['category']}")
                print(f"   🎯 Optimization Score: {result['optimization_score']}%")
                print(f"   💰 Estimated Cost: {result.get('cost_estimate', 'Very low')}")
                
                # Save sample result
                with open('sample_ai_result.json', 'w') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"   💾 Full results saved to sample_ai_result.json")
                
            except Exception as e:
                print(f"⚠️ Sample test failed: {e}")

def show_usage_guide():
    """Show how to use the AI system"""
    print("\n📚 HOW TO USE GEMINI AI IN TIKTUB:")
    print("=" * 50)
    
    print("\n1️⃣ AUTOMATIC USAGE:")
    print("   • Run batch_processor.py")
    print("   • Select 'Download and process batch'")
    print("   • AI will automatically analyze each video")
    
    print("\n2️⃣ MANUAL USAGE:")
    print("   • Open any Python script in your project")
    print("   • from ai_tags_generator import AITagsGenerator")
    print("   • ai = AITagsGenerator()")
    print("   • result = ai.generate_ai_content(video_data)")
    
    print("\n3️⃣ API USAGE MONITORING:")
    print("   • Free tier: 1,500 requests/day")
    print("   • Each video = 1 request")
    print("   • Monitor at: https://aistudio.google.com/app/apikey")
    
    print("\n4️⃣ COST OPTIMIZATION:")
    print("   • Use batch processing for efficiency")
    print("   • AI only analyzes when video file exists")
    print("   • Falls back to basic AI if API fails")

if __name__ == "__main__":
    print("🚀 Welcome to TikTub Gemini AI Setup!")
    
    choice = input("\nWhat would you like to do?\n1. Setup Gemini API\n2. Show usage guide\n3. Test existing setup\nChoice (1-3): ").strip()
    
    if choice == "1":
        setup_gemini_api()
        show_usage_guide()
    elif choice == "2":
        show_usage_guide()
    elif choice == "3":
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("❌ No API key found. Run setup first.")
        else:
            try:
                ai = GeminiAIGenerator(api_key)
                if ai.test_api_connection():
                    print("✅ Gemini AI is working correctly!")
                    test_with_sample_video(ai)
                else:
                    print("❌ API connection failed.")
            except Exception as e:
                print(f"❌ Test failed: {e}")
    else:
        print("Invalid choice. Goodbye!")
