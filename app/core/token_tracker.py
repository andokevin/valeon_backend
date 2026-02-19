# app/core/token_tracker.py
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import UserActivity
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class TokenTracker:
    """
    Traqueur de consommation de tokens OpenAI.
    """
    
    def __init__(self):
        self.monthly_limit = settings.OPENAI_MAX_TOKENS_PER_MONTH
    
    def track_tokens(self, user_id: int, tokens: int, model: str, db: Session):
        """
        Enregistre la consommation de tokens.
        """
        activity = UserActivity(
            user_id=user_id,
            activity_type="token_usage",
            metadata={
                "tokens": tokens,
                "model": model,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        db.add(activity)
        db.commit()
        logger.info(f"Token usage: {tokens} tokens for user {user_id} (model: {model})")
    
    def get_user_monthly_usage(self, user_id: int, db: Session) -> int:
        """
        Récupère la consommation mensuelle d'un utilisateur.
        """
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        activities = db.query(UserActivity).filter(
            UserActivity.user_id == user_id,
            UserActivity.activity_type == "token_usage",
            UserActivity.created_at >= month_start
        ).all()
        
        total_tokens = sum(
            activity.metadata.get("tokens", 0)
            for activity in activities
            if activity.metadata
        )
        
        return total_tokens
    
    def check_token_limit(self, user_id: int, estimated_tokens: int, db: Session) -> bool:
        """
        Vérifie si l'utilisateur a encore des tokens disponibles.
        """
        if not self.monthly_limit:
            return True
        
        used = self.get_user_monthly_usage(user_id, db)
        return (used + estimated_tokens) <= self.monthly_limit

token_tracker = TokenTracker()