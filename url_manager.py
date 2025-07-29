#!/usr/bin/env python3
"""
URL Manager - Gestion des URLs TikTok avec métadonnées
====================================================
Format du fichier URLs:
url | titre_custom | background_mode | priority | custom_description
"""

import csv
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

class URLManager:
    def __init__(self, database_path="database/videos_status.json"):
        self.database_path = database_path
        self.ensure_database()
    
    def ensure_database(self):
        """Crée la base de données si elle n'existe pas"""
        Path(self.database_path).parent.mkdir(exist_ok=True)
        if not os.path.exists(self.database_path):
            with open(self.database_path, 'w') as f:
                json.dump({"videos": {}, "batches": {}}, f, indent=2)
    
    def parse_url_file(self, file_path: str) -> List[Dict]:
        """Parse un fichier d'URLs avec métadonnées"""
        videos = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parse format: url | titre | background | priority | description
                parts = [p.strip() for p in line.split('|')]
                
                video_data = {
                    'url': parts[0] if len(parts) > 0 else '',
                    'custom_title': parts[1] if len(parts) > 1 and parts[1] else None,
                    'background_mode': parts[2] if len(parts) > 2 and parts[2] else 'random',
                    'priority': parts[3] if len(parts) > 3 and parts[3] else 'normal',
                    'custom_description': parts[4] if len(parts) > 4 and parts[4] else None,
                    'line_number': line_num,
                    'source_file': file_path,
                    'status': 'pending'
                }
                
                if video_data['url']:
                    videos.append(video_data)
        
        return videos
    
    def create_example_url_file(self, filename="urls_input/example_batch.txt"):
        """Crée un fichier d'exemple"""
        example_content = """# Format: URL | Titre Custom | Background Mode | Priority | Description Custom
# Background modes: random, blur, solid, gradient, specific, same_for_all
# Priority: high, normal, low

https://www.tiktok.com/@user/video/123 | Mon Super Titre | random | high | Description personnalisée pour cette vidéo
https://www.tiktok.com/@user/video/456 | | blur | normal | 
https://www.tiktok.com/@user/video/789 | Titre Anime | specific | high | Contenu anime épique !

# Ligne avec juste l'URL (utilise les defaults)
https://www.tiktok.com/@user/video/999
"""
        
        Path(filename).parent.mkdir(exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(example_content)
        
        print(f"✅ Fichier d'exemple créé: {filename}")
    
    def load_database(self) -> Dict:
        """Charge la base de données"""
        with open(self.database_path, 'r') as f:
            return json.load(f)
    
    def save_database(self, data: Dict):
        """Sauvegarde la base de données"""
        with open(self.database_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add_batch(self, batch_name: str, videos: List[Dict]):
        """Ajoute un batch de vidéos à la base"""
        db = self.load_database()
        
        # Crée le batch
        batch_id = f"{batch_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        db['batches'][batch_id] = {
            'name': batch_name,
            'created_at': datetime.now().isoformat(),
            'total_videos': len(videos),
            'status': 'pending'
        }
        
        # Ajoute les vidéos
        for video in videos:
            video_id = f"{batch_id}_{video['line_number']}"
            video['batch_id'] = batch_id
            video['video_id'] = video_id
            video['added_at'] = datetime.now().isoformat()
            
            db['videos'][video_id] = video
        
        self.save_database(db)
        print(f"✅ Batch '{batch_name}' ajouté avec {len(videos)} vidéos")
        return batch_id
    
    def get_pending_videos(self, limit: Optional[int] = None) -> List[Dict]:
        """Récupère les vidéos en attente"""
        db = self.load_database()
        pending = [v for v in db['videos'].values() if v['status'] == 'pending']
        
        # Tri par priorité
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        pending.sort(key=lambda x: priority_order.get(x['priority'], 1))
        
        return pending[:limit] if limit else pending
    
    def update_video_status(self, video_id: str, status: str, **kwargs):
        """Met à jour le statut d'une vidéo"""
        db = self.load_database()
        if video_id in db['videos']:
            db['videos'][video_id]['status'] = status
            db['videos'][video_id]['updated_at'] = datetime.now().isoformat()
            for key, value in kwargs.items():
                db['videos'][video_id][key] = value
            self.save_database(db)
    
    def get_status_summary(self) -> Dict:
        """Résumé des statuts"""
        db = self.load_database()
        statuses = {}
        for video in db['videos'].values():
            status = video['status']
            statuses[status] = statuses.get(status, 0) + 1
        return statuses

# Exemple d'utilisation
if __name__ == "__main__":
    manager = URLManager()
    
    # Crée un fichier d'exemple
    manager.create_example_url_file()
    
    print("URL Manager initialisé ✅")
    print("Structure créée:")
    print("- database/videos_status.json")
    print("- urls_input/example_batch.txt")
    print("\n📝 Édite le fichier example_batch.txt avec tes URLs TikTok")