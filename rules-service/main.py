from fastapi import FastAPI

from evaluator import evaluate_rules
from models import EvaluateRequest, EvaluateResponse

app = FastAPI(title="FlowForge Rules Service", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(payload: EvaluateRequest):
    actions = evaluate_rules([rule.model_dump() for rule in payload.rules], payload.data)
    return EvaluateResponse(actions=actions)
