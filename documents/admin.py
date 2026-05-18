from django.contrib import admin
from .models import Document, OTP


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "is_signed", "retention_days", "days_remaining_display", "created_at"]
    list_filter = ["is_signed", "created_at"]
    search_fields = ["title", "user__username"]
    fieldsets = (
        (None, {
            "fields": ("user", "title", "pdf_file", "total_pages", "is_signed", "signed_pdf")
        }),
        ("Retention Settings", {
            "fields": ("retention_days",),
            "description": "Documents are automatically deleted after this many days from upload. Set to 0 to keep indefinitely.",
        }),
    )

    @admin.display(description="Days Left")
    def days_remaining_display(self, obj):
        if obj.retention_days == 0:
            return "♾️ Never"
        remaining = obj.days_remaining
        if remaining == 0 and obj.is_expired:
            return "⚠️ Expired"
        return f"{remaining} days"


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ["user", "document", "is_used", "created_at"]
    list_filter = ["is_used", "created_at"]
    search_fields = ["user__username", "code"]
