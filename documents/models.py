import uuid
import secrets
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.utils import timezone


class Document(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255, blank=True, db_index=True)
    pdf_file = models.FileField(
        upload_to='documents/',
        validators=[FileExtensionValidator(['pdf'])]
    )
    preview_image = models.ImageField(upload_to='previews/', blank=True, null=True)
    total_pages = models.IntegerField(default=1)
    is_signed = models.BooleanField(default=False, db_index=True)
    signed_pdf = models.FileField(upload_to='signed/', blank=True, null=True)
    public_access_token = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        help_text="Secret token for public (no-login) access to download the signed document"
    )
    retention_days = models.IntegerField(
        default=5,
        help_text="Number of days to keep this document before automatic deletion (0 = keep indefinitely)"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.public_access_token:
            self.public_access_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title or 'Untitled'} - {self.user.username}"

    @property
    def expires_at(self):
        """Return the date when this document will be auto-deleted."""
        if self.retention_days:
            return self.created_at + timedelta(days=self.retention_days)
        return None

    @property
    def is_expired(self):
        """Check if the document has passed its retention period."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    @property
    def days_remaining(self):
        """Return the number of days remaining before auto-deletion."""
        if not self.expires_at:
            return None
        remaining = (self.expires_at - timezone.now()).days
        return max(0, remaining)


class Placement(models.Model):
    PLACEMENT_TYPES = [
        ('signature', 'Signature'),
        ('stamp', 'Stamp'),
    ]
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='placements')
    placement_type = models.CharField(max_length=10, choices=PLACEMENT_TYPES)
    page_number = models.IntegerField(default=1)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)

    class Meta:
        ordering = ['page_number', 'placement_type']

    def __str__(self):
        return f"{self.get_placement_type_display()} on page {self.page_number} of {self.document.title or 'Untitled'}"


class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=None, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        if not self.expires_at:
            return True
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.user.username} - {self.code}"
