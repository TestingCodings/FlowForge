from django.contrib import admin
from django.utils.html import format_html

from .models import NotificationLog, NotificationTemplate, WebhookDeliveryLog
from .tasks import deliver_webhook_task


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("event_trigger", "channel", "workflow_definition", "is_active", "created_at")
    list_filter = ("event_trigger", "channel", "is_active")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("workflow_instance", "channel", "recipient", "status", "attempts", "sent_at")
    list_filter = ("channel", "status")
    search_fields = ("recipient", "workflow_instance__reference_number")


@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(admin.ModelAdmin):
    list_display = ("webhook_subscription", "event_trigger", "status_badge", "attempt", "next_retry_at", "created_at")
    list_filter = ("status", "event_trigger", "created_at")
    search_fields = ("webhook_subscription__url", "workflow_instance__reference_number")
    readonly_fields = ("id", "payload", "created_at", "updated_at", "delivered_at")
    actions = ["replay_delivery"]

    fieldsets = (
        ("Delivery Info", {
            "fields": ("id", "webhook_subscription", "workflow_instance", "event_trigger")
        }),
        ("Payload", {
            "fields": ("payload",),
            "classes": ("collapse",),
        }),
        ("Status", {
            "fields": ("status", "attempt", "http_status_code", "error_message", "next_retry_at")
        }),
        ("Timeline", {
            "fields": ("created_at", "updated_at", "delivered_at"),
        }),
    )

    def status_badge(self, obj):
        colors = {
            "queued": "#3498db",
            "delivered": "#27ae60",
            "failed": "#f39c12",
            "dead_letter": "#e74c3c",
        }
        color = colors.get(obj.status, "#95a5a6")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def replay_delivery(self, request, queryset):
        count = 0
        for log in queryset.filter(status__in=["failed", "dead_letter"]):
            log.status = "queued"
            log.attempt = 0
            log.error_message = ""
            log.next_retry_at = None
            log.save(update_fields=["status", "attempt", "error_message", "next_retry_at"])
            try:
                deliver_webhook_task.delay(str(log.id))
                count += 1
            except Exception:
                pass
        self.message_user(request, f"Queued {count} webhooks for retry.")
    replay_delivery.short_description = "Replay delivery"
