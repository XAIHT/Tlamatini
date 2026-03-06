# Tlamatini/asgi.py
import os

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# This line must come first, BEFORE any Django imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tlamatini.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import agent.routing

# This line initializes Django
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            agent.routing.websocket_urlpatterns
        )
    ),
})