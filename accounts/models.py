from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F
from django.utils import timezone


class User(AbstractUser):
    """
    Django'ning standart User modelini kengaytiramiz.

    Online/Offline status uchun ikkita maydon qo'shamiz:
    - active_connections: userning nechta ochiq tab/qurilmasi bor.
      Bitta user 2 ta tab ochsa va bittasini yopsa, u hali ham online.
    - last_seen: oxirgi marta qachon online bo'lgan.
    """

    active_connections = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(null=True, blank=True)

    @property
    def is_online(self) -> bool:
        return self.active_connections > 0

    # F() - qiymatni Python'da emas, to'g'ridan-to'g'ri DB ichida o'zgartiradi.
    # Ikki tab bir vaqtda ulansa ham "race condition" bo'lmaydi.
    @classmethod
    def mark_connected(cls, user_id: int) -> None:
        cls.objects.filter(pk=user_id).update(
            active_connections=F("active_connections") + 1,
            last_seen=timezone.now(),
        )

    @classmethod
    def mark_disconnected(cls, user_id: int) -> None:
        cls.objects.filter(pk=user_id, active_connections__gt=0).update(
            active_connections=F("active_connections") - 1,
            last_seen=timezone.now(),
        )

    def __str__(self) -> str:
        return self.username
