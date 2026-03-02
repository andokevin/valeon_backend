# app/core/modules/whisper_client.py
import whisper
import os
import tempfile
import logging
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class WhisperClient:
    """
    Client Whisper en Python pour la transcription audio.
    Alternative plus fiable à whisper.cpp.
    """
    
    # Modèles disponibles par ordre de taille/vitesse
    AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large"]
    
    def __init__(self, model_size: str = "base", language: str = "fr"):
        """
        Initialise le client Whisper.
        
        Args:
            model_size: Taille du modèle (tiny, base, small, medium, large)
            language: Code de langue par défaut (fr, en, etc.)
        """
        self.model_size = model_size
        self.language = language
        self.model = None
        self._load_model()
        
    def _load_model(self):
        """Charge le modèle Whisper (téléchargement auto si nécessaire)."""
        try:
            logger.info(f"WhisperClient: Chargement du modèle '{self.model_size}'...")
            self.model = whisper.load_model(self.model_size)
            logger.info(f"WhisperClient: Modèle '{self.model_size}' chargé avec succès")
        except Exception as e:
            logger.error(f"WhisperClient: Erreur chargement modèle: {e}")
            self.model = None
    
    async def transcribe(self, file_path: str, language: Optional[str] = None) -> str:
        """
        Transcrit un fichier audio en texte.
        
        Args:
            file_path: Chemin vers le fichier audio
            language: Code de langue (si None, utilise la langue par défaut)
            
        Returns:
            Texte transcrit
        """
        if not self.model:
            logger.error("WhisperClient: Modèle non chargé")
            return ""
        
        if not os.path.exists(file_path):
            logger.error(f"WhisperClient: Fichier non trouvé: {file_path}")
            return ""
        
        # Vérifier la taille du fichier
        file_size = os.path.getsize(file_path)
        logger.info(f"WhisperClient: Transcription de {os.path.basename(file_path)} (taille: {file_size} bytes)")
        
        try:
            # Exécuter la transcription dans un thread pour ne pas bloquer
            result = await asyncio.to_thread(
                self.model.transcribe,
                file_path,
                language=language or self.language,
                verbose=False,
                fp16=False,  # Désactiver fp16 pour CPU
                task="transcribe",  # "transcribe" ou "translate"
                temperature=0.0,  # Température basse pour plus de précision
                compression_ratio_threshold=2.4,
                logprob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=True,
                initial_prompt=None,
                word_timestamps=False,
                prepend_punctuations="\"'“¿([{-",
                append_punctuations="\"'.。,，!！?？:：”)]}、",
            )
            
            text = result.get("text", "").strip()
            logger.info(f"WhisperClient: Transcription terminée ({len(text)} caractères)")
            
            # Logger un extrait pour déboguer
            if text:
                logger.debug(f"WhisperClient: Extrait: {text[:200]}...")
            else:
                logger.warning("WhisperClient: Transcription vide")
            
            return text
            
        except Exception as e:
            logger.error(f"WhisperClient: Erreur transcription: {e}", exc_info=True)
            return ""
    
    async def transcribe_with_timestamps(self, file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcrit avec timestamps (pour sous-titres).
        
        Returns:
            Dict avec 'text', 'segments' et 'language'
        """
        if not self.model:
            return {"text": "", "segments": [], "language": self.language}
        
        try:
            result = await asyncio.to_thread(
                self.model.transcribe,
                file_path,
                language=language or self.language,
                verbose=False,
                fp16=False,
                word_timestamps=True,  # Activer les timestamps
            )
            
            segments = []
            for segment in result.get("segments", []):
                segments.append({
                    "start": segment.get("start", 0),
                    "end": segment.get("end", 0),
                    "text": segment.get("text", "").strip(),
                    "words": [
                        {
                            "word": w.get("word", ""),
                            "start": w.get("start", 0),
                            "end": w.get("end", 0),
                            "probability": w.get("probability", 0)
                        }
                        for w in segment.get("words", [])
                    ]
                })
            
            return {
                "text": result.get("text", "").strip(),
                "segments": segments,
                "language": result.get("language", language or self.language),
                "duration": result.get("duration", 0)
            }
            
        except Exception as e:
            logger.error(f"WhisperClient: Erreur transcription avec timestamps: {e}")
            return {"text": "", "segments": [], "language": self.language}
    
    async def detect_language(self, file_path: str) -> str:
        """
        Détecte la langue du fichier audio.
        """
        if not self.model:
            return self.language
        
        try:
            # Charger l'audio et détecter la langue
            audio = whisper.load_audio(file_path)
            audio = whisper.pad_or_trim(audio)
            
            # Faire un premier passage pour détecter la langue
            mel = whisper.log_mel_spectrogram(audio).to(self.model.device)
            _, probs = self.model.detect_language(mel)
            
            detected_lang = max(probs, key=probs.get)
            logger.info(f"WhisperClient: Langue détectée: {detected_lang}")
            
            return detected_lang
            
        except Exception as e:
            logger.error(f"WhisperClient: Erreur détection langue: {e}")
            return self.language
    
    def get_available_models(self) -> list:
        """Retourne la liste des modèles disponibles."""
        return self.AVAILABLE_MODELS
    
    def get_model_info(self) -> Dict[str, Any]:
        """Retourne des infos sur le modèle chargé."""
        return {
            "model_size": self.model_size,
            "is_loaded": self.model is not None,
            "device": str(self.model.device) if self.model else None,
            "multilingual": True,
            "languages": ["fr", "en", "es", "de", "it", "pt", "ru", "zh", "ja", "ko"],
            "parameters": {
                "tiny": "39M",
                "base": "74M",
                "small": "244M",
                "medium": "769M",
                "large": "1550M"
            }.get(self.model_size, "unknown")
        }
