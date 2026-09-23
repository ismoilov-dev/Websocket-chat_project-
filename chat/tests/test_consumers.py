"""
WebSocket testlari. Redis shart emas: testda InMemoryChannelLayer ishlatamiz.
Ishga tushirish: python manage.py test
"""
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from chat.models import Message
from chat.routing import websocket_urlpatterns

User = get_user_model()

IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

application = URLRouter(websocket_urlpatterns)


async def assert_rejected(testcase, comm, code):
    """Consumer accept() qilib, darhol berilgan kod bilan yopishi kerak."""
    await comm.connect()
    testcase.assertEqual(await comm.receive_output(), {"type": "websocket.close", "code": code})


def communicator_for(user, path):
    comm = WebsocketCommunicator(application, path)
    comm.scope["user"] = user  # AuthMiddlewareStack o'rniga userni qo'lda beramiz
    return comm


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class ChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.ali = User.objects.create_user("ali", password="x")
        self.vali = User.objects.create_user("vali", password="x")

    async def test_anonymous_is_rejected(self):
        for path in (f"/ws/chat/{self.vali.id}/", "/ws/presence/"):
            await assert_rejected(self, communicator_for(AnonymousUser(), path), 4001)

    async def test_cannot_connect_to_self_or_missing_user(self):
        await assert_rejected(self, communicator_for(self.ali, f"/ws/chat/{self.ali.id}/"), 4003)
        await assert_rejected(self, communicator_for(self.ali, "/ws/chat/99999/"), 4004)

    async def test_message_typing_and_read_flow(self):
        ali = communicator_for(self.ali, f"/ws/chat/{self.vali.id}/")
        vali = communicator_for(self.vali, f"/ws/chat/{self.ali.id}/")
        self.assertTrue((await ali.connect())[0])
        self.assertTrue((await vali.connect())[0])

        # typing: faqat suhbatdoshga boradi
        await ali.send_json_to({"type": "typing", "is_typing": True})
        event = await vali.receive_json_from()
        self.assertEqual(event, {"type": "typing", "user_id": self.ali.id, "is_typing": True})
        self.assertTrue(await ali.receive_nothing())

        # xabar: ikkala tomonga keladi va DB'ga saqlanadi
        await ali.send_json_to({"type": "chat_message", "message": "Salom"})
        for comm in (ali, vali):
            event = await comm.receive_json_from()
            self.assertEqual(event["type"], "chat_message")
            self.assertEqual(event["message"]["content"], "Salom")
            self.assertFalse(event["message"]["is_read"])
        msg_id = event["message"]["id"]
        self.assertTrue(await database_sync_to_async(Message.objects.filter(id=msg_id).exists)())

        # read: vali o'qidi -> ali ✓✓ oladi
        await vali.send_json_to({"type": "read"})
        event = await ali.receive_json_from()
        self.assertEqual(event, {"type": "messages_read", "reader_id": self.vali.id, "message_ids": [msg_id]})

        await ali.disconnect()
        await vali.disconnect()

    async def test_invalid_payloads_return_errors(self):
        comm = communicator_for(self.ali, f"/ws/chat/{self.vali.id}/")
        await comm.connect()
        await comm.send_to(text_data="not json")
        self.assertEqual((await comm.receive_json_from())["type"], "error")
        await comm.send_json_to({"type": "chat_message", "message": "   "})
        self.assertEqual((await comm.receive_json_from())["type"], "error")
        await comm.send_json_to({"type": "unknown"})
        self.assertEqual((await comm.receive_json_from())["type"], "error")
        await comm.disconnect()


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class PresenceConsumerTests(TransactionTestCase):
    def setUp(self):
        self.ali = User.objects.create_user("ali", password="x")
        self.vali = User.objects.create_user("vali", password="x")

    async def test_online_offline_and_notifications(self):
        ali = communicator_for(self.ali, "/ws/presence/")
        await ali.connect()

        vali = communicator_for(self.vali, "/ws/presence/")
        await vali.connect()
        event = await ali.receive_json_from()
        self.assertEqual((event["user_id"], event["is_online"]), (self.vali.id, True))

        # Vali'ning ikkinchi tabi: status o'zgarmaydi -> hech kim xabar olmaydi
        vali_tab2 = communicator_for(self.vali, "/ws/presence/")
        await vali_tab2.connect()
        self.assertTrue(await ali.receive_nothing())
        await vali_tab2.disconnect()
        self.assertTrue(await ali.receive_nothing())

        # Ali -> Vali xabar: Vali'ning presence connectioni bildirishnoma oladi
        chat = communicator_for(self.ali, f"/ws/chat/{self.vali.id}/")
        await chat.connect()
        await chat.send_json_to({"type": "chat_message", "message": "Salom"})
        event = await vali.receive_json_from()
        self.assertEqual(event["type"], "new_message")
        await chat.disconnect()

        await vali.disconnect()
        event = await ali.receive_json_from()
        self.assertEqual((event["user_id"], event["is_online"]), (self.vali.id, False))
        await ali.disconnect()
