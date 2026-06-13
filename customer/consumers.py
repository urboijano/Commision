import json
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
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

    if order.status == 'ready_for_pickup' and order.user.user_type in ('student', 'faculty'):
        stores = order.items.filter(store__isnull=False).values_list('store__name', flat=True).distinct()
        store_names = list(stores)
        stores_text = ', '.join(store_names) if store_names else 'the store'

        eta_html = ''
        if order.estimated_ready_at:
            eta = order.estimated_ready_at
            if timezone.is_aware(eta):
                eta = timezone.localtime(eta)
            eta_html = f'<p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Estimated ready time: {eta.strftime("%B %d, %Y at %I:%M %p")}</p>'

        html_content = f'''
    <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
      <div style="background:#1a1a1a;padding:1.5rem;text-align:center;">
        <span style="font-size:1.4rem;font-weight:800;color:#ccff00;">KaonISU</span>
      </div>
      <div style="padding:1.5rem;">
        <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a1a;margin:0 0 0.5rem;">Order Ready for Pickup!</h2>
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Hi {order.user.full_name},</p>
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Your order <strong>{order.order_number}</strong> from {stores_text} is now ready for pickup!</p>
        {eta_html}
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Total amount: <strong>&#8369;{order.total_amount}</strong></p>
        <p style="font-size:0.85rem;color:#6b7280;margin:0.5rem 0 0;">Please proceed to the store to pick up your order. Thank you for choosing KaonISU!</p>
      </div>
      <div style="background:#f9fafb;padding:1rem;text-align:center;border-top:1px solid #f0f0f0;">
        <span style="font-size:0.75rem;color:#9ca3af;">&copy; 2026 KaonISU. All rights reserved.</span>
      </div>
    </div>
    '''
        text_content = f'Hi {order.user.full_name}, your order {order.order_number} from {stores_text} is now ready for pickup! Please proceed to the store.'

        try:
            msg = EmailMultiAlternatives(
                f'Order Ready for Pickup - {order.order_number}',
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [order.user.email],
            )
            msg.attach_alternative(html_content, 'text/html')
            msg.send(fail_silently=False)
        except Exception:
            pass
