import re

from django.db import models
from rest_framework import serializers
from .models import (
    User, ValidID, MenuItem, ItemVariation, Cart, CartItem,
    Order, OrderItem, OrderStatusHistory, Feedback,
    StoreProfile, Store, Discount, BundleDeal, BundleItem,
)


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = '__all__'


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100)
    student_faculty_id = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    user_type = serializers.ChoiceField(choices=['student', 'faculty'])
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    faculty_id_image = serializers.ImageField(required=False)

    def validate_password(self, value):
        errors = []
        if len(value) < 8:
            errors.append('at least 8 characters')
        if not re.search(r'[A-Z]', value):
            errors.append('an uppercase letter')
        if not re.search(r'[a-z]', value):
            errors.append('a lowercase letter')
        if not re.search(r'\d', value):
            errors.append('a digit')
        if not re.search(r'[^A-Za-z0-9]', value):
            errors.append('a special character')
        if errors:
            raise serializers.ValidationError(
                f'Password must contain {", ".join(errors)}.'
            )
        return value

    def validate_full_name(self, value):
        value = value.strip()
        if not re.match(r'^[A-Za-zÀ-ÿ\s.]+,\s[A-Za-zÀ-ÿ\s.]+$', value):
            raise serializers.ValidationError(
                'Full name must be in the format: Surname, First Name Middle Initial (e.g. Dela Cruz, Juan P.)'
            )
        if User.objects.filter(
            full_name__iexact=value,
            user_type__in=['student', 'faculty']
        ).exists():
            raise serializers.ValidationError(
                'A student or faculty account with this name already exists.'
            )
        return value


class StoreRegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100)
    store_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    dti_permit = serializers.ImageField(required=True)

    def validate_password(self, value):
        errors = []
        if len(value) < 8:
            errors.append('at least 8 characters')
        if not re.search(r'[A-Z]', value):
            errors.append('an uppercase letter')
        if not re.search(r'[a-z]', value):
            errors.append('a lowercase letter')
        if not re.search(r'\d', value):
            errors.append('a digit')
        if not re.search(r'[^A-Za-z0-9]', value):
            errors.append('a special character')
        if errors:
            raise serializers.ValidationError(
                f'Password must contain {", ".join(errors)}.'
            )
        return value

    def validate_full_name(self, value):
        value = value.strip()
        if not re.match(r'^[A-Za-zÀ-ÿ\s.]+,\s[A-Za-zÀ-ÿ\s.]+$', value):
            raise serializers.ValidationError(
                'Full name must be in the format: Surname, First Name Middle Initial (e.g. Dela Cruz, Juan P.)'
            )
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, min_length=8)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    user_type_display = serializers.CharField(source='get_user_type_display', read_only=True)

    class Meta:
        model = User
        fields = ['user_id', 'full_name', 'email', 'user_type', 'user_type_display', 'student_faculty_id', 'store_name', 'dti_permit', 'faculty_id_image', 'is_active', 'date_joined']


class StoreProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreProfile
        fields = [
            'store_name', 'store_slug', 'description', 'logo', 'banner',
            'contact_number', 'address', 'is_open',
            'opening_time', 'closing_time', 'created_at', 'updated_at',
        ]
        read_only_fields = ['store_slug', 'created_at', 'updated_at']


class StoreProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreProfile
        fields = [
            'store_name', 'description', 'logo', 'banner',
            'contact_number', 'address', 'is_open',
            'opening_time', 'closing_time',
        ]


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = [
            'store_id', 'name', 'slug', 'description', 'logo', 'banner',
            'contact_number', 'contact_person', 'address', 'dti_permit',
            'is_open', 'is_approved',
            'opening_time', 'closing_time', 'created_at', 'updated_at',
        ]
        read_only_fields = ['store_id', 'slug', 'is_approved', 'created_at', 'updated_at']


class StoreUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = [
            'name', 'description', 'logo', 'banner',
            'contact_number', 'contact_person', 'address', 'dti_permit',
            'is_open', 'opening_time', 'closing_time',
        ]


class ItemVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemVariation
        fields = ['variation_id', 'name', 'price_adjustment', 'is_available']


class BundleItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = BundleItem
        fields = ['item', 'item_name', 'quantity']


class BundleDealSerializer(serializers.ModelSerializer):
    items = BundleItemSerializer(source='bundle_items', many=True, read_only=True)

    class Meta:
        model = BundleDeal
        fields = [
            'bundle_id', 'name', 'items', 'bundle_price',
            'is_active', 'valid_until', 'created_at',
        ]
        read_only_fields = ['bundle_id', 'created_at']


class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = [
            'discount_id', 'name', 'code', 'discount_type', 'discount_value',
            'min_order_amount', 'max_discount', 'valid_from', 'valid_until',
            'usage_limit', 'used_count', 'is_active', 'created_at',
        ]
        read_only_fields = ['discount_id', 'used_count', 'created_at']


class ApplyDiscountSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)


class MenuItemSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    store_id = serializers.IntegerField(read_only=True)
    variations = ItemVariationSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            'item_id', 'name', 'description', 'price', 'category', 'category_display',
            'image_url', 'is_available', 'stock', 'is_featured', 'featured_order',
            'available_from', 'available_to', 'available_days', 'low_stock_threshold',
            'store_name', 'store_id', 'variations',
        ]

    def validate(self, data):
        if 'stock' in data:
            data['is_available'] = data['stock'] > 0
        return data

    def get_category_display(self, obj):
        return obj.get_category_display()

    def get_store_name(self, obj):
        if obj.store_id and obj.store:
            return obj.store.name
        if obj.store_owner:
            return obj.store_owner.store_name
        return '(No Store)'


class CartItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_price = serializers.DecimalField(source='item.price', max_digits=8, decimal_places=2, read_only=True)
    item_image = serializers.URLField(source='item.image_url', read_only=True)
    subtotal = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    store_owner_id = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['cart_item_id', 'item', 'item_name', 'item_price', 'item_image', 'quantity', 'subtotal', 'store_name', 'store_owner_id']

    def get_subtotal(self, obj):
        return obj.item.price * obj.quantity

    def get_store_name(self, obj):
        if obj.item.store:
            return obj.item.store.name
        if obj.item.store_owner:
            return obj.item.store_owner.store_name
        return ''

    def get_store_owner_id(self, obj):
        if obj.item.store_owner:
            return str(obj.item.store_owner.user_id)
        return ''


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['cart_id', 'items', 'total_items', 'total_price', 'updated_at']

    def get_total_items(self, obj):
        try:
            cached = getattr(obj, '_prefetched_objects_cache', {})
            if 'items' in cached:
                return sum(item.quantity for item in cached['items'])
        except Exception:
            pass
        return obj.items.aggregate(total=models.Sum('quantity'))['total'] or 0

    def get_total_price(self, obj):
        try:
            cached = getattr(obj, '_prefetched_objects_cache', {})
            if 'items' in cached:
                return sum(item.item.price * item.quantity for item in cached['items'])
        except Exception:
            pass
        return sum(
            item.item.price * item.quantity
            for item in obj.items.select_related('item').only('item__price', 'quantity')
        )


class AddCartItemSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)


class OrderItemSerializer(serializers.ModelSerializer):
    item_image = serializers.URLField(source='item.image_url', read_only=True, default='')
    category = serializers.CharField(source='item.category', read_only=True, default='')
    store_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['order_item_id', 'item_id', 'item_name', 'unit_price', 'quantity', 'subtotal', 'item_image', 'category', 'store_name']

    def get_store_name(self, obj):
        if obj.store:
            return obj.store.name
        if obj.store_owner:
            return obj.store_owner.store_name
        return ''


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['status', 'changed_by', 'changed_at']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            'order_id', 'order_number', 'total_amount', 'status',
            'status_display', 'payment_status', 'items', 'status_history',
            'notes', 'rejection_reason', 'estimated_ready_at',
            'parent_order_group', 'created_at', 'updated_at', 'user'
        ]


