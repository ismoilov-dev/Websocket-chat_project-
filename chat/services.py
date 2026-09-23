"""
Biznes-logika shu yerda. Uni ham REST API view'lari, ham WebSocket consumer
ishlatadi - kod takrorlanmaydi (DRY).
"""
from django.utils import timezone

from .models import Conversation, Message

MAX_MESSAGE_LENGTH = 2000


def create_message(conversation: Conversation, sender, content: str) -> Message:
    content = (content or "").strip()
    if not content:
        raise ValueError("Xabar bo'sh bo'lishi mumkin emas.")
    if len(content) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Xabar {MAX_MESSAGE_LENGTH} belgidan oshmasligi kerak.")

    message = Message.objects.create(conversation=conversation, sender=sender, content=content)
    # updated_at yangilanadi -> suhbatlar ro'yxatini "oxirgi faollik" bo'yicha saralash mumkin
    conversation.save(update_fields=["updated_at"])
    return message


def mark_conversation_read(conversation: Conversation, reader) -> list[int]:
    """
    `reader`ga kelgan (ya'ni boshqa user yuborgan) o'qilmagan xabarlarni
    o'qilgan deb belgilaydi. O'zgargan xabarlar id'larini qaytaradi.
    """
    unread = conversation.messages.filter(is_read=False).exclude(sender=reader)
    ids = list(unread.values_list("id", flat=True))
    if ids:
        Message.objects.filter(id__in=ids).update(is_read=True, read_at=timezone.now())
    return ids


def serialize_message(message: Message) -> dict:
    """WebSocket orqali yuborish uchun JSON-ga mos dict (serializer bilan bir xil format)."""
    return {
        "id": message.id,
        "conversation": message.conversation_id,
        "sender": message.sender_id,
        "sender_username": message.sender.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "is_read": message.is_read,
        "read_at": message.read_at.isoformat() if message.read_at else None,
    }
