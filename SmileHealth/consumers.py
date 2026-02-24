import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        from django.contrib.auth.models import User

        user = self.scope["user"]
        print(f"ChatConsumer connect called. User: {user}, authenticated: {user.is_authenticated}")

        if not user.is_authenticated:
            print("User not authenticated, closing connection")
            await self.close()
            return

        self.user = user
        self.receiver_id = int(self.scope['url_route']['kwargs']['receiver_id'])
        self.room_group_name = f"chat_{min(self.user.id, self.receiver_id)}_{max(self.user.id, self.receiver_id)}"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Send chat history
        messages_data = await self.get_serialized_chat_history(self.user.id, self.receiver_id)
        for message in messages_data:
            await self.send(text_data=json.dumps(message))

    async def disconnect(self, close_code):
        print(f"Disconnecting user {self.user} from room {self.room_group_name}")
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        from django.contrib.auth.models import User

        data = json.loads(text_data)
        message = data.get('message', '').strip()
        if not message:
            return  # ignore empty messages

        # Save message in DB
        msg = await self.save_message(self.user.id, self.receiver_id, message)

        # Broadcast message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'message_id': msg.id,
            }
        )

    async def chat_message(self, event):
        if self.user.id != event['sender_id']:
            await self.mark_message_read(event.get('message_id'))
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'message_id': event.get('message_id'),
        }))

    @database_sync_to_async
    def get_serialized_chat_history(self, user1_id, user2_id):
        from .models import Message
        messages = Message.objects.filter(
            sender_id__in=[user1_id, user2_id],
            receiver_id__in=[user1_id, user2_id]
        ).select_related('sender').order_by('timestamp')

        Message.objects.filter(
            sender_id=user2_id,
            receiver_id=user1_id,
            is_read=False
        ).update(is_read=True)

        return [
            {
                'message': msg.content,
                'sender_id': msg.sender.id,
                'sender_username': msg.sender.username,
                'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for msg in messages
        ]

    @database_sync_to_async
    def save_message(self, sender_id, receiver_id, content):
        from django.contrib.auth.models import User
        from .models import Message
        sender = User.objects.get(id=sender_id)
        receiver = User.objects.get(id=receiver_id)
        return Message.objects.create(sender=sender, receiver=receiver, content=content)

    @database_sync_to_async
    def mark_message_read(self, message_id):
        if not message_id:
            return 0
        from .models import Message
        return Message.objects.filter(id=message_id).update(is_read=True)
