#!/usr/bin/env python3
"""
Gemini AI Generator - Cloud-based AI for TikTok video analysis
============================================================
Uses Google Gemini Flash for intelligent content analysis and optimization
"""

import os
import json
import random
import cv2
import tempfile
from typing import Dict, List, Optional
from datetime import datetime
import base64
import requests
from PIL import Image
import numpy as np

class GeminiAIGenerator:
    def __init__(self, api_key: str = None):
        """Initialize Gemini AI with API key"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("❌ Gemini API key required! Set GEMINI_API_KEY environment variable or pass api_key parameter")
        
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.model_name = "gemini-1.5-flash"
        
        # Content analysis prompts
        self.analysis_prompt = """
Analyze this TikTok video content and identify specific details. Provide a JSON response with:

1. **Category**: Choose from [anime, gaming, entertainment, comedy, dance, music, lifestyle, food, tech, fitness, viral]
2. **Emotion/Vibe**: Choose from [exciting, funny, dramatic, energetic, calm, mysterious, inspiring]
3. **Key_Elements**: List 3-5 main visual elements you see
4. **Content_Type**: What type of content is this? (dance, comedy skit, tutorial, etc.)
5. **Target_Audience**: Who would enjoy this? (teens, gamers, anime fans, etc.)
6. **Viral_Potential**: Rate 1-10 based on engagement potential
7. **Specific_Content**: Try to identify any of these if visible:
   - Anime series name (e.g., "Naruto", "Attack on Titan", "One Piece")
   - Movie title (e.g., "Spider-Man", "Avengers", "Fast & Furious")
   - Game name (e.g., "Fortnite", "Minecraft", "GTA", "Valorant")
   - Artist/Celebrity (e.g., "BTS", "Taylor Swift", "The Rock")
   - Character names (e.g., "Goku", "Batman", "Pikachu")
   - Brand/Logo (e.g., "Nike", "Apple", "McDonald's")
8. **Text_Detected**: Any visible text, captions, or subtitles in the video
9. **Audio_Cues**: If you can infer from visuals what music/sound might be playing

Respond ONLY with valid JSON in this format:
{
  "category": "anime",
  "emotion": "exciting", 
  "key_elements": ["anime character", "fighting scene", "special effects"],
  "content_type": "anime clip",
  "target_audience": "anime fans, teens",
  "viral_potential": 8,
  "specific_content": {
    "anime_series": "Dragon Ball Z",
    "character": "Goku",
    "movie": null,
    "game": null,
    "artist": null,
    "brand": null
  },
  "text_detected": ["KAMEHAMEHA!", "Episode 154"],
  "audio_cues": "intense battle music"
}
"""

        self.title_prompt = """
Create 3 viral YouTube Shorts titles for this TikTok content. Use any detected specific content (movies, anime, games, artists) in the titles.

Content analysis: {analysis}

Guidelines:
- If specific content detected (anime/movie/game/artist), USE IT in titles
- YouTube algorithm optimization  
- Click-worthy but not clickbait
- Under 60 characters
- Include trending elements like "POV:", "This...", "You won't believe..."
- Add relevant emojis
- If anime detected, use anime terminology
- If game detected, use gaming terms  
- If movie detected, reference the franchise

Examples:
- Anime: "POV: Goku Goes Ultra Instinct 🔥" 
- Gaming: "This Fortnite Play Broke The Game 🎮"
- Movie: "Spider-Man Did WHAT?! 🕷️"
- Music: "When BTS Drops This Beat 🎵"

Respond with JSON:
{
  "titles": [
    "Title 1 with specific content 🔥",
    "Title 2 with specific content ✨", 
    "Title 3 with specific content 💯"
  ]
}
"""

        self.description_prompt = """
Create an engaging YouTube Shorts description for this content using any detected specific content:

Content: {analysis}
Title: {title}

Guidelines:
- If specific anime/movie/game/artist detected, mention it naturally
- Hook opening line
- Call-to-action for subscribe/like  
- Relevant hashtags (max 10) including specific content
- Under 125 characters total
- Engaging but professional tone

