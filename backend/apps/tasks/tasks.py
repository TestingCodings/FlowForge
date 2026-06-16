from celery import shared_task

from .services import mark_overdue_tasks


@shared_task(name="tasks.mark_overdue_tasks")
def mark_overdue_tasks_job():
    return mark_overdue_tasks()
