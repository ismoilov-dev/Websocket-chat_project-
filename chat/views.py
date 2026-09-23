from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Conversation
from .serializers import MessageSerializer, UserSerializer
from .services import mark_conversation_read

User = get_user_model()

HISTORY_PAGE_SIZE = 50


# ---------------------------------------------------------------------------
# HTML sahifa
# ---------------------------------------------------------------------------
@login_required
def index(request):
    """Chat sahifasi. Qolgan hamma narsani JavaScript API va WebSocket orqali oladi."""
    return render(request, "chat/index.html")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
class UserListAPIView(generics.ListAPIView):
    """
    GET /api/users/
    Menden boshqa barcha userlar + har biridan menga kelgan o'qilmagan xabarlar soni.
    """

    serializer_class = UserSerializer

    def get_queryset(self):
        me = self.request.user
        unread_filter = (
            Q(sent_messages__is_read=False)
            & (Q(sent_messages__conversation__user1=me) | Q(sent_messages__conversation__user2=me))
        )
        return (
            User.objects.filter(is_active=True)
            .exclude(pk=me.pk)
            .annotate(unread_count=Count("sent_messages", filter=unread_filter))
            .order_by("-active_connections", "username")
        )


class ConversationMixin:
    """URL'dagi user_id bo'yicha suhbatdoshni va suhbatni topadi."""

    def get_conversation(self):
        other = get_object_or_404(User, pk=self.kwargs["user_id"], is_active=True)
        if other.pk == self.request.user.pk:
            raise ValidationError("O'zingiz bilan suhbat ocha olmaysiz.")
        return Conversation.get_or_create_between(self.request.user, other)


class MessageHistoryAPIView(ConversationMixin, generics.ListAPIView):
    """
    GET /api/chat/<user_id>/messages/?before=<message_id>
    Oxirgi 50 ta xabar. `before` berilsa - undan oldingi 50 ta (eski xabarlarni yuklash).
    """

    serializer_class = MessageSerializer

    def get_queryset(self):
        conversation = self.get_conversation()
        qs = conversation.messages.select_related("sender")
        before = self.request.query_params.get("before")
        if before:
            if not before.isdigit():
                raise ValidationError({"before": "Butun son bo'lishi kerak."})
            qs = qs.filter(id__lt=int(before))
        # Eng yangi 50 tasini olib, keyin vaqt bo'yicha o'sish tartibida qaytaramiz
        latest = list(qs.order_by("-created_at", "-id")[:HISTORY_PAGE_SIZE])
        return list(reversed(latest))


class MarkReadAPIView(ConversationMixin, APIView):
    """
    POST /api/chat/<user_id>/read/
    WebSocket ishlamay qolsa ham xabarlarni o'qilgan deb belgilash uchun zaxira yo'l.
    """

    def post(self, request, user_id):
        ids = mark_conversation_read(self.get_conversation(), request.user)
        return Response({"marked_read": ids})
