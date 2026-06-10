from django.contrib import admin
from .models import User, ValidID, MenuItem, Cart, CartItem, Order, OrderItem, OrderStatusHistory, Feedback, StoreProfile, Store, StoreOwnerStatus


admin.site.register(User)
admin.site.register(ValidID)
admin.site.register(MenuItem)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderStatusHistory)
admin.site.register(Feedback)
admin.site.register(StoreProfile)
admin.site.register(Store)
admin.site.register(StoreOwnerStatus)
