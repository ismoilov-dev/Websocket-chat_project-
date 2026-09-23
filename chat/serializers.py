from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Message

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)
    # View'dagi .annotate(unread_count=...) dan keladi
    unread_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = User
        fields = ("id", "username", "full_name", "is_online", "last_seen", "unread_count")

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "conversation",
            "sender",
            "sender_username",
            "content",
            "created_at",
            "is_read",
            "read_at",
        )
        read_only_fields = fields
