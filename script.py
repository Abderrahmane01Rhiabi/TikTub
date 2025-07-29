#!/usr/bin/env python3
"""
TikTok to YouTube Shorts Automation Script
==========================================
This script automates the process of downloading your own TikTok videos,
adding backgrounds to fill empty space, and uploading them to YouTube Shorts.

Requirements:
- pip install yt-dlp moviepy google-api-python-client google-auth-oauthlib pillow
- credentials.json file with YouTube API credentials
- backgrounds/ folder with background images
"""

import os
import json
import random
import re
from pathlib import Path
from typing import Optional, Tuple
import logging

# Third-party imports
import yt_dlp
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Configuration
CONFIG = {
    'backgrounds_folder': 'backgrounds/',
    'temp_folder': 'temp/',
    'output_folder': 'processed_videos/',
    'credentials_file': 'credentials.json',
    'token_file': 'token.json',
    'youtube_scopes': ['https://www.googleapis.com/auth/youtube.upload'],
    'target_resolution': (1080, 1920),  # 9:16 aspect ratio for YouTube Shorts
    'max_duration': 60,  # YouTube Shorts max duration
    'manual_approval': True,  # Set to False for auto-upload
    'default_tags': ['Shorts', 'TikTok', 'Viral', 'Entertainment'],
    'default_description': 'Originally posted on TikTok. Follow for more content!'
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TikTokToYouTubeProcessor:
    def __init__(self):
        self.setup_directories()
        self.youtube_service = None
        
    def setup_directories(self):
        """Create necessary directories if they don't exist."""
        for folder in [CONFIG['temp_folder'], CONFIG['output_folder'], CONFIG['backgrounds_folder']]:
            Path(folder).mkdir(exist_ok=True)
            
    def download_tiktok_video(self, url: str) -> Optional[str]:
        """Download TikTok video using yt-dlp."""
        try:
            logger.info(f"Downloading TikTok video: {url}")
            
            # Configure yt-dlp options
            ydl_opts = {
                'outtmpl': f"{CONFIG['temp_folder']}/%(title)s.%(ext)s",
                'format': 'best[height<=1920]',  # Limit to reasonable quality
                'writeinfojson': True,  # Save metadata for title/description
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'TikTok Video')
                
                # Download the video
                ydl.download([url])
                
                # Find the downloaded file
                temp_files = list(Path(CONFIG['temp_folder']).glob('*.mp4'))
                if temp_files:
                    video_path = str(temp_files[-1])  # Get the most recent file
                    logger.info(f"Downloaded: {video_path}")
                    return video_path, video_title
                    
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            return None, None
            
    def get_random_background(self) -> Optional[str]:
        """Select a random background image from the backgrounds folder."""
        try:
            bg_folder = Path(CONFIG['backgrounds_folder'])
            backgrounds = list(bg_folder.glob('*.{jpg,jpeg,png,gif}'))
            
            if not backgrounds:
                logger.warning("No background images found in backgrounds/ folder")
                return None
                
            selected_bg = random.choice(backgrounds)
            logger.info(f"Selected background: {selected_bg}")
            return str(selected_bg)
            
        except Exception as e:
            logger.error(f"Error selecting background: {e}")
            return None
            
    def process_video(self, video_path: str, video_title: str) -> Optional[str]:
        """Process video: resize, add background, format for YouTube Shorts."""
        try:
            logger.info(f"Processing video: {video_path}")
            
            # Load video
            video = VideoFileClip(video_path)
            
            # Check duration (YouTube Shorts max 60 seconds)
            if video.duration > CONFIG['max_duration']:
                logger.warning(f"Video duration ({video.duration}s) exceeds YouTube Shorts limit")
                video = video.subclip(0, CONFIG['max_duration'])
                
            # Get video dimensions
            video_w, video_h = video.size
            target_w, target_h = CONFIG['target_resolution']
            
            # Calculate scaling to fit within target resolution while maintaining aspect ratio
            scale = min(target_w / video_w, target_h / video_h)
            new_w = int(video_w * scale)
            new_h = int(video_h * scale)
            
            # Resize video
            video_resized = video.resize((new_w, new_h))
            
            # Create background if needed
            if new_w < target_w or new_h < target_h:
                background_path = self.get_random_background()
                
                if background_path:
                    # Create background clip
                    background = ImageClip(background_path, duration=video.duration)
                    background = background.resize(CONFIG['target_resolution'])
                    
                    # Center the video on the background
                    video_centered = video_resized.set_position('center')
                    final_video = CompositeVideoClip([background, video_centered])
                else:
                    # No background available, create black background
                    logger.info("No background found, using black background")
                    final_video = video_resized.on_color(
                        size=CONFIG['target_resolution'],
                        color=(0, 0, 0),
                        pos='center'
                    )
            else:
                final_video = video_resized
                
            # Generate output filename
            safe_title = re.sub(r'[^\w\s-]', '', video_title)[:50]
            output_path = f"{CONFIG['output_folder']}/{safe_title}_processed.mp4"
            
            # Export video with YouTube Shorts optimized settings
            logger.info("Exporting processed video...")
            final_video.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                preset='medium',
                ffmpeg_params=['-crf', '23']  # Good quality for YouTube
            )
            
            # Cleanup
            video.close()
            final_video.close()
            
            logger.info(f"Video processed successfully: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            return None
            
    def authenticate_youtube(self):
        """Authenticate with YouTube API."""
        try:
            creds = None
            
            # Load existing token
            if os.path.exists(CONFIG['token_file']):
                creds = Credentials.from_authorized_user_file(
                    CONFIG['token_file'], 
                    CONFIG['youtube_scopes']
                )
                
            # If no valid credentials, run OAuth flow
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        CONFIG['credentials_file'], 
                        CONFIG['youtube_scopes']
                    )
                    creds = flow.run_local_server(port=0)
                    
                # Save credentials for next run
                with open(CONFIG['token_file'], 'w') as token:
                    token.write(creds.to_json())
                    
            self.youtube_service = build('youtube', 'v3', credentials=creds)
            logger.info("YouTube authentication successful")
            
        except Exception as e:
            logger.error(f"YouTube authentication failed: {e}")
            raise
            
    def upload_to_youtube(self, video_path: str, title: str) -> bool:
        """Upload video to YouTube as a Short."""
        try:
            if not self.youtube_service:
                self.authenticate_youtube()
                
            # Prepare video metadata
            video_metadata = {
                'snippet': {
                    'title': title[:100],  # YouTube title limit
                    'description': CONFIG['default_description'],
                    'tags': CONFIG['default_tags'],
                    'categoryId': '24'  # Entertainment category
                },
                'status': {
                    'privacyStatus': 'public',  # Change to 'private' if you want to review first
                    'selfDeclaredMadeForKids': False
                }
            }
            
            # Manual approval check
            if CONFIG['manual_approval']:
                print(f"\nReady to upload: {title}")
                print(f"Video path: {video_path}")
                approval = input("Proceed with upload? (y/n): ").lower()
                if approval != 'y':
                    logger.info("Upload cancelled by user")
                    return False
                    
            # Upload video
            logger.info(f"Uploading to YouTube: {title}")
            
            media = MediaFileUpload(
                video_path,
                chunksize=-1,
                resumable=True,
                mimetype='video/mp4'
            )
            
            request = self.youtube_service.videos().insert(
                part='snippet,status',
                body=video_metadata,
                media_body=media
            )
            
            response = request.execute()
            video_id = response.get('id')
            
            if video_id:
                youtube_url = f"https://youtube.com/watch?v={video_id}"
                logger.info(f"Upload successful! Video URL: {youtube_url}")
                return True
            else:
                logger.error("Upload failed - no video ID returned")
                return False
                
        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return False
            
    def cleanup_temp_files(self):
        """Clean up temporary files."""
        try:
            temp_folder = Path(CONFIG['temp_folder'])
            for file in temp_folder.glob('*'):
                file.unlink()
            logger.info("Temporary files cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
            
    def process_tiktok_url(self, tiktok_url: str):
        """Main workflow: download, process, and upload a TikTok video."""
        logger.info(f"Starting processing for: {tiktok_url}")
        
        try:
            # Step 1: Download TikTok video
            video_path, video_title = self.download_tiktok_video(tiktok_url)
            if not video_path:
                logger.error("Failed to download video")
                return False
                
            # Step 2: Process video (resize, add background)
            processed_video_path = self.process_video(video_path, video_title)
            if not processed_video_path:
                logger.error("Failed to process video")
                return False
                
            # Step 3: Upload to YouTube
            upload_success = self.upload_to_youtube(processed_video_path, video_title)
            
            # Step 4: Cleanup
            self.cleanup_temp_files()
            
            if upload_success:
                logger.info("Workflow completed successfully!")
                return True
            else:
                logger.error("Upload failed")
                return False
                
        except Exception as e:
            logger.error(f"Workflow error: {e}")
            return False

def main():
    """Main function to run the script."""
    print("TikTok to YouTube Shorts Automation")
    print("=" * 40)
    
    # Initialize processor
    processor = TikTokToYouTubeProcessor()
    
    while True:
        print("\nOptions:")
        print("1. Process single TikTok URL")
        print("2. Process multiple URLs from file")
        print("3. Exit")
        
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == '1':
            url = input("Enter TikTok URL: ").strip()
            if url:
                processor.process_tiktok_url(url)
            else:
                print("Invalid URL")
                
        elif choice == '2':
            file_path = input("Enter path to text file with URLs (one per line): ").strip()
            try:
                with open(file_path, 'r') as f:
                    urls = [line.strip() for line in f if line.strip()]
                    
                for i, url in enumerate(urls, 1):
                    print(f"\nProcessing URL {i}/{len(urls)}: {url}")
                    processor.process_tiktok_url(url)
                    
            except FileNotFoundError:
                print("File not found")
            except Exception as e:
                print(f"Error reading file: {e}")
                
        elif choice == '3':
            print("Goodbye!")
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()