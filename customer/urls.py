from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('api/auth/register/', views.register, name='register'),
    path('api/auth/login/', views.login, name='login'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/auth/me/', views.me, name='me'),
    path('api/menu/', views.menu_list, name='menu-list'),
    path('api/cart/', views.get_cart, name='cart'),
    path('api/cart/add/', views.add_to_cart, name='cart-add'),
    path('api/cart/item/<uuid:cart_item_id>/', views.update_cart_item, name='cart-item-update'),
    path('api/cart/clear/', views.clear_cart, name='cart-clear'),
    path('api/orders/', views.my_orders, name='my-orders'),
    path('api/orders/place/', views.place_order, name='place-order'),
    path('api/orders/<uuid:order_id>/', views.order_detail, name='order-detail'),
    path('api/orders/<uuid:order_id>/track/', views.track_order, name='track-order'),
    path('api/feedback/', views.submit_feedback, name='submit-feedback'),
    path('api/seed/menu/', views.seed_menu, name='seed-menu'),
    path('api/seed/ids/', views.seed_valid_ids, name='seed-ids'),
    path('api/admin/orders/<uuid:order_id>/status/', views.force_order_status, name='force-order-status'),

    path('', views.landing_page, name='landing'),
    path('login/', views.login_page, name='login-page'),
    path('register/', views.register_page, name='register-page'),
    path('menu/', views.menu_page, name='menu-page'),
    path('cart/', views.cart_page, name='cart-page'),
    path('orders/', views.my_orders_page, name='my-orders-page'),
    path('order/<uuid:order_id>/', views.order_confirmation_page, name='order-confirmation-page'),
    path('order/<uuid:order_id>/track/', views.order_tracking_page, name='order-tracking-page'),
    path('order/<uuid:order_id>/feedback/', views.feedback_page, name='feedback-page'),
]
