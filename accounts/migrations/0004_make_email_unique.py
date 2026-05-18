from django.db import migrations, models


def deduplicate_emails(apps, schema_editor):
    """Remove duplicate emails by appending a suffix to duplicates."""
    User = apps.get_model('auth', 'User')
    # Find users with duplicate emails
    duplicates = (
        User.objects.values('email')
        .annotate(count=models.Count('id'))
        .filter(count__gt=1)
    )
    for dup in duplicates:
        email = dup['email']
        users = User.objects.filter(email=email).order_by('date_joined')
        # Keep the first user's email, append suffix to the rest
        for i, user in enumerate(users):
            if i > 0:
                local_part = email.split('@')[0]
                domain = email.split('@')[1]
                user.email = f"{local_part}+dup{i}@{domain}"
                user.save(update_fields=['email'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_make_phone_number_unique'),
    ]

    operations = [
        migrations.RunPython(deduplicate_emails, reverse_code=migrations.RunPython.noop),
        migrations.RunSQL(
            sql='CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_unique ON auth_user (email);',
            reverse_sql='DROP INDEX IF EXISTS auth_user_email_unique;',
        ),
    ]
