from django.db import migrations


def migrate_profiles(apps, schema_editor):
    StoreProfile = apps.get_model('customer', 'StoreProfile')
    Store = apps.get_model('customer', 'Store')
    MenuItem = apps.get_model('customer', 'MenuItem')
    OrderItem = apps.get_model('customer', 'OrderItem')
    Discount = apps.get_model('customer', 'Discount')
    BundleDeal = apps.get_model('customer', 'BundleDeal')

    store_profile_map = {}
    for sp in StoreProfile.objects.all():
        store, _ = Store.objects.get_or_create(
            owner=sp.user,
            name=sp.store_name,
            defaults={
                'slug': sp.store_slug,
                'description': sp.description,
                'logo': sp.logo,
                'banner': sp.banner,
                'contact_number': sp.contact_number,
                'address': sp.address,
                'dti_permit': sp.dti_permit,
                'is_open': sp.is_open,
                'opening_time': sp.opening_time,
                'closing_time': sp.closing_time,
            }
        )
        store_profile_map[sp.user_id] = store

    for mi in MenuItem.objects.filter(store__isnull=True).select_related('store_owner'):
        if mi.store_owner_id in store_profile_map:
            mi.store = store_profile_map[mi.store_owner_id]
            mi.save(update_fields=['store'])

    for oi in OrderItem.objects.filter(store__isnull=True).select_related('store_owner'):
        if oi.store_owner_id in store_profile_map:
            oi.store = store_profile_map[oi.store_owner_id]
            oi.save(update_fields=['store'])

    for d in Discount.objects.filter(store__isnull=True).select_related('store_owner'):
        if d.store_owner_id in store_profile_map:
            d.store = store_profile_map[d.store_owner_id]
            d.save(update_fields=['store'])

    for b in BundleDeal.objects.filter(store__isnull=True).select_related('store_owner'):
        if b.store_owner_id in store_profile_map:
            b.store = store_profile_map[b.store_owner_id]
            b.save(update_fields=['store'])


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0024_multi_store_support'),
    ]

    operations = [
        migrations.RunPython(migrate_profiles, migrations.RunPython.noop),
    ]
