import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta
import openai
from collections import Counter, defaultdict
import json
import asyncio

from app.core.config import settings
from app.models import User, Content, Scan, Favorite, UserActivity, Playlist
from app.services.audio.spotify_client import SpotifyClient
from app.services.vision.tmdb_client import TMDBClient

class RecommendationEngine:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self.spotify_client = SpotifyClient()
        self.tmdb_client = TMDBClient()
    
    async def get_personalized_recommendations(
        self,
        user: User,
        db: Session,
        limit: int = 10,
        content_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Génère des recommandations personnalisées pour un utilisateur
        """
        # Récupérer l'historique de l'utilisateur
        user_history = self._get_user_history(user, db)
        
        if not user_history:
            # Nouvel utilisateur : recommandations populaires
            return await self._get_popular_recommendations(db, limit, content_type)
        
        # 1. Recommandations basées sur le contenu
        content_based = await self._content_based_recommendations(
            user_history, db, limit//2, content_type
        )
        
        # 2. Recommandations collaboratives
        collaborative = await self._collaborative_recommendations(
            user, user_history, db, limit//2, content_type
        )
        
        # 3. Recommandations des APIs externes (Spotify/TMDB)
        external = await self._external_api_recommendations(
            user_history, db, limit//3
        )
        
        # Fusionner et dédupliquer
        all_recs = content_based + collaborative + external
        recommendations = self._merge_recommendations(all_recs, limit)
        
        # Ajouter les raisons
        recommendations = await self._enhance_with_reasons(recommendations, user_history)
        
        return recommendations
    
    def _get_user_history(self, user: User, db: Session) -> List[Dict]:
        """
        Récupère l'historique complet de l'utilisateur avec pondération
        """
        # Récupérer les favoris (poids 3)
        favorites = db.query(Favorite)\
            .filter(Favorite.user_id == user.user_id)\
            .order_by(desc(Favorite.created_at))\
            .limit(50)\
            .all()
        
        # Récupérer les scans récents (poids 2)
        recent_scans = db.query(Scan)\
            .filter(Scan.scan_user == user.user_id)\
            .filter(Scan.recognized_content_id.isnot(None))\
            .order_by(desc(Scan.scan_date))\
            .limit(100)\
            .all()
        
        # Récupérer les activités (poids 1)
        activities = db.query(UserActivity)\
            .filter(UserActivity.user_id == user.user_id)\
            .filter(UserActivity.content_id.isnot(None))\
            .order_by(desc(UserActivity.created_at))\
            .limit(200)\
            .all()
        
        # Récupérer les playlists
        playlists = db.query(Playlist)\
            .filter(Playlist.user_id == user.user_id)\
            .all()
        
        history = []
        content_weights = {}
        
        # Ajouter les favoris (poids 3)
        for fav in favorites:
            if fav.content_id not in content_weights:
                content_weights[fav.content_id] = 3
                content = db.query(Content).filter(Content.content_id == fav.content_id).first()
                if content:
                    history.append({
                        "content": content,
                        "type": "favorite",
                        "date": fav.created_at,
                        "weight": 3
                    })
        
        # Ajouter les scans (poids 2)
        for scan in recent_scans:
            if scan.recognized_content_id not in content_weights:
                content_weights[scan.recognized_content_id] = 2
                content = db.query(Content).filter(Content.content_id == scan.recognized_content_id).first()
                if content:
                    history.append({
                        "content": content,
                        "type": "scan",
                        "date": scan.scan_date,
                        "weight": 2
                    })
        
        # Ajouter les activités (poids 1)
        for activity in activities:
            if activity.content_id and activity.content_id not in content_weights:
                content_weights[activity.content_id] = 1
                content = db.query(Content).filter(Content.content_id == activity.content_id).first()
                if content:
                    history.append({
                        "content": content,
                        "type": "activity",
                        "date": activity.created_at,
                        "weight": 1
                    })
        
        # Ajouter les contenus des playlists
        for playlist in playlists:
            for content in playlist.contents:
                if content.content_id not in content_weights:
                    content_weights[content.content_id] = 1.5
                    history.append({
                        "content": content,
                        "type": "playlist",
                        "date": playlist.updated_at,
                        "weight": 1.5
                    })
        
        # Trier par date et poids
        history.sort(key=lambda x: (x["date"], x["weight"]), reverse=True)
        
        return history
    
    async def _content_based_recommendations(
        self,
        user_history: List[Dict],
        db: Session,
        limit: int,
        content_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Recommandations basées sur le contenu similaire
        """
        # Analyser les préférences de l'utilisateur
        type_counter = Counter()
        artist_counter = Counter()
        genre_counter = Counter()
        
        for item in user_history[:20]:
            content = item["content"]
            type_counter[content.content_type] += item["weight"]
            
            if content.content_artist:
                artist_counter[content.content_artist] += item["weight"]
            
            if content.metadata and "genres" in content.metadata:
                for genre in content.metadata["genres"]:
                    genre_counter[genre] += item["weight"]
        
        # Obtenir les types, artistes et genres préférés
        preferred_type = type_counter.most_common(1)[0][0] if type_counter else "music"
        preferred_artists = [a for a, _ in artist_counter.most_common(3)]
        preferred_genres = [g for g, _ in genre_counter.most_common(3)]
        
        # Construire la requête
        query = db.query(Content)
        
        if content_type:
            query = query.filter(Content.content_type == content_type)
        else:
            query = query.filter(Content.content_type == preferred_type)
        
        # Exclure les contenus déjà vus
        seen_ids = [item["content"].content_id for item in user_history]
        if seen_ids:
            query = query.filter(~Content.content_id.in_(seen_ids))
        
        # Trier par pertinence
        recommendations = query\
            .order_by(func.random())\
            .limit(limit * 2)\
            .all()
        
        result = []
        for content in recommendations:
            score = 0
            
            # Bonus pour les artistes préférés
            if content.content_artist in preferred_artists:
                score += 0.5
            
            # Bonus pour les genres similaires
            if content.metadata and "genres" in content.metadata:
                for genre in content.metadata["genres"]:
                    if genre in preferred_genres:
                        score += 0.3
            
            result.append({
                "content": content,
                "score": score,
                "reason": "Basé sur vos préférences"
            })
        
        # Trier par score
        result.sort(key=lambda x: x["score"], reverse=True)
        
        return result[:limit]
    
    async def _collaborative_recommendations(
        self,
        user: User,
        user_history: List[Dict],
        db: Session,
        limit: int,
        content_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Recommandations basées sur les utilisateurs similaires
        """
        # Obtenir les IDs des contenus préférés
        preferred_content_ids = [item["content"].content_id for item in user_history[:20]]
        
        if not preferred_content_ids:
            return []
        
        # Trouver les utilisateurs qui ont aimé les mêmes contenus
        similar_users = db.query(Favorite.user_id, func.count(Favorite.content_id).label('count'))\
            .filter(Favorite.content_id.in_(preferred_content_ids))\
            .filter(Favorite.user_id != user.user_id)\
            .group_by(Favorite.user_id)\
            .order_by(desc('count'))\
            .limit(20)\
            .all()
        
        recommendations = []
        seen_ids = set([item["content"].content_id for item in user_history])
        
        for similar_user_id, _ in similar_users:
            # Récupérer les favoris de l'utilisateur similaire
            their_favorites = db.query(Favorite)\
                .filter(Favorite.user_id == similar_user_id)\
                .filter(~Favorite.content_id.in_(seen_ids))\
                .limit(10)\
                .all()
            
            for fav in their_favorites:
                content = db.query(Content).filter(Content.content_id == fav.content_id).first()
                if content and (not content_type or content.content_type == content_type):
                    recommendations.append({
                        "content": content,
                        "score": 0.7,
                        "reason": "Recommandé par des utilisateurs avec des goûts similaires"
                    })
                    seen_ids.add(content.content_id)
        
        return recommendations[:limit]
    
    async def _external_api_recommendations(
        self,
        user_history: List[Dict],
        db: Session,
        limit: int
    ) -> List[Dict]:
        """
        Recommandations des APIs externes (Spotify, TMDB)
        """
        recommendations = []
        
        # Séparer par type
        music_contents = [item for item in user_history 
                         if item["content"].content_type == "music"][:3]
        movie_contents = [item for item in user_history 
                         if item["content"].content_type in ["movie", "tv_show"]][:3]
        
        # Recommandations Spotify
        if music_contents and self.spotify_client:
            spotify_ids = [item["content"].spotify_id for item in music_contents 
                          if item["content"].spotify_id]
            if spotify_ids:
                spotify_recs = await self.spotify_client.get_recommendations(
                    spotify_ids[:5], limit=limit//2
                )
                
                for rec in spotify_recs:
                    # Vérifier si le contenu existe déjà
                    existing = db.query(Content)\
                        .filter(Content.spotify_id == rec['spotify_id'])\
                        .first()
                    
                    if existing:
                        recommendations.append({
                            "content": existing,
                            "score": 0.8,
                            "reason": "Recommandé par Spotify"
                        })
        
        # Recommandations TMDB
        if movie_contents and self.tmdb_client:
            tmdb_ids = [item["content"].tmdb_id for item in movie_contents 
                       if item["content"].tmdb_id]
            if tmdb_ids:
                for tmdb_id in tmdb_ids[:2]:
                    tmdb_recs = await self.tmdb_client.get_recommendations(tmdb_id, limit=limit//2)
                    
                    for rec in tmdb_recs:
                        existing = db.query(Content)\
                            .filter(Content.tmdb_id == rec['tmdb_id'])\
                            .first()
                        
                        if existing:
                            recommendations.append({
                                "content": existing,
                                "score": 0.8,
                                "reason": "Recommandé par TMDB"
                            })
        
        return recommendations
    
    async def _get_popular_recommendations(
        self,
        db: Session,
        limit: int,
        content_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Recommandations populaires pour les nouveaux utilisateurs
        """
        # Contenus les plus scannés
        query = db.query(Content)\
            .join(Scan)\
            .group_by(Content.content_id)\
            .order_by(desc(func.count(Scan.scan_id)))
        
        if content_type:
            query = query.filter(Content.content_type == content_type)
        
        popular = query.limit(limit).all()
        
        return [{
            "content": content,
            "score": 1.0,
            "reason": "Populaire cette semaine"
        } for content in popular]
    
    def _merge_recommendations(
        self,
        recommendations: List[Dict],
        limit: int
    ) -> List[Dict]:
        """
        Fusionne et déduplique les recommandations
        """
        seen = set()
        merged = []
        
        for rec in recommendations:
            content_id = rec["content"].content_id
            if content_id not in seen:
                seen.add(content_id)
                merged.append(rec)
        
        # Trier par score
        merged.sort(key=lambda x: x["score"], reverse=True)
        
        return merged[:limit]
    
    async def _enhance_with_reasons(
        self,
        recommendations: List[Dict],
        user_history: List[Dict]
    ) -> List[Dict]:
        """
        Ajoute des raisons personnalisées aux recommandations
        """
        for rec in recommendations:
            content = rec["content"]
            
            # Vérifier les similarités avec l'historique
            similar_contents = []
            for hist in user_history[:10]:
                hist_content = hist["content"]
                
                if hist_content.content_type == content.content_type:
                    if content.content_artist and hist_content.content_artist == content.content_artist:
                        similar_contents.append(f"du même artiste ({hist_content.content_artist})")
                    elif content.metadata and hist_content.metadata:
                        # Comparer les genres
                        hist_genres = hist_content.metadata.get("genres", [])
                        content_genres = content.metadata.get("genres", [])
                        common_genres = set(hist_genres) & set(content_genres)
                        if common_genres:
                            similar_contents.append(f"du même genre ({', '.join(common_genres)})")
            
            if similar_contents:
                rec["reason"] = f"Similaire à ce que vous avez aimé: {similar_contents[0]}"
        
        return recommendations
    
    async def get_ai_chat_recommendation(
        self,
        user_query: str,
        user: User,
        db: Session
    ) -> Dict[str, Any]:
        """
        Utilise GPT pour des recommandations conversationnelles
        """
        # Récupérer l'historique récent de l'utilisateur
        recent_history = self._get_user_history(user, db)[:10]
        
        # Récupérer les préférences
        preferences = user.preferences or {}
        
        # Préparer le contexte
        context = "Historique récent de l'utilisateur:\n"
        for item in recent_history:
            content = item["content"]
            context += f"- {content.content_title} ({content.content_type})"
            if content.content_artist:
                context += f" par {content.content_artist}"
            context += "\n"
        
        if preferences:
            context += f"\nPréférences: {json.dumps(preferences, indent=2)}\n"
        
        # Appel à GPT
        response = self.openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """Tu es un expert en recommandations de films, musiques, séries et livres.
                Analyse l'historique et la requête de l'utilisateur pour recommander des contenus pertinents.
                Pour chaque recommandation, donne:
                - Le titre
                - Le type (film, musique, série, livre)
                - L'artiste/réalisateur
                - Une brève description
                - Pourquoi ça pourrait plaire à l'utilisateur
                
                Formate ta réponse en JSON avec une liste de recommandations."""},
                {"role": "user", "content": f"{context}\n\nRequête: {user_query}"}
            ],
            temperature=0.7,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        try:
            recommendations = json.loads(response.choices[0].message.content)
        except:
            recommendations = {
                "recommendations": [{
                    "title": "Désolé, je n'ai pas pu analyser votre demande",
                    "type": "error"
                }]
            }
        
        return {
            "recommendations": recommendations,
            "source": "gpt-4"
        }