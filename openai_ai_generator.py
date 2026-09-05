#!/usr/bin/env python3
"""
OpenAI AI Generator - Cloud-based AI for TikTok video analysis
============================================================
Uses OpenAI GPT-4 Vision for intelligent content analysis and optimization
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

class OpenAIGenerator:
    def __init__(self, api_key: str = None):
        """Initialize OpenAI with API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("❌ OpenAI API key required! Set OPENAI_API_KEY environment variable or pass api_key parameter")
        
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.model_name = "gpt-4o-mini"  # More cost-effective than gpt-4-vision-preview

        # Tracks degraded/failed calls so a silent fallback to generic
        # content isn't mistaken for a genuine success by the caller.
        self._api_error_count = 0

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

    def extract_video_frames(self, video_path: str, n: int = 3) -> List[str]:
        """Extract n frames spread across the video as base64 JPEGs"""
        frames = []
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return frames

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                cap.release()
                return frames

            n = max(1, n)
            positions = [int(total_frames * (i + 1) / (n + 1)) for i in range(n)]

            for pos in positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if not ret:
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                pil_image.thumbnail((800, 600), Image.Resampling.LANCZOS)

                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    pil_image.save(tmp.name, 'JPEG', quality=85)
                    with open(tmp.name, 'rb') as img_file:
                        frames.append(base64.b64encode(img_file.read()).decode('utf-8'))
                    os.unlink(tmp.name)

            cap.release()
            return frames

        except Exception as e:
            print(f"⚠️ Frame extraction error: {e}")
            return frames

    def extract_video_frame(self, video_path: str) -> Optional[str]:
        """Backward-compatible single-frame extraction (middle frame)"""
        frames = self.extract_video_frames(video_path, n=1)
        return frames[0] if frames else None

    def call_openai_api(self, prompt: str, images: List[str] = None, max_tokens: int = 1000) -> Dict:
        """Make API call to OpenAI. `images` is a list of base64-encoded JPEGs."""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            # Prepare messages
            if images:
                content = [{"type": "text", "text": prompt}]
                for image_base64 in images:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "low"  # Use low detail to save costs
                        }
                    })
                messages = [{"role": "user", "content": content}]
            else:
                messages = [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            
            payload = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7
            }
            
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                try:
                    # Try to parse as JSON
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    # If JSON parsing fails, try to extract JSON from the text
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            return json.loads(json_match.group(0))
                        except:
                            pass
                    
                    # If it's a connection test, handle specially
                    if "test" in content.lower() and "success" in content.lower():
                        return {"test": "success"}
                    
                    print(f"⚠️ JSON parsing failed: {str(e)}")
                    print(f"Raw response: {content[:200]}...")
                    self._api_error_count += 1
                    return {"raw_response": content, "parsing_error": True}
            else:
                print(f"❌ OpenAI API error: {response.status_code} - {response.text}")
                self._api_error_count += 1
                return {"error": f"API error: {response.status_code}"}

        except Exception as e:
            print(f"❌ OpenAI API call failed: {e}")
            self._api_error_count += 1
            return {"error": str(e)}

    def test_api_connection(self) -> bool:
        """Test OpenAI API connection"""
        try:
            result = self.call_openai_api("Respond with JSON: {'test': 'success', 'status': 'connected'}")
            return "test" in result and result["test"] == "success"
        except:
            return False

    def analyze_video_content(self, video_path: str, custom_prompt: str = None,
                               transcript: str = None, use_frames: bool = True,
                               tiktok_caption: str = None) -> Dict:
        """Analyze video content using OpenAI Vision (and optionally an audio transcript)"""
        print(f"🔍 Analyzing video with OpenAI: {os.path.basename(video_path)}")

        prompt = self.analysis_prompt
        if custom_prompt:
            prompt += f"\n\nChannel-specific style instructions:\n{custom_prompt}"
        if tiktok_caption:
            prompt += f"\n\nOriginal TikTok caption (use for context, don't just copy it):\n\"\"\"{tiktok_caption}\"\"\""
        if transcript:
            prompt += f"\n\nAudio transcript of this video:\n\"\"\"{transcript}\"\"\""

        frames = self.extract_video_frames(video_path, n=3) if use_frames else []
        if use_frames and not frames and not transcript:
            return {"error": "Failed to extract video frames"}

        # Analyze content
        analysis = self.call_openai_api(prompt, frames)

        if "error" in analysis:
            print(f"⚠️ Content analysis failed: {analysis['error']}")
            return self.get_fallback_analysis()
        
        print(f"✅ Content analyzed - Category: {analysis.get('category', 'unknown')}")
        return analysis

    def generate_titles(self, analysis: Dict, custom_prompt: str = None) -> List[str]:
        """Generate optimized titles using OpenAI"""
        print("📝 Generating viral titles...")

        # Plain .replace(), not .format(): the prompt templates contain literal JSON
        # example braces that .format() would misparse as extra replacement fields.
        prompt = self.title_prompt.replace('{analysis}', json.dumps(analysis, indent=2))
        if custom_prompt:
            prompt += f"\n\nChannel-specific style instructions (these override the generic guidelines/examples above — follow them exactly, including language):\n{custom_prompt}"
        result = self.call_openai_api(prompt)
        
        if "error" in result or "titles" not in result:
            print("⚠️ Title generation failed, using fallback")
            return self.get_fallback_titles(analysis.get('category', 'entertainment'))
        
        titles = result["titles"]
        print(f"✅ Generated {len(titles)} viral titles")
        return titles

    def generate_description(self, analysis: Dict, title: str, custom_prompt: str = None) -> str:
        """Generate optimized description using OpenAI"""
        print("📄 Generating SEO description...")

        prompt = self.description_prompt.replace(
            '{analysis}', json.dumps(analysis, indent=2)
        ).replace('{title}', title)
        if custom_prompt:
            prompt += f"\n\nChannel-specific style instructions (these override the generic guidelines/examples above — follow them exactly, including language):\n{custom_prompt}"
        result = self.call_openai_api(prompt)
        
        if "error" in result or "description" not in result:
            print("⚠️ Description generation failed, using fallback")
            return self.get_fallback_description(title, analysis.get('category', 'entertainment'))
        
        description = result["description"]
        print("✅ SEO description generated")
        return description

    def generate_tags(self, analysis: Dict, title: str, custom_prompt: str = None) -> List[str]:
        """Generate optimized tags using OpenAI"""
        print("🏷️ Generating SEO tags...")

        prompt = self.tags_prompt.replace(
            '{analysis}', json.dumps(analysis, indent=2)
        ).replace('{title}', title)
        if custom_prompt:
            prompt += f"\n\nChannel-specific style instructions (these override the generic guidelines/examples above — follow them exactly, including language):\n{custom_prompt}"
        result = self.call_openai_api(prompt)
        
        if "error" in result or "tags" not in result:
            print("⚠️ Tag generation failed, using fallback")
            return self.get_fallback_tags(analysis.get('category', 'entertainment'))
        
        tags = result["tags"]
        print(f"✅ Generated {len(tags)} SEO tags")
        return tags[:20]  # Limit to 20 tags

    def generate_ai_data(self, video_path: str, original_title: str = "",
                          custom_prompt: str = None, transcript: str = None,
                          use_frames: bool = True, tiktok_caption: str = None) -> Dict:
        """Main function to generate complete AI data for video"""
        try:
            print(f"🤖 Starting OpenAI analysis for: {os.path.basename(video_path)}")
            self._api_error_count = 0

            # Step 1: Analyze video content (channel-aware prompt / transcript)
            analysis = self.analyze_video_content(
                video_path, custom_prompt=custom_prompt,
                transcript=transcript, use_frames=use_frames, tiktok_caption=tiktok_caption
            )
            if "error" in analysis:
                return self.get_complete_fallback(original_title)

            # Step 2: Generate titles
            titles = self.generate_titles(analysis, custom_prompt=custom_prompt)
            best_title = titles[0] if titles else f"Amazing {analysis.get('category', 'Viral')} Video! 🔥"

            # Step 3: Generate description
            description = self.generate_description(analysis, best_title, custom_prompt=custom_prompt)

            # Step 4: Generate tags
            tags = self.generate_tags(analysis, best_title, custom_prompt=custom_prompt)

            if self._api_error_count > 0:
                print(f"⚠️ OpenAI degraded ({self._api_error_count} failed sub-call(s)) — deferring to next provider")
                return self.get_complete_fallback(original_title)

            result = {
                'title': best_title,
                'description': description,
                'tags': tags,
                'category': analysis.get('category', 'entertainment'),
                'confidence': 0.85,  # High confidence for OpenAI
                'analysis_timestamp': datetime.now().isoformat(),
                'optimization_score': analysis.get('viral_potential', 8) * 10,
                'openai_analysis': analysis,
                'alternative_titles': titles[1:] if len(titles) > 1 else [],
                'ai_provider': 'openai-gpt4-mini',
                'cost_estimate': 'Low ($0.01-0.05 per video)'
            }
            
            print(f"✅ OpenAI analysis complete! Optimization score: {result['optimization_score']}%")
            return result
            
        except Exception as e:
            print(f"❌ OpenAI analysis failed: {e}")
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
            'anime': [
                'This Anime Moment Hit Different 🔥',
                'POV: You See This Anime Scene ✨',
                'Anime Fans Will Understand This 💯'
            ],
            'gaming': [
                'This Gaming Play Was Insane 🎮',
                'POV: You Pull Off This Move 🔥',
                'Gamers Will Know This Feeling ✨'
            ],
            'entertainment': [
                'You Won\'t Believe What Happens Next 🤯',
                'This Will Make Your Day Better 😂',
                'Everyone Needs To See This ✨'
            ]
        }
        return templates.get(category, templates['entertainment'])

    def get_fallback_description(self, title: str, category: str) -> str:
        """Fallback description when API fails"""
        return f"""🔥 {title}

📱 From TikTok to YouTube - bringing you the best viral content!

🔔 SUBSCRIBE for more amazing videos!
👍 LIKE if you enjoyed this!
💬 COMMENT your thoughts!

#{category} #viral #trending #shorts #tiktok"""

    def get_fallback_tags(self, category: str) -> List[str]:
        """Fallback tags when API fails"""
        base_tags = ['shorts', 'viral', 'trending', 'tiktok', 'entertainment']
        category_tags = {
            'anime': ['anime', 'manga', 'otaku', 'anime shorts'],
            'gaming': ['gaming', 'gamer', 'gameplay', 'gaming moments'],
            'entertainment': ['funny', 'comedy', 'amazing', 'must watch']
        }
        return base_tags + category_tags.get(category, category_tags['entertainment'])

    def get_complete_fallback(self, original_title: str) -> Dict:
        """Complete fallback when everything fails. Carries an 'error' key on
        purpose so the caller doesn't mistake this degraded content for a
        genuine success."""
        return {
            'error': 'openai_unavailable_or_degraded',
            'title': f"Amazing Viral Content! 🔥",
            'description': self.get_fallback_description("Amazing Viral Content! 🔥", "entertainment"),
            'tags': self.get_fallback_tags("entertainment"),
            'category': 'entertainment',
            'confidence': 0.5,
            'analysis_timestamp': datetime.now().isoformat(),
            'optimization_score': 70,
            'ai_provider': 'openai-fallback',
            'note': 'Generated using fallback system'
        }

if __name__ == "__main__":
    # Test the OpenAI generator
    print("🤖 Testing OpenAI AI Generator...")
    
    try:
        generator = OpenAIGenerator()
        
        # Test API connection
        if generator.test_api_connection():
            print("✅ OpenAI API connected successfully!")
        else:
            print("❌ OpenAI API connection failed")
            
    except Exception as e:
        print(f"❌ OpenAI generator test failed: {e}")
