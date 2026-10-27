import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Message

logger = logging.getLogger(__name__)

User = get_user_model()

MAX_MESSAGE_LENGTH = 5000
HISTORY_LIMIT = 100


class PrivateChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Private real-time chat between authenticated staff members.

    WebSocket URL:
        /ws/chat/<user_id>/
    """

    async def connect(self):
        self.user = self.scope["user"]

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in self.scope.get("headers", [])
        }

        logger.info(
            "CHAT WS CONNECT | path=%s | authenticated=%s | "
            "user_id=%s | origin=%s | host=%s",
            self.scope.get("path"),
            self.user.is_authenticated,
            self.user.pk if self.user.is_authenticated else None,
            headers.get("origin"),
            headers.get("host"),
        )

        if not self.user.is_authenticated:
            logger.warning("CHAT WS REJECTED: anonymous user")
            await self.close(code=4001)
            return

        try:
            self.other_user_id = int(
                self.scope["url_route"]["kwargs"]["user_id"]
            )
        except (KeyError, TypeError, ValueError):
            await self.close(code=4000)
            return

        self.user_group = f"chat_user_{self.user.pk}"

        try:
            # Join before reading history so incoming events are not missed.
            await self.channel_layer.group_add(
                self.user_group,
                self.channel_name,
            )

            await self.accept()

            logger.info(
                "CHAT WS ACCEPTED | user=%s | recipient=%s",
                self.user.pk,
                self.other_user_id,
            )

            # If connecting to a specific recipient (not self), load history & mark read
            if self.other_user_id != self.user.pk:
                read_ids = await self.mark_messages_read(
                    sender_id=self.other_user_id,
                )

                if read_ids:
                    await self.channel_layer.group_send(
                        f"chat_user_{self.other_user_id}",
                        {
                            "type": "chat_read_receipt",
                            "message_ids": read_ids,
                            "reader_id": self.user.pk,
                        },
                    )

                messages = await self.get_history(self.other_user_id)

                await self.send_json({
                    "type": "chat_history",
                    "messages": messages,
                })

        except Exception:
            logger.exception("CHAT WS ERROR during connection setup")
            await self.close(code=1011)

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(
                self.user_group,
                self.channel_name,
            )

        logger.info(
            "CHAT WS DISCONNECTED | user=%s | code=%s",
            getattr(getattr(self, "user", None), "pk", None),
            close_code,
        )

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.send_error("Invalid message format.")
            return

        message_type = content.get("type")

        if message_type == "mark_read":
            message_ids = content.get("message_ids", [])

            if not isinstance(message_ids, list):
                await self.send_error("message_ids must be a list.")
                return

            message_ids = [
                message_id
                for message_id in message_ids[:HISTORY_LIMIT]
                if isinstance(message_id, (int, str))
                and str(message_id).isdigit()
            ]

            read_ids = await self.mark_specific_messages_read(
                message_ids=message_ids,
                sender_id=self.other_user_id,
            )

            if read_ids:
                await self.channel_layer.group_send(
                    f"chat_user_{self.other_user_id}",
                    {
                        "type": "chat_read_receipt",
                        "message_ids": read_ids,
                        "reader_id": self.user.pk,
                    },
                )

            return

        text = content.get("message", "")

        if not isinstance(text, str):
            await self.send_error("Message must be text.")
            return

        text = text.strip()

        if not text:
            await self.send_error("Message cannot be empty.")
            return

        if len(text) > MAX_MESSAGE_LENGTH:
            await self.send_error(
                f"Message cannot exceed {MAX_MESSAGE_LENGTH} characters."
            )
            return

        if self.other_user_id == self.user.pk:
            await self.send_error("Cannot send message to yourself.")
            return

        saved = await self.save_message(
            sender_id=self.user.pk,
            recipient_id=self.other_user_id,
            content=text,
        )

        if saved is None:
            await self.send_error("Recipient not found or inactive.")
            return

        message_data = {
            "id": saved["id"],
            "sender_id": self.user.pk,
            "recipient_id": self.other_user_id,
            "sender_name": await self.get_display_name(self.user.pk),
            "message": saved["content"],
            "sent_at": saved["sent_at"],
            "is_read": False,
        }

        # Send to the recipient's active WebSocket connections.
        await self.channel_layer.group_send(
            f"chat_user_{self.other_user_id}",
            {
                "type": "chat_message",
                "message_data": message_data,
            },
        )

        # Confirm to the sender.
        await self.send_json({
            "type": "chat_message",
            "message_data": message_data,
        })

    async def chat_message(self, event):
        message_data = event["message_data"]

        # 1. If this message is directed to me (recipient_id == my_id)
        if message_data["recipient_id"] == self.user.pk:
            # If the socket is open specifically with this sender, mark as read
            if message_data["sender_id"] == self.other_user_id:
                was_marked_read = await self.mark_single_message_read(
                    message_id=message_data["id"],
                    sender_id=self.other_user_id,
                )

                if was_marked_read:
                    await self.channel_layer.group_send(
                        f"chat_user_{self.other_user_id}",
                        {
                            "type": "chat_read_receipt",
                            "message_ids": [message_data["id"]],
                            "reader_id": self.user.pk,
                        },
                    )

                    message_data["is_read"] = True

            # Deliver the message payload over WebSocket to trigger background notification!
            await self.send_json({
                "type": "chat_message",
                "message_data": message_data,
            })
            return

        # 2. If I am the sender and this socket is open with the recipient
        if message_data["sender_id"] == self.user.pk and message_data["recipient_id"] == self.other_user_id:
            await self.send_json({
                "type": "chat_message",
                "message_data": message_data,
            })

    async def chat_read_receipt(self, event):
        reader_id = event.get("reader_id")

        if reader_id != self.other_user_id:
            return

        await self.send_json({
            "type": "chat_read_receipt",
            "message_ids": event.get("message_ids", []),
            "reader_id": reader_id,
        })

    async def send_error(self, message):
        await self.send_json({
            "type": "error",
            "message": message,
        })

    @database_sync_to_async
    def user_exists(self, user_id):
        return User.objects.filter(
            pk=user_id,
            is_active=True,
        ).exists()

    @database_sync_to_async
    def get_display_name(self, user_id):
        user = User.objects.filter(pk=user_id).first()

        if user is None:
            return "Unknown user"

        return (
            getattr(user, "full_name", None)
            or user.get_username()
        )

    @database_sync_to_async
    def get_history(self, other_user_id):
        queryset = (
            Message.objects.filter(
                Q(
                    sender_id=self.user.pk,
                    recipient_id=other_user_id,
                )
                | Q(
                    sender_id=other_user_id,
                    recipient_id=self.user.pk,
                )
            )
            .select_related("sender")
            .order_by("-sent_at", "-pk")[:HISTORY_LIMIT]
        )

        messages = list(reversed(list(queryset)))

        return [
            {
                "id": message.pk,
                "sender_id": message.sender_id,
                "recipient_id": message.recipient_id,
                "sender_name": (
                    getattr(message.sender, "full_name", None)
                    or message.sender.get_username()
                ),
                "message": message.content,
                "sent_at": message.sent_at.isoformat(),
                "is_read": message.is_read,
            }
            for message in messages
        ]

    @database_sync_to_async
    def save_message(self, sender_id, recipient_id, content):
        recipient = User.objects.filter(
            pk=recipient_id,
            is_active=True,
        ).first()

        if recipient is None:
            return None

        message = Message.objects.create(
            sender_id=sender_id,
            recipient=recipient,
            content=content,
        )

        return {
            "id": message.pk,
            "content": message.content,
            "sent_at": message.sent_at.isoformat(),
        }

    @database_sync_to_async
    def mark_messages_read(self, sender_id):
        queryset = Message.objects.filter(
            sender_id=sender_id,
            recipient_id=self.user.pk,
            is_read=False,
        )

        message_ids = list(
            queryset.values_list("pk", flat=True)
        )

        if message_ids:
            queryset.update(is_read=True)

        return message_ids

    @database_sync_to_async
    def mark_single_message_read(self, message_id, sender_id):
        updated = Message.objects.filter(
            pk=message_id,
            sender_id=sender_id,
            recipient_id=self.user.pk,
            is_read=False,
        ).update(is_read=True)

        return updated > 0

    @database_sync_to_async
    def mark_specific_messages_read(self, message_ids, sender_id):
        if not message_ids:
            return []

        queryset = Message.objects.filter(
            pk__in=message_ids,
            sender_id=sender_id,
            recipient_id=self.user.pk,
            is_read=False,
        )

        read_ids = list(queryset.values_list("pk", flat=True))

        if read_ids:
            queryset.update(is_read=True)

        return read_ids