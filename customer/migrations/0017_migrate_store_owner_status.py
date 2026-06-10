from django.db import migrations


def create_status_records(apps, schema_editor):
    User = apps.get_model('customer', 'User')
    StoreOwnerStatus = apps.get_model('customer', 'StoreOwnerStatus')
    for user in User.objects.filter(user_type='store_owner'):
        StoreOwnerStatus.objects.get_or_create(user=user)


def reverse_status(apps, schema_editor):
    StoreOwnerStatus = apps.get_model('customer', 'StoreOwnerStatus')
    StoreOwnerStatus.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0016_store_owner_status_model'),
    ]

    operations = [
        migrations.RunPython(create_status_records, reverse_status),
    ]
