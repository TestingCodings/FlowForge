from rest_framework import serializers

from apps.audit.services import form_submitted
from apps.instances.models import WorkflowInstance
from apps.notifications.services import queue_event_notifications

from .models import FormDefinition, FormSubmission
from .validation import validate_submission


class FormDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormDefinition
        fields = (
            "id",
            "workflow_definition",
            "state",
            "name",
            "schema",
            "version",
            "created_by",
            "created_at",
        )
        read_only_fields = ("id", "created_by", "created_at")

    def validate(self, attrs):
        workflow_definition = attrs.get("workflow_definition") or self.instance.workflow_definition
        state = attrs.get("state") or self.instance.state
        if state.workflow_definition_id != workflow_definition.id:
            raise serializers.ValidationError("state must belong to workflow_definition")
        return attrs

    def create(self, validated_data):
        return FormDefinition.objects.create(created_by=self.context["request"].user, **validated_data)


class FormSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormSubmission
        fields = (
            "id",
            "workflow_instance",
            "form_definition",
            "form_definition_version",
            "submitted_by",
            "submitted_at",
            "data",
        )
        read_only_fields = ("id", "submitted_by", "submitted_at", "form_definition_version")

    def validate(self, attrs):
        workflow_instance: WorkflowInstance = attrs["workflow_instance"]
        form_definition: FormDefinition = attrs["form_definition"]

        if form_definition.workflow_definition_id != workflow_instance.workflow_definition_id:
            raise serializers.ValidationError("form_definition does not belong to instance workflow")

        if form_definition.state_id != workflow_instance.current_state_id:
            raise serializers.ValidationError("form_definition does not match current instance state")

        validate_submission(form_definition.schema, attrs.get("data", {}))
        return attrs

    def create(self, validated_data):
        # Capture form version at submission time for historical accuracy
        form_def = validated_data["form_definition"]
        validated_data["form_definition_version"] = form_def.version
        submission = FormSubmission.objects.create(submitted_by=self.context["request"].user, **validated_data)

        # Merge submitted values into instance metadata so rules can evaluate them
        instance = submission.workflow_instance
        merged = dict(instance.metadata_json or {})
        merged.update(submission.data or {})
        instance.metadata_json = merged
        instance.save(update_fields=["metadata_json", "updated_at"])

        form_submitted(
            workflow_instance=submission.workflow_instance,
            actor=self.context["request"].user,
            payload={"submission_id": str(submission.id), "form_definition_id": str(submission.form_definition_id)},
        )
        queue_event_notifications(
            workflow_instance=submission.workflow_instance,
            event_trigger="form_submitted",
            context_data={
                "form_id": str(submission.form_definition_id),
                "instance": {"reference_number": submission.workflow_instance.reference_number},
                "recipient_email": self.context["request"].user.email,
            },
        )
        return submission
