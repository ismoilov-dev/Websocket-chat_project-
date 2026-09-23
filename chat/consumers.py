"""
chat/consumers.py

Consumer - bu WebSocket uchun "view". Django view bitta HTTP so'rovni qabul qilib,
bitta javob qaytaradi. Consumer esa bitta WebSocket connection yashagan butun vaqt
davomida ishlaydi va uchta asosiy hodisaga javob beradi:

    connect()     - brauzer ulanmoqchi bo'ldi
    receive()     - brauzer xabar yubordi
    disconnect()  - connection yopildi

Bu faylda ikkita consumer bor:

1. PresenceConsumer  (/ws/presence/)
   Har bir login qilgan user chat sahifasini ochganda ulanadi.
   Vazifasi: Online/Offline status va "sizga yangi xabar keldi" bildirishnomasi.

2. ChatConsumer      (/ws/chat/<user_id>/)
   Aniq bitta suhbatdosh bilan private chat. Xabar, typing, read status.

Group nomlari:
    "presence"        - hamma online userlar (status o'zgarishini hammaga tarqatish)
    "user_<id>"       - bitta userning barcha tablari (shaxsiy bildirishnoma)
    "chat_<conv_id>"  - bitta suhbatning ikkala ishtirokchisi
"""
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import Conversation
from .services import create_message, mark_conversation_read, serialize_message

logger = logging.getLogger(__name__)
User = get_user_model()

PRESENCE_GROUP = "presence"

# WebSocket close kodlari: 4000-4999 oralig'i ilovaning o'zi uchun ajratilgan
CLOSE_UNAUTHENTICATED = 4001
CLOSE_FORBIDDEN = 4003
CLOSE_NOT_FOUND = 4004


def user_group(user_id: int) -> str:
    return f"user_{user_id}"


class BaseJsonConsumer(AsyncWebsocketConsumer):
    """JSON yuborish/qabul qilish va xatolarni qayta ishlash uchun umumiy yordamchilar."""

    async def send_json(self, data: dict) -> None:
        # self.send() - xabarni AYNAN SHU connection'ga (bitta brauzer tabiga) yuboradi
        await self.send(text_data=json.dumps(data))

    async def send_error(self, detail: str) -> None:
        await self.send_json({"type": "error", "detail": detail})

    async def receive(self, text_data=None, bytes_data=None):
        """
        receive() - brauzer `socket.send(...)` qilganda chaqiriladi.
        Kelgan matnni JSON'ga o'giramiz va `type` bo'yicha kerakli handlerga yo'naltiramiz.
        """
        if text_data is None:
            return await self.send_error("Faqat matnli (JSON) xabarlar qabul qilinadi.")
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return await self.send_error("Noto'g'ri JSON.")
        if not isinstance(payload, dict):
            return await self.send_error("JSON obyekt kutilgan edi.")

        handler = self.client_handlers().get(payload.get("type"))
        if handler is None:
            return await self.send_error(f"Noma'lum xabar turi: {payload.get('type')!r}")

        try:
            await handler(payload)
        except ValueError as exc:  # validatsiya xatolari - userga ko'rsatamiz
            await self.send_error(str(exc))
        except Exception:  # kutilmagan xato - logga yozamiz, connectionni yiqitmaymiz
            logger.exception("Consumer xatosi")
            await self.send_error("Serverda xatolik yuz berdi.")

    def client_handlers(self) -> dict:
        return {}

    async def reject(self, code: int) -> None:
        """
        Connectionni aniq kod bilan rad etish.
        accept()dan OLDIN close() qilinsa, brauzer faqat 1006 kodini ko'radi
        (handshake muvaffaqiyatsiz). Shuning uchun avval qabul qilib, darhol
        o'z kodimiz bilan yopamiz - frontend sababini bila oladi.
        """
        await self.accept()
        await self.close(code=code)


