import json
from urllib.parse import parse_qs
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from rest_framework_simplejwt.tokens import AccessToken
from .models import User


class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query_string = self.scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]
        if token:
            try:
                access = AccessToken(token)
                user = User.objects.get(user_id=access['user_id'])
                self.scope['user'] = user
            except Exception:
                pass
        self.user = self.scope.get('user')
        if self.user and self.user.is_authenticated:
            self.group_name = f"user_{self.user.user_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.channel_layer.group_add('menu_updates', self.channel_name)
            if self.user.user_type == 'admin':
                await self.channel_layer.group_add('admin', self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            await self.channel_layer.group_discard('menu_updates', self.channel_name)

    async def receive(self, text_data):
        pass

    async def order_status_update(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def new_registration(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def menu_updated(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def store_approval_request(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def store_approved(self, event):
        await self.send(text_data=json.dumps(event['data']))


def _send_to_group(group_name, data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {'type': 'order_status_update', 'data': data}
    )


def notify_admin_new_registration(user_data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'admin',
        {
            'type': 'new_registration',
            'data': {
                'type': 'new_registration',
                'message': f'New {user_data.get("user_type", "user")} registration: {user_data.get("full_name", "Unknown")}',
            }
        }
    )


def notify_store_approved(store):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{store.owner.user_id}",
        {
            'type': 'store_approved',
            'data': {
                'type': 'store_approved',
                'store_id': store.store_id,
                'store_name': store.name,
                'message': f'Your store "{store.name}" has been approved!',
            }
        }
    )


def notify_admin_new_store(store_data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'admin',
        {
            'type': 'store_approval_request',
            'data': {
                'type': 'store_approval_request',
                'message': f'New store needs approval: {store_data.get("store_name", "Unknown")} by {store_data.get("owner_name", "Unknown")}',
            }
        }
    )


def notify_store_new_order(order):
    store_owner_ids = set(
        order.items.filter(store_owner__isnull=False)
        .values_list('store_owner__user_id', flat=True)
    )
    data = {
        'type': 'new_order',
        'order_id': str(order.order_id),
        'order_number': order.order_number,
        'message': f'New order #{order.order_number} received!',
    }
    for uid in store_owner_ids:
        _send_to_group(f"user_{uid}", data)


def notify_order_status_change(order):
    data = {
        'order_id': str(order.order_id),
        'order_number': order.order_number,
        'status': order.status,
        'message': f"Order {order.order_number} is now: {order.get_status_display()}",
    }
    _send_to_group(f"user_{order.user.user_id}", data)

    store_owner_ids = set(
        order.items.filter(store_owner__isnull=False)
        .values_list('store_owner__user_id', flat=True)
    )
    for uid in store_owner_ids:
        _send_to_group(f"user_{uid}", data)

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


def notify_store_new_feedback(feedback):
    store_owner_ids = set(
        feedback.order.items.filter(store_owner__isnull=False)
        .values_list('store_owner__user_id', flat=True)
    )
    data = {
        'type': 'new_feedback',
        'feedback_id': str(feedback.feedback_id),
        'rating': feedback.rating,
        'satisfaction_level': feedback.satisfaction_level,
        'message': f'New feedback received — {feedback.rating}/5',
    }
    for uid in store_owner_ids:
        _send_to_group(f"user_{uid}", data)


def notify_menu_updated():
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'menu_updates',
        {
            'type': 'menu_updated',
            'data': {
                'type': 'menu_updated',
                'message': 'Menu availability updated',
            }
        }
    )