class StoreOrderItemSerializer(serializers.ModelSerializer):
    item_image = serializers.URLField(source='item.image_url', read_only=True, default='')
    category = serializers.CharField(source='item.category', read_only=True, default='')
    store_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['order_item_id', 'item_name', 'unit_price', 'quantity', 'subtotal', 'item_image', 'category', 'store_name']

    def get_store_name(self, obj):
        if obj.store:
            return obj.store.name
        if obj.store_owner:
            return obj.store_owner.store_name
        return ''


class StoreOrderSerializer(serializers.ModelSerializer):
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            'order_id', 'order_number', 'total_amount', 'status',
            'status_display', 'payment_status', 'status_history',
            'notes', 'rejection_reason', 'estimated_ready_at',
            'created_at', 'updated_at', 'user'
        ]


class FeedbackSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    store_names = serializers.SerializerMethodField()
    food_names = serializers.SerializerMethodField()
    has_food = serializers.SerializerMethodField()
    has_bad_words = serializers.SerializerMethodField()
    satisfaction_display = serializers.CharField(source='get_satisfaction_level_display', read_only=True)

    class Meta:
        model = Feedback
        fields = ['feedback_id', 'order', 'order_number', 'user_name', 'store_names', 'food_names', 'has_food', 'has_bad_words', 'satisfaction_display', 'rating', 'satisfaction_level', 'comments', 'created_at']
        read_only_fields = ['feedback_id', 'created_at', 'user_name', 'order_number', 'store_names', 'food_names', 'has_food', 'has_bad_words', 'satisfaction_display']

    def get_store_names(self, obj):
        stores = set()
        for item in obj.order.items.all():
            if item.store:
                stores.add(item.store.name)
        return list(stores)

    def get_food_names(self, obj):
        return [item.item_name for item in obj.order.items.all()]

    def get_has_food(self, obj):
        return obj.order.items.filter(store__isnull=False).exists()

    def get_has_bad_words(self, obj):
        BAD_WORDS = [
            'fuck', 'shit', 'damn', 'bitch', 'ass', 'bastard', 'crap',
            'stupid', 'idiot', 'dumb', 'hate', 'kill', 'die', 'wtf',
            'putang', 'gago', 'bobo', 'tanga', 'ulol', 'lintik',
        ]
        if not obj.comments:
            return False
        comments_lower = obj.comments.lower()
        return any(word in comments_lower for word in BAD_WORDS)

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


class CreateFeedbackSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    satisfaction_level = serializers.ChoiceField(choices=[
        'very_satisfied', 'satisfied', 'neutral', 'dissatisfied', 'very_dissatisfied'
    ])
    comments = serializers.CharField(required=False, allow_blank=True, max_length=500)


class MenuItemDetailSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    store_owner_name = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    feedbacks = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            'item_id', 'name', 'description', 'price', 'category', 'category_display',
            'image_url', 'is_available', 'stock', 'store_owner_name', 'store_name', 'feedbacks'
        ]

    def get_category_display(self, obj):
        return obj.get_category_display()

    def get_store_owner_name(self, obj):
        if obj.store_owner:
            return obj.store_owner.full_name
        return None

    def get_store_name(self, obj):
        if obj.store_owner:
            return obj.store_owner.store_name
        return None

    def get_feedbacks(self, obj):
        from django.db.models import Prefetch
        order_items = OrderItem.objects.filter(item=obj).select_related('order')
        order_ids = order_items.values_list('order_id', flat=True).distinct()
        feedbacks = Feedback.objects.filter(order_id__in=order_ids).select_related('user').order_by('-created_at')[:10]
        return FeedbackSerializer(feedbacks, many=True).data
