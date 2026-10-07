from django.db import migrations


def backfill_companies(apps, schema_editor):
    """Create a default Company for every user.

    Existing users stored their signature/stamp on ``UserProfile``; copy those
    images onto the newly created default company so no data is lost.
    """
    User = apps.get_model('auth', 'User')
    Company = apps.get_model('accounts', 'Company')
    UserProfile = apps.get_model('accounts', 'UserProfile')

    profiles = {p.user_id: p for p in UserProfile.objects.all()}

    for user in User.objects.all():
        if Company.objects.filter(user_id=user.id).exists():
            continue

        company = Company(
            user_id=user.id,
            name=f"{user.username}'s Company",
            is_default=True,
        )

        profile = profiles.get(user.id)
        if profile is not None:
            if profile.signature:
                company.signature.name = profile.signature.name
            if profile.stamp:
                company.stamp.name = profile.stamp.name

        company.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_company'),
    ]

    operations = [
        migrations.RunPython(backfill_companies, noop),
    ]
