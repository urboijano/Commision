import json
import random
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.contrib.auth import authenticate, login as django_login
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    User, ValidID, PasswordResetCode, MenuItem, Cart, CartItem,
    Order, OrderItem, OrderStatusHistory, Feedback
)
from .serializers import (
    RegisterSerializer, StoreRegisterSerializer, LoginSerializer, UserSerializer,
    MenuItemSerializer, CartSerializer, CartItemSerializer,
    AddCartItemSerializer, UpdateCartItemSerializer,
    OrderSerializer, FeedbackSerializer, CreateFeedbackSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer
)
from .consumers import notify_order_status_change


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    id_record = ValidID.objects.filter(
        id_value=data['student_faculty_id'],
        user_type=data['user_type'],
        is_used=False
    ).first()

    if not id_record:
        return Response(
            {'error': 'Invalid ID. Please verify your credentials and try again.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email=data['email']).exists():
        return Response(
            {'error': 'An account with this email already exists.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        id_record.is_used = True
        id_record.save()

        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=data['password'],
            full_name=data['full_name'],
            user_type=data['user_type'],
            student_faculty_id=data['student_faculty_id'],
        )

        Cart.objects.create(user=user)

    django_login(request, user)

    tokens = get_tokens_for_user(user)
    return Response({
        'user': UserSerializer(user).data,
        'tokens': tokens,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def store_register(request):
    serializer = StoreRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    if User.objects.filter(email=data['email']).exists():
        return Response(
            {'error': 'An account with this email already exists.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create_user(
        username=data['email'],
        email=data['email'],
        password=data['password'],
        full_name=data['full_name'],
        store_name=data['store_name'],
        user_type='store_owner',
        student_faculty_id=None,
    )

    django_login(request, user)

    tokens = get_tokens_for_user(user)
    return Response({
        'user': UserSerializer(user).data,
        'tokens': tokens,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    serializer = ForgotPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'No account found with this email.'}, status=status.HTTP_400_BAD_REQUEST)

    PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)

    code = f"{random.randint(100000, 999999)}"
    PasswordResetCode.objects.create(user=user, code=code)

    return Response({'message': 'Reset code sent.', 'code': code})


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    serializer = ResetPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        user = User.objects.get(email=data['email'])
    except User.DoesNotExist:
        return Response({'error': 'Invalid request.'}, status=status.HTTP_400_BAD_REQUEST)

    reset_code = PasswordResetCode.objects.filter(
        user=user, code=data['code'], is_used=False
    ).first()

    if not reset_code:
        return Response({'error': 'Invalid or expired reset code.'}, status=status.HTTP_400_BAD_REQUEST)

    reset_code.is_used = True
    reset_code.save()

    user.set_password(data['password'])
    user.save()

    return Response({'message': 'Password reset successfully.'})


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    user = authenticate(username=data['email'], password=data['password'])

    if not user:
        return Response(
            {'error': 'Invalid email or password.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    django_login(request, user)

    tokens = get_tokens_for_user(user)
    return Response({
        'user': UserSerializer(user).data,
        'tokens': tokens,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def menu_list(request):
    category = request.query_params.get('category')
    items = MenuItem.objects.filter(is_available=True)
    if category:
        items = items.filter(category=category)
    serializer = MenuItemSerializer(items, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cart(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    serializer = CartSerializer(cart)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    serializer = AddCartItemSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    menu_item = get_object_or_404(MenuItem, item_id=data['item_id'], is_available=True)

    cart, _ = Cart.objects.get_or_create(user=request.user)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        item=menu_item,
        defaults={'quantity': data['quantity']}
    )
    if not created:
        cart_item.quantity += data['quantity']
        cart_item.save()

    return Response(CartSerializer(cart).data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_cart_item(request, cart_item_id):
    cart_item = get_object_or_404(CartItem, cart_item_id=cart_item_id, cart__user=request.user)
    serializer = UpdateCartItemSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    qty = serializer.validated_data['quantity']
    if qty == 0:
        cart_item.delete()
    else:
        cart_item.quantity = qty
        cart_item.save()

    cart = Cart.objects.get(user=request.user)
    return Response(CartSerializer(cart).data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_cart(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart.items.all().delete()
    return Response({'message': 'Cart cleared.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_order(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = CartItem.objects.filter(cart=cart).select_related('item')

    if not cart_items.exists():
        return Response(
            {'error': 'Your cart is empty.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    for ci in cart_items:
        if not ci.item.is_available:
            return Response(
                {'error': f'{ci.item.name} is no longer available.'},
                status=status.HTTP_400_BAD_REQUEST
            )

    with transaction.atomic():
        total = sum(ci.item.price * ci.quantity for ci in cart_items)
        order = Order.objects.create(
            user=request.user,
            total_amount=total,
        )

        for ci in cart_items:
            OrderItem.objects.create(
                order=order,
                item=ci.item,
                item_name=ci.item.name,
                unit_price=ci.item.price,
                quantity=ci.quantity,
                subtotal=ci.item.price * ci.quantity,
            )

        OrderStatusHistory.objects.create(
            order=order,
            status='received',
            changed_by='customer',
        )

        cart.items.all().delete()

    serializer = OrderSerializer(order)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_orders(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items', 'status_history')
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    serializer = OrderSerializer(order)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def track_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    history = OrderStatusHistory.objects.filter(order=order).order_by('changed_at')
    return Response({
        'order_number': order.order_number,
        'current_status': order.status,
        'status_history': [
            {
                'status': h.status,
                'changed_at': h.changed_at.isoformat(),
                'changed_by': h.changed_by,
            }
            for h in history
        ],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_feedback(request):
    serializer = CreateFeedbackSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    order = get_object_or_404(Order, order_id=data['order_id'], user=request.user)

    if order.status != 'completed':
        return Response(
            {'error': 'Feedback can only be submitted for completed orders.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if hasattr(order, 'feedback'):
        return Response(
            {'error': 'Feedback for this order has already been submitted.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    feedback = Feedback.objects.create(
        order=order,
        user=request.user,
        rating=data['rating'],
        satisfaction_level=data['satisfaction_level'],
        comments=data.get('comments', ''),
    )

    return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def seed_menu(request):
    if MenuItem.objects.exists():
        return Response({'message': 'Menu already seeded.'})

    items = [
        MenuItem(name='Chicken Rice Meal', price=65.00, category='rice', is_available=True),
        MenuItem(name='Pork Adobo Rice', price=70.00, category='rice', is_available=True),
        MenuItem(name='Beef Steak Rice', price=85.00, category='rice', is_available=True),
        MenuItem(name='Vegetable Stir Fry Rice', price=55.00, category='rice', is_available=True),
        MenuItem(name='Pancit Canton', price=50.00, category='noodles', is_available=True),
        MenuItem(name='Spaghetti', price=60.00, category='noodles', is_available=True),
        MenuItem(name='Lomi', price=55.00, category='noodles', is_available=True),
        MenuItem(name='Iced Tea', price=25.00, category='drinks', is_available=True),
        MenuItem(name='Bottled Water', price=15.00, category='drinks', is_available=True),
        MenuItem(name='Coffee', price=30.00, category='drinks', is_available=True),
        MenuItem(name='Fruit Shake', price=45.00, category='drinks', is_available=True),
        MenuItem(name='Lumpia Shanghai (6 pcs)', price=35.00, category='snacks', is_available=True),
        MenuItem(name='Siomai (4 pcs)', price=30.00, category='snacks', is_available=True),
        MenuItem(name='Leche Flan', price=40.00, category='desserts', is_available=True),
        MenuItem(name='Buko Pandan', price=35.00, category='desserts', is_available=True),
    ]
    MenuItem.objects.bulk_create(items)
    return Response({'message': f'{len(items)} menu items created.'})


@api_view(['POST'])
@permission_classes([AllowAny])
def seed_valid_ids(request):
    ids = [
        ValidID(id_value='00-00001', user_type='student'),
        ValidID(id_value='00-00002', user_type='student'),
        ValidID(id_value='00-00003', user_type='student'),
        ValidID(id_value='F-0001', user_type='faculty'),
        ValidID(id_value='F-0002', user_type='faculty'),
    ]
    for vid in ids:
        ValidID.objects.get_or_create(id_value=vid.id_value, defaults={'user_type': vid.user_type})
    return Response({'message': 'Valid IDs seeded.'})


@api_view(['POST'])
@permission_classes([AllowAny])
def force_order_status(request, order_id):
    status_val = request.data.get('status')
    if status_val not in dict(Order.STATUS_CHOICES):
        return Response({'error': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)

    order = get_object_or_404(Order, order_id=order_id)

    valid_transitions = {
        'received': ['preparing'],
        'preparing': ['ready_for_pickup'],
        'ready_for_pickup': ['completed'],
    }

    if order.status != status_val:
        allowed = valid_transitions.get(order.status, [])
        if status_val not in allowed and status_val != 'cancelled':
            return Response(
                {'error': f'Cannot transition from {order.status} to {status_val}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = status_val
        if status_val == 'completed':
            order.payment_status = 'paid'
        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=status_val,
            changed_by='cashier',
        )

        notify_order_status_change(order)

    return Response(OrderSerializer(order).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_orders(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    orders = Order.objects.all().prefetch_related('items', 'status_history', 'user').order_by('-created_at')
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_update_order_status(request, order_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    status_val = request.data.get('status')
    if status_val not in dict(Order.STATUS_CHOICES):
        return Response({'error': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)

    order = get_object_or_404(Order, order_id=order_id)

    valid_transitions = {
        'received': ['preparing'],
        'preparing': ['ready_for_pickup'],
    }

    if order.status != status_val:
        allowed = valid_transitions.get(order.status, [])
        if status_val not in allowed and status_val != 'cancelled':
            return Response(
                {'error': f'Cannot transition from {order.status} to {status_val}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = status_val
        if status_val == 'completed':
            order.payment_status = 'paid'
        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=status_val,
            changed_by='store_owner',
        )

        notify_order_status_change(order)

    return Response(OrderSerializer(order).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_create_menu_item(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = MenuItemSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def store_update_menu_item(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id)
    serializer = MenuItemSerializer(item, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def store_delete_menu_item(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id)
    item.delete()
    return Response({'message': 'Menu item deleted.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_all_menu_items(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    items = MenuItem.objects.all().order_by('name')
    serializer = MenuItemSerializer(items, many=True)
    return Response(serializer.data)


@ensure_csrf_cookie
def landing_page(request):
    menu_items = MenuItem.objects.filter(is_available=True)[:8]
    categories = MenuItem.CATEGORY_CHOICES
    return render(request, 'landing.html', {
        'menu_items': menu_items,
        'categories': categories,
    })


@ensure_csrf_cookie
def login_page(request):
    return render(request, 'login.html')


@ensure_csrf_cookie
def register_page(request):
    return render(request, 'register.html')


@ensure_csrf_cookie
def forgot_password_page(request):
    return render(request, 'forgot_password.html')


@ensure_csrf_cookie
def reset_password_page(request):
    return render(request, 'reset_password.html')


@ensure_csrf_cookie
def store_register_page(request):
    return render(request, 'store_register.html')


@login_required
def store_dashboard_page(request):
    if request.user.user_type != 'store_owner':
        return render(request, 'store_register.html')
    return render(request, 'store_dashboard.html')


@login_required
def menu_page(request):
    return render(request, 'menu.html')


@login_required
def cart_page(request):
    return render(request, 'cart_review.html')


@login_required
def order_confirmation_page(request, order_id):
    return render(request, 'order_confirmation.html', {'order_id': order_id})


@login_required
def order_tracking_page(request, order_id):
    return render(request, 'order_tracking.html', {'order_id': order_id})


@login_required
def feedback_page(request, order_id):
    return render(request, 'feedback.html', {'order_id': order_id})


@login_required
def my_orders_page(request):
    return render(request, 'my_orders.html')
