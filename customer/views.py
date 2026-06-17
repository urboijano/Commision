import io
import json
import random
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction, models
from django.db.models import Exists, OuterRef, Sum, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from PIL import Image
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    User, ValidID, PasswordResetCode, MenuItem, ItemVariation, Cart, CartItem,
    Order, OrderItem, OrderStatusHistory, Feedback, StoreProfile, Store,
    Discount, BundleDeal, BundleItem, StoreOwnerStatus,
)
from .consumers import notify_store_status_changed
from .serializers import (
    RegisterSerializer, StoreRegisterSerializer, LoginSerializer, UserSerializer,
    MenuItemSerializer, MenuItemDetailSerializer, CartSerializer, CartItemSerializer,
    AddCartItemSerializer, UpdateCartItemSerializer,
    OrderSerializer, FeedbackSerializer, CreateFeedbackSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer,
    StoreProfileSerializer, StoreProfileUpdateSerializer,
    ItemVariationSerializer,
    StoreOrderSerializer, StoreOrderItemSerializer,
    DiscountSerializer, BundleDealSerializer, ApplyDiscountSerializer,
    StoreSerializer, StoreUpdateSerializer,
)
from .consumers import notify_order_status_change, notify_store_new_order, notify_menu_updated, notify_admin_new_registration, notify_admin_new_store, notify_store_approved, notify_store_new_feedback


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def compress_image(uploaded_file, max_width=1200, quality=75):
    img = Image.open(uploaded_file)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    buf.seek(0)
    return InMemoryUploadedFile(
        buf, 'ImageField', uploaded_file.name.replace('.png', '.jpg').replace('.PNG', '.jpg'),
        'image/jpeg', buf.getbuffer().nbytes, None
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    faculty_id_image = request.FILES.get('faculty_id_image')

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                password=data['password'],
                full_name=data['full_name'],
                user_type=data['user_type'],
                student_faculty_id=data.get('student_faculty_id') or None,
                is_active=False,
            )
            if data['user_type'] == 'faculty' and faculty_id_image:
                user.faculty_id_image = compress_image(faculty_id_image)
                user.save()
            Cart.objects.create(user=user)
    except IntegrityError:
        return Response(
            {'error': 'An account with this email or ID already exists.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    notify_admin_new_registration(UserSerializer(user).data)
    return Response({
        'message': 'Registration submitted. Your account is pending admin approval.',
        'user': UserSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def store_register(request):
    serializer = StoreRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    dti_permit = request.FILES.get('dti_permit')

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                password=data['password'],
                full_name=data['full_name'],
                store_name=data['store_name'],
                user_type='store_owner',
                student_faculty_id=None,
                is_active=False,
            )
            if dti_permit:
                user.dti_permit = compress_image(dti_permit)
                user.save()
            StoreProfile.objects.create(
                user=user,
                store_name=data['store_name'],
                dti_permit=user.dti_permit if user.dti_permit else dti_permit,
            )
            store = Store.objects.create(
                owner=user,
                name=data['store_name'],
                dti_permit=user.dti_permit if user.dti_permit else dti_permit,
            )
    except IntegrityError:
        return Response(
            {'error': 'An account with this email already exists.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    notify_admin_new_registration(UserSerializer(user).data)
    return Response({
        'message': 'Registration submitted. Your account is pending admin approval.',
        'user': UserSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def store_profile(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    profile = get_object_or_404(StoreProfile, user=request.user)

    if request.method == 'GET':
        serializer = StoreProfileSerializer(profile)
        return Response(serializer.data)

    data = request.data.copy()
    for field in ['logo', 'banner']:
        if field in request.FILES:
            data[field] = request.FILES[field]
    serializer = StoreProfileUpdateSerializer(profile, data=data, partial=request.method == 'PATCH')
    if serializer.is_valid():
        serializer.save()
        return Response(StoreProfileSerializer(profile).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_toggle_open(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)

    store_id = request.session.get('active_store_id')
    if store_id:
        store = Store.objects.filter(store_id=store_id, owner=request.user).first()
    else:
        store = Store.objects.filter(owner=request.user).first()
    if not store:
        return Response({'error': 'No store found.'}, status=status.HTTP_404_NOT_FOUND)

    store.is_open = not store.is_open
    if store.is_open:
        store.closed_at = None
    else:
        store.closed_at = timezone.now()
    store.save(update_fields=['is_open', 'closed_at'])
    notify_store_status_changed(store.store_id, store.is_open, store.name, request.user.user_id)

    return Response({'is_open': store.is_open})


def get_active_store(request):
    store_id = request.session.get('active_store_id')
    if store_id:
        try:
            return Store.objects.get(store_id=store_id, owner=request.user, is_approved=True)
        except Store.DoesNotExist:
            pass
    return Store.objects.filter(owner=request.user, is_approved=True).first()


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def store_manage(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        stores = Store.objects.filter(owner=request.user, is_approved=True).order_by('name')
        return Response(StoreSerializer(stores, many=True).data)
    serializer = StoreUpdateSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        dti_permit = request.FILES.get('dti_permit')
        store = Store.objects.create(owner=request.user, **data)
        if dti_permit:
            store.dti_permit = compress_image(dti_permit)
            store.save()
        notify_admin_new_store({
            'store_id': store.store_id,
            'store_name': store.name,
            'owner_name': request.user.full_name,
            'owner_email': request.user.email,
        })
        return Response(StoreSerializer(store).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def store_manage_detail(request, store_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    store = get_object_or_404(Store, store_id=store_id, owner=request.user, is_approved=True)
    if request.method == 'GET':
        return Response(StoreSerializer(store).data)
    if request.method == 'PUT':
        serializer = StoreUpdateSerializer(store, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(StoreSerializer(store).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    store.delete()
    return Response({'message': 'Store deleted.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_switch(request, store_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    store = get_object_or_404(Store, store_id=store_id, owner=request.user, is_approved=True)
    request.session['active_store_id'] = store.store_id
    return Response({'store_id': store.store_id, 'store_name': store.name})


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

    html_content = f'''
    <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
      <div style="background:#1a1a1a;padding:1.5rem;text-align:center;">
        <span style="font-size:1.4rem;font-weight:800;color:#ccff00;">KaonISU</span>
      </div>
      <div style="padding:1.5rem;">
        <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a1a;margin:0 0 0.5rem;">Password Reset Code</h2>
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 1rem;">Use the code below to reset your password. This code is valid for a limited time.</p>
        <div style="background:#f3f4f6;border-radius:12px;padding:1rem;text-align:center;margin-bottom:1rem;">
          <span style="font-size:2rem;font-weight:800;letter-spacing:0.3em;color:#1a1a1a;">{code}</span>
        </div>
        <p style="font-size:0.8rem;color:#9ca3af;margin:0;">If you did not request a password reset, please ignore this email. Do not share this code with anyone.</p>
      </div>
      <div style="background:#f9fafb;padding:1rem;text-align:center;border-top:1px solid #f0f0f0;">
        <span style="font-size:0.75rem;color:#9ca3af;">&copy; 2026 KaonISU. All rights reserved.</span>
      </div>
    </div>
    '''
    text_content = f'Your password reset code is: {code}\n\nThis code is valid for a limited time. Do not share this with anyone.'
    msg = EmailMultiAlternatives(
        'Your Password Reset Code - KaonISU',
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send(fail_silently=False)

    return Response({'message': 'Reset code sent.'})


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
        try:
            existing_user = User.objects.get(email=data['email'])
            if not existing_user.is_active:
                msg = ('Your account is inactive. Please contact support.'
                       if existing_user.deactivated_at
                       else 'Your account is pending admin approval. Please wait for approval before logging in.')
                return Response({'error': msg}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            pass
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


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def logout(request):
    django_logout(request)
    return Response({'message': 'Logged out successfully.'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def menu_list(request):
    category = request.query_params.get('category')
    items = MenuItem.objects.filter(is_available=True, store__is_approved=True, store__is_open=True).select_related('store_owner')
    if category:
        items = items.filter(category=category)
    serializer = MenuItemSerializer(items, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def menu_item_detail(request, item_id):
    item = get_object_or_404(MenuItem.objects.filter(store__is_approved=True).select_related('store_owner'), item_id=item_id)
    serializer = MenuItemDetailSerializer(item)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cart(request):
    cart, _ = Cart.objects.prefetch_related('items__item').get_or_create(user=request.user)
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

    if menu_item.store and not menu_item.store.is_approved:
        return Response({'error': 'This store is not yet approved.'}, status=status.HTTP_400_BAD_REQUEST)

    cart, _ = Cart.objects.prefetch_related('items__item').get_or_create(user=request.user)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        item=menu_item,
        defaults={'quantity': data['quantity']}
    )
    if not created:
        cart_item.quantity += data['quantity']
        cart_item.save()

    cart = Cart.objects.prefetch_related('items__item').get(pk=cart.pk)
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

    cart = Cart.objects.prefetch_related('items__item').get(user=request.user)
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
    import uuid as uuid_mod
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = CartItem.objects.filter(cart=cart).select_related('item__store_owner', 'item__store')

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
        if ci.item.stock < ci.quantity:
            return Response(
                {'error': f'Not enough stock for {ci.item.name}. Available: {ci.item.stock}, requested: {ci.quantity}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

    from collections import defaultdict
    store_groups = defaultdict(list)
    for ci in cart_items:
        owner_id = ci.item.store_owner.user_id if ci.item.store_owner else None
        store_groups[owner_id].append(ci)

    group_id = uuid_mod.uuid4()
    orders = []

    with transaction.atomic():
        for owner_id, items in store_groups.items():
            total = sum(ci.item.price * ci.quantity for ci in items)
            store_owner = items[0].item.store_owner
            store_name = store_owner.store_name.strip() if store_owner and store_owner.store_name.strip() else 'Store'

            order = Order.objects.create(
                user=request.user,
                total_amount=total,
                parent_order_group=group_id,
            )

            for ci in items:
                OrderItem.objects.create(
                    order=order,
                    item=ci.item,
                    item_name=ci.item.name,
                    unit_price=ci.item.price,
                    quantity=ci.quantity,
                    subtotal=ci.item.price * ci.quantity,
                    store_owner=ci.item.store_owner,
                    store=ci.item.store,
                )

                ci.item.stock -= ci.quantity
                ci.item.save()

            OrderStatusHistory.objects.create(
                order=order,
                status='pending',
                changed_by=store_name,
            )

            orders.append(order)

        for order in orders:
            notify_store_new_order(order)

        notify_menu_updated()

        cart.items.all().delete()

    serializer = OrderSerializer(orders, many=True)
    return Response({
        'orders': serializer.data,
        'group_id': group_id,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_group(request, group_id):
    orders = Order.objects.filter(
        user=request.user, parent_order_group=group_id
    ).prefetch_related('items', 'status_history').order_by('created_at')
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_orders(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items', 'status_history')
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_completed_orders(request):
    completed = Order.objects.filter(user=request.user, status__in=['completed', 'store_rejected'])
    count = completed.count()
    completed.delete()
    return Response({'message': f'Cleared {count} order{"s" if count != 1 else ""}.', 'deleted_count': count})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.status not in ['pending', 'store_accepted']:
        return Response(
            {'error': 'This order can no longer be cancelled.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    order.status = 'cancelled'
    order.save()

    OrderStatusHistory.objects.create(
        order=order,
        status='cancelled',
        changed_by='customer',
    )

    notify_order_status_change(order)

    return Response(OrderSerializer(order).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def repeat_last_order(request):
    last_order = Order.objects.filter(user=request.user).order_by('-created_at').prefetch_related('items__item').first()
    if not last_order:
        return Response(
            {'error': 'No previous orders found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    order_items = list(last_order.items.all())
    if not order_items:
        return Response(
            {'error': 'Your last order has no items.'},
            status=status.HTTP_404_NOT_FOUND
        )

    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart.items.all().delete()

    skipped = []
    added = 0
    for oi in order_items:
        store_approved = not oi.item.store or oi.item.store.is_approved
        if oi.item and oi.item.is_available and store_approved:
            CartItem.objects.create(cart=cart, item=oi.item, quantity=oi.quantity)
            added += 1
        else:
            skipped.append(oi.item_name)

    if added == 0:
        cart.items.all().delete()
        return Response(
            {'error': 'None of the items from your last order are available right now.'},
            status=status.HTTP_404_NOT_FOUND
        )

    cart = Cart.objects.prefetch_related('items__item').get(pk=cart.pk)
    data = CartSerializer(cart).data
    if skipped:
        data['warning'] = f'Some items were unavailable and were skipped: {", ".join(skipped)}.'
    return Response(data)


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
        'rejection_reason': order.rejection_reason,
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

    notify_store_new_feedback(feedback)

    return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def seed_admin(request):
    if User.objects.filter(user_type='admin').exists():
        return Response({'message': 'Admin already exists.'})
    import uuid
    User.objects.create_superuser(
        username=f'admin-{uuid.uuid4().hex[:6]}',
        email='admin@kaonisu.com',
        password='admin123',
        full_name='System Admin',
        user_type='admin',
        student_faculty_id=None,
    )
    return Response({'message': 'Admin user created. Email: admin@kaoisu.com, Password: admin123'})


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
        'pending': ['store_accepted'],
        'store_accepted': ['preparing'],
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
    store = get_active_store(request)
    order_filter = {'items__store': store} if store else {'items__store_owner': request.user}
    orders = Order.objects.filter(
        **order_filter
    ).prefetch_related(
        'status_history', 'user'
    ).distinct().order_by('-created_at')

    data = []
    for order in orders:
        order_data = StoreOrderSerializer(order).data
        my_items = order.items.filter(store_owner=request.user)
        order_data['items'] = StoreOrderItemSerializer(my_items, many=True).data
        order_data['total_items'] = my_items.count()
        data.append(order_data)
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_update_order_status(request, order_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    status_val = request.data.get('status')
    if status_val not in dict(Order.STATUS_CHOICES):
        return Response({'error': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)

    order = get_object_or_404(
        Order.objects.filter(items__store_owner=request.user).distinct(),
        order_id=order_id
    )

    valid_transitions = {
        'pending': ['store_accepted', 'store_rejected'],
        'store_accepted': ['preparing'],
        'store_rejected': ['pending'],
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

        if status_val == 'store_rejected':
            reason = request.data.get('reason', '')
            order.rejection_reason = reason

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
def store_set_eta(request, order_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    order = get_object_or_404(
        Order.objects.filter(items__store_owner=request.user).distinct(),
        order_id=order_id
    )
    eta = request.data.get('estimated_ready_at')
    if not eta:
        return Response({'error': 'estimated_ready_at is required.'}, status=status.HTTP_400_BAD_REQUEST)
    from django.utils import dateparse
    parsed = dateparse.parse_datetime(eta)
    if not parsed:
        return Response({'error': 'Invalid datetime format. Use ISO 8601.'}, status=status.HTTP_400_BAD_REQUEST)
    order.estimated_ready_at = parsed
    order.save(update_fields=['estimated_ready_at'])
    return Response({'estimated_ready_at': parsed.isoformat()})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_analytics_summary(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    today = timezone.now().date()
    store = get_active_store(request)
    order_filter = {'items__store': store} if store else {'items__store_owner': request.user}
    item_filter = {'store': store} if store else {'store_owner': request.user}
    menu_filter = {'store': store} if store else {'store_owner': request.user}
    feedback_filter = {'order__items__store': store} if store else {'order__items__store_owner': request.user}

    store_orders_qs = Order.objects.filter(**order_filter).distinct()
    today_orders = store_orders_qs.filter(created_at__date=today)
    completed_orders = store_orders_qs.filter(status='completed')
    total_revenue = OrderItem.objects.filter(
        order__in=completed_orders, **item_filter
    ).aggregate(total=models.Sum('subtotal'))['total'] or 0
    today_revenue = OrderItem.objects.filter(
        order__in=today_orders.filter(status='completed'), **item_filter
    ).aggregate(total=models.Sum('subtotal'))['total'] or 0
    total_orders = completed_orders.count()
    today_order_count = today_orders.count()
    menu_count = MenuItem.objects.filter(**menu_filter).count()
    feedback_count = Feedback.objects.filter(**feedback_filter).distinct().count()

    return Response({
        'total_orders': total_orders,
        'today_orders': today_order_count,
        'total_revenue': float(total_revenue),
        'today_revenue': float(today_revenue),
        'menu_count': menu_count,
        'feedback_count': feedback_count,
        'average_order_value': float(total_revenue / total_orders) if total_orders else 0,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_analytics_revenue(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    period = request.query_params.get('period', 'daily')
    days = int(request.query_params.get('days', '30'))
    from django.utils import timezone
    from django.db.models import Sum, Count
    from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
    trunc_fn = {'daily': TruncDate, 'weekly': TruncWeek, 'monthly': TruncMonth}
    trunc = trunc_fn.get(period, TruncDate)
    cutoff = timezone.now() - timezone.timedelta(days=days)
    store = get_active_store(request)
    item_filter = {'store': store} if store else {'store_owner': request.user}
    data = (
        Order.objects
        .filter(
            Exists(OrderItem.objects.filter(
                order=OuterRef('pk'), **item_filter
            )),
            status='completed', created_at__gte=cutoff
        )
        .annotate(period=trunc('created_at'))
        .values('period')
        .annotate(revenue=Sum('total_amount'), count=Count('order_id'))
        .order_by('period')
    )
    return Response([
        {'period': entry['period'].isoformat() if entry['period'] else None,
         'revenue': float(entry['revenue']),
         'orders': entry['count']}
        for entry in data
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_analytics_top_items(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    limit = int(request.query_params.get('limit', '10'))
    store = get_active_store(request)
    item_filter = {'store': store} if store else {'store_owner': request.user}
    data = (
        OrderItem.objects
        .filter(**item_filter, order__status='completed')
        .values('item_name')
        .annotate(
            total_qty=models.Sum('quantity'),
            total_revenue=models.Sum('subtotal')
        )
        .order_by('-total_qty')[:limit]
    )
    return Response([
        {'name': entry['item_name'],
         'quantity': entry['total_qty'],
         'revenue': float(entry['total_revenue'])}
        for entry in data
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_analytics_peak_hours(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    from django.db.models.functions import ExtractHour
    store = get_active_store(request)
    order_filter = {'items__store': store} if store else {'items__store_owner': request.user}
    data = (
        Order.objects
        .filter(**order_filter)
        .annotate(hour=ExtractHour('created_at'))
        .values('hour')
        .annotate(count=models.Count('order_id'))
        .order_by('hour')
    )
    return Response([
        {'hour': entry['hour'], 'orders': entry['count']}
        for entry in data
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_create_menu_item(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = MenuItemSerializer(data=request.data)
    if serializer.is_valid():
        store = get_active_store(request)
        serializer.save(store_owner=request.user, store=store)
        notify_menu_updated()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def store_update_menu_item(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id, store_owner=request.user)
    serializer = MenuItemSerializer(item, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        notify_menu_updated()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def store_delete_menu_item(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id, store_owner=request.user)
    item.delete()
    notify_menu_updated()
    return Response({'message': 'Menu item deleted.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_toggle_featured(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id, store_owner=request.user)
    item.is_featured = not item.is_featured
    item.save(update_fields=['is_featured'])
    notify_menu_updated()
    return Response({'is_featured': item.is_featured})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_bulk_menu_update(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item_ids = request.data.get('item_ids', [])
    updates = request.data.get('updates', {})
    if not item_ids:
        return Response({'error': 'No items specified.'}, status=status.HTTP_400_BAD_REQUEST)
    items = MenuItem.objects.filter(item_id__in=item_ids, store_owner=request.user)
    allowed_fields = {'is_available', 'price', 'category', 'is_featured', 'stock'}
    update_kwargs = {k: v for k, v in updates.items() if k in allowed_fields}
    if not update_kwargs:
        return Response({'error': 'No valid fields to update.'}, status=status.HTTP_400_BAD_REQUEST)
    updated = items.update(**update_kwargs)
    notify_menu_updated()
    return Response({'message': f'{updated} item(s) updated.', 'updated_fields': list(update_kwargs.keys())})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_duplicate_menu_item(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    original = get_object_or_404(MenuItem, item_id=item_id, store_owner=request.user)
    new_item = MenuItem.objects.create(
        store_owner=request.user,
        name=f"{original.name} (Copy)",
        description=original.description,
        price=original.price,
        category=original.category,
        image_url=original.image_url,
        stock=0,
        is_featured=False,
        available_from=original.available_from,
        available_to=original.available_to,
        available_days=original.available_days,
    )
    serializer = MenuItemSerializer(new_item)
    notify_menu_updated()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def store_item_variations(request, item_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id, store_owner=request.user)

    if request.method == 'GET':
        variations = item.variations.all()
        serializer = ItemVariationSerializer(variations, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = ItemVariationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(item=item)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'PUT':
        variation_id = request.data.get('variation_id')
        if not variation_id:
            return Response({'error': 'variation_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        variation = get_object_or_404(ItemVariation, variation_id=variation_id, item=item)
        serializer = ItemVariationSerializer(variation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        variation_id = request.data.get('variation_id')
        if not variation_id:
            return Response({'error': 'variation_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        variation = get_object_or_404(ItemVariation, variation_id=variation_id, item=item)
        variation.delete()
        return Response({'message': 'Variation deleted.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_feedback(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    store = get_active_store(request)
    feedback = Feedback.objects.filter(
        order__items__store=store
    ).select_related('user', 'order').distinct().order_by('-created_at')
    serializer = FeedbackSerializer(feedback, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_notifications(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    from django.utils import timezone
    last_read = request.user.notifications_last_read_at
    if last_read is None:
        last_read = timezone.now() - timezone.timedelta(days=7)
    new_orders = Order.objects.filter(
        created_at__gt=last_read,
        items__item__store_owner=request.user
    ).distinct().order_by('-created_at')[:5]
    new_feedback = Feedback.objects.filter(
        created_at__gt=last_read,
        order__items__item__store_owner=request.user
    ).select_related('user', 'order').distinct().order_by('-created_at')[:5]
    return Response({
        'new_orders_count': new_orders.count(),
        'new_feedback_count': new_feedback.count(),
        'total_unread': new_orders.count() + new_feedback.count(),
        'orders': [{
            'order_id': str(o.order_id),
            'order_number': o.order_number,
            'total_amount': str(o.total_amount),
            'status': o.status,
            'created_at': o.created_at.isoformat(),
            'customer_name': o.user.full_name if o.user else 'Unknown',
        } for o in new_orders],
        'feedback': FeedbackSerializer(new_feedback, many=True).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_notifications_read(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    from django.utils import timezone
    request.user.notifications_last_read_at = timezone.now()
    request.user.save(update_fields=['notifications_last_read_at'])
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_all_menu_items(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    store = get_active_store(request)
    items = MenuItem.objects.filter(store=store).order_by('name') if store else MenuItem.objects.filter(store_owner=request.user).order_by('name')
    serializer = MenuItemSerializer(items, many=True)
    return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def store_discounts(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        store = get_active_store(request)
        discounts = Discount.objects.filter(store=store).order_by('-created_at') if store else Discount.objects.filter(store_owner=request.user).order_by('-created_at')
        serializer = DiscountSerializer(discounts, many=True)
        return Response(serializer.data)
    serializer = DiscountSerializer(data=request.data)
    if serializer.is_valid():
        store = get_active_store(request)
        serializer.save(store_owner=request.user, store=store)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def store_discount_detail(request, discount_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    discount = get_object_or_404(Discount, discount_id=discount_id, store_owner=request.user)
    if request.method == 'GET':
        return Response(DiscountSerializer(discount).data)
    if request.method == 'PUT':
        serializer = DiscountSerializer(discount, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    discount.delete()
    return Response({'message': 'Discount deleted.'})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def store_bundles(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        store = get_active_store(request)
        bundles = BundleDeal.objects.filter(store=store).prefetch_related('bundle_items__item').order_by('-created_at') if store else BundleDeal.objects.filter(store_owner=request.user).prefetch_related('bundle_items__item').order_by('-created_at')
        serializer = BundleDealSerializer(bundles, many=True)
        return Response(serializer.data)
    serializer = BundleDealSerializer(data=request.data)
    if serializer.is_valid():
        store = get_active_store(request)
        bundle = serializer.save(store_owner=request.user, store=store)
        items_data = request.data.get('items', [])
        for item_data in items_data:
            BundleItem.objects.create(
                bundle=bundle,
                item_id=item_data.get('item'),
                quantity=item_data.get('quantity', 1),
            )
        return Response(BundleDealSerializer(bundle).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def store_bundle_detail(request, bundle_id):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    bundle = get_object_or_404(BundleDeal, bundle_id=bundle_id, store_owner=request.user)
    if request.method == 'GET':
        return Response(BundleDealSerializer(bundle).data)
    if request.method == 'PUT':
        serializer = BundleDealSerializer(bundle, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            if 'items' in request.data:
                bundle.bundle_items.all().delete()
                for item_data in request.data.get('items', []):
                    BundleItem.objects.create(
                        bundle=bundle,
                        item_id=item_data.get('item'),
                        quantity=item_data.get('quantity', 1),
                    )
            return Response(BundleDealSerializer(bundle).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    bundle.delete()
    return Response({'message': 'Bundle deleted.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def apply_discount(request):
    serializer = ApplyDiscountSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    code = serializer.validated_data['code']
    from django.utils import timezone
    now = timezone.now()
    try:
        discount = Discount.objects.get(
            code=code, is_active=True,
            valid_from__lte=now, valid_until__gte=now,
        )
    except Discount.DoesNotExist:
        return Response({'error': 'Invalid or expired discount code.'}, status=status.HTTP_400_BAD_REQUEST)

    cart = Cart.objects.filter(user=request.user).prefetch_related('items__item').first()
    if not cart or not cart.items.exists():
        return Response({'error': 'Cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

    cart_total = sum(ci.item.price * ci.quantity for ci in cart.items.all())
    if cart_total < discount.min_order_amount:
        return Response({
            'error': f'Minimum order amount is ₱{discount.min_order_amount}. Your total is ₱{cart_total}.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if discount.usage_limit and discount.used_count >= discount.usage_limit:
        return Response({'error': 'Discount code usage limit reached.'}, status=status.HTTP_400_BAD_REQUEST)

    if discount.discount_type == 'percentage':
        amount = cart_total * (discount.discount_value / 100)
        if discount.max_discount:
            amount = min(amount, discount.max_discount)
    else:
        amount = min(discount.discount_value, cart_total)

    return Response({
        'discount_id': discount.discount_id,
        'code': discount.code,
        'name': discount.name,
        'discount_amount': float(amount),
        'new_total': float(cart_total - amount),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_stats(request):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    total_users = User.objects.filter(is_active=True).exclude(user_type='admin').count()
    total_students = User.objects.filter(user_type='student', is_active=True).count()
    total_faculty = User.objects.filter(user_type='faculty', is_active=True).count()
    total_stores = User.objects.filter(user_type='store_owner', is_active=True).count()
    total_orders = Order.objects.count()
    total_feedback = Feedback.objects.count()
    pending_approval = User.objects.filter(is_active=False, user_type='store_owner').count()
    pending_store_approvals = Store.objects.filter(is_approved=False, owner__is_active=True).count()
    pending_faculty = User.objects.filter(is_active=False, user_type='faculty').count()
    pending_students = User.objects.filter(is_active=False, user_type='student').count()
    top_selling = (
        OrderItem.objects.values('item_name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )
    return Response({
        'total_users': total_users,
        'total_students': total_students,
        'total_faculty': total_faculty,
        'total_stores': total_stores,
        'total_orders': total_orders,
        'total_feedback': total_feedback,
        'pending_approval': pending_approval,
        'pending_store_approvals': pending_store_approvals,
        'pending_faculty': pending_faculty,
        'pending_students': pending_students,
        'top_selling': list(top_selling),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_users(request):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    users = User.objects.prefetch_related('stores').all().order_by('-date_joined')
    serializer = UserSerializer(users, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_approve_user(request, user_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    user = get_object_or_404(User, user_id=user_id)
    if user.is_active:
        return Response({'error': 'User is already active.'}, status=status.HTTP_400_BAD_REQUEST)
    user.is_active = True
    user.deactivated_at = None
    user.save()

    user.stores.update(is_approved=True)

    if user.user_type == 'store_owner':
        status_obj, _ = StoreOwnerStatus.objects.get_or_create(user=user)
        status_obj.rejection_reason = ''
        status_obj.is_deactivated = False
        status_obj.deactivation_reason = ''
        status_obj.reviewed_by = request.user
        status_obj.save()

    login_url = request.build_absolute_uri('/login/')
    html_content = f'''
    <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
      <div style="background:#1a1a1a;padding:1.5rem;text-align:center;">
        <span style="font-size:1.4rem;font-weight:800;color:#ccff00;">KaonISU</span>
      </div>
      <div style="padding:1.5rem;">
        <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a1a;margin:0 0 0.5rem;">Account Approved</h2>
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 1rem;">Hi {user.full_name}, your account has been approved. You can now log in and start using KaonISU.</p>
        <div style="text-align:center;margin-bottom:0.5rem;">
          <a href="{login_url}" style="display:inline-block;background:#1a1a1a;color:#ccff00;font-weight:700;padding:0.75rem 2rem;border-radius:12px;text-decoration:none;font-size:0.9rem;">Log In Now</a>
        </div>
      </div>
      <div style="background:#f9fafb;padding:1rem;text-align:center;border-top:1px solid #f0f0f0;">
        <span style="font-size:0.75rem;color:#9ca3af;">&copy; 2026 KaonISU. All rights reserved.</span>
      </div>
    </div>
    '''
    text_content = f'Hi {user.full_name}, your account has been approved. You can now log in at {login_url}.'
    try:
        msg = EmailMultiAlternatives(
            'Account Approved - KaonISU',
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        msg.attach_alternative(html_content, 'text/html')
        msg.send(fail_silently=False)
    except Exception:
        pass

    return Response({'message': 'User approved.', 'user': UserSerializer(user).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_reject_user(request, user_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    user = get_object_or_404(User, user_id=user_id)
    if user.is_active:
        return Response({'error': 'Cannot reject an active user. Delete instead.'}, status=status.HTTP_400_BAD_REQUEST)

    reason = request.data.get('reason', '')

    if user.user_type == 'store_owner':
        status_obj, _ = StoreOwnerStatus.objects.get_or_create(user=user)
        status_obj.rejection_reason = reason
        status_obj.resubmit_count = 0
        status_obj.reviewed_by = request.user
        status_obj.save()

    html_content = f'''
    <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
      <div style="background:#1a1a1a;padding:1.5rem;text-align:center;">
        <span style="font-size:1.4rem;font-weight:800;color:#ccff00;">KaonISU</span>
      </div>
      <div style="padding:1.5rem;">
        <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a1a;margin:0 0 0.5rem;">Registration Not Approved</h2>
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Hi {user.full_name}, we regret to inform you that your account registration was not approved.</p>
        {f'<p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Reason: {reason}</p>' if reason else ''}
        {f'<p style="font-size:0.85rem;color:#6b7280;margin:0;">You can re-submit your registration with corrected information by visiting <a href="{request.build_absolute_uri("/register/store/")}" style="color:#4f46e5;">the registration page</a>.</p>' if user.user_type == 'store_owner' else ''}
      </div>
      <div style="background:#f9fafb;padding:1rem;text-align:center;border-top:1px solid #f0f0f0;">
        <span style="font-size:0.75rem;color:#9ca3af;">&copy; 2026 KaonISU. All rights reserved.</span>
      </div>
    </div>
    '''
    text_content = f'Hi {user.full_name}, your account registration was not approved. If you believe this is a mistake, please contact support.'
    try:
        msg = EmailMultiAlternatives(
            'Registration Update - KaonISU',
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        msg.attach_alternative(html_content, 'text/html')
        msg.send(fail_silently=False)
    except Exception:
        pass

    user.delete()
    return Response({'message': 'User rejected and deleted.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_edit_user(request, user_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    user = get_object_or_404(User, user_id=user_id)
    user_type = request.data.get('user_type')
    is_active = request.data.get('is_active')
    if user_type and user_type in dict(User.USER_TYPE_CHOICES):
        user.user_type = user_type
    if is_active is not None:
        user.is_active = bool(is_active)
        if is_active:
            user.deactivated_at = None
        else:
            user.deactivated_at = timezone.now()
    user.save()
    return Response({'message': 'User updated.', 'user': UserSerializer(user).data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_all_orders(request):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    orders = Order.objects.all().prefetch_related('items', 'status_history', 'user').order_by('-created_at')
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_feedback(request):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    feedback = Feedback.objects.all().select_related('user', 'order').prefetch_related(
        Prefetch('order__items', queryset=OrderItem.objects.select_related('store'))
    ).order_by('-created_at')
    serializer = FeedbackSerializer(feedback, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def admin_delete_feedback(request, feedback_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    feedback = get_object_or_404(Feedback, feedback_id=feedback_id)
    user_email = feedback.user.email
    user_name = feedback.user.full_name
    order_number = feedback.order.order_number if feedback.order else 'N/A'
    feedback.delete()
    if user_email:
        try:
            html_content = f'''
            <div style="max-width:480px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:2rem;">
                <div style="text-align:center;margin-bottom:1.5rem;">
                    <span style="font-size:1.5rem;font-weight:800;color:#1a1a1a;">KaonISU</span>
                </div>
                <div style="background:#fff;border-radius:16px;padding:1.5rem;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
                    <h2 style="font-size:1.1rem;font-weight:700;margin:0 0 0.5rem;">Feedback Removed</h2>
                    <p style="color:#6b7280;font-size:0.9rem;margin:0 0 1rem;">Hi {user_name}, your feedback for order <strong>{order_number}</strong> has been removed by an administrator.</p>
                    <p style="color:#9ca3af;font-size:0.8rem;margin:0;">If you have any questions, please contact support.</p>
                </div>
            </div>
            '''
            text_content = f'Hi {user_name}, your feedback for order {order_number} has been removed by an administrator.'
            msg = EmailMultiAlternatives(
                'Feedback Removed - KaonISU',
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [user_email],
            )
            msg.attach_alternative(html_content, 'text/html')
            msg.send(fail_silently=False)
        except Exception:
            pass
    return Response({'message': 'Feedback deleted.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_all_menu_items(request):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    items = MenuItem.objects.select_related('store', 'store_owner').all().order_by('store__name', 'name')
    serializer = MenuItemSerializer(items, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def admin_delete_menu_item(request, item_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    item = get_object_or_404(MenuItem, item_id=item_id)
    reason = request.data.get('reason', '')
    if not reason and request.body:
        try:
            body_data = json.loads(request.body)
            reason = body_data.get('reason', '')
        except (json.JSONDecodeError, AttributeError):
            pass

    owner_name = item.store_owner.full_name if item.store_owner else ''
    owner_email = item.store_owner.email if item.store_owner else None
    item_name = item.name

    item.delete()
    notify_menu_updated()

    if owner_email:
        html_content = f'''
        <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
          <div style="background:#1a1a1a;padding:1.5rem;text-align:center;">
            <span style="font-size:1.4rem;font-weight:800;color:#ccff00;">KaonISU</span>
          </div>
          <div style="padding:1.5rem;">
            <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a1a;margin:0 0 0.5rem;">Menu Item Removed</h2>
            <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Hi {owner_name},</p>
            <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Your menu item <strong>{item_name}</strong> has been removed by an administrator.</p>
            {f'<p style="font-size:0.85rem;color:#6b7280;margin:0;">Reason: {reason}</p>' if reason else ''}
          </div>
          <div style="background:#f9fafb;padding:1rem;text-align:center;border-top:1px solid #f0f0f0;">
            <span style="font-size:0.75rem;color:#9ca3af;">&copy; 2026 KaonISU. All rights reserved.</span>
          </div>
        </div>
        '''
        text_content = f'Hi {owner_name}, your menu item "{item_name}" has been removed by an administrator.{" Reason: " + reason if reason else ""}'
        try:
            msg = EmailMultiAlternatives(
                'Menu Item Removed - KaonISU',
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [owner_email],
            )
            msg.attach_alternative(html_content, 'text/html')
            msg.send(fail_silently=False)
        except Exception:
            pass

    return Response({'message': 'Menu item deleted.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_stores(request):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    stores = Store.objects.select_related('owner__store_profile', 'owner__store_status').order_by('-created_at')
    data = []
    for s in stores:
        status_obj = getattr(s.owner, 'store_status', None)
        menu_count = MenuItem.objects.filter(store=s, is_available=True).count()
        setattr(s.owner, 'contact_person', getattr(s, 'contact_person', ''))
        data.append({
            'store_id': s.store_id,
            'full_name': s.owner.full_name,
            'email': s.owner.email,
            'is_active': s.owner.is_active,
            'store_name': s.name,
            'description': s.description,
            'is_open': s.is_open,
            'is_approved': s.is_approved,
            'contact_number': s.contact_number,
            'contact_person': s.contact_person,
            'dti_permit': s.dti_permit.url if s.dti_permit else '',
            'store_slug': s.slug,
            'rejection_reason': status_obj.rejection_reason if status_obj else '',
            'is_deactivated': status_obj.is_deactivated if status_obj else False,
            'deactivation_reason': status_obj.deactivation_reason if status_obj else '',
            'resubmit_count': status_obj.resubmit_count if status_obj else 0,
            'menu_count': menu_count,
            'closed_at': s.closed_at.isoformat() if s.closed_at else None,
            'date_joined': s.created_at.isoformat(),
        })
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_deactivate_store(request, user_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    user = get_object_or_404(User, user_id=user_id, user_type='store_owner')
    reason = request.data.get('reason', '')
    status_obj, _ = StoreOwnerStatus.objects.get_or_create(user=user)
    status_obj.is_deactivated = True
    status_obj.deactivation_reason = reason
    status_obj.reviewed_by = request.user
    status_obj.save()
    user.is_active = False
    user.save()
    return Response({'message': f'Store {user.store_name} deactivated.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_activate_store(request, user_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    user = get_object_or_404(User, user_id=user_id, user_type='store_owner')
    status_obj, _ = StoreOwnerStatus.objects.get_or_create(user=user)
    status_obj.is_deactivated = False
    status_obj.deactivation_reason = ''
    status_obj.reviewed_by = request.user
    status_obj.save()
    user.is_active = True
    user.save()
    return Response({'message': f'Store {user.store_name} activated.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_approve_store(request, store_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    store = get_object_or_404(Store, store_id=store_id)
    store.is_approved = True
    store.save()
    notify_store_approved(store)
    return Response({'message': f'Store "{store.name}" approved.', 'store_id': store.store_id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_reject_store(request, store_id):
    if request.user.user_type != 'admin':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    store = get_object_or_404(Store, store_id=store_id)
    if store.is_approved:
        return Response({'error': 'Cannot reject an already approved store.'}, status=status.HTTP_400_BAD_REQUEST)

    reason = request.data.get('reason', '')
    owner = store.owner

    status_obj, _ = StoreOwnerStatus.objects.get_or_create(user=owner)
    status_obj.rejection_reason = reason
    status_obj.resubmit_count = 0
    status_obj.reviewed_by = request.user
    status_obj.save()

    store_name = store.name
    store.delete()

    html_content = f'''
    <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
      <div style="background:#1a1a1a;padding:1.5rem;text-align:center;">
        <span style="font-size:1.4rem;font-weight:800;color:#ccff00;">KaonISU</span>
      </div>
      <div style="padding:1.5rem;">
        <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a1a;margin:0 0 0.5rem;">Store Not Approved</h2>
        <p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Hi {owner.full_name}, your store "{store_name}" was not approved.</p>
        {f'<p style="font-size:0.85rem;color:#6b7280;margin:0 0 0.5rem;">Reason: {reason}</p>' if reason else ''}
        <p style="font-size:0.85rem;color:#6b7280;margin:0;">You can re-submit your store with corrected information.</p>
      </div>
      <div style="background:#f9fafb;padding:1rem;text-align:center;border-top:1px solid #f0f0f0;">
        <span style="font-size:0.75rem;color:#9ca3af;">&copy; 2026 KaonISU. All rights reserved.</span>
      </div>
    </div>
    '''
    text_content = f'Hi {owner.full_name}, your store "{store_name}" was not approved.'
    try:
        msg = EmailMultiAlternatives(
            'Store Registration Update - KaonISU',
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [owner.email],
        )
        msg.attach_alternative(html_content, 'text/html')
        msg.send(fail_silently=False)
    except Exception:
        pass

    return Response({'message': f'Store "{store_name}" rejected and removed.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_resubmit_permit(request):
    if request.user.user_type != 'store_owner':
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)
    if request.user.is_active:
        return Response({'error': 'Account is already active.'}, status=status.HTTP_400_BAD_REQUEST)
    dti_permit = request.FILES.get('dti_permit')
    if not dti_permit:
        return Response({'error': 'DTI permit is required.'}, status=status.HTTP_400_BAD_REQUEST)
    profile, _ = StoreProfile.objects.get_or_create(user=request.user)
    profile.dti_permit = compress_image(dti_permit)
    profile.save()
    status_obj, _ = StoreOwnerStatus.objects.get_or_create(user=request.user)
    status_obj.resubmit_count += 1
    status_obj.last_resubmit_at = timezone.now()
    status_obj.rejection_reason = ''
    status_obj.save()
    return Response({'message': 'Permit re-submitted. Pending admin review.'})


@ensure_csrf_cookie
def landing_page(request):
    menu_items = MenuItem.objects.filter(is_available=True, store__is_approved=True)[:8]
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
def add_store_page(request):
    if request.user.user_type != 'store_owner':
        return redirect('/dashboard/')
    return render(request, 'add_store.html')


@login_required
def logout_page(request):
    django_logout(request)
    return redirect('/')

@login_required
def store_dashboard_page(request):
    if request.user.user_type == 'admin':
        return redirect('admin-dashboard-page')
    if request.user.user_type != 'store_owner':
        return render(request, 'store_register.html')
    return render(request, 'store_dashboard.html')


@login_required
def admin_dashboard_page(request):
    if request.user.user_type != 'admin':
        return redirect('/')
    return render(request, 'admin_dashboard.html')


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
def order_group_page(request, group_id):
    return render(request, 'order_group.html', {'group_id': group_id})


@login_required
def order_tracking_page(request, order_id):
    return render(request, 'order_tracking.html', {'order_id': order_id})


@login_required
def feedback_page(request, order_id):
    return render(request, 'feedback.html', {'order_id': order_id})


@login_required
def my_orders_page(request):
    return render(request, 'my_orders.html')
