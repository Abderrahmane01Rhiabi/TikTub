#!/usr/bin/env python3
"""
Multi-Platform Social Media Batch Processor
Processes TikTok, Instagram, and YouTube Shorts URLs from batch files
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

# Import the enhanced functions from test3_script
from test3_script import (
    download_social_video, 
    detect_target_channel_ai, 
    process_video_with_background_options,
    detect_platform,
    setup_directories,
    CONFIG
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MultiPlatformProcessor:
    def __init__(self):
        self.processed_videos = []
        self.failed_videos = []
        self.channel_stats = {}
        
    def process_urls_from_file(self, file_path: str, bg_mode: str = 'random', specific_bg: str = None) -> Dict:
        """Process multiple URLs from a text file"""
        
        if not os.path.exists(file_path):
            logger.error(f"❌ File not found: {file_path}")
            return {"success": False, "error": "File not found"}
        
        # Read URLs from file
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not urls:
            logger.error("❌ No valid URLs found in file")
            return {"success": False, "error": "No URLs found"}
        
        logger.info(f"📋 Found {len(urls)} URLs to process")
        
        # Process each URL
        for i, url in enumerate(urls, 1):
            logger.info(f"\n🔄 Processing {i}/{len(urls)}: {url}")
            
            try:
                self.process_single_url(url, bg_mode, specific_bg)
            except Exception as e:
                logger.error(f"❌ Failed to process {url}: {e}")
                self.failed_videos.append({"url": url, "error": str(e)})
        
        # Generate summary report
        return self.generate_report()
    
    def process_single_url(self, url: str, bg_mode: str, specific_bg: str = None):
        """Process a single URL"""
        
        # Detect platform
        platform = detect_platform(url)
        logger.info(f"🎯 Platform: {platform}")
        
        # Download video with metadata
        video_path, metadata = download_social_video(url)
        if not video_path or not metadata:
            raise Exception("Download failed")
        
        # AI-powered channel detection
        target_channel = detect_target_channel_ai(metadata)
        logger.info(f"🤖 Target channel: {target_channel}")
        
        # Process video
        output_path = process_video_with_background_options(
            video_path,
            metadata['safe_title'],
            bg_mode,
            specific_bg,
            channel_name=target_channel,
            video_data=metadata
        )
        
        if not output_path:
            raise Exception("Video processing failed")
        
        # Track success
        video_info = {
            "url": url,
            "platform": platform,
            "title": metadata.get('title', 'Unknown'),
            "uploader": metadata.get('uploader', 'Unknown'),
            "target_channel": target_channel,
            "output_path": output_path,
            "file_size_mb": round(os.path.getsize(output_path) / 1024 / 1024, 2)
        }
        
        self.processed_videos.append(video_info)
        
        # Update channel stats
        if target_channel not in self.channel_stats:
            self.channel_stats[target_channel] = {"count": 0, "platforms": {}}
        
        self.channel_stats[target_channel]["count"] += 1
        if platform not in self.channel_stats[target_channel]["platforms"]:
            self.channel_stats[target_channel]["platforms"][platform] = 0
        self.channel_stats[target_channel]["platforms"][platform] += 1
        
        logger.info(f"✅ Processed successfully: {output_path}")
        
        # Cleanup temp files
        for f in Path(CONFIG['temp_folder']).glob('*'):
            try:
                f.unlink()
            except:
                pass
    
    def generate_report(self) -> Dict:
        """Generate processing report"""
        
        total_processed = len(self.processed_videos)
        total_failed = len(self.failed_videos)
        total_urls = total_processed + total_failed
        
        success_rate = (total_processed / total_urls * 100) if total_urls > 0 else 0
        
        report = {
            "success": True,
            "summary": {
                "total_urls": total_urls,
                "processed": total_processed,
                "failed": total_failed,
                "success_rate": round(success_rate, 2)
            },
            "channel_distribution": self.channel_stats,
            "processed_videos": self.processed_videos,
            "failed_videos": self.failed_videos
        }
        
        return report
    
    def save_report(self, report: Dict, output_file: str = "processing_report.json"):
        """Save processing report to JSON file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"📊 Report saved to: {output_file}")

def print_usage():
    """Print usage instructions"""
    print("📹 Multi-Platform Social Media Batch Processor")
    print("🎯 Supports: TikTok, Instagram, YouTube Shorts")
    print("\nUsage:")
    print("python multi_platform_processor.py <urls_file> [background_mode]")
    print("\nBackground modes:")
    print("  smart     - Channel-matched backgrounds (recommended)")
    print("  random    - Random background image")
    print("  blur      - Blurred video background")
    print("  solid     - Solid color background")
    print("  gradient  - Gradient background")
    print("  none      - Black background")
    print("\nExample:")
    print("python multi_platform_processor.py urls_input/mixed_batch.txt smart")
    print("python multi_platform_processor.py urls_input/mixed_batch.txt random")

def main():
    if len(sys.argv) < 2:
        print_usage()
        return
    
    urls_file = sys.argv[1]
    bg_mode = sys.argv[2] if len(sys.argv) > 2 else 'smart'  # Default to smart mode
    
    # Setup directories
    setup_directories()
    
    # Create processor and run
    processor = MultiPlatformProcessor()
    
    print(f"🚀 Starting batch processing...")
    print(f"📁 URLs file: {urls_file}")
    print(f"🎨 Background mode: {bg_mode}")
    
    # Process URLs
    report = processor.process_urls_from_file(urls_file, bg_mode)
    
    if report["success"]:
        # Print summary
        summary = report["summary"]
        print(f"\n📊 PROCESSING COMPLETE")
        print(f"{'='*50}")
        print(f"📋 Total URLs: {summary['total_urls']}")
        print(f"✅ Processed: {summary['processed']}")
        print(f"❌ Failed: {summary['failed']}")
        print(f"📈 Success Rate: {summary['success_rate']}%")
        
        # Print channel distribution
        print(f"\n🎯 CHANNEL DISTRIBUTION")
        print(f"{'='*30}")
        for channel, stats in report["channel_distribution"].items():
            print(f"📺 {channel}: {stats['count']} videos")
            for platform, count in stats["platforms"].items():
                print(f"   └── {platform}: {count}")
        
        # Save detailed report
        processor.save_report(report)
        
    else:
        print(f"❌ Processing failed: {report.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main()
