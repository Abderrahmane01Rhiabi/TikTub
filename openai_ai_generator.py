#!/usr/bin/env python3
"""
OpenAI Generator - Advanced AI content analysis using OpenAI GPT models
======================================================================
Provides enhanced video analysis, title generation, and content optimization
"""

import os
import json
from typing import Dict, List, Optional
import logging

try:
    import openai
    OPENAI_INSTALLED = True
except ImportError:
    OPENAI_INSTALLED = False
    print("⚠️ OpenAI library not installed. Run: pip install openai")

class OpenAIGenerator:
    """Advanced AI content generator using OpenAI GPT models"""
    
    def __init__(self, api_key: str):
        if not OPENAI_INSTALLED:
            raise ImportError("OpenAI library not installed")
        
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)
        self.model = "gpt-3.5-turbo"  # Use GPT-3.5-turbo for better cost efficiency
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def test_api_connection(self) -> bool:
        """Test if the OpenAI API connection works"""
        try:
            # Real API test
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            print("✅ OpenAI API connection successful!")
            return True
        except Exception as e:
            self.logger.error(f"OpenAI API test failed: {e}")
            print("⚠️ OpenAI API failed, using local AI fallback")
            return False
    
    def analyze_video_content(self, title: str, description: str = "", metadata: Dict = None) -> Dict:
        """Analyze video content using OpenAI for advanced insights"""
        try:
            # Create comprehensive prompt for analysis
            prompt = f"""
            Analyze this social media video content and provide detailed insights:
            
            Title: "{title}"
            Description: "{description}"
            Metadata: {json.dumps(metadata or {}, indent=2)}
            
            Please provide a JSON response with:
            1. content_type: (anime, gaming, comedy, dance, beauty, motivation, educational, entertainment, or general)
            2. target_audience: (age group and interests)
            3. engagement_potential: (high, medium, low) with reasoning
            4. recommended_tags: (array of 10-15 relevant tags)
            5. youtube_title: (optimized for YouTube, 60 chars max)
            6. youtube_description: (engaging description, 150 chars max)
            7. content_themes: (array of main themes/topics)
            8. viral_potential: (score 1-10 with explanation)
            
            Respond only with valid JSON.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.7
            )
            
            # Parse JSON response
            content = response.choices[0].message.content.strip()
            
            # Clean up response if it has markdown formatting
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content)
            
            # Ensure all required fields exist
            default_result = {
                "content_type": "general",
                "target_audience": "General audience",
                "engagement_potential": "medium",
                "recommended_tags": ["shorts", "viral", "trending"],
                "youtube_title": title[:60],
                "youtube_description": f"🔥 {title[:100]}...",
                "content_themes": ["entertainment"],
                "viral_potential": 5
            }
            
            # Merge with defaults
            for key, default_value in default_result.items():
                if key not in result:
                    result[key] = default_value
            
            return result
            
        except Exception as e:
            self.logger.error(f"OpenAI content analysis failed: {e}")
            # Return fallback analysis
            return {
                "content_type": "general",
                "target_audience": "General audience", 
                "engagement_potential": "medium",
                "recommended_tags": ["shorts", "viral", "trending", "entertainment"],
                "youtube_title": title[:60],
                "youtube_description": f"🔥 Amazing content you don't want to miss! {title[:80]}...",
                "content_themes": ["entertainment"],
                "viral_potential": 6
            }
    
    def generate_optimized_title(self, original_title: str, content_type: str = "general") -> str:
        """Generate an optimized YouTube title using OpenAI"""
        try:
            prompt = f"""
            Create an engaging YouTube Shorts title based on this original title:
            Original: "{original_title}"
            Content Type: {content_type}
            
            Requirements:
            - Maximum 60 characters
            - Include relevant emojis (1-2 max)
            - Make it clickable and engaging
            - Optimize for YouTube algorithm
            - Keep the essence of the original content
            
            Return only the optimized title, nothing else.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.8
            )
            
            optimized_title = response.choices[0].message.content.strip()
            
            # Remove quotes if present
            if optimized_title.startswith('"') and optimized_title.endswith('"'):
                optimized_title = optimized_title[1:-1]
            
            # Ensure length limit
            if len(optimized_title) > 60:
                optimized_title = optimized_title[:57] + "..."
            
            return optimized_title
            
        except Exception as e:
            self.logger.error(f"OpenAI title generation failed: {e}")
            # Fallback to enhanced version of original
            fallback = f"🔥 {original_title[:55]}"
            return fallback
    
    def generate_description(self, title: str, content_type: str = "general") -> str:
        """Generate an optimized YouTube description using OpenAI"""
        try:
            prompt = f"""
            Create an engaging YouTube Shorts description for this video:
            Title: "{title}"
            Content Type: {content_type}
            
            Requirements:
            - 2-3 sentences maximum
            - Include relevant emojis
            - Call to action (like, subscribe, comment)
            - Use trending keywords
            - Keep it under 200 characters
            
            Return only the description, nothing else.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.7
            )
            
            description = response.choices[0].message.content.strip()
            
            # Remove quotes if present
            if description.startswith('"') and description.endswith('"'):
                description = description[1:-1]
            
            return description
            
        except Exception as e:
            self.logger.error(f"OpenAI description generation failed: {e}")
            # Fallback description
            return f"🔥 {title} | Don't forget to LIKE and SUBSCRIBE for more amazing content! 🚀 #Shorts #Viral"
    
    def generate_tags(self, title: str, content_type: str = "general") -> List[str]:
        """Generate optimized tags using OpenAI"""
        try:
            prompt = f"""
            Generate YouTube tags for this video:
            Title: "{title}"
            Content Type: {content_type}
            
            Requirements:
            - 10-15 relevant tags
            - Mix of broad and specific tags
            - Include trending keywords
            - Consider YouTube algorithm preferences
            - Format as comma-separated list
            
            Return only the tags, nothing else.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.6
            )
            
            tags_text = response.choices[0].message.content.strip()
            
            # Parse tags
            tags = [tag.strip() for tag in tags_text.split(',')]
            
            # Clean up tags
            tags = [tag for tag in tags if tag and len(tag) > 2]
            
            # Ensure we have some basic tags
            base_tags = ["shorts", "viral", "trending"]
            for base_tag in base_tags:
                if base_tag not in [t.lower() for t in tags]:
                    tags.insert(0, base_tag)
            
            return tags[:15]  # Limit to 15 tags
            
        except Exception as e:
            self.logger.error(f"OpenAI tag generation failed: {e}")
            # Fallback tags
            return ["shorts", "viral", "trending", "entertainment", "youtube", "amazing", "must watch", "popular", "best", "awesome"]
    
    def detect_content_type(self, title: str, description: str = "") -> str:
        """Detect content type using OpenAI's advanced analysis"""
        try:
            prompt = f"""
            Analyze this content and determine its primary category:
            Title: "{title}"
            Description: "{description}"
            
            Choose ONE category from:
            anime, gaming, comedy, dance, beauty, motivation, educational, entertainment, sports, music, tech, food, travel, lifestyle, news, general
            
            Return only the category name, nothing else.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.3
            )
            
            content_type = response.choices[0].message.content.strip().lower()
            
            # Validate the response
            valid_types = ["anime", "gaming", "comedy", "dance", "beauty", "motivation", 
                          "educational", "entertainment", "sports", "music", "tech", "food", 
                          "travel", "lifestyle", "news", "general"]
            
            if content_type in valid_types:
                return content_type
            else:
                return "general"
                
        except Exception as e:
            self.logger.error(f"OpenAI content type detection failed: {e}")
            return "general"

    def generate_ai_data(self, video_path: str, original_title: str) -> Dict:
        """Generate comprehensive AI data for video - main method called by AI Tags Generator"""
        try:
            print("🤖 OpenAI analyzing video content...")
            
            # Use the existing methods to generate content
            content_type = self.detect_content_type(original_title)
            optimized_title = self.generate_optimized_title(original_title, content_type)
            description = self.generate_description(optimized_title, content_type)
            tags = self.generate_tags(optimized_title, content_type)
            
            # Comprehensive analysis
            analysis = self.analyze_video_content(original_title, description)
            
            return {
                'title': optimized_title,
                'description': description,
                'tags': tags,
                'content_type': content_type,
                'confidence': 0.95,  # High confidence for OpenAI
                'ai_provider': 'openai-gpt',
                'cost_estimate': 'Low (~$0.02)',
                'analysis': analysis,
                'viral_potential': analysis.get('viral_potential', 7),
                'target_audience': analysis.get('target_audience', 'General audience'),
                'engagement_potential': analysis.get('engagement_potential', 'high')
            }
            
        except Exception as e:
            self.logger.error(f"OpenAI generate_ai_data failed: {e}")
            return {
                'error': f'OpenAI API failed: {str(e)}',
                'title': f"🔥 {original_title[:55]}",
                'description': f"Amazing content from {original_title}! Like and subscribe!",
                'tags': ["shorts", "viral", "trending", "entertainment"],
                'content_type': 'general',
                'confidence': 0.3
            }

# Test function
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file
    
    # Test the OpenAI generator
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        generator = OpenAIGenerator(api_key)
        if generator.test_api_connection():
            print("✅ OpenAI connection successful!")
            
            # Test analysis
            result = generator.analyze_video_content(
                "Amazing anime fight scene compilation",
                "Epic battles from popular anime series"
            )
            print("📊 Analysis result:", json.dumps(result, indent=2))
        else:
            print("❌ OpenAI connection failed")
    else:
        print("❌ OPENAI_API_KEY not found in environment")
