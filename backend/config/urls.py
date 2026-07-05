from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import RegisterView, LoginView, MeView, UserViewSet, WorkspaceView
from apps.audit.views import AuditLogAdminViewSet, AuditTrailByInstanceView
from apps.forms.views import FormDefinitionViewSet, FormSubmissionViewSet
from apps.instances.views import WorkflowInstanceViewSet
from apps.notifications.views import (
    NotificationLogViewSet,
    NotificationTemplateViewSet,
    WebhookSubscriptionViewSet,
)
from apps.tasks.views import TaskViewSet
from apps.workflows.views import WorkflowDefinitionViewSet, RuleViewSet, StateViewSet, TransitionViewSet
from .health import health_check

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"workflows", WorkflowDefinitionViewSet, basename="workflow")
router.register(r"states", StateViewSet, basename="state")
router.register(r"transitions", TransitionViewSet, basename="transition")
router.register(r"rules", RuleViewSet, basename="rule")
router.register(r"instances", WorkflowInstanceViewSet, basename="instance")
router.register(r"forms", FormDefinitionViewSet, basename="form")
router.register(r"submissions", FormSubmissionViewSet, basename="submission")
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"audit", AuditLogAdminViewSet, basename="audit")
router.register(r"notification-templates", NotificationTemplateViewSet, basename="notification-template")
router.register(r"notification-logs", NotificationLogViewSet, basename="notification-log")
router.register(r"webhooks", WebhookSubscriptionViewSet, basename="webhook")

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path("api/auth/register/", RegisterView.as_view(), name="auth-register"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),
    path("api/workspace/", WorkspaceView.as_view(), name="workspace"),
    path("api/audit/<uuid:instance_id>/", AuditTrailByInstanceView.as_view(), name="audit-by-instance"),
    path("api/", include(router.urls)),
    # Health
    path("api/health/", health_check, name="health-check"),
]
