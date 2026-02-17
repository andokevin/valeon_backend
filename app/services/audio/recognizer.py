import openai
from openai import OpenAI
import base64
import os
from typing import Optional, Dict, Any, List
import tempfile
import httpx
import asyncio
from app.core.config import settings
import librosa
import numpy as np
from app.services.audio.youtube_client import YouTubeClient  # AJOUT

class AudioRecognizer:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.audd_api_key = settings.AUDD_API_KEY
        self.spotify_client = None  # Sera initialisé séparément
        self.youtube_client = YouTubeClient()  # AJOUT
        
    async def recognize_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Reconnaît la musique à partir d'un fichier audio en utilisant plusieurs méthodes
        """
        results = {}
        
        # Méthode 1: AudD API (spécialisée musique)
        audd_result = await self._recognize_with_audd(file_path)
        if audd_result and audd_result.get('status') == 'success':
            results['audd'] = audd_result
        
        # Méthode 2: Whisper (transcription)
        whisper_result = await self._transcribe_with_whisper(file_path)
        if whisper_result:
            results['whisper'] = whisper_result
        
        # Méthode 3: Analyse audio locale
        audio_features = await self._extract_audio_features(file_path)
        if audio_features:
            results['features'] = audio_features
        
        # Fusionner et améliorer les résultats
        final_result = await self._merge_audio_results(results, file_path)
        
        return final_result
    
    async def _recognize_with_audd(self, file_path: str) -> Optional[Dict]:
        """Utilise AudD API pour la reconnaissance musicale"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {'api_token': self.audd_api_key}
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        'https://api.audd.io/',
                        files=files,
                        data=data
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('status') == 'success':
                            return {
                                'status': 'success',
                                'artist': result.get('result', {}).get('artist'),
                                'title': result.get('result', {}).get('title'),
                                'album': result.get('result', {}).get('album'),
                                'release_date': result.get('result', {}).get('release_date'),
                                'label': result.get('result', {}).get('label'),
                                'song_link': result.get('result', {}).get('song_link'),
                                'apple_music': result.get('result', {}).get('apple_music'),
                                'spotify': result.get('result', {}).get('spotify'),
                                'deezer': result.get('result', {}).get('deezer'),
                                'confidence': result.get('result', {}).get('score', 0) / 100
                            }
        except Exception as e:
            print(f"Erreur AudD: {e}")
        return None
    
    async def _transcribe_with_whisper(self, file_path: str) -> Optional[Dict]:
        """Transcription avec Whisper pour obtenir des indices"""
        try:
            with open(file_path, "rb") as audio_file:
                transcription = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            # Analyser la transcription pour trouver des indices sur la musique
            return {
                'transcription': transcription.text,
                'language': transcription.language,
                'duration': transcription.duration,
                'words': [{'word': w.word, 'start': w.start, 'end': w.end} 
                         for w in transcription.words] if hasattr(transcription, 'words') else []
            }
        except Exception as e:
            print(f"Erreur Whisper: {e}")
        return None
    
    async def _extract_audio_features(self, file_path: str) -> Optional[Dict]:
        """Extrait les caractéristiques audio pour l'analyse"""
        try:
            y, sr = librosa.load(file_path, duration=30)
            
            features = {
                'duration': librosa.get_duration(y=y, sr=sr),
                'tempo': float(librosa.beat.tempo(y=y, sr=sr)[0]),
                'key': self._estimate_key(y, sr),
                'energy': float(np.mean(librosa.feature.rms(y=y))),
                'spectral_centroid': float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))),
                'zero_crossing_rate': float(np.mean(librosa.feature.zero_crossing_rate(y=y))),
            }
            
            return features
        except Exception as e:
            print(f"Erreur extraction features: {e}")
        return None
    
    def _estimate_key(self, y, sr):
        """Estime la tonalité de la musique"""
        try:
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            key_index = np.argmax(chroma_mean)
            
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            return keys[key_index]
        except:
            return 'C'  # Default
    
    async def _merge_audio_results(self, results: Dict, file_path: str) -> Dict:
        """Fusionne les résultats des différentes méthodes avec AJOUT YOUTUBE"""
        final = {
            'source': 'merged',
            'confidence': 0,
            'artist': None,
            'title': None,
            'metadata': {},
            'external_links': {}  # AJOUT
        }
        
        # Priorité à AudD pour la musique
        if 'audd' in results and results['audd']:
            final.update({
                'artist': results['audd'].get('artist'),
                'title': results['audd'].get('title'),
                'album': results['audd'].get('album'),
                'release_date': results['audd'].get('release_date'),
                'external_links': {
                    'spotify': results['audd'].get('spotify'),
                    'apple_music': results['audd'].get('apple_music'),
                    'deezer': results['audd'].get('deezer')
                },
                'confidence': results['audd'].get('confidence', 0.8)
            })
            
            # AJOUT: Rechercher sur YouTube si on a artiste et titre
            if final.get('artist') and final.get('title'):
                youtube_videos = await self.youtube_client.search_music_video(
                    final['title'],
                    final['artist']
                )
                if youtube_videos:
                    final['external_links']['youtube'] = youtube_videos[0]['url']
                    final['youtube'] = {
                        'id': youtube_videos[0]['youtube_id'],
                        'title': youtube_videos[0]['title'],
                        'thumbnail': youtube_videos[0]['thumbnail'],
                        'url': youtube_videos[0]['url'],
                        'embed_url': youtube_videos[0]['embed_url'],
                        'channel': youtube_videos[0]['channel'],
                        'view_count': youtube_videos[0]['view_count']
                    }
                    
                    # AJOUT: Chercher aussi la version lyrics
                    lyrics_video = await self.youtube_client.search_lyrics_video(
                        final['title'],
                        final['artist']
                    )
                    if lyrics_video:
                        final['youtube_lyrics'] = lyrics_video
        
        # Si pas de résultat AudD mais transcription Whisper
        elif 'whisper' in results and results['whisper']:
            whisper_text = results['whisper'].get('transcription', '')
            
            # AJOUT: Essayer de chercher sur YouTube avec la transcription
            if whisper_text:
                youtube_videos = await self.youtube_client.search_music_video(
                    whisper_text[:100]  # Premiers 100 caractères
                )
                if youtube_videos:
                    final['external_links']['youtube'] = youtube_videos[0]['url']
                    final['youtube'] = {
                        'id': youtube_videos[0]['youtube_id'],
                        'title': youtube_videos[0]['title'],
                        'thumbnail': youtube_videos[0]['thumbnail'],
                        'url': youtube_videos[0]['url'],
                        'channel': youtube_videos[0]['channel']
                    }
                    final['confidence'] = 0.6
                    final['title'] = youtube_videos[0]['title']
        
        # Ajouter la transcription si disponible
        if 'whisper' in results and results['whisper']:
            final['transcription'] = results['whisper'].get('transcription')
            final['language'] = results['whisper'].get('language')
        
        # Ajouter les caractéristiques audio
        if 'features' in results and results['features']:
            final['audio_features'] = results['features']
        
        return final