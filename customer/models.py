import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify


class User(AbstractUser):
    USER_TYPE_CHOICES = [
        ('student', 'Student'),
        ('faculty', 'Faculty'),
        ('store_owner', 'Store Owner'),
        ('admin', 'Admin'),
    ]
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, db_index=True)
    student_faculty_id = models.CharField(max_length=30, unique=True, blank=True, null=True)
    store_name = models.CharField(max_length=200, blank=True, default='')
    dti_permit = models.ImageField(upload_to='dti_permits/', blank=True, null=True)
    faculty_id_image = models.ImageField(upload_to='faculty_ids/', blank=True, null=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100)
    notifications_last_read_at = models.DateTimeField(blank=True, null=True)
    deactivated_at = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name', 'user_type', 'student_faculty_id']

    class Meta:
        indexes = [
            models.Index(fields=['is_active'], name='idx_user_is_active'),
        ]
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return f"{self.full_name} ({self.student_faculty_id})"


class Store(models.Model):
    store_id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stores')
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='store_logos/', blank=True, null=True)
    banner = models.ImageField(upload_to='store_banners/', blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    dti_permit = models.ImageField(upload_to='dti_permits/', blank=True, null=True)
    contact_person = models.CharField(max_length=200, blank=True)
    is_open = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Store"
        verbose_name_plural = "Stores"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Store.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner.full_name})"


class StoreProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='store_profile')
    store_name = models.CharField(max_length=200)
    store_slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='store_logos/', blank=True, null=True)
    banner = models.ImageField(upload_to='store_banners/', blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    dti_permit = models.ImageField(upload_to='dti_permits/', blank=True, null=True)
    is_open = models.BooleanField(default=True)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Store Profile"
        verbose_name_plural = "Store Profiles"

    def save(self, *args, **kwargs):
        if not self.store_slug:
            base_slug = slugify(self.store_name)
            slug = base_slug
            counter = 1
            while StoreProfile.objects.filter(store_slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.store_slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.store_name} ({self.user.full_name})"


class StoreOwnerStatus(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='store_status')
    rejection_reason = models.TextField(blank=True)
    resubmit_count = models.IntegerField(default=0)
    last_resubmit_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='store_reviews'
    )
    is_deactivated = models.BooleanField(default=False)
    deactivation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Store Owner Status"
        verbose_name_plural = "Store Owner Statuses"

    def __str__(self):
        return f"{self.user.full_name} - {'Active' if not self.is_deactivated else 'Deactivated'}"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=False)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_used'], name='idx_reset_user_used'),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.code}"


class ValidID(models.Model):
    USER_TYPE_CHOICES = [
        ('student', 'Student'),
        ('faculty', 'Faculty'),
    ]
    id_value = models.CharField(max_length=30, unique=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Valid ID"
        verbose_name_plural = "Valid IDs"

    def __str__(self):
        return f"{self.id_value} ({self.user_type}) - {'Used' if self.is_used else 'Available'}"


class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ('rice', 'Rice Meals'),
        ('noodles', 'Noodles'),
        ('drinks', 'Drinks'),
        ('snacks', 'Snacks'),
        ('desserts', 'Desserts'),
    ]
    item_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    image_url = models.URLField(max_length=500, blank=True)
    is_available = models.BooleanField(default=True)
    stock = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    featured_order = models.IntegerField(default=0)
    available_from = models.TimeField(null=True, blank=True)
    available_to = models.TimeField(null=True, blank=True)
    available_days = models.CharField(max_length=50, blank=True, default='')
    low_stock_threshold = models.IntegerField(default=5)
    store = models.ForeignKey(
        'Store', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='menu_items'
    )
    store_owner = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='menu_items', limit_choices_to={'user_type': 'store_owner'}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Menu Item"
        verbose_name_plural = "Menu Items"

    def save(self, *args, **kwargs):
        self.is_available = self.stock > 0
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ItemVariation(models.Model):
    variation_id = models.AutoField(primary_key=True)
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='variations')
    name = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Item Variation"
        verbose_name_plural = "Item Variations"

    def __str__(self):
        return f"{self.item.name} - {self.name}"


