from django.contrib import admin

from .models import NotificationLog, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("event_trigger", "channel", "workflow_definition", "is_active", "created_at")
    list_filter = ("event_trigger", "channel", "is_active")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("workflow_instance", "channel", "recipient", "status", "attempts", "sent_at")
    list_filter = ("channel", "status")
    search_fields = ("recipient", "workflow_instance__reference_number")
