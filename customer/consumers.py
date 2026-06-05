import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        if self.user and self.user.is_authenticated:
            self.group_name = f"user_{self.user.user_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def order_status_update(self, event):
        await self.send(text_data=json.dumps(event['data']))


def notify_order_status_change(order):
    channel_layer = get_channel_layer()
    user_id_str = str(order.user.user_id)
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id_str}",
        {
            'type': 'order_status_update',
            'data': {
                'order_id': str(order.order_id),
                'order_number': order.order_number,
                'status': order.status,
                'message': f"Order {order.order_number} is now: {order.get_status_display()}",
            }
        }
    )
