from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "has_signature", "has_stamp", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "user__email"]

    def has_signature(self, obj):
        return bool(obj.signature)
    has_signature.boolean = True

    def has_stamp(self, obj):
        return bool(obj.stamp)
    has_stamp.boolean = True
