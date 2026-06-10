from django.db import migrations


def backfill_store_owner(apps, schema_editor):
    OrderItem = apps.get_model('customer', 'OrderItem')
    for oi in OrderItem.objects.filter(store_owner__isnull=True).select_related('item__store_owner'):
        if oi.item and oi.item.store_owner:
            oi.store_owner = oi.item.store_owner
            oi.save(update_fields=['store_owner'])


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0021_order_management_enhancements'),
    ]

    operations = [
        migrations.RunPython(backfill_store_owner, migrations.RunPython.noop),
    ]
