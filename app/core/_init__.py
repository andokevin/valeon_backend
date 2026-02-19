# app/core/__init__.py
"""
Module core contenant l'orchestrateur et les modules spécialisés.
"""
from .orchestrator.main_orchestrator import MainOrchestrator
from .subscription.manager import SubscriptionManager

__all__ = [
    'MainOrchestrator',
    'SubscriptionManager'
]