import os
import shutil
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from documents.models import Document


class Command(BaseCommand):
    help = "Permanently delete documents that have passed their retention period"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate deletion without actually removing anything",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override retention period (delete documents older than this many days)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        override_days = options.get("days")

        now = timezone.now()

        if override_days:
            # Delete all documents older than the specified days regardless of retention_days
            cutoff = now - timedelta(days=override_days)
            expired_docs = Document.objects.filter(created_at__lt=cutoff)
            reason = f"older than {override_days} days (--days override)"
        else:
            # Delete documents where retention_days > 0 and created_at + retention_days < now
            expired_docs = Document.objects.filter(
                retention_days__gt=0,
                created_at__lt=now - timedelta(days=1),  # at least 1 day old to avoid edge cases
            )
            # Filter in Python for precise date comparison
            expired_docs = [doc for doc in expired_docs if doc.is_expired]
            reason = "past their retention period"

        if not expired_docs:
            self.stdout.write(self.style.SUCCESS("No expired documents found."))
            return

        self.stdout.write(
            f"Found {len(expired_docs)} expired document(s) to delete ({reason}):"
        )

        for doc in expired_docs:
            doc_id = doc.id
            doc_title = doc.title or "Untitled"
            doc_user = doc.user.username
            doc_created = doc.created_at.strftime("%Y-%m-%d %H:%M")
            doc_expires = doc.expires_at.strftime("%Y-%m-%d %H:%M") if doc.expires_at else "N/A"

            self.stdout.write(
                f"  • [{doc_id}] '{doc_title}' by {doc_user} "
                f"(created: {doc_created}, expires: {doc_expires})"
            )

            if dry_run:
                continue

            # Delete physical files
            if doc.pdf_file and os.path.exists(doc.pdf_file.path):
                os.remove(doc.pdf_file.path)
                self.stdout.write(f"    - Deleted PDF: {doc.pdf_file.path}")

            if doc.signed_pdf and os.path.exists(doc.signed_pdf.path):
                os.remove(doc.signed_pdf.path)
                self.stdout.write(f"    - Deleted signed PDF: {doc.signed_pdf.path}")

            # Delete preview directories
            for dir_name in ["previews", "signed_previews"]:
                dir_path = os.path.join(
                    os.path.dirname(os.path.dirname(doc.pdf_file.path)),  # media root
                    dir_name,
                    str(doc_id),
                )
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)
                    self.stdout.write(f"    - Deleted directory: {dir_path}")

            # Delete the database record (cascades to placements and OTPs)
            doc.delete()
            self.stdout.write(f"    ✓ Document #{doc_id} permanently deleted")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry run complete. {len(expired_docs)} document(s) would have been deleted."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully deleted {len(expired_docs)} expired document(s)."
                )
            )