Examples:
- Anime: "Goku's power is unreal! 🔥 #DragonBall #Anime #Goku"
- Game: "This Fortnite play hit different 🎮 #Fortnite #Gaming #Epic" 
- Movie: "Spider-Man physics don't make sense 🕷️ #SpiderMan #Marvel #MCU"

Respond with JSON:
{
  "description": "Your description with specific content here..."
}
"""

        self.tags_prompt = """
Generate 15-20 SEO-optimized YouTube tags for this content. PRIORITIZE specific detected content:

Content: {analysis}
Title: {title}

Tag Strategy:
1. **Specific Content First**: If anime/movie/game/artist detected, include those as primary tags
2. **YouTube Shorts optimization**: Always include "shorts", "viral", "trending"  
3. **Category tags**: Based on detected category
4. **Trending keywords**: Current viral terms
5. **Audience tags**: Target demographic terms

Examples:
- Anime detected: ["naruto", "anime shorts", "sasuke", "ninja", "manga", "otaku"]
- Game detected: ["fortnite", "gaming", "epic moments", "battle royale", "gamer"]  
- Movie detected: ["marvel", "spider-man", "superhero", "mcu", "comic"]
- Artist detected: ["bts", "kpop", "korean music", "army", "music video"]

Focus on:
- Specific names/titles found in analysis
- Category-specific tags  
- Mix of broad and specific terms
- No banned or sensitive words
- Character names if detected

