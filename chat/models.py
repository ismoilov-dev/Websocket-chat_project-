from django.conf import settings
from django.db import models
from django.db.models import Q


class ConversationQuerySet(models.QuerySet):
    def for_user(self, user):
        """User ishtirok etgan barcha suhbatlar."""
        return self.filter(Q(user1=user) | Q(user2=user))


class Conversation(models.Model):
    """
    Ikki user o'rtasidagi bitta private suhbat.

    Muhim qoida: har doim user1.id < user2.id.
    Shunda (Ali, Vali) va (Vali, Ali) bitta suhbat bo'ladi, dublikat yaratilmaydi.
    """

    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_user1"
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_user2"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConversationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user1", "user2"], name="unique_conversation_pair"),
            models.CheckConstraint(condition=Q(user1__lt=models.F("user2")), name="user1_lt_user2"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user1} <-> {self.user2}"

    @classmethod
    def get_or_create_between(cls, user_a, user_b):
        """Ikki user o'rtasidagi suhbatni topadi yoki yaratadi (tartib muhim emas)."""
        if user_a.pk == user_b.pk:
            raise ValueError("User o'zi bilan suhbat ocha olmaydi.")
        first, second = sorted([user_a, user_b], key=lambda u: u.pk)
        conversation, _ = cls.objects.get_or_create(user1=first, user2=second)
        return conversation

    def has_participant(self, user) -> bool:
        return user.pk in (self.user1_id, self.user2_id)

    def other_user(self, user):
        return self.user2 if user.pk == self.user1_id else self.user1


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            # "Menga kelgan o'qilmagan xabarlar" so'rovini tezlashtiradi
            models.Index(fields=["conversation", "is_read"]),
        ]

    def __str__(self) -> str:
        return f"{self.sender}: {self.content[:30]}"
