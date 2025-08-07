#!/usr/bin/env python3
"""
TikTub - Simple Database-Free Video Processor
============================================
One script to rule them all! No database, just simple file processing.
"""

import os
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
from dotenv import load_dotenv
import cv2
import base64

# Load environment variables from .env file
load_dotenv()

class TikTubProcessor:
    """Simple channel-based video processor"""
    
    def __init__(self):
        # Configuration options
        self.USE_OPENAI_API = os.getenv('USE_OPENAI_API', 'true').lower() == 'true'  # Set to 'false' to disable OpenAI
        self.FORCE_LOCAL_AI_ONLY = os.getenv('FORCE_LOCAL_AI_ONLY', 'false').lower() == 'true'  # Force local AI only
        
        print(f"🤖 AI Configuration:")
        if self.FORCE_LOCAL_AI_ONLY:
            print("   🏠 LOCAL AI ONLY MODE - OpenAI disabled")
        elif self.USE_OPENAI_API:
            print("   ☁️ OpenAI API enabled (with local fallback)")
        else:
            print("   🏠 OpenAI API disabled - using local AI only")
        self.workspace = "/root/pytest/tik"
        self.urls_dir = os.path.join(self.workspace, "urls_input")
        self.temp_dir = os.path.join(self.workspace, "temp")
        self.channels_processed_dir = os.path.join(self.workspace, "channels_processed")  # New folder structure
        self.backgrounds_dir = os.path.join(self.workspace, "backgrounds")
        self.channels_dir = os.path.join(self.workspace, "channels")
        
        # Cost tracking
        self.total_analysis_cost = 0.0
        self.video_count = 0
        
        # Ensure directories exist
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.channels_processed_dir, exist_ok=True)
        os.makedirs(os.path.join(self.workspace, "processed_videos"), exist_ok=True)  # For test3_script
        
        # Channel configuration
        self.channels = {
            "ZitBliss": {
                "urls_file": "zitbliss_urls.txt",
                "background": "zitbliss.png",
                "description_template": "🔥 Amazing content from ZitBliss! Don't miss this! 🚀"
            },
            "AnimeShorts137": {
                "urls_file": "anime_urls.txt", 
                "background": "animeshorts.png",
                "description_template": "⚡ Epic anime moments! Subscribe for more! 🎌"
            },
            "meme0culture": {
                "urls_file": "meme_urls.txt",
                "background": "memeculture.jpg", 
                "description_template": "😂 Hilarious memes that will make your day! 🤣"
            },
            "LungTeMotivates": {
                "urls_file": "motivation_urls.txt",
                "background": "LungTeMotivates.png",
                "description_template": "💪 Motivation that changes lives! Keep pushing! 🌟"
            },
            "lungte8888": {
                "urls_file": "lungte8888_urls.txt",
                "background": "lungTe888.png",
                "description_template": "🎯 Inspiring content from LungTe888! Subscribe for more! ✨"
            }
        }
        
        # Load AI generator if available
        self.ai_generator = self._setup_ai()
    
    def _setup_ai(self):
        """Setup AI generator if available"""
        # Check if OpenAI should be disabled
        if self.FORCE_LOCAL_AI_ONLY:
            print("🏠 Forcing local AI only - skipping OpenAI setup")
            return None
        
        if not self.USE_OPENAI_API:
            print("🏠 OpenAI API disabled - using local AI only")
            return None
            
        try:
            from openai_ai_generator import OpenAIGenerator
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                generator = OpenAIGenerator(api_key)
                if generator.test_api_connection():
                    print("🤖 AI Generator ready!")
                    return generator
            print("⚠️ AI Generator not available, using fallback")
        except Exception as e:
            print(f"⚠️ AI setup failed: {e}")
        return None
    
    def list_channels(self):
        """Show available channels"""
        print("\n🎬 Available Channels:")
        print("=" * 50)
        
        for i, (channel_name, config) in enumerate(self.channels.items(), 1):
            urls_file = os.path.join(self.urls_dir, config["urls_file"])
            
            # Count URLs in file
            url_count = 0
            if os.path.exists(urls_file):
                with open(urls_file, 'r') as f:
                    url_count = len([line for line in f if line.strip() and not line.startswith('#')])
            
            status = "✅ Ready" if url_count > 0 else "⚠️ No URLs"
            print(f"{i}. {channel_name} - {url_count} URLs - {status}")
        
        print("\n💡 To add URLs, edit files in urls_input/ folder")
    
    def download_video(self, url: str, output_name: str) -> Optional[str]:
        """Download video using yt-dlp"""
        print(f"📥 Downloading: {url}")
        
        output_template = os.path.join(self.temp_dir, f"{output_name}.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "--no-write-info-json",
            "--output", output_template,
            "--format", "best[height<=720]/best",  # Fallback format
            url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                print(f"❌ yt-dlp error: {result.stderr}")
                return None
            
            # Find downloaded file
            for file in os.listdir(self.temp_dir):
                if file.startswith(output_name) and file.endswith(('.mp4', '.webm', '.mkv')):
                    video_path = os.path.join(self.temp_dir, file)
                    print(f"✅ Downloaded: {os.path.basename(video_path)}")
                    return video_path
            
            print(f"❌ Download failed: No output file found")
            return None
            
        except subprocess.TimeoutExpired:
            print(f"⏰ Download timeout: {url}")
            return None
        except Exception as e:
            print(f"❌ Download error: {e}")
            return None
    
    def analyze_video(self, video_path: str, url: str, channel_name: str, video_index: int = 1) -> Dict:
        """Analyze video with AI-powered vision analysis and generate metadata"""
        title = os.path.splitext(os.path.basename(video_path))[0]
        channel_config = self.channels[channel_name]
        
        # 🔗 Extract hashtags and context from TikTok/Instagram URL
        url_context = self._extract_url_context(url)
        
        # Always use standard 1-frame analysis (URL context provides the accuracy boost)
        use_premium = False
        
        # Try advanced video vision analysis first (now with URL context)
        vision_analysis = self._analyze_video_with_vision(video_path, title, channel_name, premium=use_premium, url_context=url_context)
        
        # 🧠 SMART AI SELF-DETECTION: Only retry if vision analysis completely failed
        if vision_analysis and not use_premium:
            # Only retry if vision analysis returned completely generic/failed results
            analysis_method = vision_analysis.get('analysis_method', '')
            confidence = vision_analysis.get('confidence_score', 1.0)
            
            # Only upgrade to premium in extreme cases (complete failure)
            if analysis_method == 'vision_failed' or confidence < 0.3:
                print("🤖 Vision analysis completely failed - retrying with premium (5 frames)...")
                premium_analysis = self._analyze_video_with_vision(video_path, title, channel_name, premium=True, url_context=url_context)
                if premium_analysis:
                    vision_analysis = premium_analysis
        
        if vision_analysis:
            # Track cost and video count
            cost = vision_analysis.get("analysis_cost", 0)
            self.total_analysis_cost += cost
            self.video_count += 1
            
            return {
                **vision_analysis,
                "url": url,
                "channel": channel_name,
                "processed_at": datetime.now().isoformat(),
                "video_index": video_index
            }
        
        # Fallback to text-only AI if available
        if self.ai_generator:
            try:
                analysis = self.ai_generator.analyze_video_content(title, "", {"channel": channel_name})
                cost = 0.002  # Estimated text-only cost
                self.total_analysis_cost += cost
                self.video_count += 1
                
                text_analysis = {
                    "original_title": title,
                    "optimized_title": analysis.get("youtube_title", title)[:60],
                    "description": analysis.get("youtube_description", channel_config["description_template"]),
                    "tags": analysis.get("recommended_tags", ["shorts", "viral"]),
                    "content_type": analysis.get("content_type", "general"),
                    "url": url,
                    "channel": channel_name,
                    "processed_at": datetime.now().isoformat(),
                    "analysis_method": "text_only",
                    "analysis_cost": cost,
                    "video_index": video_index
                }
                
                # 🧠 SMART AI SELF-DETECTION: Only retry if text-only analysis failed completely
                if not use_premium:
                    # Only upgrade to premium vision if text-only analysis completely failed
                    if len(analysis.get("youtube_title", "")) < 10 or "tiktok" in analysis.get("youtube_description", "").lower():
                        print("🤖 Text-only analysis insufficient - retrying with vision (1 frame + URL context)...")
                        premium_vision = self._analyze_video_with_vision(video_path, title, channel_name, premium=False, url_context=url_context)
                        if premium_vision:
                            print("✅ Vision analysis with URL context successful - using improved results!")
                            return {
                                **premium_vision,
                                "url": url,
                                "channel": channel_name,
                                "processed_at": datetime.now().isoformat(),
                                "video_index": video_index
                            }
                        else:
                            print("⚠️ Vision also failed - using text-only results")
                
                return text_analysis
            except Exception as e:
                print(f"⚠️ AI analysis failed: {e}")
        
        # Final fallback metadata
        return {
            "original_title": title,
            "optimized_title": f"🔥 {title[:55]}",
            "description": channel_config["description_template"],
            "tags": ["shorts", "viral", "trending", channel_name.lower()],
            "content_type": "general", 
            "url": url,
            "channel": channel_name,
            "processed_at": datetime.now().isoformat(),
            "analysis_method": "fallback",
            "analysis_cost": 0.0,
            "video_index": video_index
        }
    
    def _analyze_video_with_vision(self, video_path: str, original_title: str, channel_name: str, premium: bool = False, url_context: str = "") -> Optional[Dict]:
        """Analyze video using OpenAI Vision API"""
        # Check if OpenAI should be disabled
        if self.FORCE_LOCAL_AI_ONLY or not self.USE_OPENAI_API:
            print("🏠 OpenAI Vision disabled - skipping vision analysis")
            return None
            
        try:
            import openai
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                return None
            
            client = openai.OpenAI(api_key=api_key)
            
            # Extract frames (1 frame standard, 5 frames only when explicitly premium requested)
            num_frames = 5 if premium else 1
            frames_b64 = self._extract_video_frames(video_path, num_frames)
            
            if not frames_b64:
                return None
            
            analysis_type = "PREMIUM (5-FRAME)" if premium else "STANDARD (1-FRAME + URL CONTEXT)"
            print(f"🤖 {analysis_type} Vision Analysis")
            
            # Get channel context for better analysis
            channel_context = self._get_channel_context(channel_name)
            
            # Create vision analysis prompt
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
                            CRITICAL: Analyze ONLY what you actually see in the video frames. Use URL context to enhance accuracy.
                            
                            Video Analysis Task:
                            - Original title: "{original_title}"
                            - Frames analyzed: {len(frames_b64)}
                            - Channel: "{channel_name}" (context: {channel_context})
                            
                            🔗 URL CONTEXT (from TikTok/Instagram):
                            {url_context if url_context else 'No URL context available'}
                            
                            STEP 1: Describe exactly what you see in the video (characters, scenes, text, actions)
                            STEP 2: Cross-reference visuals with URL hashtags/description for accuracy
                            STEP 3: Create metadata that matches ACTUAL content based on both visuals AND URL context
                            
                            If URL context mentions specific shows/characters (like #wednesday #enid #netflixseries), include them!
                            
                            Provide optimized YouTube metadata in JSON format:
                            {{
                                "original_title": "{original_title}",
                                "optimized_title": "compelling 60-char YouTube title with emojis that matches actual content",
                                "description": "engaging 2-3 sentence description about what's actually in the video",
                                "tags": ["15-20 relevant YouTube tags based on ACTUAL visual content"],
                                "content_type": "anime/gaming/comedy/dance/beauty/motivation/educational/entertainment/sports/music/tech/food/travel/lifestyle/news/general/tv_edit/movie_edit/character_edit",
                                "actual_content_description": "detailed description of what's actually shown in frames",
                                "viral_potential_score": 1-10,
                                "confidence_score": 0.0-1.0,
                                "main_subjects": "what's happening in the video based on visuals",
                                "emotional_tone": "happy/exciting/dramatic/calm/funny/inspiring/etc",
                                "visual_style": "animation/live-action/graphics/etc",
                                "target_audience": "teens/young adults/general/etc",
                                "best_upload_time": "morning/afternoon/evening/night",
                                "thumbnail_suggestions": ["3 specific thumbnail ideas based on visual content"],
                                "content_channel_mismatch": "true/false - does content match channel theme?"
                            }}
                            
                            Make it highly optimized for YouTube algorithm and the specific channel theme.
                            Respond only with valid JSON.
                            """
                        }
                    ]
                }
            ]
            
            # Add frames
            for frame_b64 in frames_b64:
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_b64}",
                        "detail": "low"
                    }
                })
            
            # Make API call
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            # Calculate cost - much cheaper with 1-frame standard analysis
            if premium:  # 5 frames (only when explicitly requested)
                total_cost = 0.3084
                cost_note = "5-frame premium analysis"
            else:  # 1 frame + URL context (standard approach)
                total_cost = 0.0674
                cost_note = "1-frame + URL context"
            
            print(f"💰 Vision analysis cost: ${total_cost:.4f} ({cost_note})")
            
            # Parse response
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            try:
                result = json.loads(content)
                
                # Add metadata
                result["analysis_cost"] = total_cost
                result["frames_analyzed"] = num_frames
                result["analysis_method"] = f"vision_{num_frames}frame{'s' if num_frames > 1 else ''}"
                
                # Ensure title is properly formatted for YouTube
                if "optimized_title" in result:
                    result["optimized_title"] = result["optimized_title"][:100]  # YouTube limit
                
                return result
                
            except json.JSONDecodeError as e:
                print(f"⚠️ Vision analysis JSON parsing failed: {e}")
                return None
                
        except Exception as e:
            print(f"⚠️ Vision analysis failed: {e}")
            return None
    
    def _extract_video_frames(self, video_path: str, num_frames: int = 1) -> List[str]:
        """Extract frames from video for vision analysis"""
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames == 0:
                return []
            
            frames_b64 = []
            
            # Calculate frame positions
            if num_frames == 1:
                frame_positions = [total_frames // 2]  # Middle frame
            else:
                frame_positions = []
                for i in range(num_frames):
                    pos = int((i + 1) * total_frames / (num_frames + 1))
                    frame_positions.append(pos)
            
            for frame_pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                
                if ret:
                    # Resize to reduce costs (max 512px)
                    height, width = frame.shape[:2]
                    if max(height, width) > 512:
                        scale = 512 / max(height, width)
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Convert to base64
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_b64 = base64.b64encode(buffer).decode('utf-8')
                    frames_b64.append(frame_b64)
            
            cap.release()
            return frames_b64
            
        except Exception as e:
            print(f"❌ Frame extraction failed: {e}")
            return []
    
    def _get_channel_context(self, channel_name: str) -> str:
        """Get channel-specific context for better AI analysis"""
        channel_contexts = {
            "ZitBliss": "Beauty and skincare focused channel, young audience, trending beauty content",
            "AnimeShorts137": "Anime clips and moments, anime fans, short entertaining clips from popular anime",
            "meme0culture": "Meme and comedy content, humor-focused, viral funny content for young adults",
            "LungTeMotivates": "Motivational and inspirational content, self-improvement, success mindset",
            "lungte8888": "General inspiring content, lifestyle motivation, positive mindset content"
        }
        return channel_contexts.get(channel_name, "General entertainment content")
    
    def _should_retry_with_premium(self, analysis: Dict, channel_name: str) -> bool:
        """🧠 Smart AI Self-Detection: Only retry in extreme failure cases (URL context handles most accuracy issues)"""
        
        # Check 1: Complete analysis failure
        analysis_method = analysis.get('analysis_method', '')
        if 'failed' in analysis_method or 'error' in analysis_method:
            print(f"   ❌ Analysis completely failed")
            return True
        
        # Check 2: Extremely low confidence (complete failure)
        confidence = analysis.get('confidence_score', 1.0)
        if confidence < 0.3:
            print(f"   🎯 Extremely low confidence: {confidence:.2f}")
            return True
        
        # Check 3: No meaningful content extracted
        title = analysis.get('optimized_title', '').lower()
        if len(title) < 10 or title == 'untitled':
            print(f"   � No meaningful title extracted")
            return True
        
        # URL context should handle accuracy - no need for premium upgrades in most cases
        print(f"   ✅ Analysis quality acceptable (URL context provides accuracy boost)")
        return False
    
    def _extract_url_context(self, url: str) -> str:
        """🔗 Extract hashtags and context from TikTok/Instagram URLs"""
        try:
            # Import here to avoid dependency issues
            import requests
            from bs4 import BeautifulSoup
            import re
            
            print(f"🔍 Extracting context from URL...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            context_info = {
                'hashtags': [],
                'description': '',
                'title': '',
                'platform': 'unknown'
            }
            
            # Detect platform
            if 'tiktok.com' in url:
                context_info['platform'] = 'tiktok'
            elif 'instagram.com' in url:
                context_info['platform'] = 'instagram'
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract title/description
                    title_tag = soup.find('title')
                    if title_tag:
                        context_info['title'] = title_tag.get_text().strip()
                    
                    # Look for meta descriptions
                    meta_desc = soup.find('meta', attrs={'name': 'description'}) or \
                               soup.find('meta', attrs={'property': 'og:description'})
                    if meta_desc:
                        context_info['description'] = meta_desc.get('content', '').strip()
                    
                    # Extract hashtags using regex
                    page_text = response.text
                    hashtag_pattern = r'#[\w\d_]+\b'
                    hashtags = re.findall(hashtag_pattern, page_text, re.IGNORECASE)
                    
                    # Clean and deduplicate hashtags
                    unique_hashtags = list(set([tag.lower() for tag in hashtags[:20]]))  # Max 20 hashtags
                    context_info['hashtags'] = unique_hashtags
                    
                    if unique_hashtags:
                        print(f"✅ Found {len(unique_hashtags)} hashtags: {', '.join(unique_hashtags[:5])}{'...' if len(unique_hashtags) > 5 else ''}")
                    else:
                        print("⚠️ No hashtags found")
                    
            except Exception as e:
                print(f"⚠️ URL context extraction failed: {e}")
                
            return self._format_url_context(context_info)
            
        except ImportError:
            print("⚠️ requests/beautifulsoup not available - skipping URL context extraction")
            return ""
        except Exception as e:
            print(f"⚠️ URL context extraction error: {e}")
            return ""
    
    def _format_url_context(self, context_info: dict) -> str:
        """Format extracted URL context for AI prompt"""
        context_parts = []
        
        if context_info['hashtags']:
            hashtags_str = ' '.join(context_info['hashtags'])
            context_parts.append(f"Hashtags: {hashtags_str}")
        
        if context_info['description']:
            context_parts.append(f"Description: {context_info['description'][:200]}")
        
        if context_info['title']:
            context_parts.append(f"Original Title: {context_info['title'][:100]}")
        
        context_parts.append(f"Platform: {context_info['platform']}")
        
        return '\n'.join(context_parts) if context_parts else ""
    
    def apply_background(self, video_path: str, channel_name: str, video_index: int) -> str:
        """Apply channel-specific background using test3_script processing"""
        # Create channel folder
        channel_folder = os.path.join(self.channels_processed_dir, channel_name)
        os.makedirs(channel_folder, exist_ok=True)
        
        # Get channel-specific background
        channel_config = self.channels[channel_name]
        background_image = channel_config["background"]
        
        try:
            # Import and use the background processing from test3_script
            from test3_script import process_video_with_background_options
            
            # Create temporary output name
            temp_output = os.path.join(self.temp_dir, f"temp_processed_{video_index}.mp4")
            
            # Process video with channel background
            result = process_video_with_background_options(
                video_path=video_path,
                title=f"{channel_name}_video_{video_index}",
                bg_mode='specific',  # Use specific background
                specific_bg=background_image,
                channel_name=channel_name
            )
            
            if result and os.path.exists(result):
                # Move processed video to channel folder
                final_name = f"video_{video_index}.mp4"
                final_path = os.path.join(channel_folder, final_name)
                shutil.move(result, final_path)
                
                # Clean up original temp file
                if video_path != final_path and os.path.exists(video_path):
                    os.remove(video_path)
                
                print(f"🎨 Applied {background_image} background → {channel_name}/video_{video_index}.mp4")
                return final_path
            else:
                # Fallback: just copy without background if processing fails
                final_name = f"video_{video_index}.mp4"
                final_path = os.path.join(channel_folder, final_name)
                shutil.copy2(video_path, final_path)
                
                if video_path != final_path:
                    os.remove(video_path)
                
                print(f"⚠️ Background processing failed, using original → {channel_name}/video_{video_index}.mp4")
                return final_path
                
        except Exception as e:
            print(f"❌ Background processing error: {e}")
            # Fallback: just copy without background
            final_name = f"video_{video_index}.mp4"
            final_path = os.path.join(channel_folder, final_name)
            shutil.copy2(video_path, final_path)
            
            if video_path != final_path:
                os.remove(video_path)
            
            print(f"⚠️ Using fallback (no background) → {channel_name}/video_{video_index}.mp4")
            return final_path
    
    def save_metadata(self, video_path: str, metadata: Dict):
        """Save metadata alongside video in channel folder"""
        metadata_path = video_path.replace('.mp4', '_metadata.json')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Also log where it was saved
        print(f"💾 Metadata saved: {os.path.basename(metadata_path)}")
    
    def show_video_metadata(self, video_path: str):
        """Display detailed metadata for a video (useful for YouTube upload planning)"""
        metadata_path = video_path.replace('.mp4', '_metadata.json')
        
        if not os.path.exists(metadata_path):
            print(f"❌ No metadata found for {os.path.basename(video_path)}")
            return
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        print(f"\n📊 METADATA FOR: {os.path.basename(video_path)}")
        print("=" * 60)
        print(f"🎬 Title: {metadata.get('optimized_title', metadata.get('title', 'N/A'))}")
        print(f"📝 Description: {metadata.get('description', 'N/A')[:100]}{'...' if len(metadata.get('description', '')) > 100 else ''}")
        print(f"🏷️ Tags: {', '.join(metadata.get('tags', []))}")
        print(f"📂 Content Type: {metadata.get('content_type', 'N/A')}")
        print(f"📊 Analysis Method: {metadata.get('analysis_method', 'N/A')}")
        
        if metadata.get('analysis_cost'):
            print(f"💰 Analysis Cost: ${metadata.get('analysis_cost', 0):.4f}")
        
        if metadata.get('confidence_score'):
            print(f"🎯 AI Confidence: {metadata.get('confidence_score', 0):.2f}")
        
        if metadata.get('viral_potential_score'):
            print(f"🔥 Viral Potential: {metadata.get('viral_potential_score', 0)}/10")
        
        if metadata.get('target_audience'):
            print(f"👥 Target Audience: {metadata.get('target_audience', 'N/A')}")
        
        if metadata.get('best_upload_time'):
            print(f"⏰ Best Upload Time: {metadata.get('best_upload_time', 'N/A')}")
        
        if metadata.get('thumbnail_suggestions'):
            print(f"🖼️ Thumbnail Ideas:")
            for i, suggestion in enumerate(metadata.get('thumbnail_suggestions', []), 1):
                print(f"   {i}. {suggestion}")
        
        print(f"🕒 Processed: {metadata.get('processed_at', 'N/A')}")
        print(f"🔗 Original URL: {metadata.get('url', 'N/A')}")
    
    def prepare_youtube_metadata(self, video_path: str) -> Dict:
        """Prepare metadata specifically formatted for YouTube upload"""
        metadata_path = video_path.replace('.mp4', '_metadata.json')
        
        if not os.path.exists(metadata_path):
            return {}
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Format for YouTube API requirements
        youtube_metadata = {
            "title": metadata.get('optimized_title', metadata.get('title', ''))[:100],  # YouTube limit
            "description": metadata.get('description', '')[:5000],  # YouTube limit
            "tags": metadata.get('tags', [])[:500],  # YouTube has tag limits
            "categoryId": "24",  # Entertainment category
            "privacyStatus": "private",  # Start as private
            "madeForKids": False,
            # Additional metadata for internal use
            "originalMetadata": metadata
        }
        
        return youtube_metadata
    
    def upload_video(self, video_path: str, metadata: Dict, channel_name: str = "default") -> bool:
        """Upload video to YouTube - REAL UPLOAD"""
        try:
            # Import YouTube uploader functions
            from youtube_uploader import authenticate_youtube, upload_video
            
            # Get title with fallback to different key names
            title = metadata.get('optimized_title', metadata.get('title', 'Unknown Title'))
            print(f"🚀 REAL YouTube Upload: {title}")
            
            # Get YouTube service for the channel
            youtube = authenticate_youtube(channel_name)
            if not youtube:
                print(f"❌ Failed to authenticate YouTube service for {channel_name}")
                return False
            
            # Prepare video data
            clean_title = title[:100]  # YouTube limit
            description = metadata.get('description', '')[:5000]  # YouTube limit
            tags = metadata.get('tags', [])
            
            # Convert tags to string list if needed
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(',')]
            
            # Clean and limit tags
            clean_tags = []
            total_length = 0
            for tag in tags[:15]:  # Max 15 tags
                tag = str(tag).strip()
                if tag and total_length + len(tag) < 450:
                    clean_tags.append(tag)
                    total_length += len(tag)
            
            # Upload immediately (no scheduling)
            result = upload_video(
                youtube=youtube,
                video_path=video_path,
                title=clean_title,
                description=description,
                tags=clean_tags,
                scheduled_time=None,  # No scheduling = immediate upload
                auto_confirm=True,
                channel_name=channel_name
            )
            
            if result:
                print(f"✅ Successfully uploaded to YouTube!")
                print(f"📺 Check YouTube Studio to see your video")
                return True
            else:
                print(f"❌ YouTube upload failed")
                return False
                
        except ImportError as e:
            print(f"❌ YouTube uploader import error: {e}")
            print("💡 Please ensure youtube_uploader.py is properly configured")
            return False
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return False
    
    def upload_video_with_schedule(self, video_path: str, metadata: Dict, scheduled_time: str, channel_name: str = "default") -> bool:
        """Upload video to YouTube with scheduled publish time"""
        try:
            # Import YouTube uploader functions
            from youtube_uploader import authenticate_youtube, upload_video
            
            print(f"🚀 Uploading scheduled video: {metadata.get('optimized_title', 'Unknown Title')}")
            print(f"📅 Scheduled for: {scheduled_time}")
            
            # Get YouTube service for the channel
            youtube = authenticate_youtube(channel_name)
            if not youtube:
                print(f"❌ Failed to authenticate YouTube service for {channel_name}")
                return False
            
            # Prepare video data
            title = metadata.get('optimized_title', metadata.get('title', 'Untitled Video'))[:100]
            description = metadata.get('optimized_description', metadata.get('description', ''))[:5000]
            tags = metadata.get('optimized_tags', metadata.get('tags', []))
            
            # Convert tags to string list if needed
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(',')]
            
            # Clean and limit tags
            clean_tags = []
            total_length = 0
            for tag in tags[:15]:  # Max 15 tags
                tag = str(tag).strip()
                if tag and total_length + len(tag) < 450:
                    clean_tags.append(tag)
                    total_length += len(tag)
            
            # Upload with scheduled time
            result = upload_video(
                youtube=youtube,
                video_path=video_path,
                title=title,
                description=description,
                tags=clean_tags,
                scheduled_time=scheduled_time,
                auto_confirm=True,  # Auto-confirm for scheduled uploads
                channel_name=channel_name
            )
            
            if result:
                print(f"✅ Successfully uploaded and scheduled!")
                print(f"📺 Check YouTube Studio to see your scheduled video")
                return True
            else:
                print(f"❌ Upload failed")
                return False
                
        except ImportError as e:
            print(f"❌ YouTube uploader import error: {e}")
            print("💡 Please ensure youtube_uploader.py is properly configured")
            return False
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return False

    def list_ready_videos(self, channel_name: str = None) -> Dict[str, List[str]]:
        """List processed videos ready for upload from channel folders"""
        ready_videos = {}
        
        channels_to_check = [channel_name] if channel_name else self.channels.keys()
        
        for ch_name in channels_to_check:
            channel_folder = os.path.join(self.channels_processed_dir, ch_name)
            
            if not os.path.exists(channel_folder):
                continue
                
            videos = []
            for file in os.listdir(channel_folder):
                if file.endswith('.mp4'):
                    video_path = os.path.join(channel_folder, file)
                    metadata_path = video_path.replace('.mp4', '_metadata.json')
                    if os.path.exists(metadata_path):
                        videos.append(video_path)
            
            if videos:
                ready_videos[ch_name] = sorted(videos)
        
        return ready_videos
    
    def show_upload_status(self):
        """Show all channels and their ready videos"""
        print("\n📊 Upload Status - Ready Videos")
        print("=" * 60)
        
        ready_videos = self.list_ready_videos()
        
        if not ready_videos:
            print("⚠️ No videos ready for upload")
            print("💡 Process some channels first!")
            return
        
        for channel_name, videos in ready_videos.items():
            print(f"\n🎬 {channel_name}: {len(videos)} videos ready")
            for i, video_path in enumerate(videos, 1):
                metadata_path = video_path.replace('.mp4', '_metadata.json')
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    title = metadata.get('optimized_title', metadata.get('title', 'Unknown Title'))[:50]
                    print(f"   {i}. {title}...")
                except:
                    print(f"   {i}. {os.path.basename(video_path)}")
    
    def upload_channel_with_schedule(self, channel_name: str):
        """Upload channel videos with scheduling options"""
        ready_videos = self.list_ready_videos(channel_name)
        
        if channel_name not in ready_videos:
            print(f"⚠️ No videos ready for {channel_name}")
            print("💡 Process the channel first!")
            return
        
        videos = ready_videos[channel_name]
        print(f"\n🚀 Upload Manager - {channel_name}")
        print(f"📺 {len(videos)} videos ready for upload")
        print("=" * 50)
        
        # Scheduling options
        print("\n📅 Choose upload schedule:")
        print("1. Dynamic Schedule - Smart timing")
        print("2. Upload All Now - Immediate upload")
        print("3. Static Days Schedule - Choose specific days")
        print("4. Cancel")
        
        schedule_choice = input("\nEnter choice (1-4): ").strip()
        
        if schedule_choice == "1":
            self._upload_dynamic_schedule(channel_name, videos)
        elif schedule_choice == "2":
            self._upload_all_now(channel_name, videos)
        elif schedule_choice == "3":
            self._upload_static_days_schedule(channel_name, videos)
        elif schedule_choice == "4":
            print("❌ Upload cancelled")
        else:
            print("❌ Invalid choice")
    
    def _upload_static_days_schedule(self, channel_name: str, videos: List[str]):
        """Upload with AI-proposed days and intervals"""
        print(f"\n📅 Static Days Schedule for {channel_name}")
        
        # AI proposes optimal schedule based on video count and channel type
        from datetime import datetime, timedelta
        
        # Smart interval based on video count
        if len(videos) <= 5:
            interval_days = 2  # Every 2 days for small batches
        elif len(videos) <= 10:
            interval_days = 3  # Every 3 days for medium batches  
        else:
            interval_days = 2  # Every 2 days for large batches (more frequent)
        
        # Channel-specific optimal days and times
        channel_schedules = {
            "meme0culture": {"days": [1, 3, 5], "time": "18:00", "reason": "Comedy content peaks evening weekdays"},
            "AnimeShorts137": {"days": [2, 4, 6], "time": "20:00", "reason": "Anime fans active evening/weekends"},
            "LungTeMotivates": {"days": [1, 3, 5], "time": "07:00", "reason": "Motivational content works best morning start"},
            "ZitBliss": {"days": [2, 4, 7], "time": "15:00", "reason": "Beauty content peaks afternoon/weekend"},
            "lungte8888": {"days": [1, 4, 6], "time": "12:00", "reason": "General content optimal midday spread"}
        }
        
        # Get proposed schedule or default
        if channel_name in channel_schedules:
            schedule_info = channel_schedules[channel_name]
            proposed_days = schedule_info["days"]
            proposed_time = schedule_info["time"] 
            reason = schedule_info["reason"]
        else:
            # Default schedule
            proposed_days = [1, 3, 5]  # Monday, Wednesday, Friday
            proposed_time = "14:00"
            reason = "Standard optimal engagement pattern"
        
        # Generate actual schedule with dates
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        selected_day_names = [day_names[d-1] for d in proposed_days]
        
        # Calculate distribution across weeks
        videos_per_week = len(proposed_days)
        total_weeks = (len(videos) + videos_per_week - 1) // videos_per_week
        
        print(f"\n🤖 AI Proposed Schedule:")
        print(f"   📅 Days: {', '.join(selected_day_names)}")
        print(f"   ⏰ Time: {proposed_time}")
        print(f"   📊 Pattern: Every {interval_days} days on optimal weekdays")
        print(f"   💡 Reason: {reason}")
        print(f"   📈 Distribution: {videos_per_week} videos/week for {total_weeks} weeks")
        
        # Show detailed schedule preview
        print(f"\n📋 Detailed Upload Schedule:")
        current_date = datetime.now().date()
        schedule_dates = []
        
        # Find next occurrence of first proposed day
        days_ahead = proposed_days[0] - current_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        next_date = current_date + timedelta(days=days_ahead)
        day_index = 0
        
        for i, video_path in enumerate(videos, 1):
            video_name = os.path.basename(video_path)[:30]
            day_name = day_names[proposed_days[day_index]]
            upload_datetime = f"{next_date.strftime('%Y-%m-%d')} {proposed_time}"
            
            print(f"   {i}. {video_name}... → {day_name} {next_date.strftime('%m/%d')} at {proposed_time}")
            
            schedule_dates.append(upload_datetime)
            
            # Move to next day in cycle
            day_index = (day_index + 1) % len(proposed_days)
            if day_index == 0:  # Completed one cycle, move to next week
                next_date += timedelta(days=7)
            else:
                # Calculate days to next scheduled day
                current_day = proposed_days[day_index - 1]
                next_day = proposed_days[day_index]
                days_to_add = (next_day - current_day) % 7
                if days_to_add == 0:
                    days_to_add = 7
                next_date += timedelta(days=days_to_add)
        
        total_duration_days = (schedule_dates[-1] if schedule_dates else datetime.now().isoformat())
        print(f"\n⏰ Complete in: ~{total_weeks} weeks")
        print(f"🎯 Optimized for {channel_name} audience engagement")
        
        confirm = input("\nAccept AI proposed schedule? (y/n): ").strip().lower()
        if confirm == 'y':
            self._execute_days_schedule(channel_name, videos, proposed_days, proposed_time, schedule_dates)
        else:
            print("❌ Schedule cancelled")
    
    def _upload_dynamic_schedule(self, channel_name: str, videos: List[str]):
        """Upload with smart timing based on engagement"""
        print(f"\n🤖 Dynamic Schedule for {channel_name}")
        
        print("📊 Smart timing options:")
        print("1. Peak Hours - Upload during high engagement times")
        print("2. Consistent Growth - Spread uploads for steady growth")
        print("3. Viral Optimization - Time uploads for maximum reach")
        
        strategy = input("\nChoose strategy (1-3): ").strip()
        
        strategies = {
            "1": "Peak Hours (12PM, 6PM, 9PM)",
            "2": "Consistent Growth (Every 4-6 hours)",
            "3": "Viral Optimization (Random optimal times)"
        }
        
        if strategy in strategies:
            print(f"\n📋 Schedule Preview:")
            print(f"   Strategy: {strategies[strategy]}")
            print(f"   Total videos: {len(videos)}")
            print(f"   Estimated completion: {len(videos) * 4} hours")
            
            confirm = input("\nConfirm dynamic schedule? (y/n): ").strip().lower()
            if confirm == 'y':
                self._execute_upload_schedule(channel_name, videos, "dynamic", strategy)
            else:
                print("❌ Schedule cancelled")
        else:
            print("❌ Invalid strategy")
    
    def _upload_all_now(self, channel_name: str, videos: List[str]):
        """Upload all videos immediately"""
        print(f"\n🚀 Immediate Upload - {channel_name}")
        print(f"⚠️ This will upload {len(videos)} videos now!")
        
        confirm = input("Are you sure? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Upload cancelled")
            return
        
        successful_uploads = 0
        
        for i, video_path in enumerate(videos, 1):
            print(f"\n📤 Uploading {i}/{len(videos)}")
            
            try:
                # Load metadata
                metadata_path = video_path.replace('.mp4', '_metadata.json')
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Upload
                if self.upload_video(video_path, metadata, channel_name="AnimeShorts137"):
                    successful_uploads += 1
                    
                    # Clean up after successful upload
                    os.remove(video_path)
                    if os.path.exists(metadata_path):
                        os.remove(metadata_path)
                
            except Exception as e:
                print(f"❌ Upload failed for video {i}: {e}")
        
        print(f"\n✅ Upload complete: {successful_uploads}/{len(videos)} videos uploaded")
    
    def _execute_days_schedule(self, channel_name: str, videos: List[str], selected_days: List[int], upload_time: str, schedule_dates: List[str]):
        """Execute the days-based upload schedule by actually uploading to YouTube"""
        from datetime import datetime, timedelta
        
        print(f"\n🚀 Starting YouTube Upload & Schedule for {channel_name}!")
        print(f"📺 Uploading {len(videos)} videos with scheduled publish times")
        print("=" * 60)
        
        # Calculate next upload dates
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        selected_day_names = [day_names[d-1] for d in selected_days]
        
        # Show final schedule confirmation
        print(f"\n📋 Upload Schedule:")
        print(f"   📅 Days: {', '.join(selected_day_names)}")
        print(f"   ⏰ Time: {upload_time}")
        print(f"   📊 Total uploads: {len(schedule_dates)}")
        
        # Track upload results
        successful_uploads = 0
        failed_uploads = 0
        
        # Upload each video with its scheduled time
        for i, (video_path, schedule_date) in enumerate(zip(videos, schedule_dates), 1):
            video_name = os.path.basename(video_path)[:40]
            print(f"\n📤 Uploading {i}/{len(videos)}: {video_name}")
            print(f"📅 Scheduled for: {schedule_date}")
            
            try:
                # Load metadata for this video
                metadata_path = video_path.replace(".mp4", "_metadata.json")
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                # Upload with scheduled time
                upload_success = self.upload_video_with_schedule(
                    video_path=video_path,
                    metadata=metadata,
                    scheduled_time=schedule_date,
                    channel_name=channel_name
                )
                
                if upload_success:
                    successful_uploads += 1
                    print(f"✅ Upload {i} successful!")
                    
                    # Clean up local files after successful upload
                    try:
                        os.remove(video_path)
                        if os.path.exists(metadata_path):
                            os.remove(metadata_path)
                        print(f"🗑️ Cleaned up local files")
                    except:
                        pass
                else:
                    failed_uploads += 1
                    print(f"❌ Upload {i} failed!")
                
                # Small delay between uploads to avoid rate limits
                if i < len(videos):
                    print("⏳ Waiting 3 seconds before next upload...")
                    time.sleep(3)
                    
            except Exception as e:
                failed_uploads += 1
                print(f"❌ Upload error for video {i}: {e}")
                continue
        
        # Show final results
        print(f"\n🎉 Upload Complete!")
        print("=" * 50)
        print(f"✅ Successful uploads: {successful_uploads}")
        print(f"❌ Failed uploads: {failed_uploads}")
        print(f"📊 Success rate: {(successful_uploads/len(videos)*100):.1f}%")
        
        if successful_uploads > 0:
            print(f"\n🎯 {successful_uploads} videos scheduled on YouTube!")
            print(f"📅 Publishing on: {', '.join(selected_day_names)} at {upload_time}")
            print(f"📺 Check YouTube Studio to see your scheduled videos")
            print(f"⏰ Videos will automatically publish at scheduled times")
        
        if failed_uploads > 0:
            print(f"\n⚠️ {failed_uploads} uploads failed - videos remain in channels_processed/")
            print(f"💡 You can retry failed uploads later")
        
        # Calculate schedule analytics
        videos_per_week = len(selected_days)
        total_weeks = (successful_uploads + videos_per_week - 1) // videos_per_week
        
        print(f"\n📈 Schedule Analytics:")
        print(f"   🔄 Frequency: {videos_per_week} videos per week")
        print(f"   📅 Duration: ~{total_weeks} weeks")
        print(f"   ⚡ Pattern: Every {', '.join(selected_day_names)} at {upload_time}")
        print(f"   🎯 Optimized for {channel_name} audience engagement")
        print("\n📋 Next Steps:")
        print("   - Videos remain in channels_processed/ until uploaded")
        print("   - Schedule optimized for maximum engagement") 
        print("   - Check upload status anytime")
        print("   - Analytics will track performance")
    
    def process_channel_videos(self, channel_name: str) -> int:
        """Download and process videos for a channel (NO UPLOAD)"""
        if channel_name not in self.channels:
            print(f"❌ Unknown channel: {channel_name}")
            return 0
        
        config = self.channels[channel_name]
        urls_file = os.path.join(self.urls_dir, config["urls_file"])
        
        if not os.path.exists(urls_file):
            print(f"❌ URLs file not found: {urls_file}")
            return 0
        
        # Read URLs
        urls = []
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not urls:
            print(f"⚠️ No URLs found in {config['urls_file']}")
            return 0
        
        print(f"\n🎬 Processing {channel_name} videos - {len(urls)} URLs")
        print("=" * 60)
        
        processed_count = 0
        
        for i, url in enumerate(urls, 1):
            print(f"\n📺 Video {i}/{len(urls)}")
            
            try:
                # Check if already processed in channel folder
                channel_folder = os.path.join(self.channels_processed_dir, channel_name)
                expected_video = os.path.join(channel_folder, f"video_{i}.mp4")
                if os.path.exists(expected_video):
                    print(f"✅ Already processed: {channel_name}/video_{i}.mp4")
                    processed_count += 1
                    continue
                
                # Download
                video_path = self.download_video(url, f"{channel_name}_{i}")
                if not video_path:
                    continue
                
                # Analyze with AI (includes video index for premium analysis logic)
                metadata = self.analyze_video(video_path, url, channel_name, video_index=i)
                
                # Apply background
                final_video = self.apply_background(video_path, channel_name, i)
                
                # Save metadata
                self.save_metadata(final_video, metadata)
                
                processed_count += 1
                print(f"✅ Processed & Ready: {channel_name}/video_{i}.mp4")
                
            except Exception as e:
                print(f"❌ Error processing video {i}: {e}")
                continue
        
        print(f"\n✅ Channel {channel_name} processing complete: {processed_count} videos ready for upload")
        
        # Show cost summary
        if self.video_count > 0:
            avg_cost = self.total_analysis_cost / self.video_count
            print(f"💰 Analysis costs: ${self.total_analysis_cost:.4f} total, ${avg_cost:.4f} per video")
            
        return processed_count
    
    def show_ai_settings(self):
        """Show and modify AI settings"""
        print("\n🤖 AI Configuration Settings")
        print("=" * 40)
        
        # Show current settings
        print(f"Current Settings:")
        if self.FORCE_LOCAL_AI_ONLY:
            print("   🏠 LOCAL AI ONLY MODE - All OpenAI features disabled")
        elif self.USE_OPENAI_API:
            print("   ☁️ OpenAI API ENABLED - with local fallback")
        else:
            print("   🏠 OpenAI API DISABLED - local AI only")
        
        print(f"   OpenAI API Key: {'✅ Set' if os.getenv('OPENAI_API_KEY') else '❌ Missing'}")
        
        print("\n🎯 Options:")
        print("1. Enable OpenAI API (with local fallback)")
        print("2. Disable OpenAI API (local only)")
        print("3. Force local AI only (disable all OpenAI)")
        print("4. Back to main menu")
        
        choice = input("\nChoose option (1-4): ").strip()
        
        if choice == "1":
            self.USE_OPENAI_API = True
            self.FORCE_LOCAL_AI_ONLY = False
            print("✅ OpenAI API enabled (with local fallback)")
            # Reinitialize AI generator
            self.ai_generator = self._setup_ai()
            
        elif choice == "2":
            self.USE_OPENAI_API = False
            self.FORCE_LOCAL_AI_ONLY = False
            self.ai_generator = None
            print("✅ OpenAI API disabled - using local AI only")
            
        elif choice == "3":
            self.USE_OPENAI_API = False
            self.FORCE_LOCAL_AI_ONLY = True
            self.ai_generator = None
            print("✅ Forced local AI only - all OpenAI features disabled")
            
        elif choice == "4":
            return
            
        else:
            print("❌ Invalid choice")
    
    def run_interactive(self):
        """Interactive mode"""
        print("🎥 TikTub - Simple Video Processor")
        print("=" * 50)
        
        while True:
            print("\n🎯 Choose an option:")
            print("1. List channels")
            print("2. Process channel videos (Download + AI + Background)")
            print("3. Upload Management")
            print("4. Show upload status")
            print("5. View video metadata (YouTube upload planning)")
            print("6. Process all channels")
            print("7. AI Settings (Toggle OpenAI/Local)")
            print("8. Exit")
            
            choice = input("\nEnter choice (1-8): ").strip()
            
            if choice == "1":
                self.list_channels()
            
            elif choice == "2":
                self.list_channels()
                channel_input = input("\nEnter channel name or number: ").strip()
                
                # Handle number input
                if channel_input.isdigit():
                    channel_num = int(channel_input)
                    channel_names = list(self.channels.keys())
                    if 1 <= channel_num <= len(channel_names):
                        channel = channel_names[channel_num - 1]
                        self.process_channel_videos(channel)
                    else:
                        print("❌ Invalid channel number")
                # Handle name input
                elif channel_input in self.channels:
                    self.process_channel_videos(channel_input)
                else:
                    print("❌ Invalid channel name or number")
            
            elif choice == "3":
                self.show_upload_status()
                print("\n🚀 Upload Management:")
                
                ready_videos = self.list_ready_videos()
                if not ready_videos:
                    continue
                
                # Show channels with numbers
                channel_names = list(ready_videos.keys())
                for i, ch_name in enumerate(channel_names, 1):
                    video_count = len(ready_videos[ch_name])
                    print(f"{i}. {ch_name} ({video_count} videos)")
                
                channel_input = input(f"\nChoose channel to upload (1-{len(channel_names)}): ").strip()
                
                if channel_input.isdigit():
                    channel_num = int(channel_input)
                    if 1 <= channel_num <= len(channel_names):
                        selected_channel = channel_names[channel_num - 1]
                        self.upload_channel_with_schedule(selected_channel)
                    else:
                        print("❌ Invalid channel number")
                else:
                    print("❌ Please enter a number")
            
            elif choice == "4":
                self.show_upload_status()
            
            elif choice == "5":
                # View video metadata
                ready_videos = self.list_ready_videos()
                if not ready_videos:
                    print("❌ No processed videos found")
                    continue
                
                # Show channels
                channel_names = list(ready_videos.keys())
                for i, ch_name in enumerate(channel_names, 1):
                    video_count = len(ready_videos[ch_name])
                    print(f"{i}. {ch_name} ({video_count} videos)")
                
                channel_input = input(f"\nChoose channel (1-{len(channel_names)}): ").strip()
                
                if channel_input.isdigit():
                    channel_num = int(channel_input)
                    if 1 <= channel_num <= len(channel_names):
                        selected_channel = channel_names[channel_num - 1]
                        videos = ready_videos[selected_channel]
                        
                        # Show videos in that channel
                        for i, video_path in enumerate(videos, 1):
                            video_name = os.path.basename(video_path)
                            print(f"{i}. {video_name}")
                        
                        video_input = input(f"\nChoose video to view metadata (1-{len(videos)}): ").strip()
                        
                        if video_input.isdigit():
                            video_num = int(video_input)
                            if 1 <= video_num <= len(videos):
                                self.show_video_metadata(videos[video_num - 1])
                            else:
                                print("❌ Invalid video number")
                        else:
                            print("❌ Please enter a number")
                    else:
                        print("❌ Invalid channel number")
                else:
                    print("❌ Please enter a number")
            
            elif choice == "6":
                total_processed = 0
                for channel_name in self.channels:
                    processed = self.process_channel_videos(channel_name)
                    total_processed += processed
                print(f"\n🎉 All channels processed! Total videos ready: {total_processed}")
            
            elif choice == "7":
                self.show_ai_settings()
            
            elif choice == "8":
                print("👋 Goodbye!")
                break
            
            else:
                print("❌ Invalid choice")

if __name__ == "__main__":
    processor = TikTubProcessor()
    processor.run_interactive()
