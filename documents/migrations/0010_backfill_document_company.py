from django.db import migrations


def backfill_document_company(apps, schema_editor):
    """Assign every existing document to its owner's default company."""
    Document = apps.get_model('documents', 'Document')
    Company = apps.get_model('accounts', 'Company')

    for document in Document.objects.filter(company__isnull=True):
        company = (
            Company.objects.filter(user_id=document.user_id, is_default=True).first()
            or Company.objects.filter(user_id=document.user_id).first()
        )
        if company is not None:
            document.company_id = company.id
            document.save(update_fields=['company'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_backfill_companies'),
        ('documents', '0009_document_company'),
    ]

    operations = [
        migrations.RunPython(backfill_document_company, noop),
    ]
