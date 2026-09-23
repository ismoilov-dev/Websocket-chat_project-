from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from chat.models import Conversation, Message

User = get_user_model()


class ChatAPITests(TestCase):
    def setUp(self):
        self.ali = User.objects.create_user("ali", password="StrongPass123!")
        self.vali = User.objects.create_user("vali", password="StrongPass123!")
        self.sardor = User.objects.create_user("sardor", password="StrongPass123!")
        self.client.force_login(self.ali)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("chat_api:api-users"))
        self.assertEqual(response.status_code, 403)

    def test_user_list_excludes_me_and_counts_unread(self):
        conv = Conversation.get_or_create_between(self.ali, self.vali)
        Message.objects.create(conversation=conv, sender=self.vali, content="Salom")
        Message.objects.create(conversation=conv, sender=self.ali, content="Salom")  # meniki, hisoblanmaydi

        data = self.client.get(reverse("chat_api:api-users")).json()
        by_name = {u["username"]: u for u in data}
        self.assertNotIn("ali", by_name)
        self.assertEqual(by_name["vali"]["unread_count"], 1)
        self.assertEqual(by_name["sardor"]["unread_count"], 0)

    def test_conversation_is_same_regardless_of_order(self):
        a = Conversation.get_or_create_between(self.ali, self.vali)
        b = Conversation.get_or_create_between(self.vali, self.ali)
        self.assertEqual(a.pk, b.pk)

    def test_history_only_contains_this_conversation(self):
        c1 = Conversation.get_or_create_between(self.ali, self.vali)
        c2 = Conversation.get_or_create_between(self.vali, self.sardor)
        Message.objects.create(conversation=c1, sender=self.vali, content="for ali")
        Message.objects.create(conversation=c2, sender=self.vali, content="for sardor")

        data = self.client.get(reverse("chat_api:api-messages", args=[self.vali.id])).json()
        self.assertEqual([m["content"] for m in data], ["for ali"])

    def test_cannot_chat_with_self(self):
        response = self.client.get(reverse("chat_api:api-messages", args=[self.ali.id]))
        self.assertEqual(response.status_code, 400)

    def test_mark_read(self):
        conv = Conversation.get_or_create_between(self.ali, self.vali)
        msg = Message.objects.create(conversation=conv, sender=self.vali, content="Salom")
        response = self.client.post(reverse("chat_api:api-mark-read", args=[self.vali.id]))
        self.assertEqual(response.json(), {"marked_read": [msg.id]})
        msg.refresh_from_db()
        self.assertTrue(msg.is_read)