class Discount(models.Model):
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]
    discount_id = models.AutoField(primary_key=True)
    store = models.ForeignKey(
        'Store', on_delete=models.CASCADE, null=True, blank=True,
        related_name='discounts'
    )
    store_owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='discounts',
        limit_choices_to={'user_type': 'store_owner'}
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    usage_limit = models.IntegerField(default=0)
    used_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discount"
        verbose_name_plural = "Discounts"

    def __str__(self):
        return f"{self.name} ({self.code or 'auto'})"


class BundleDeal(models.Model):
    bundle_id = models.AutoField(primary_key=True)
    store = models.ForeignKey(
        'Store', on_delete=models.CASCADE, null=True, blank=True,
        related_name='bundles'
    )
    store_owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bundles',
        limit_choices_to={'user_type': 'store_owner'}
    )
    name = models.CharField(max_length=200)
    items = models.ManyToManyField(MenuItem, through='BundleItem')
    bundle_price = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bundle Deal"
        verbose_name_plural = "Bundle Deals"

    def __str__(self):
        return self.name


class BundleItem(models.Model):
    bundle = models.ForeignKey(BundleDeal, on_delete=models.CASCADE, related_name='bundle_items')
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Bundle Item"
        verbose_name_plural = "Bundle Items"
        unique_together = ('bundle', 'item')

    def __str__(self):
        return f"{self.bundle.name} - {self.item.name} x{self.quantity}"


class DiscountUsage(models.Model):
    usage_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    discount = models.ForeignKey(Discount, on_delete=models.CASCADE, related_name='usages')
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='discount_usages')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discount Usage"
        verbose_name_plural = "Discount Usages"

    def __str__(self):
        return f"{self.discount.code} on {self.order.order_number}"


class Cart(models.Model):
    cart_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart ({self.user.email})"


class CartItem(models.Model):
    cart_item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'item')

    def __str__(self):
        return f"{self.item.name} x{self.quantity}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Acceptance'),
        ('store_accepted', 'Accepted by Store'),
        ('store_rejected', 'Rejected by Store'),
        ('preparing', 'Preparing'),
        ('ready_for_pickup', 'Ready for Pick-Up'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
    ]
    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='pending', db_index=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    estimated_ready_at = models.DateTimeField(null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    discount_code = models.CharField(max_length=50, blank=True, default='')
    parent_order_group = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_number} ({self.status})"


class OrderItem(models.Model):
    order_item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    item_name = models.CharField(max_length=150)
    store = models.ForeignKey(
        'Store', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_items'
    )
    store_owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_items'
    )
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_name} x{self.quantity}"


class OrderStatusHistory(models.Model):
    STATUS_CHOICES = Order.STATUS_CHOICES
    status_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    changed_by = models.CharField(max_length=50, default='system')
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Order Status History"
        verbose_name_plural = "Order Status Histories"
        ordering = ['changed_at']

    def __str__(self):
        return f"{self.order.order_number} -> {self.status} at {self.changed_at}"


class Feedback(models.Model):
    SATISFACTION_CHOICES = [
        ('very_satisfied', 'Very Satisfied'),
        ('satisfied', 'Satisfied'),
        ('neutral', 'Neutral'),
        ('dissatisfied', 'Dissatisfied'),
        ('very_dissatisfied', 'Very Dissatisfied'),
    ]
    feedback_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='feedback')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedback')
    rating = models.IntegerField()
    satisfaction_level = models.CharField(max_length=20, choices=SATISFACTION_CHOICES)
    comments = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback"

    def __str__(self):
        return f"Feedback for {self.order.order_number} - {self.rating}/5"
