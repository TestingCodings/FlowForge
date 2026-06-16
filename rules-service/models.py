from pydantic import BaseModel, Field


class Condition(BaseModel):
    field: str | None = None
    operator: str
    value: object | None = None
    conditions: list["Condition"] | None = None


Condition.model_rebuild()


class Rule(BaseModel):
    id: str | None = None
    condition: Condition
    action: dict = Field(default_factory=dict)
    priority: int = 100


class EvaluateRequest(BaseModel):
    rules: list[Rule]
    data: dict


class EvaluateResponse(BaseModel):
    actions: list[dict]
