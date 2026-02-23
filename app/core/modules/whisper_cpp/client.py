import asyncio
import os
import subprocess
import tempfile
import json
import logging
from typing import Optional, Dict, Any
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
            
            # Vérifier que les fichiers existent
            if not os.path.exists(self.executable_path):
                logger.error(f"WhisperCppClient: Exécutable non trouvé: {self.executable_path}")
                self.enabled = False
            elif not os.path.exists(self.model_path):
                logger.error(f"WhisperCppClient: Modèle non trouvé: {self.model_path}")
                self.enabled = False
            else:
                logger.info("WhisperCppClient: Configuration valide")
        else:
            logger.warning("WhisperCppClient: Service désactivé, mode mock")

    async def transcribe(self, file_path: str) -> str:
        """
        Transcrit un fichier audio en texte.
        """
        if not os.path.exists(file_path):
            logger.error(f"WhisperCppClient: Fichier non trouvé: {file_path}")
            return ""
        
        if not self.enabled:
            logger.info(f"WhisperCppClient: Mode mock pour {os.path.basename(file_path)}")
            return self._mock_transcribe(file_path)
        
        logger.info(f"WhisperCppClient: Transcription de {os.path.basename(file_path)}")
        
        try:
            # Créer un fichier temporaire pour la sortie
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tmp_file:
                output_path = tmp_file.name
            
            # Construire la commande whisper.cpp
            cmd = [
                self.executable_path,
                "-f", file_path,
                "-m", self.model_path,
                "-otxt",  # Sortie texte
                "-of", output_path.replace('.txt', '')  # Fichier de sortie sans extension
            ]
            
            # Exécuter la commande
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"WhisperCppClient: Erreur: {stderr.decode()}")
                return self._mock_transcribe(file_path)
            
            # Lire le résultat
            output_file = output_path
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    result = f.read().strip()
                
                # Nettoyer
                os.unlink(output_file)
                logger.info(f"WhisperCppClient: Transcription réussie ({len(result)} caractères)")
                return result
            
            return ""
            
        except Exception as e:
            logger.error(f"WhisperCppClient: Erreur: {e}")
            return self._mock_transcribe(file_path)
        
        finally:
            # Nettoyer les fichiers temporaires
            for f in [output_path, output_path.replace('.txt', '.json')]:
                if os.path.exists(f):
                    try:
                        os.unlink(f)
                    except:
                        pass

    async def transcribe_with_timestamps(self, file_path: str) -> Dict[str, Any]:
        """
        Transcrit avec timestamps (format JSON).
        """
        if not os.path.exists(file_path):
            return {"text": "", "segments": []}
        
        if not self.enabled:
            return {"text": self._mock_transcribe(file_path), "segments": []}
        
        try:
            # Créer un fichier temporaire pour la sortie JSON
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp_file:
                output_path = tmp_file.name
            
            cmd = [
                self.executable_path,
                "-f", file_path,
                "-m", self.model_path,
                "-oj",  # Sortie JSON
                "-of", output_path.replace('.json', '')
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"WhisperCppClient: Erreur: {stderr.decode()}")
                return {"text": "", "segments": []}
            
            # Lire le résultat JSON
            json_file = output_path
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Nettoyer
                os.unlink(json_file)
                
                # Formater le résultat
                return self._format_result(data)
            
            return {"text": "", "segments": []}
            
        except Exception as e:
            logger.error(f"WhisperCppClient: Erreur: {e}")
            return {"text": "", "segments": []}

    def _format_result(self, data: dict) -> Dict[str, Any]:
        """
        Formate le résultat JSON de Whisper.cpp.
        """
        result = {
            "text": data.get("text", ""),
            "language": data.get("language", "unknown"),
            "segments": []
        }
        
        segments = data.get("segments", [])
        for seg in segments:
            result["segments"].append({
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "")
            })
        
        return result

    def _mock_transcribe(self, file_path: str) -> str:
        """Génère une transcription mock."""
        filename = os.path.basename(file_path).lower()
        
        mock_responses = {
            "music": "This is a song with melodic rhythm and lyrics about love.",
            ".mp3": "Audio track with musical elements detected.",
            "speech": "This is a speech about technology and innovation.",
            "interview": "Interview discussing various topics.",
            "podcast": "Podcast episode discussing current events.",
        }
        
        for keyword, response in mock_responses.items():
            if keyword in filename:
                return response
        
        return "Audio content detected with speech and background sounds."