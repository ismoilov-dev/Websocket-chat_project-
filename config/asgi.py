"""
config/asgi.py

ASGI - server (daphne/uvicorn) va Django o'rtasidagi "kirish eshigi".
ProtocolTypeRouter kelgan connection turini tekshiradi:
    - "http"      -> oddiy Django (view, template, API)
    - "websocket" -> Channels consumer'lari
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# MUHIM: Django'ni birinchi ishga tushiramiz, keyin model import qiladigan
# modullarni (routing -> consumers -> models) import qilamiz.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Qatlamlar tashqaridan ichkariga:
        # 1) AllowedHostsOriginValidator - Origin header ALLOWED_HOSTS'da bo'lmasa rad etadi.
        #    Begona sayt foydalanuvchi cookie'si bilan bizga ulanishining oldini oladi (CSWSH).
        # 2) AuthMiddlewareStack - session cookie'dan userni topib scope["user"] ga qo'yadi.
        # 3) URLRouter - manzil bo'yicha kerakli consumer'ni tanlaydi.
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