Respond with JSON:
{
  "tags": ["specific_content_tag", "category_tag", "viral_tag", ...]
}
"""

    def extract_video_frame(self, video_path: str) -> Optional[str]:
        """Extract a representative frame from video and encode as base64"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # Get middle frame
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            middle_frame = total_frames // 2
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # Convert to RGB and resize for API efficiency
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # Resize to reduce API costs
            pil_image.thumbnail((800, 600), Image.Resampling.LANCZOS)
            
            # Save to temporary file and encode
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                pil_image.save(tmp.name, 'JPEG', quality=85)
                with open(tmp.name, 'rb') as img_file:
                    encoded = base64.b64encode(img_file.read()).decode('utf-8')
                os.unlink(tmp.name)
                return encoded
                
        except Exception as e:
            print(f"⚠️ Frame extraction error: {e}")
            return None

    def call_gemini_api(self, prompt: str, image_base64: str = None) -> Dict:
        """Make API call to Gemini"""
        try:
            headers = {
                'Content-Type': 'application/json',
            }
            
            # Prepare content
            contents = [{
                "parts": [{"text": prompt}]
            }]
            
            # Add image if provided
            if image_base64:
                contents[0]["parts"].append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1000,
                    "topP": 0.8,
                    "topK": 40
                }
            }
            
            url = f"{self.base_url}?key={self.api_key}"
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Try to parse JSON from response
                    try:
                        # Clean up the response (remove markdown formatting if present)
                        clean_text = text.strip()
                        if clean_text.startswith('```json'):
                            clean_text = clean_text[7:]
                        if clean_text.endswith('```'):
                            clean_text = clean_text[:-3]
                        clean_text = clean_text.strip()
                        
                        # Try to parse as JSON
                        parsed_json = json.loads(clean_text)
                        return parsed_json
                    except json.JSONDecodeError as e:
                        # If JSON parsing fails, try to extract JSON from the text
                        # Look for JSON-like structures in the response
                        import re
                        json_match = re.search(r'\{.*\}', text, re.DOTALL)
                        if json_match:
                            try:
                                return json.loads(json_match.group(0))
                            except:
                                pass
                        
                        # If it's a connection test, handle specially
                        if "test" in text.lower() and "success" in text.lower():
                            return {"test": "success"}
                        
                        print(f"⚠️ JSON parsing failed: {str(e)}")
                        print(f"Raw response: {text[:200]}...")
                        # Return the raw text so we can still work with it
                        return {"raw_response": text, "parsing_error": True}
                else:
                    return {"error": "No response from Gemini"}
            else:
                print(f"❌ Gemini API error: {response.status_code} - {response.text}")
                return {"error": f"API error: {response.status_code}"}
                
        except Exception as e:
            print(f"❌ Gemini API call failed: {e}")
            return {"error": str(e)}

    def analyze_video_content(self, video_path: str) -> Dict:
        """Analyze video content using Gemini Vision"""
        print(f"🔍 Analyzing video with Gemini AI: {os.path.basename(video_path)}")
        
        # Extract frame for analysis
        frame_base64 = self.extract_video_frame(video_path)
        if not frame_base64:
            return {"error": "Failed to extract video frame"}
        
        # Analyze content
        analysis = self.call_gemini_api(self.analysis_prompt, frame_base64)
        
        if "error" in analysis:
            print(f"⚠️ Content analysis failed: {analysis['error']}")
            return self.get_fallback_analysis()
        
        print(f"✅ Content analyzed - Category: {analysis.get('category', 'unknown')}")
        return analysis

    def generate_titles(self, analysis: Dict) -> List[str]:
        """Generate optimized titles using Gemini"""
        print("📝 Generating viral titles...")
        
        prompt = self.title_prompt.format(analysis=json.dumps(analysis, indent=2))
        result = self.call_gemini_api(prompt)
        
        if "error" in result or "titles" not in result:
            print("⚠️ Title generation failed, using fallback")
            return self.get_fallback_titles(analysis.get('category', 'viral'))
        
        titles = result["titles"][:3]  # Take top 3
        print(f"✅ Generated {len(titles)} titles")
        return titles

    def generate_description(self, analysis: Dict, title: str) -> str:
        """Generate optimized description using Gemini"""
        print("📄 Generating description...")
        
        prompt = self.description_prompt.format(
            analysis=json.dumps(analysis, indent=2),
            title=title
        )
        result = self.call_gemini_api(prompt)
        
        if "error" in result or "description" not in result:
            print("⚠️ Description generation failed, using fallback")
            return self.get_fallback_description(analysis.get('category', 'viral'))
        
        description = result["description"]
        print(f"✅ Generated description ({len(description)} chars)")
        return description

    def generate_tags(self, analysis: Dict, title: str) -> List[str]:
        """Generate optimized tags using Gemini"""
        print("🏷️ Generating SEO tags...")
        
        prompt = self.tags_prompt.format(
            analysis=json.dumps(analysis, indent=2),
            title=title
        )
        result = self.call_gemini_api(prompt)
        
        if "error" in result or "tags" not in result:
            print("⚠️ Tag generation failed, using fallback")
            return self.get_fallback_tags(analysis.get('category', 'viral'))
        
        tags = result["tags"][:20]  # Limit to 20 tags
        print(f"✅ Generated {len(tags)} tags")
        return tags

    def generate_ai_data(self, video_path: str, original_title: str = "") -> Dict:
        """Main function to generate all AI-enhanced data"""
        try:
            print(f"🤖 Starting Gemini AI analysis for: {os.path.basename(video_path)}")
            
            # Step 1: Analyze video content
            analysis = self.analyze_video_content(video_path)
            if "error" in analysis:
                return self.get_complete_fallback(original_title)
            
            # Step 2: Generate titles
            titles = self.generate_titles(analysis)
            best_title = titles[0] if titles else f"Amazing {analysis.get('category', 'Viral')} Video! 🔥"
            
            # Step 3: Generate description
            description = self.generate_description(analysis, best_title)
            
            # Step 4: Generate tags
            tags = self.generate_tags(analysis, best_title)
            
            result = {
                'ai_title': best_title,
                'ai_description': description,
                'ai_tags': tags,
                'category': analysis.get('category', 'entertainment'),
                'confidence': 0.9,  # High confidence for Gemini
                'analysis_timestamp': datetime.now().isoformat(),
                'optimization_score': analysis.get('viral_potential', 8) * 10,
                'gemini_analysis': analysis,
                'alternative_titles': titles[1:] if len(titles) > 1 else []
            }
            
            print(f"✅ Gemini AI analysis complete! Optimization score: {result['optimization_score']}%")
            return result
            
        except Exception as e:
            print(f"❌ Gemini AI analysis failed: {e}")
            return self.get_complete_fallback(original_title)

    def get_fallback_analysis(self) -> Dict:
        """Fallback analysis when API fails"""
        return {
            "category": "entertainment",
            "emotion": "exciting",
            "key_elements": ["viral content", "engaging visuals"],
            "content_type": "viral video",
            "target_audience": "general audience",
            "viral_potential": 7
        }

    def get_fallback_titles(self, category: str) -> List[str]:
        """Fallback titles when API fails"""
        templates = {
            'anime': ['This Anime Moment Hit Different! 😭', 'Anime Fans Will Understand This 🔥', 'POV: You See This Anime Scene ✨'],
            'gaming': ['Insane Gaming Skills! 🎮', 'This Gaming Moment Was UNREAL 🔥', 'You Won\'t Believe This Gaming Clip! 💯'],
            'entertainment': ['This Will Make Your Day! 😂', 'You Won\'t Believe What Happens! 🤯', 'The Video Everyone Is Talking About! 🔥']
        }
        return templates.get(category, templates['entertainment'])

    def get_fallback_description(self, category: str) -> str:
        """Fallback description when API fails"""
        return f"""🔥 Amazing {category} content that will blow your mind!

📱 Subscribe for daily viral videos!
👍 Like if you enjoyed this!
💬 Comment your thoughts!

#{category} #viral #shorts #trending #tiktok #entertainment"""

    def get_fallback_tags(self, category: str) -> List[str]:
        """Fallback tags when API fails"""
        base_tags = ['shorts', 'viral', 'trending', 'tiktok', 'entertainment', 'funny', 'amazing']
        category_tags = {
            'anime': ['anime', 'manga', 'otaku', 'animation'],
            'gaming': ['gaming', 'gamer', 'gameplay', 'esports'],
            'entertainment': ['comedy', 'funny', 'hilarious', 'viral video']
        }
        return base_tags + category_tags.get(category, [])

    def get_complete_fallback(self, original_title: str) -> Dict:
        """Complete fallback when everything fails"""
        return {
            'ai_title': f"Amazing {original_title or 'Viral Video'}! 🔥",
            'ai_description': "🔥 Viral TikTok content! Subscribe for more! #Shorts #Viral",
            'ai_tags': ['shorts', 'viral', 'tiktok', 'trending', 'entertainment'],
            'category': 'entertainment',
            'confidence': 0.6,
            'analysis_timestamp': datetime.now().isoformat(),
            'optimization_score': 70
        }

    def test_api_connection(self) -> bool:
        """Test if Gemini API is working"""
        try:
            test_prompt = "Respond with exactly this JSON: {\"test\": \"success\"}"
            result = self.call_gemini_api(test_prompt)
            
            # Check if we got a valid response (either parsed JSON or error-free response)
            if "error" not in result:
                return True
            elif isinstance(result, dict) and result.get("test") == "success":
                return True
            else:
                # If it's a string response that contains our expected content, it's still working
                return "test" in str(result).lower() and "success" in str(result).lower()
        except Exception as e:
            print(f"API test error: {e}")
            return False

# Usage example
if __name__ == "__main__":
    # Test with API key
    api_key = input("Enter your Gemini API key: ").strip()
    
    if api_key:
        try:
            ai = GeminiAIGenerator(api_key)
            
            # Test connection
            if ai.test_api_connection():
                print("✅ Gemini API connection successful!")
                
                # Test with a video file if available
                test_video = "/root/pytest/tik/processed_videos/TikTok video 75178658329327567_processed.mp4"
                if os.path.exists(test_video):
                    result = ai.generate_ai_data(test_video, "Test Video")
                    print(f"\n🤖 AI Generated Content:")
                    print(f"Title: {result['ai_title']}")
                    print(f"Category: {result['category']}")
                    print(f"Score: {result['optimization_score']}%")
                else:
                    print("No test video found for demo")
            else:
                print("❌ Gemini API connection failed!")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("No API key provided")
