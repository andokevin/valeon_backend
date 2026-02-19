# app/api/routers/__init__.py
from . import auth
from . import scans
from . import library
from . import recommendations
from . import streaming
from . import websocket
from . import admin  # NOUVEAU

__all__ = [
    'auth',
    'scans',
    'library',
    'recommendations',
    'streaming',
    'websocket',
    'admin'
]