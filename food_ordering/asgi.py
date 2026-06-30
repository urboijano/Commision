import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'food_ordering.settings')

django_asgi_app = get_asgi_application()

from customer.routing import websocket_urlpatterns

from django.conf import settings

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

if settings.DEBUG:
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    application = ASGIStaticFilesHandler(application)
else:
    from whitenoise import WhiteNoise
    application = WhiteNoise(application, root=settings.STATIC_ROOT)
