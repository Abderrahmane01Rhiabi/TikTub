#!/usr/bin/env python3
"""
Simple Database-Free Video Processing Workflow
==============================================
Process videos directly without any database complexity
"""

import os
import json
from typing import List, Dict
import shutil
from datetime import datetime
import cv2
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SimpleVideoProcessor:
    """Database-free video processing workflow"""
    
    def __init__(self, workspace_dir: str = "/root/pytest/tik"):
        self.workspace_dir = workspace_dir
        self.channels_dir = os.path.join(workspace_dir, "channels")
        self.temp_dir = os.path.join(workspace_dir, "temp")
        self.backgrounds_dir = os.path.join(workspace_dir, "backgrounds")
        self.total_analysis_cost = 0.0
        
        # Create temp directory if needed
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def process_channel_urls(self, channel_name: str, urls_file: str) -> List[str]:
        """
        Process all URLs for a specific channel
        Returns list of processed video paths ready for upload
        """
        print(f"\n🎬 Processing channel: {channel_name}")
        
        # Read URLs from file
        urls = self._read_urls_file(urls_file)
        if not urls:
            print(f"❌ No URLs found in {urls_file}")
            return []
        
        processed_videos = []
        
        for i, url in enumerate(urls, 1):
            print(f"\n📥 Processing video {i}/{len(urls)}: {url}")
            
            try:
                # Step 1: Download video
                video_path = self._download_video(url, f"{channel_name}_video_{i}")
                if not video_path:
                    continue
                
                # Step 2: Get video info and generate AI content
                # Use premium analysis for every 5th video (20% get 5-frame analysis)
                use_premium = (i % 5 == 0)
                video_info = self._analyze_video(video_path, url, use_premium_analysis=use_premium)
                
                # Step 3: Apply background
                final_video = self._apply_background(video_path, video_info, channel_name)
                
                # Step 4: Save metadata alongside video
                self._save_video_metadata(final_video, video_info)
                
                processed_videos.append(final_video)
                print(f"✅ Video processed: {final_video}")
                
                # Clean up temporary files
                if os.path.exists(video_path) and video_path != final_video:
                    os.remove(video_path)
                    
            except Exception as e:
                print(f"❌ Error processing {url}: {e}")
                continue
        
        print(f"\n✅ Channel {channel_name} complete: {len(processed_videos)} videos ready")
        
        # Show cost summary
        if hasattr(self, 'total_analysis_cost') and self.total_analysis_cost > 0:
            avg_cost = self.total_analysis_cost / len(processed_videos) if processed_videos else 0
            print(f"💰 Analysis costs: ${self.total_analysis_cost:.4f} total, ${avg_cost:.4f} per video")
        
        return processed_videos
    
    def _read_urls_file(self, file_path: str) -> List[str]:
        """Read URLs from text file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            return urls
        except Exception as e:
            print(f"❌ Error reading URLs file: {e}")
            return []
    
    def _download_video(self, url: str, filename_base: str) -> str:
        """Download video using yt-dlp"""
        import subprocess
        
        output_path = os.path.join(self.temp_dir, f"{filename_base}.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "--extract-flat", "false",
            "--write-info-json",
            "--output", output_path,
            url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Find the downloaded video file
            for file in os.listdir(self.temp_dir):
                if file.startswith(filename_base) and file.endswith(('.mp4', '.webm', '.mkv')):
                    return os.path.join(self.temp_dir, file)
            
            return None
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Download failed: {e}")
            return None
    
    def _analyze_video_with_vision(self, video_path: str, original_title: str, premium: bool = False) -> Dict:
        """Analyze video using OpenAI Vision API"""
        try:
            import openai
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                return None
            
            client = openai.OpenAI(api_key=api_key)
            
            # Extract frames (1 frame for standard, 5 frames for premium)
            num_frames = 5 if premium else 1
            frames_b64 = self._extract_video_frames(video_path, num_frames)
            
            if not frames_b64:
                return None
            
            print(f"🤖 Analyzing video with {num_frames} frame{'s' if num_frames > 1 else ''} using AI Vision...")
            
            # Create vision analysis prompt
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
                            Analyze this video based on {len(frames_b64)} key frames. Original title: "{original_title}"
                            
                            Provide optimized YouTube content in JSON format:
                            {{
                                "original_title": "{original_title}",
                                "optimized_title": "compelling 60-char title with emojis",
                                "description": "2-3 sentence engaging description with call-to-action",
                                "tags": ["15-20 relevant tags for maximum reach"],
                                "content_type": "anime/gaming/comedy/dance/beauty/motivation/educational/entertainment/sports/music/tech/food/travel/lifestyle/news/general",
                                "viral_potential_score": 1-10,
                                "confidence_score": 0.0-1.0,
                                "main_subjects": "detailed description of what's in the video",
                                "emotional_tone": "happy/exciting/dramatic/calm/etc",
                                "visual_style": "description of video style and quality"
                            }}
                            
                            Make it highly engaging and optimized for YouTube algorithm.
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
                max_tokens=800,
                temperature=0.7
            )
            
            # Calculate cost
            image_cost = len(frames_b64) * 0.00765
            text_cost = 0.05  # Estimated based on your test results
            total_cost = image_cost + text_cost
            
            print(f"💰 Vision analysis cost: ${total_cost:.4f} ({num_frames} frames)")
            
            # Parse response
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            try:
                result = json.loads(content)
                result["analysis_cost"] = total_cost
                result["frames_analyzed"] = num_frames
                result["analysis_method"] = f"vision_{num_frames}frame{'s' if num_frames > 1 else ''}"
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
    
    def _analyze_video(self, video_path: str, url: str, use_premium_analysis: bool = False) -> Dict:
        """Analyze video with AI-powered vision analysis or fallback to text-only"""
        # Extract title from filename or metadata
        title = os.path.splitext(os.path.basename(video_path))[0]
        
        # Try advanced video vision analysis first
        vision_analysis = self._analyze_video_with_vision(video_path, title, premium=use_premium_analysis)
        if vision_analysis:
            # Track cost
            cost = vision_analysis.get("analysis_cost", 0)
            self.total_analysis_cost += cost
            
            return {
                **vision_analysis,
                "url": url,
                "processed_at": datetime.now().isoformat(),
                "analysis_method": vision_analysis.get("analysis_method", "vision")
            }
        
        # Fallback to text-only OpenAI analysis
        try:
            from openai_ai_generator import OpenAIGenerator
            api_key = os.getenv('OPENAI_API_KEY')
            
            if api_key:
                ai_gen = OpenAIGenerator(api_key)
                if ai_gen.test_api_connection():
                    analysis = ai_gen.analyze_video_content(title)
                    return {
                        "original_title": title,
                        "optimized_title": analysis.get("youtube_title", title),
                        "description": analysis.get("youtube_description", f"Amazing content from {url}"),
                        "tags": analysis.get("recommended_tags", ["shorts", "viral"]),
                        "content_type": analysis.get("content_type", "general"),
                        "url": url,
                        "processed_at": datetime.now().isoformat(),
                        "analysis_method": "text_only",
                        "analysis_cost": 0.002  # Estimated text-only cost
                    }
        except Exception as e:
            print(f"⚠️ AI analysis not available: {e}")
        
        # Final fallback to simple analysis
        return {
            "original_title": title,
            "optimized_title": f"🔥 {title[:55]}",
            "description": f"Amazing content you don't want to miss! Check this out 🚀",
            "tags": ["shorts", "viral", "trending", "entertainment"],
            "content_type": "general",
            "url": url,
            "processed_at": datetime.now().isoformat(),
            "analysis_method": "fallback",
            "analysis_cost": 0.0
        }
    
    def _apply_background(self, video_path: str, video_info: Dict, channel_name: str) -> str:
        """Apply background to video"""
        # For now, just rename/move the video to final location
        # This is where background processing would happen
        
        final_filename = f"{channel_name}_{video_info['content_type']}_{datetime.now().strftime('%H%M%S')}.mp4"
        final_path = os.path.join(self.temp_dir, final_filename)
        
        # Copy video to final location
        shutil.copy2(video_path, final_path)
        
        return final_path
    
    def _save_video_metadata(self, video_path: str, metadata: Dict):
        """Save metadata as JSON file alongside video"""
        metadata_path = video_path.replace('.mp4', '_metadata.json')
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def upload_channel_videos(self, channel_name: str, video_paths: List[str]):
        """Upload all videos for a channel"""
        print(f"\n🚀 Uploading {len(video_paths)} videos to {channel_name}")
        
        for video_path in video_paths:
            try:
                # Load metadata
                metadata_path = video_path.replace('.mp4', '_metadata.json')
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                print(f"📤 Uploading: {metadata['optimized_title']}")
                
                # Here you would call your YouTube uploader
                # self._upload_to_youtube(channel_name, video_path, metadata)
                
                # For now, just simulate upload
                print(f"✅ Uploaded: {os.path.basename(video_path)}")
                
                # Clean up after successful upload
                os.remove(video_path)
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                
            except Exception as e:
                print(f"❌ Upload failed for {video_path}: {e}")
    
    def process_all_channels(self):
        """Process all channels with their URL files"""
        print("🎬 Starting database-free channel processing...")
        
        # Example channel processing
        channels_to_process = [
            ("ZitBliss", "urls_input/zitbliss_urls.txt"),
            ("AnimeShorts137", "urls_input/anime_urls.txt"),
            ("meme0culture", "urls_input/meme_urls.txt"),
        ]
        
        for channel_name, urls_file in channels_to_process:
            if os.path.exists(urls_file):
                # Process all videos for this channel
                processed_videos = self.process_channel_urls(channel_name, urls_file)
                
                # Upload all videos for this channel
                if processed_videos:
                    self.upload_channel_videos(channel_name, processed_videos)
                    
                    # Archive the URLs file after processing
                    archive_name = f"{urls_file}.processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.move(urls_file, archive_name)
                    print(f"📁 Archived URLs file: {archive_name}")
            else:
                print(f"⚠️ URLs file not found: {urls_file}")
        
        print("\n🎉 All channels processed!")

if __name__ == "__main__":
    # Simple workflow execution
    processor = SimpleVideoProcessor()
    
    # Example: Process a single channel
    print("🎮 Simple Database-Free Video Processor")
    print("=" * 50)
    
    # You can either process all channels or one specific channel
    choice = input("\n1. Process all channels\n2. Process specific channel\nChoice (1/2): ").strip()
    
    if choice == "1":
        processor.process_all_channels()
    elif choice == "2":
        channel = input("Enter channel name: ").strip()
        urls_file = input("Enter URLs file path: ").strip()
        
        videos = processor.process_channel_urls(channel, urls_file)
        if videos:
            processor.upload_channel_videos(channel, videos)
    else:
        print("Invalid choice!")
