"""
chat/routing.py

WebSocket uchun urls.py. HTTP'da `path()` view'ga yo'naltirsa,
bu yerda `re_path()` WebSocket manzilini consumer'ga yo'naltiradi.

.as_asgi() - xuddi View.as_view() kabi: har bir yangi connection uchun
consumer'ning yangi nusxasini (instance) yaratadi.
"""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/presence/$", consumers.PresenceConsumer.as_asgi()),
    re_path(r"^ws/chat/(?P<user_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
]
