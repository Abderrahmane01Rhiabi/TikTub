#!/usr/bin/env python3
"""
AI Tags Generator - Génère des tags et optimise les titres
========================================================
Supporte OpenAI et des alternatives locales/gratuites
"""

import re
import json
import requests
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class AITagsGenerator:
    def __init__(self, provider="local", api_key=None):
        self.provider = provider
        self.api_key = api_key
        
        # Templates pour différents types de contenu
        self.content_templates = {
            'anime': {
                'tags': ['anime', 'manga', 'otaku', 'animeedit', 'animelover'],
                'hashtags': ['#anime', '#manga', '#animeedit', '#viral']
            },
            'gaming': {
                'tags': ['gaming', 'gameplay', 'gamer', 'videogames'],
                'hashtags': ['#gaming', '#gameplay', '#gamer', '#viral']
            },
            'comedy': {
                'tags': ['funny', 'comedy', 'humor', 'laugh', 'entertainment'],
                'hashtags': ['#funny', '#comedy', '#viral', '#entertainment']
            },
            'lifestyle': {
                'tags': ['lifestyle', 'daily', 'vlog', 'life'],
                'hashtags': ['#lifestyle', '#daily', '#life', '#viral']
            }
        }
    
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
        
        # Tags de base selon le type de contenu
        base_tags = self.content_templates.get(content_type, {}).get('tags', [])
        hashtags = self.content_templates.get(content_type, {}).get('hashtags', [])
        
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
            'hashtags': hashtags + ['#Shorts', '#Viral'],
            'optimized_title': optimized_title,
            'content_type': content_type,
            'description_suggestions': self.generate_description_suggestions(content_type)
        }
    
    def extract_keywords_from_text(self, text: str) -> List[str]:
        """Extrait des mots-clés pertinents d'un texte"""
        if not text:
            return []
        
        # Nettoie le texte
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # Filtre les mots courts et communs
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        return keywords[:5]  # Max 5 mots-clés par texte
    
    def optimize_title_for_youtube(self, title: str) -> str:
        """Optimise le titre pour YouTube (SEO)"""
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
            logger.warning("Pas de clé API OpenAI, utilisation de la méthode locale")
            return self.generate_tags_local(title, description)
        
        # Implémentation OpenAI ici si besoin
        # Pour l'instant, utilise la méthode locale
        return self.generate_tags_local(title, description)
    
    def generate_tags(self, title: str, description: str = "", content_type: str = None) -> Dict:
        """Point d'entrée principal pour générer des tags"""
        try:
            if self.provider == "openai":
                return self.generate_tags_openai(title, description)
            else:
                return self.generate_tags_local(title, description, content_type)
        except Exception as e:
            logger.error(f"Erreur génération tags: {e}")
            # Fallback sur méthode locale
            return self.generate_tags_local(title, description, content_type)

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