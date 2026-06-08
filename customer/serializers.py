import re

from rest_framework import serializers
from .models import (
    User, ValidID, MenuItem, Cart, CartItem,
    Order, OrderItem, OrderStatusHistory, Feedback
)


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = '__all__'


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100)
    student_faculty_id = serializers.CharField(max_length=30)
    user_type = serializers.ChoiceField(choices=['student', 'faculty'])
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

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


class StoreRegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100)
    store_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

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
        fields = ['user_id', 'full_name', 'email', 'user_type', 'user_type_display', 'student_faculty_id', 'store_name', 'is_active', 'date_joined']


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['item_id', 'name', 'description', 'price', 'category', 'image_url', 'is_available']


class CartItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_price = serializers.DecimalField(source='item.price', max_digits=8, decimal_places=2, read_only=True)
    item_image = serializers.URLField(source='item.image_url', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['cart_item_id', 'item', 'item_name', 'item_price', 'item_image', 'quantity', 'subtotal']

    def get_subtotal(self, obj):
        return obj.item.price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['cart_id', 'items', 'total_items', 'total_price', 'updated_at']

    def get_total_items(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_total_price(self, obj):
        return sum(item.item.price * item.quantity for item in obj.items.all())


class AddCartItemSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['order_item_id', 'item_name', 'unit_price', 'quantity', 'subtotal']


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
            'notes', 'created_at', 'updated_at', 'user'
        ]


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ['feedback_id', 'order', 'rating', 'satisfaction_level', 'comments', 'created_at']
        read_only_fields = ['feedback_id', 'created_at']

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
