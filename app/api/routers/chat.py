# app/api/routers/chat.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import get_db
from app.api.dependencies.auth import get_current_user
from app.models import User, UserActivity
from app.core.modules.gemini import GeminiClient

router = APIRouter(prefix="/chat", tags=["Chat"])
gemini = GeminiClient()

class ChatMessage(BaseModel):
    role: str  # "user" ou "assistant"
    content: str
    timestamp: Optional[datetime] = None

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    timestamp: datetime
    recommendations: Optional[List[Dict[str, Any]]] = None

@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Envoie un message à l'assistant IA et reçoit une réponse.
    """
    try:
        # Enregistrer l'activité
        activity = UserActivity(
            user_id=current_user.user_id,
            activity_type="chat_query",
            activity_metadata={
                "message": request.message[:100],
                "conversation_id": request.conversation_id
            }
        )
        db.add(activity)
        db.commit()

        # Récupérer l'historique récent des scans pour contexte
        from app.models import Scan
        recent_scans = db.query(Scan).filter(
            Scan.scan_user == current_user.user_id,
            Scan.status == "completed",
            Scan.result.isnot(None)
        ).order_by(Scan.scan_date.desc()).limit(10).all()

        scans_context = []
        for scan in recent_scans:
            if scan.result:
                scans_context.append({
                    "type": scan.scan_type,
                    "title": scan.result.get("title", "Inconnu"),
                    "artist": scan.result.get("artist"),
                    "date": scan.scan_date.isoformat() if scan.scan_date else None
                })

        # ===== MODIFICATION 1: PROMPT SYSTÈME AMÉLIORÉ =====
        # Instructions plus précises pour éviter les salutations et forcer les recommandations
        system_prompt = f"""Tu es l'assistant IA de Valeon, une application de reconnaissance de musique, films et images.

RÈGLES IMPORTANTES:
1. NE COMMENCE JAMAIS tes réponses par "Bonjour", "Salut" ou toute autre salutation
2. Va DIRECTEMENT à l'essentiel de la question
3. Si l'utilisateur demande des recommandations, donne des suggestions concrètes avec artistes et titres
4. Structure tes recommandations en liste claire
5. Réponds UNIQUEMENT en français
6. Sois concis mais informatif

Informations sur l'utilisateur:
- Nom: {current_user.user_full_name}
- Scans récents: {len(scans_context)} scans
"""

        # Ajouter le contexte des scans si disponibles
        user_context = ""
        if scans_context:
            user_context = "Voici ses scans récents pour référence:\n"
            for s in scans_context[:3]:
                user_context += f"- {s['type']}: {s['title']} par {s.get('artist', 'inconnu')}\n"

        # ===== MODIFICATION 2: PROMPT UTILISATEUR AMÉLIORÉ =====
        prompt = f"""{system_prompt}

{user_context}

Question de l'utilisateur: {request.message}

INSTRUCTION: Si la question concerne des recommandations, réponds avec une liste de 3-5 suggestions incluant titre, artiste et raison.

Réponse (sans salutation):"""

        gemini_response = await gemini.generate_text(
            prompt=prompt,
            max_tokens=800,  # Augmenté pour permettre plus de recommandations
            temperature=0.7
        )

        response_text = gemini_response.get("text", "Désolé, je n'ai pas pu traiter votre demande.")

        # ===== MODIFICATION 3: EXTRAIRE LES RECOMMANDATIONS =====
        recommendations = []
        try:
            # Chercher des motifs de recommandations dans la réponse
            lines = response_text.split('\n')
            for line in lines:
                if '-' in line and ('recommand' in line.lower() or 'suggère' in line.lower()):
                    # Essayer d'extraire titre et artiste
                    parts = line.replace('-', '').strip().split('par')
                    if len(parts) >= 2:
                        title = parts[0].strip()
                        artist = parts[1].strip().split(',')[0].split('.')[0]
                        recommendations.append({
                            "title": title,
                            "artist": artist,
                            "type": "music" if "musique" in line.lower() or "chanson" in line.lower() else "movie",
                            "reason": line
                        })
        except:
            pass

        # Générer un ID de conversation si nécessaire
        conversation_id = request.conversation_id or f"conv_{current_user.user_id}_{datetime.utcnow().timestamp()}"

        return ChatResponse(
            response=response_text,
            conversation_id=conversation_id,
            timestamp=datetime.utcnow(),
            recommendations=recommendations if recommendations else None
        )

    except Exception as e:
        # En cas d'erreur, retourner une réponse par défaut
        print(f"❌ Erreur chat: {e}")
        return ChatResponse(
            response="Désolé, une erreur technique est survenue. Veuillez réessayer.",
            conversation_id=request.conversation_id or f"error_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow()
        )

@router.get("/history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère l'historique d'une conversation.
    """
    # Cette fonctionnalité nécessiterait de stocker les conversations en base
    # Pour l'instant, retourner un historique vide
    return {"conversation_id": conversation_id, "messages": []}

@router.delete("/history/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprime une conversation.
    """
    # À implémenter avec stockage en base
    return {"message": "Conversation supprimée"}