#!/usr/bin/env python3
"""
AI Tags Generator - Intelligent content analysis for TikTok videos
================================================================
Uses cloud AI (Gemini) for advanced video analysis and optimization
"""

import os
import json
import random
from typing import Dict, List
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, use manual loading
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

try:
    from gemini_ai_generator import GeminiAIGenerator
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini AI not available")

try:
    from openai_ai_generator import OpenAIGenerator
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not available")

class AITagsGenerator:
    def __init__(self, api_key: str = None, openai_key: str = None, preferred_provider: str = "gemini"):
        """Initialize AI generator with multiple providers"""
        self.gemini_key = api_key or os.getenv('GEMINI_API_KEY')
        self.openai_key = openai_key or os.getenv('OPENAI_API_KEY')
        self.preferred_provider = preferred_provider.lower()
        
        # Initialize providers
        self.gemini_ai = None
        self.openai_ai = None
        self.use_gemini = False
        self.use_openai = False
        
        # Try to initialize Gemini AI
        if GEMINI_AVAILABLE and self.gemini_key:
            try:
                self.gemini_ai = GeminiAIGenerator(self.gemini_key)
                if self.gemini_ai.test_api_connection():
                    self.use_gemini = True
                    print("✅ Gemini AI initialized successfully")
                else:
                    print("⚠️ Gemini API connection failed")
            except Exception as e:
                print(f"⚠️ Gemini AI initialization failed: {e}")
        
        # Try to initialize OpenAI
        if OPENAI_AVAILABLE and self.openai_key:
            try:
                self.openai_ai = OpenAIGenerator(self.openai_key)
                if self.openai_ai.test_api_connection():
                    self.use_openai = True
                    print("✅ OpenAI initialized successfully")
                else:
                    print("⚠️ OpenAI API connection failed")
            except Exception as e:
                print(f"⚠️ OpenAI initialization failed: {e}")
        
        # Show available providers
        providers = []
        if self.use_gemini: providers.append("Gemini")
        if self.use_openai: providers.append("OpenAI") 
        providers.append("Local AI")
        
        print(f"🤖 Available AI providers: {' → '.join(providers)}")
        
        if not self.use_gemini and not self.use_openai:
            print("⚠️ No cloud AI providers available, using local AI only")
        
        # Fallback basic AI data
        self.basic_categories = {
            'anime': {
                'keywords': ['anime', 'manga', 'otaku', 'kawaii', 'senpai', 'waifu', 'cosplay'],
                'titles': [
                    'Epic Anime Moment That Will Blow Your Mind! 🔥',
                    'This Anime Scene Hit Different 😭',
                    'POV: You See This Anime Character ✨',
                    'Anime Fans Will Understand This 💯'
                ],
                'tags': ['anime', 'manga', 'otaku', 'animation', 'viral anime', 'anime shorts']
            },
            'gaming': {
                'keywords': ['gaming', 'gamer', 'gameplay', 'streamer', 'esports', 'pro'],
                'titles': [
                    'Insane Gaming Skills That Broke The Internet! 🎮',
                    'This Gaming Moment Was UNREAL 🔥',
                    'You Won\'t Believe This Gaming Clip 🤯',
                    'Gaming Skills That Made Me Question Everything 💯'
                ],
                'tags': ['gaming', 'gamer', 'gameplay', 'gaming moments', 'pro gaming', 'esports']
            },
            'entertainment': {
                'keywords': ['funny', 'comedy', 'entertainment', 'viral', 'trending'],
                'titles': [
                    'This Will Make Your Day Better! 😂',
                    'You Won\'t Believe What Happens Next 🤯',
                    'The Video That Broke The Internet 🔥',
                    'Everyone Needs To See This ✨'
                ],
                'tags': ['entertainment', 'funny', 'comedy', 'viral', 'trending', 'must watch']
            }
        }
        
        self.viral_tags = [
            'shorts', 'viral', 'trending', 'tiktok', 'entertainment', 'funny', 
            'amazing', 'must watch', 'viral video', 'short video', 'youtube shorts'
        ]

    def generate_ai_content(self, video_data: Dict) -> Dict:
        """Generate AI-enhanced content using multiple providers with fallback"""
        
        video_path = video_data.get('processed_video_path', '')
        original_title = video_data.get('title', '')
        
        # Determine provider order based on preference
        providers = []
        if self.preferred_provider == "openai" and self.use_openai:
            providers = ["openai", "gemini"]
        elif self.preferred_provider == "gemini" and self.use_gemini:
            providers = ["gemini", "openai"]
        else:
            # Default order: Gemini first (cheaper), then OpenAI
            if self.use_gemini: providers.append("gemini")
            if self.use_openai: providers.append("openai")
        
        # Try each provider in order
        for provider in providers:
            try:
                if provider == "gemini" and self.use_gemini and os.path.exists(video_path):
                    print(f"🤖 Using Gemini AI for video analysis...")
                    result = self.gemini_ai.generate_ai_data(video_path, original_title)
                    
                    if "error" not in result:
                        result['ai_provider'] = 'gemini-flash'
                        result['cost_estimate'] = 'Very low (< $0.01)'
                        print(f"✅ Gemini AI analysis complete with {result['confidence']*100:.0f}% confidence")
                        return result
                    else:
                        print(f"⚠️ Gemini AI failed: {result.get('error', 'Unknown error')}")
                
                elif provider == "openai" and self.use_openai and os.path.exists(video_path):
                    print(f"🤖 Using OpenAI for video analysis...")
                    result = self.openai_ai.generate_ai_data(video_path, original_title)
                    
                    if "error" not in result:
                        print(f"✅ OpenAI analysis complete with {result['confidence']*100:.0f}% confidence")
                        return result
                    else:
                        print(f"⚠️ OpenAI failed: {result.get('error', 'Unknown error')}")
                        
            except Exception as e:
                print(f"⚠️ {provider.title()} AI failed: {e}")
        
        # Final fallback to basic AI
        print("🔄 Using local AI fallback")
        return self.generate_basic_ai_content(video_data)
    
    def generate_basic_ai_content(self, video_data: Dict) -> Dict:
        """Basic AI content generation (fallback)"""
        original_title = video_data.get('title', '').lower()
        
        # Detect category from title
        category = 'entertainment'  # default
        for cat, data in self.basic_categories.items():
            if any(keyword in original_title for keyword in data['keywords'][:3]):
                category = cat
                break
        
        category_data = self.basic_categories.get(category, self.basic_categories['entertainment'])
        
        # Generate title
        ai_title = random.choice(category_data['titles'])
        
        # Generate description
        description = f"""🔥 {ai_title}

📱 From TikTok to YouTube - bringing you the best viral content!

🔔 SUBSCRIBE for more amazing videos!
👍 LIKE if you enjoyed this!
💬 COMMENT your thoughts!
📤 SHARE with friends!

#{category} #viral #trending #shorts #tiktok #entertainment"""
        
        # Generate tags
        tags = self.viral_tags + category_data['tags']
        tags = list(dict.fromkeys(tags))[:20]  # Remove duplicates, limit to 20
        
        return {
            'title': ai_title,
            'description': description,
            'tags': tags,
            'category': category,
            'confidence': 0.75,
            'analysis_timestamp': datetime.now().isoformat(),
            'optimization_score': random.randint(75, 85),
            'ai_provider': 'basic',
            'cost_estimate': 'Free'
        }

    def set_api_key(self, api_key: str):
        """Update Gemini API key and reinitialize"""
        self.api_key = api_key
        if GEMINI_AVAILABLE:
            try:
                self.gemini_ai = GeminiAIGenerator(api_key)
                if self.gemini_ai.test_api_connection():
                    self.use_gemini = True
                    print("✅ Gemini AI updated and connected")
                    return True
                else:
                    print("❌ Invalid API key or connection failed")
                    return False
            except Exception as e:
                print(f"❌ Failed to update Gemini AI: {e}")
                return False
        return False

    def get_api_status(self) -> Dict:
        """Get current API status and usage info"""
        return {
            'gemini_available': GEMINI_AVAILABLE,
            'gemini_active': self.use_gemini,
            'api_key_set': bool(self.api_key),
            'provider': 'gemini-flash' if self.use_gemini else 'basic',
            'cost_per_video': '< $0.01' if self.use_gemini else 'Free',
            'features': {
                'video_analysis': self.use_gemini,
                'visual_recognition': self.use_gemini,
                'advanced_optimization': self.use_gemini,
                'basic_content_generation': True
            }
        }

    # Legacy methods for backward compatibility
    def detect_content_type(self, title: str, description: str = "") -> str:
        """Détecte le type de contenu basé sur le titre/description"""
        text = f"{title} {description}".lower()
        
        # Mots-clés pour détecter le type
        keywords = {
            'anime': ['anime', 'manga', 'otaku', 'sololeveling', 'naruto', 'onepiece', 'dragonball'],
            'gaming': ['game', 'gaming', 'gameplay', 'gamer', 'level', 'boss', 'play'],
            'comedy': ['funny', 'laugh', 'humor', 'joke', 'lol', 'hilarious', 'comedy'],
            'lifestyle': ['life', 'daily', 'routine', 'lifestyle', 'vlog', 'day']
        }
        
        scores = {}
        for content_type, words in keywords.items():
            scores[content_type] = sum(1 for word in words if word in text)
        
        # Retourne le type avec le plus de matches, ou 'general' par défaut
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return 'general'
    
    def generate_tags_local(self, title: str, description: str = "", content_type: str = None) -> Dict:
        """Génère des tags sans API externe (méthode locale/gratuite)"""
        
        if not content_type:
            content_type = self.detect_content_type(title, description)
        
        # Use basic categories instead of content_templates
        category_data = self.basic_categories.get(content_type, self.basic_categories.get('entertainment', {}))
        base_tags = category_data.get('tags', [])
        
        # Extraction de mots-clés du titre
        title_keywords = self.extract_keywords_from_text(title)
        desc_keywords = self.extract_keywords_from_text(description) if description else []
        
        # Combine tout
        all_tags = base_tags + title_keywords + desc_keywords
        
        # Tags universels pour YouTube Shorts
        universal_tags = ['Shorts', 'TikTok', 'Viral', 'Trending', 'Entertainment']
        
        # Filtre et déduplique
        final_tags = list(dict.fromkeys(all_tags + universal_tags))[:15]  # Max 15 tags
        
        # Optimise le titre pour YouTube
        optimized_title = self.optimize_title_for_youtube(title)
        
        return {
            'tags': final_tags,
            'hashtags': ['#Shorts', '#Viral', f'#{content_type}'],
            'optimized_title': optimized_title,
            'content_type': content_type,
            'description_suggestions': self.generate_description_suggestions(content_type)
        }
    
    def extract_keywords_from_text(self, text: str) -> List[str]:
        """Extrait des mots-clés pertinents d'un texte"""
        if not text:
            return []
        
        import re
        # Nettoie le texte
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # Filtre les mots courts et communs
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        return keywords[:5]  # Max 5 mots-clés par texte
    
    def optimize_title_for_youtube(self, title: str) -> str:
        """Optimise le titre pour YouTube (SEO)"""
        import re
        # Nettoie le titre
        title = re.sub(r'[^\w\s!?-]', '', title)
        
        # Limite à 100 caractères
        if len(title) > 100:
            title = title[:97] + "..."
        
        # Ajoute des éléments accrocheurs si pas présents
        if not any(char in title for char in ['!', '?', '😱', '🔥']):
            title += " 🔥"
        
        return title
    
    def generate_description_suggestions(self, content_type: str) -> List[str]:
        """Génère des suggestions de description"""
        templates = {
            'anime': [
                "Contenu anime épique ! Abonne-toi pour plus d'animés 🔥",
                "Les meilleurs moments d'anime compilés ! #anime #manga",
                "Anime lovers, cette vidéo est pour vous ! 🎌"
            ],
            'gaming': [
                "Epic gaming moment ! Like si tu es gamer 🎮",
                "Les meilleurs fails/wins gaming 🔥 #gaming #gameplay",
                "Gamer life be like... Abonne-toi pour plus ! 🎯"
            ],
            'comedy': [
                "😂 Tu vas mourir de rire ! Partage à tes amis",
                "Humour du jour 🤣 Abonne-toi pour plus de fun !",
                "Quand la vie te fait rire... #comedy #funny"
            ],
            'general': [
                "Contenu viral du jour ! 🔥 Abonne-toi pour plus",
                "Tu as vu ça ? Partage en commentaire ! 💬",
                "Tendance TikTok à ne pas manquer ! #viral #trending"
            ]
        }
        
        return templates.get(content_type, templates['general'])
    
    def generate_tags_openai(self, title: str, description: str = "") -> Dict:
        """Génère des tags via OpenAI (nécessite API key)"""
        if not self.api_key:
            print("⚠️ Pas de clé API OpenAI, utilisation de la méthode locale")
            return self.generate_tags_local(title, description)
        
        # Implémentation OpenAI ici si besoin
        # Pour l'instant, utilise la méthode locale
        return self.generate_tags_local(title, description)
    
    def generate_tags(self, title: str, description: str = "", content_type: str = None) -> Dict:
        """Point d'entrée principal pour générer des tags"""
        try:
            # Always use local generation for now (legacy compatibility)
            return self.generate_tags_local(title, description, content_type)
        except Exception as e:
            print(f"❌ Erreur génération tags: {e}")
            # Fallback sur méthode locale simple
            return {
                'tags': ['shorts', 'viral', 'tiktok', 'trending', 'entertainment'],
                'hashtags': ['#Shorts', '#Viral'],
                'optimized_title': title + " 🔥",
                'content_type': 'general',
                'description_suggestions': ["Contenu viral du jour ! 🔥"]
            }

# Test du générateur
if __name__ == "__main__":
    generator = AITagsGenerator()
    
    # Test avec différents types de contenu
    test_cases = [
        ("Sung Jin Woo Epic Fight Solo Leveling", "Anime action epic moment"),
        ("Gaming Fail Compilation 2024", "Best gaming moments and fails"),
        ("Daily Life Routine Morning", "My morning routine lifestyle vlog")
    ]
    
    for title, desc in test_cases:
        result = generator.generate_tags(title, desc)
        print(f"\n🎬 Titre: {title}")
        print(f"📊 Type détecté: {result['content_type']}")
        print(f"🏷️ Tags: {', '.join(result['tags'])}")
        print(f"# Hashtags: {' '.join(result['hashtags'])}")
        print(f"✨ Titre optimisé: {result['optimized_title']}")