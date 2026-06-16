from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import FormDefinition, FormSubmission
from .serializers import FormDefinitionSerializer, FormSubmissionSerializer


class FormDefinitionViewSet(viewsets.ModelViewSet):
    queryset = FormDefinition.objects.select_related("workflow_definition", "state", "created_by").all()
    serializer_class = FormDefinitionSerializer
    permission_classes = [IsAuthenticated]


class FormSubmissionViewSet(viewsets.ModelViewSet):
    queryset = FormSubmission.objects.select_related(
        "workflow_instance", "form_definition", "submitted_by"
    ).all()
    serializer_class = FormSubmissionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]
