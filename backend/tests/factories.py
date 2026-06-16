import factory

from apps.accounts.models import User
from apps.instances.models import WorkflowInstance
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = factory.Sequence(lambda n: f"User{n}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "StrongPass123!")
        if create:
            obj.save(update_fields=["password"])


class WorkflowDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorkflowDefinition

    name = factory.Sequence(lambda n: f"Workflow {n}")
    description = "Generated workflow"
    version = 1
    is_active = True
    created_by = factory.SubFactory(UserFactory)


class StateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = State

    workflow_definition = factory.SubFactory(WorkflowDefinitionFactory)
    name = factory.Sequence(lambda n: f"State-{n}")
    display_name = factory.LazyAttribute(lambda o: o.name)
    is_initial = False
    is_terminal = False
    position_order = factory.Sequence(lambda n: n + 1)


class TransitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transition

    workflow_definition = factory.SubFactory(WorkflowDefinitionFactory)
    from_state = factory.SubFactory(StateFactory, workflow_definition=factory.SelfAttribute("..workflow_definition"))
    to_state = factory.SubFactory(StateFactory, workflow_definition=factory.SelfAttribute("..workflow_definition"))
    name = factory.Sequence(lambda n: f"Transition-{n}")
    requires_approval = False


class WorkflowInstanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorkflowInstance

    workflow_definition = factory.SubFactory(WorkflowDefinitionFactory)
    created_by = factory.SelfAttribute("workflow_definition.created_by")
    metadata = factory.Dict({"seeded": True})

    @factory.post_generation
    def ensure_initial_state(obj, create, extracted, **kwargs):
        if not create:
            return
        if not obj.workflow_definition.states.filter(is_initial=True).exists():
            StateFactory(
                workflow_definition=obj.workflow_definition,
                name="Draft",
                display_name="Draft",
                is_initial=True,
                is_terminal=False,
                position_order=1,
            )
            obj.save()


class RuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Rule

    workflow_definition = factory.SubFactory(WorkflowDefinitionFactory)
    transition = None
    condition = factory.Dict({"field": "value", "operator": "eq", "value": 1})
    action = factory.Dict({"type": "notify", "channel": "email"})
    priority = 100
