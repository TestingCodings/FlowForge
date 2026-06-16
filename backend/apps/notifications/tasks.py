from celery import shared_task

from .services import dispatch_notification


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def dispatch_notification_task(self, notification_log_id: str):
    try:
        dispatch_notification(notification_log_id)
    except Exception as exc:
        raise self.retry(exc=exc)
