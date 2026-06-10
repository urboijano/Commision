from django.db import migrations


def migrate_store_owners(apps, schema_editor):
    User = apps.get_model('customer', 'User')
    StoreProfile = apps.get_model('customer', 'StoreProfile')
    for user in User.objects.filter(user_type='store_owner'):
        StoreProfile.objects.get_or_create(
            user=user,
            defaults={
                'store_name': user.store_name or user.full_name,
                'dti_permit': user.dti_permit,
            }
        )


def reverse_migrate(apps, schema_editor):
    StoreProfile = apps.get_model('customer', 'StoreProfile')
    StoreProfile.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0014_store_profile_model'),
    ]

    operations = [
        migrations.RunPython(migrate_store_owners, reverse_migrate),
    ]
