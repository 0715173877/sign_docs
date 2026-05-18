import re
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator


def normalize_phone(phone):
    """Normalize phone number for storage by stripping non-digits and normalizing prefix.
    Handles cases like 0712345678 vs 255712345678 vs +255712345678 vs 712345678.
    Returns a normalized digit-only string for comparison, or None if empty.
    """
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return None
    # Normalize: if starts with 0, replace with 255 (Tanzania country code)
    if digits.startswith('0'):
        digits = '255' + digits[1:]
    # If it's a short number without country code (e.g., 712345678), assume 255
    elif not digits.startswith('255') and len(digits) == 9:
        digits = '255' + digits
    return digits


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    signature = models.ImageField(
        upload_to='signatures/',
        validators=[FileExtensionValidator(['png'])],
        blank=True, null=True,
        help_text="Upload your signature as a transparent PNG"
    )
    stamp = models.ImageField(
        upload_to='stamps/',
        validators=[FileExtensionValidator(['png'])],
        blank=True, null=True,
        help_text="Upload your stamp/logo as a transparent PNG"
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="Phone number for receiving OTP via SMS (e.g. +255712345678)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Auto-normalize phone number before saving."""
        if self.phone_number:
            normalized = normalize_phone(self.phone_number)
            if normalized:
                self.phone_number = normalized
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def has_signature(self):
        return bool(self.signature)

    def has_stamp(self):
        return bool(self.stamp)

    def has_phone(self):
        return bool(self.phone_number)

    def formatted_phone(self):
        """Return phone number in a human-readable format (e.g., +255 712 345 678)."""
        if not self.phone_number:
            return ''
        num = self.phone_number
        if len(num) == 12 and num.startswith('255'):
            return f"+{num[:3]} {num[3:6]} {num[6:9]} {num[9:]}"
        return f"+{num}"
