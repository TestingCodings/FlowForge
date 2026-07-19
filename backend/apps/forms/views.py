from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsViewer, require_min_role

from .models import FormDefinition, FormSubmission
from .serializers import FormDefinitionSerializer, FormSubmissionSerializer


class FormDefinitionViewSet(viewsets.ModelViewSet):
    queryset = FormDefinition.objects.select_related("workflow_definition", "state", "created_by").all()
    serializer_class = FormDefinitionSerializer
    permission_classes = [IsAuthenticated, IsViewer]
    filterset_fields = ["workflow_definition", "state"]

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="create a form definition")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="edit a form definition")
        instance = self.get_object()

        # Check if form has submissions: if yes, create new version instead of editing
        if instance.submissions.exists():
            # Create new version instead of modifying the existing one
            new_version_data = request.data.copy()
            new_version_data["version"] = instance.version + 1
            new_version_data["workflow_definition"] = instance.workflow_definition_id
            new_version_data["state"] = instance.state_id

            serializer = self.get_serializer(data=new_version_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(
                {
                    "detail": "Form has submissions. Created new version instead.",
                    "form": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        # No submissions: safe to edit
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="delete a form definition")
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "This form has submissions and cannot be deleted. Publish a new workflow version instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class FormSubmissionViewSet(viewsets.ModelViewSet):
    queryset = FormSubmission.objects.select_related(
        "workflow_instance", "form_definition", "submitted_by"
    ).all()
    serializer_class = FormSubmissionSerializer
    permission_classes = [IsAuthenticated, IsViewer]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "participant", action="submit a form")
        return super().create(request, *args, **kwargs)
