#!/usr/bin/env python3
"""
Comprehensive Frame Analysis Comparison
======================================
Tests 1, 5, and 15 frames to compare quality vs cost
"""

import os
import cv2
import base64
import json
from typing import Dict, List
from dotenv import load_dotenv
import time

load_dotenv()

try:
    import openai
    OPENAI_INSTALLED = True
except ImportError:
    OPENAI_INSTALLED = False
    print("⚠️ OpenAI library not installed")
    exit(1)

class ComprehensiveVideoAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)
        self.vision_model = "gpt-4o"  # Cheaper vision model
        self.text_model = "gpt-3.5-turbo"
        self.total_cost = 0.0
        self.analysis_history = []
    
    def extract_frames(self, video_path: str, num_frames: int = 1) -> List[str]:
        """Extract evenly distributed frames from video"""
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames == 0:
                print(f"❌ Could not read video: {video_path}")
                return []
            
            # Calculate frame positions evenly distributed
            frame_positions = []
            if num_frames == 1:
                frame_positions = [total_frames // 2]  # Middle frame
            else:
                for i in range(num_frames):
                    pos = int((i + 1) * total_frames / (num_frames + 1))
                    frame_positions.append(pos)
            
            frames_b64 = []
            for frame_pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                
                if ret:
                    # Resize to reduce costs (max 512px on longest side)
                    height, width = frame.shape[:2]
                    max_size = 512
                    if max(height, width) > max_size:
                        scale = max_size / max(height, width)
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Convert to base64 with compression
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_b64 = base64.b64encode(buffer).decode('utf-8')
                    frames_b64.append(frame_b64)
            
            cap.release()
            print(f"✅ Extracted {len(frames_b64)} frames from {os.path.basename(video_path)}")
            return frames_b64
            
        except Exception as e:
            print(f"❌ Frame extraction failed: {e}")
            return []
    
    def analyze_frames_with_vision(self, frames_b64: List[str], original_title: str, num_frames: int) -> Dict:
        """Analyze video frames using GPT-4 Vision"""
        try:
            print(f"🤖 Analyzing {num_frames} frames with GPT-4 Vision...")
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
                            Analyze this video based on {len(frames_b64)} key frames. Original title: "{original_title}"
                            
                            Provide detailed JSON analysis with:
                            1. visual_content_type: (anime, gaming, comedy, dance, beauty, motivation, educational, entertainment, sports, music, tech, food, travel, lifestyle, news, or general)
                            2. main_subjects: (detailed description of people/objects/characters)
                            3. actions_happening: (specific actions and movements observed)
                            4. visual_style: (animation style, cinematography, graphics quality)
                            5. scene_setting: (location, environment, time of day)
                            6. colors_mood: (color palette, lighting, overall mood/atmosphere)
                            7. text_overlay: (any visible text, captions, graphics)
                            8. engagement_elements: (what makes it visually engaging)
                            9. story_progression: (how the scene develops across frames)
                            10. technical_quality: (video quality, effects, production value)
                            11. target_demographic: (age group, interests, culture)
                            12. emotional_tone: (happy, exciting, dramatic, calm, etc.)
                            13. viral_indicators: (elements that could make it go viral)
                            14. confidence_score: (0-1, how confident in this analysis)
                            
                            Be very detailed since you have {len(frames_b64)} frames to analyze.
                            Respond only with valid JSON.
                            """
                        }
                    ]
                }
            ]
            
            # Add each frame as an image
            for i, frame_b64 in enumerate(frames_b64):
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_b64}",
                        "detail": "low"  # Use low detail to reduce costs
                    }
                })
            
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                max_tokens=1200,  # More tokens for detailed analysis
                temperature=0.7
            )
            analysis_time = time.time() - start_time
            
            # Calculate costs (GPT-4o pricing)
            image_cost = len(frames_b64) * 0.00765  # $0.00765 per image (low detail)
            
            # Estimate token costs
            prompt_length = len(str(messages))
            response_length = len(response.choices[0].message.content)
            input_tokens = prompt_length // 4  # Rough estimation
            output_tokens = response_length // 4
            
            # GPT-4o pricing: $0.005 per 1K input tokens, $0.015 per 1K output tokens
            text_cost = (input_tokens * 0.005 + output_tokens * 0.015) / 1000
            
            total_frame_cost = image_cost + text_cost
            self.total_cost += total_frame_cost
            
            print(f"💰 Analysis cost: ${total_frame_cost:.4f}")
            print(f"   📸 Images ({len(frames_b64)}): ${image_cost:.4f}")
            print(f"   💬 Text processing: ${text_cost:.4f}")
            print(f"   ⏱️ Analysis time: {analysis_time:.1f}s")
            
            # Parse JSON response
            content = response.choices[0].message.content.strip()
            
            # Clean up markdown formatting
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON parsing error: {e}")
                print(f"Raw response: {content[:200]}...")
                # Return a basic structure if JSON parsing fails
                result = {
                    "visual_content_type": "general",
                    "main_subjects": "Could not parse detailed analysis",
                    "confidence_score": 0.5,
                    "error": "JSON parsing failed"
                }
            
            # Add metadata
            result["analysis_cost"] = total_frame_cost
            result["frames_analyzed"] = len(frames_b64)
            result["analysis_time"] = analysis_time
            result["image_cost"] = image_cost
            result["text_cost"] = text_cost
            
            return result
            
        except Exception as e:
            print(f"❌ Vision analysis failed: {e}")
            return {
                "error": f"Vision analysis failed: {str(e)}",
                "analysis_cost": 0,
                "frames_analyzed": 0
            }
    
    def generate_optimized_content(self, vision_analysis: Dict, original_title: str, num_frames: int) -> Dict:
        """Generate optimized content based on vision analysis"""
        try:
            print(f"📝 Generating optimized content based on {num_frames}-frame analysis...")
            
            # Create detailed prompt based on analysis depth
            detail_level = "detailed" if num_frames >= 5 else "standard"
            
            prompt = f"""
            Create optimized YouTube content based on this {detail_level} visual analysis:
            
            Analysis Summary:
            - Content Type: {vision_analysis.get('visual_content_type', 'unknown')}
            - Main Subjects: {vision_analysis.get('main_subjects', 'unknown')}
            - Actions: {vision_analysis.get('actions_happening', 'unknown')}
            - Mood: {vision_analysis.get('emotional_tone', 'unknown')}
            - Setting: {vision_analysis.get('scene_setting', 'unknown')}
            
            Full Analysis: {json.dumps(vision_analysis, indent=2)[:1500]}...
            
            Original Title: "{original_title}"
            
            Generate optimized content with:
            1. optimized_title: (YouTube-perfect title, max 60 chars, compelling emojis)
            2. optimized_description: (engaging 2-3 sentence description with call-to-action)
            3. optimized_tags: (20 highly relevant tags for maximum reach)
            4. thumbnail_suggestions: (3 specific thumbnail ideas based on visual content)
            5. viral_potential_score: (1-10 with reasoning)
            6. best_posting_time: (suggested posting strategy)
            7. target_keywords: (SEO keywords to include)
            8. content_category: (YouTube category recommendation)
            
            Make it highly engaging and optimized for the YouTube algorithm.
            Return only valid JSON.
            """
            
            response = self.client.chat.completions.create(
                model=self.text_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.8
            )
            
            # Calculate cost (GPT-3.5-turbo pricing)
            input_tokens = len(prompt) // 4
            output_tokens = len(response.choices[0].message.content) // 4
            optimization_cost = (input_tokens * 0.0015 + output_tokens * 0.002) / 1000
            
            self.total_cost += optimization_cost
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                result = {
                    "optimized_title": f"🔥 {original_title[:50]}",
                    "optimized_description": "Amazing content that you won't want to miss!",
                    "optimized_tags": ["shorts", "viral", "trending", "entertainment"],
                    "viral_potential_score": 7
                }
            
            result["optimization_cost"] = optimization_cost
            print(f"💰 Content optimization cost: ${optimization_cost:.4f}")
            
            return result
            
        except Exception as e:
            print(f"❌ Content optimization failed: {e}")
            return {
                "optimized_title": f"🔥 {original_title[:50]}",
                "optimized_description": "Amazing video content!",
                "optimized_tags": ["shorts", "viral", "trending"],
                "optimization_cost": 0,
                "error": str(e)
            }
    
    def analyze_video_with_frames(self, video_path: str, num_frames: int, original_title: str = "Test Video") -> Dict:
        """Complete analysis with specified number of frames"""
        print(f"\n{'='*80}")
        print(f"🎬 ANALYZING WITH {num_frames} FRAME{'S' if num_frames > 1 else ''}")
        print(f"{'='*80}")
        
        session_start_cost = self.total_cost
        
        # Extract frames
        frames_b64 = self.extract_frames(video_path, num_frames)
        if not frames_b64:
            return {"error": f"Could not extract {num_frames} frames from video"}
        
        # Vision analysis
        vision_result = self.analyze_frames_with_vision(frames_b64, original_title, num_frames)
        if "error" in vision_result:
            return vision_result
        
        # Content optimization
        optimized_content = self.generate_optimized_content(vision_result, original_title, num_frames)
        
        # Calculate session cost
        session_cost = self.total_cost - session_start_cost
        
        # Combine results
        final_result = {
            **vision_result,
            **optimized_content,
            "frames_used": num_frames,
            "original_title": original_title,
            "session_cost": session_cost,
            "total_cost_so_far": self.total_cost,
            "analysis_method": f"gpt-4o-vision-{num_frames}frames"
        }
        
        # Store in history
        self.analysis_history.append({
            "frames": num_frames,
            "cost": session_cost,
            "quality_score": vision_result.get('confidence_score', 0),
            "viral_score": optimized_content.get('viral_potential_score', 0),
            "title": optimized_content.get('optimized_title', 'N/A')
        })
        
        return final_result
    
    def print_detailed_results(self, result: Dict, frame_count: int):
        """Print comprehensive analysis results"""
        if "error" in result:
            print(f"❌ Analysis failed: {result['error']}")
            return
        
        print(f"\n🎯 DETAILED RESULTS ({frame_count} frame{'s' if frame_count > 1 else ''}):")
        print(f"├── 💰 Cost: ${result.get('session_cost', 0):.4f}")
        print(f"├── 🎨 Content Type: {result.get('visual_content_type', 'N/A')}")
        print(f"├── 📝 Optimized Title: {result.get('optimized_title', 'N/A')}")
        print(f"├── 🎯 Main Subjects: {result.get('main_subjects', 'N/A')[:100]}{'...' if len(str(result.get('main_subjects', ''))) > 100 else ''}")
        print(f"├── 🎬 Actions: {result.get('actions_happening', 'N/A')[:100]}{'...' if len(str(result.get('actions_happening', ''))) > 100 else ''}")
        print(f"├── 🎭 Emotional Tone: {result.get('emotional_tone', 'N/A')}")
        print(f"├── 🏞️ Setting: {result.get('scene_setting', 'N/A')}")
        print(f"├── 🎨 Colors/Mood: {result.get('colors_mood', 'N/A')[:80]}{'...' if len(str(result.get('colors_mood', ''))) > 80 else ''}")
        print(f"├── 📊 Confidence: {result.get('confidence_score', 0):.2f}")
        print(f"├── 🔥 Viral Score: {result.get('viral_potential_score', 'N/A')}/10")
        print(f"├── ⏱️ Analysis Time: {result.get('analysis_time', 0):.1f}s")
        print(f"└── 🏷️ Top Tags: {', '.join((result.get('optimized_tags', []))[:5])}")
        
        # Show cost breakdown
        print(f"\n💵 Cost Breakdown:")
        print(f"├── Images ({frame_count}): ${result.get('image_cost', 0):.4f}")
        print(f"├── Text Processing: ${result.get('text_cost', 0):.4f}")
        print(f"├── Content Optimization: ${result.get('optimization_cost', 0):.4f}")
        print(f"└── Total: ${result.get('session_cost', 0):.4f}")
    
    def print_comparison_summary(self):
        """Print final comparison of all frame counts"""
        if len(self.analysis_history) < 2:
            return
        
        print(f"\n{'='*80}")
        print("🏆 COMPREHENSIVE COMPARISON SUMMARY")
        print(f"{'='*80}")
        
        print(f"{'Frames':<8} {'Cost':<10} {'Quality':<10} {'Viral':<8} {'Title Preview':<40}")
        print("-" * 80)
        
        for analysis in self.analysis_history:
            frames = analysis['frames']
            cost = f"${analysis['cost']:.4f}"
            quality = f"{analysis['quality_score']:.2f}"
            viral = f"{analysis['viral_score']}/10" if analysis['viral_score'] else "N/A"
            title = analysis['title'][:35] + "..." if len(analysis['title']) > 35 else analysis['title']
            
            print(f"{frames:<8} {cost:<10} {quality:<10} {viral:<8} {title:<40}")
        
        # Cost analysis
        print(f"\n📊 SCALING PROJECTIONS:")
        print(f"{'Frames':<8} {'Per 10':<12} {'Per 100':<12} {'Per 1000':<12}")
        print("-" * 50)
        
        for analysis in self.analysis_history:
            frames = analysis['frames']
            cost = analysis['cost']
            print(f"{frames:<8} ${cost*10:<11.2f} ${cost*100:<11.2f} ${cost*1000:<11.2f}")
        
        # Quality vs Cost analysis
        print(f"\n🎯 QUALITY VS COST ANALYSIS:")
        if len(self.analysis_history) >= 2:
            base_analysis = self.analysis_history[0]  # Assume first is lowest frame count
            
            for i, analysis in enumerate(self.analysis_history[1:], 1):
                cost_increase = ((analysis['cost'] - base_analysis['cost']) / base_analysis['cost']) * 100
                quality_increase = ((analysis['quality_score'] - base_analysis['quality_score']) / base_analysis['quality_score']) * 100 if base_analysis['quality_score'] > 0 else 0
                
                print(f"├── {analysis['frames']} vs {base_analysis['frames']} frames:")
                print(f"│   Cost increase: +{cost_increase:.0f}%")
                print(f"│   Quality increase: +{quality_increase:.0f}%")
                print(f"│   Value ratio: {quality_increase/cost_increase if cost_increase > 0 else 0:.2f}")
        
        print(f"\n💡 RECOMMENDATION:")
        # Find best value (quality per dollar)
        best_value = max(self.analysis_history, key=lambda x: (x['quality_score'] * x['viral_score']) / x['cost'] if x['cost'] > 0 else 0)
        print(f"├── Best value: {best_value['frames']} frames (${best_value['cost']:.4f})")
        
        # Find highest quality
        highest_quality = max(self.analysis_history, key=lambda x: x['quality_score'])
        print(f"├── Highest quality: {highest_quality['frames']} frames (confidence: {highest_quality['quality_score']:.2f})")
        
        # Find cheapest
        cheapest = min(self.analysis_history, key=lambda x: x['cost'])
        print(f"└── Most economical: {cheapest['frames']} frames (${cheapest['cost']:.4f})")

def main():
    """Main testing function"""
    print("🧪 COMPREHENSIVE FRAME ANALYSIS COMPARISON")
    print("=" * 80)
    print("⚠️  This will test 1, 5, and 15 frames - estimated cost: $0.40-0.70")
    print("=" * 80)
    
    # Get API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return
    
    # Find video file
    video_files = []
    test_dirs = ["temp", "channels_processed", "processed_videos"]
    
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            for root, dirs, files in os.walk(test_dir):
                for file in files:
                    if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                        video_files.append(os.path.join(root, file))
    
    if not video_files:
        print("❌ No video files found in temp/, channels_processed/, or processed_videos/")
        print("💡 Please run your main script first to download some videos")
        return
    
    video_path = video_files[0]
    print(f"🎯 Testing with video: {video_path}")
    
    # Confirm before proceeding
    confirm = input(f"\nContinue with comprehensive analysis? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Test cancelled.")
        return
    
    # Initialize analyzer
    analyzer = ComprehensiveVideoAnalyzer(api_key)
    
    # Test different frame counts
    frame_counts = [1, 5, 15]
    
    print(f"\n🚀 Starting analysis of {len(frame_counts)} different frame counts...")
    
    for frame_count in frame_counts:
        try:
            result = analyzer.analyze_video_with_frames(
                video_path, 
                frame_count, 
                f"Comprehensive test with {frame_count} frames"
            )
            
            analyzer.print_detailed_results(result, frame_count)
            
            # Small delay to avoid rate limiting
            if frame_count != frame_counts[-1]:  # Don't delay after last analysis
                print("\n⏱️ Waiting 2 seconds to avoid rate limiting...")
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Failed to analyze with {frame_count} frames: {e}")
            continue
    
    # Print comprehensive comparison
    analyzer.print_comparison_summary()
    
    print(f"\n🏁 ANALYSIS COMPLETE!")
    print(f"💰 Total cost for all tests: ${analyzer.total_cost:.4f}")
    print(f"📊 Tested {len(frame_counts)} different frame configurations")

if __name__ == "__main__":
    main()
