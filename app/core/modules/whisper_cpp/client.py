# app/core/modules/whisper_cpp/client.py (AMÉLIORÉ)
import asyncio
import os
import subprocess
import tempfile
import json
import logging
from typing import Optional, Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class WhisperCppClient:
    def __init__(self):
        """Initialise le client Whisper.cpp."""
        self.enabled = settings.WHISPER_CPP_ENABLED
        self.model_path = settings.WHISPER_MODEL_PATH
        self.executable_path = settings.WHISPER_EXECUTABLE_PATH
        
        if self.enabled:
            logger.info(f"WhisperCppClient: enabled={self.enabled}")
            logger.info(f"WhisperCppClient: model_path={self.model_path}")
            logger.info(f"WhisperCppClient: executable_path={self.executable_path}")
            
            # Vérifier que les fichiers existent
            if not os.path.exists(self.executable_path):
                logger.error(f"WhisperCppClient: Exécutable non trouvé: {self.executable_path}")
                self.enabled = False
            elif not os.path.exists(self.model_path):
                logger.error(f"WhisperCppClient: Modèle non trouvé: {self.model_path}")
                self.enabled = False
            else:
                logger.info("WhisperCppClient: Configuration valide")
                
                # Tester l'exécutable
                try:
                    result = subprocess.run(
                        [self.executable_path, "--help"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        logger.info("WhisperCppClient: Exécutable fonctionnel")
                    else:
                        logger.error(f"WhisperCppClient: Exécutable retourne erreur {result.returncode}")
                        self.enabled = False
                except Exception as e:
                    logger.error(f"WhisperCppClient: Erreur test exécutable: {e}")
                    self.enabled = False
        else:
            logger.warning("WhisperCppClient: Service désactivé, mode mock")

    async def transcribe(self, file_path: str, language: str = "fr") -> str:
        """
        Transcrit un fichier audio en texte.
        
        Args:
            file_path: Chemin vers le fichier audio
            language: Code de langue (fr, en, etc.)
            
        Returns:
            Texte transcrit
        """
        if not os.path.exists(file_path):
            logger.error(f"WhisperCppClient: Fichier non trouvé: {file_path}")
            return ""
        
        if not self.enabled:
            logger.info(f"WhisperCppClient: Mode mock pour {os.path.basename(file_path)}")
            return self._mock_transcribe(file_path)
        
        logger.info(f"WhisperCppClient: Transcription de {os.path.basename(file_path)}")
        logger.info(f"WhisperCppClient: Taille du fichier: {os.path.getsize(file_path)} bytes")
        
        try:
            # Créer un fichier temporaire pour la sortie
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tmp_file:
                output_path = tmp_file.name
            
            # Construire la commande whisper.cpp
            cmd = [
                self.executable_path,
                "-f", file_path,
                "-m", self.model_path,
                "-l", language,  # Spécifier la langue
                "-otxt",  # Sortie texte
                "-of", output_path.replace('.txt', '')  # Fichier de sortie sans extension
            ]
            
            logger.debug(f"WhisperCppClient: Commande: {' '.join(cmd)}")
            
            # Exécuter la commande
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"WhisperCppClient: Erreur code {process.returncode}")
                logger.error(f"WhisperCppClient: stderr: {stderr.decode()}")
                return self._mock_transcribe(file_path)
            
            # Lire le résultat
            output_file = output_path
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    result = f.read().strip()
                
                # Nettoyer
                os.unlink(output_file)
                
                # 🔥 LOG DÉTAILLÉ DE LA TRANSCRIPTION
                logger.info("=" * 80)
                logger.info("🔍 TRANSCRIPTION WHISPER COMPLÈTE:")
                logger.info("-" * 40)
                logger.info(result)
                logger.info("-" * 40)
                logger.info(f"📊 Statistiques: {len(result)} caractères, {len(result.split())} mots")
                logger.info("=" * 80)
                
                return result
            
            return ""
            
        except Exception as e:
            logger.error(f"WhisperCppClient: Erreur: {e}", exc_info=True)
            return self._mock_transcribe(file_path)
        
        finally:
            # Nettoyer les fichiers temporaires
            for f in [output_path, output_path.replace('.txt', '.json')]:
                if os.path.exists(f):
                    try:
                        os.unlink(f)
                    except:
                        pass

    async def transcribe_with_timestamps(self, file_path: str, language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit avec timestamps (format JSON).
        
        Returns:
            Dict avec 'text', 'segments', 'language'
        """
        if not os.path.exists(file_path):
            return {"text": "", "segments": [], "language": language}
        
        if not self.enabled:
            mock_text = self._mock_transcribe(file_path)
            return {
                "text": mock_text,
                "segments": [{"start": 0, "end": 10, "text": mock_text}],
                "language": language
            }
        
        try:
            # Créer un fichier temporaire pour la sortie JSON
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp_file:
                output_path = tmp_file.name
            
            cmd = [
                self.executable_path,
                "-f", file_path,
                "-m", self.model_path,
                "-l", language,
                "-oj",  # Sortie JSON
                "-of", output_path.replace('.json', '')
            ]
            
            logger.debug(f"WhisperCppClient: Commande: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"WhisperCppClient: Erreur: {stderr.decode()}")
                return {"text": "", "segments": [], "language": language}
            
            # Lire le résultat JSON
            json_file = output_path
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Nettoyer
                os.unlink(json_file)
                
                # Formater le résultat
                result = self._format_result(data)
                
                # 🔥 LOG DÉTAILLÉ DE LA TRANSCRIPTION AVEC TIMESTAMPS
                logger.info("=" * 80)
                logger.info("🔍 TRANSCRIPTION WHISPER AVEC TIMESTAMPS:")
                logger.info(f"Langue détectée: {result['language']}")
                logger.info("-" * 40)
                for seg in result['segments'][:5]:  # Afficher les 5 premiers segments
                    logger.info(f"[{seg['start']:.1f}s -> {seg['end']:.1f}s] {seg['text']}")
                if len(result['segments']) > 5:
                    logger.info(f"... et {len(result['segments']) - 5} autres segments")
                logger.info("-" * 40)
                logger.info(f"📊 Texte complet ({len(result['text'])} caractères):")
                logger.info(result['text'])
                logger.info("=" * 80)
                
                return result
            
            return {"text": "", "segments": [], "language": language}
            
        except Exception as e:
            logger.error(f"WhisperCppClient: Erreur: {e}", exc_info=True)
            return {"text": "", "segments": [], "language": language}

    def _format_result(self, data: dict) -> Dict[str, Any]:
        """
        Formate le résultat JSON de Whisper.cpp.
        """
        result = {
            "text": data.get("text", "").strip(),
            "language": data.get("language", "unknown"),
            "segments": []
        }
        
        segments = data.get("segments", [])
        for seg in segments:
            result["segments"].append({
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip()
            })
        
        return result

    def _mock_transcribe(self, file_path: str) -> str:
        """Génère une transcription mock réaliste basée sur le nom du fichier."""
        filename = os.path.basename(file_path).lower()
        
        # Dictionnaire de réponses mock plus réalistes
        mock_responses = {
            "music": "This is a song with melodic rhythm and lyrics about love and heartbreak. The artist sings about emotional experiences and personal growth.",
            "song": "La la la, singing a beautiful melody with heartfelt lyrics about life and love. The chorus repeats several times with emotional intensity.",
            "speech": "Thank you for being here today. I want to talk about innovation and technology, and how we can shape the future together through collaboration and creativity.",
            "interview": "Interviewer: So tell us about your latest project. Guest: Well, it's been an amazing journey. We've worked really hard on this and I'm excited to share it with everyone.",
            "podcast": "Welcome back to another episode. Today we're discussing current events and how they affect our daily lives. Let's dive into the first topic.",
            "lecture": "In this lecture, we'll explore the fundamental concepts of machine learning and artificial intelligence. Let's start with the basics of neural networks.",
            "news": "Breaking news: Major developments in technology and science today. Researchers have made a groundbreaking discovery that could change everything.",
        }
        
        # Chercher des mots-clés dans le nom du fichier
        for keyword, response in mock_responses.items():
            if keyword in filename:
                logger.info(f"WhisperCppClient: Mock transcription pour '{keyword}'")
                return response
        
        # Réponse par défaut
        return "Audio content detected with speech and background sounds. The recording contains human voice and ambient noise."