# ===========================================================================
# 1. Presence: Online / Offline
# ===========================================================================
class PresenceConsumer(BaseJsonConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.joined = False

        # AuthMiddlewareStack session cookie orqali scope["user"]ni to'ldiradi.
        # Login qilmagan bo'lsa - AnonymousUser. Unday userni qabul qilmaymiz.
        if not self.user.is_authenticated:
            await self.reject(CLOSE_UNAUTHENTICATED)
            return

        # group_add - bu connection'ni (self.channel_name) guruhga qo'shadi.
        # Endi shu guruhga yuborilgan har bir xabar bu connection'ga ham keladi.
        await self.channel_layer.group_add(PRESENCE_GROUP, self.channel_name)
        await self.channel_layer.group_add(user_group(self.user.id), self.channel_name)
        self.joined = True

        became_online = await self.change_connections(+1)
        if became_online:
            await self.broadcast_presence(is_online=True)

        # accept() - handshake'ni yakunlaydi, shundan keyin brauzerda socket.onopen ishlaydi
        await self.accept()

    async def disconnect(self, close_code):
        if not self.joined:
            return
        # group_discard - connection'ni guruhdan chiqaradi (aks holda Redis'da
        # "o'lik" kanal qolib ketadi va unga bekorga xabar yuborilaveradi).
        await self.channel_layer.group_discard(PRESENCE_GROUP, self.channel_name)
        await self.channel_layer.group_discard(user_group(self.user.id), self.channel_name)

        became_offline = await self.change_connections(-1)
        if became_offline:
            await self.broadcast_presence(is_online=False)

    async def broadcast_presence(self, is_online: bool):
        last_seen = await self.get_last_seen()
        # group_send - guruhdagi HAMMA connectionlarga xabar yuboradi.
        # "type": "presence.update" -> har bir consumer'da presence_update() metodi chaqiriladi
        # (nuqta avtomatik pastki chiziqqa almashadi).
        await self.channel_layer.group_send(
            PRESENCE_GROUP,
            {
                "type": "presence.update",
                "user_id": self.user.id,
                "is_online": is_online,
                "last_seen": last_seen,
            },
        )

    # ----- Channel Layer'dan keladigan hodisalar (group_send natijasi) -----
    async def presence_update(self, event):
        if event["user_id"] == self.user.id:
            return  # o'zimizning statusimizni o'zimizga ko'rsatish shart emas
        await self.send_json(
            {
                "type": "presence",
                "user_id": event["user_id"],
                "is_online": event["is_online"],
                "last_seen": event["last_seen"],
            }
        )

    async def notify_new_message(self, event):
        """ChatConsumer yuborgan: 'sizga X dan yangi xabar keldi' (sidebar badge uchun)."""
        await self.send_json({"type": "new_message", "message": event["message"]})

    # ----- DB bilan ishlash -----
    # Consumer async, Django ORM esa sync. database_sync_to_async ORM kodini
    # alohida thread'da ishga tushiradi va event loop'ni bloklamaydi.
    @database_sync_to_async
    def change_connections(self, delta: int) -> bool:
        """Status o'zgargan bo'lsa True qaytaradi (0->1 yoki 1->0)."""
        if delta > 0:
            User.mark_connected(self.user.id)
            return User.objects.get(pk=self.user.id).active_connections == 1
        User.mark_disconnected(self.user.id)
        return User.objects.get(pk=self.user.id).active_connections == 0

    @database_sync_to_async
    def get_last_seen(self):
        last_seen = User.objects.values_list("last_seen", flat=True).get(pk=self.user.id)
        return last_seen.isoformat() if last_seen else None


# ===========================================================================
# 2. Private chat
# ===========================================================================
class ChatConsumer(BaseJsonConsumer):
    """
    Brauzer -> Server xabarlari:
        {"type": "chat_message", "message": "Salom"}
        {"type": "typing", "is_typing": true}
        {"type": "read"}

    Server -> Brauzer xabarlari:
        {"type": "chat_message", "message": {...}}
        {"type": "typing", "user_id": 5, "is_typing": true}
        {"type": "messages_read", "reader_id": 5, "message_ids": [1, 2]}
        {"type": "error", "detail": "..."}
    """

    async def connect(self):
        self.user = self.scope["user"]
        self.group_name = None

        if not self.user.is_authenticated:
            await self.reject(CLOSE_UNAUTHENTICATED)
            return

        # URL'dagi <user_id> - routing.py dagi regex orqali shu yerga keladi
        other_user_id = int(self.scope["url_route"]["kwargs"]["user_id"])
        if other_user_id == self.user.id:
            await self.reject(CLOSE_FORBIDDEN)
            return

        self.other_user = await self.get_user(other_user_id)
        if self.other_user is None:
            await self.reject(CLOSE_NOT_FOUND)
            return

        # XAVFSIZLIK: suhbatni URL'dan emas, SERVERDA (scope user + other user)
        # hisoblaymiz. Shu sababli hech kim begona suhbat guruhiga kira olmaydi.
        self.conversation = await self.get_conversation()
        self.group_name = f"chat_{self.conversation.id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if self.group_name is None:
            return
        # Tab yopilsa, "typing..." osilib qolmasin
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "typing.event", "user_id": self.user.id, "is_typing": False},
        )
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    def client_handlers(self) -> dict:
        return {
            "chat_message": self.handle_chat_message,
            "typing": self.handle_typing,
            "read": self.handle_read,
        }

    # ----- Brauzerdan kelgan xabarlar -----
    async def handle_chat_message(self, payload):
        text = payload.get("message")
        if not isinstance(text, str):
            raise ValueError("`message` matn bo'lishi kerak.")

        message = await self.save_message(text)  # 1) avval DB'ga saqlaymiz

        # 2) Suhbatdagi ikkala tomonga (barcha tablariga) yuboramiz
        await self.channel_layer.group_send(
            self.group_name, {"type": "chat.message", "message": message}
        )
        # 3) Qabul qiluvchining presence connectioniga bildirishnoma
        #    (u hozir boshqa odam bilan yozishayotgan bo'lsa, sidebar'da badge chiqadi)
        await self.channel_layer.group_send(
            user_group(self.other_user.id), {"type": "notify.new_message", "message": message}
        )

    async def handle_typing(self, payload):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "typing.event", "user_id": self.user.id, "is_typing": bool(payload.get("is_typing"))},
        )

    async def handle_read(self, payload):
        message_ids = await self.mark_read()
        if message_ids:
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "messages.read", "reader_id": self.user.id, "message_ids": message_ids},
            )

    # ----- Channel Layer'dan keladigan hodisalar -----
    # Metod nomi group_send'dagi "type" ga mos: "chat.message" -> chat_message()
    async def chat_message(self, event):
        await self.send_json({"type": "chat_message", "message": event["message"]})

    async def typing_event(self, event):
        if event["user_id"] == self.user.id:
            return  # "siz yozyapsiz..." ni o'zingizga ko'rsatmaymiz
        await self.send_json(
            {"type": "typing", "user_id": event["user_id"], "is_typing": event["is_typing"]}
        )

    async def messages_read(self, event):
        await self.send_json(
            {"type": "messages_read", "reader_id": event["reader_id"], "message_ids": event["message_ids"]}
        )

    # ----- DB -----
    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.filter(pk=user_id, is_active=True).first()

    @database_sync_to_async
    def get_conversation(self):
        return Conversation.get_or_create_between(self.user, self.other_user)

    @database_sync_to_async
    def save_message(self, text: str) -> dict:
        message = create_message(self.conversation, self.user, text)
        return serialize_message(message)

    @database_sync_to_async
    def mark_read(self) -> list[int]:
        return mark_conversation_read(self.conversation, self.user)
