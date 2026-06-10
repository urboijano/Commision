from django.db import migrations


def copy_dti_permits(apps, schema_editor):
    User = apps.get_model('customer', 'User')
    StoreProfile = apps.get_model('customer', 'StoreProfile')
    for profile in StoreProfile.objects.filter(dti_permit=''):
        try:
            user = profile.user
            if user.dti_permit:
                profile.dti_permit = user.dti_permit
                profile.save()
        except User.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0018_store_profile_dti_permit'),
    ]

    operations = [
        migrations.RunPython(copy_dti_permits, migrations.RunPython.noop),
    ]
