r"""
LangGraph orchestrator — the agentic brain of the operation.

Graph shape:

    Start -> Router --(company_id provided)--> Dispatch -> [DB: CALL_INITIATED] -> End
                  \--(transcript provided)----> Evaluate -> StateUpdate -> SaveLogs -> End

A single entry point handles both flows (campaign trigger from the frontend,
and webhook-driven evaluation from Vapi) so the orchestration logic is
centrally testable rather than split across two separate graphs.
"""
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import CallLog, Company, Customer, LeadStatus, SessionLocal
from app.llm_eval import call_llm_evaluation
from app.vapi_client import VapiCallError, trigger_outbound_call

logger = logging.getLogger(__name__)
settings = get_settings()


class OrchestratorState(TypedDict, total=False):
    # Dispatch flow inputs
    company_id: Optional[str]

    # Evaluation flow inputs (from webhook)
    customer_id: Optional[str]
    vapi_call_id: Optional[str]
    transcript: Optional[str]
    summary: Optional[str]
    call_metadata: Optional[dict]

    # Outputs
    evaluation_result: Optional[dict]
    dispatched_count: Optional[int]
    errors: Optional[list]
    dispatched_customers: Optional[list[dict]]


# --- Nodes -----------------------------------------------------------------

def router_node(state: OrchestratorState) -> OrchestratorState:
    """Pure pass-through; routing decision is made by the conditional edge below."""
    return state


def route_decision(state: OrchestratorState) -> str:
    if state.get("company_id"):
        return "dispatch"
    if state.get("transcript"):
        return "evaluate"
    # Nothing actionable provided; end gracefully rather than raising.
    return "end"


def dispatch_node(state: OrchestratorState) -> OrchestratorState:
    """
    Fetches all PENDING customers for company_id, triggers an outbound Vapi
    call for each, and updates status to CALL_INITIATED (or FAILED on error).
    """
    db: Session = SessionLocal()
    errors: list[str] = []
    dispatched = 0
    dispatched_list = []
    try:
        company = db.query(Company).filter(Company.id == state["company_id"]).first()
        if not company:
            errors.append(f"Company {state['company_id']} not found")
            return {**state, "dispatched_count": 0, "errors": errors}

        pending = (
            db.query(Customer)
            .filter(Customer.company_id == company.id, Customer.status == LeadStatus.PENDING)
            .all()
        )

        for customer in pending:
            try:
                if settings.SIMULATION_MODE:
                    import uuid
                    call_id = f"mock_call_{uuid.uuid4().hex[:8]}"
                else:
                    call_id = trigger_outbound_call(
                        customer_id=str(customer.id),
                        company_id=str(company.id),
                        customer_name=customer.name,
                        customer_phone=customer.phone_number,
                        company_name=company.name,
                        company_prompt_instructions=company.prompt_instructions,
                    )
                customer.status = LeadStatus.CALL_INITIATED
                customer.vapi_call_id = call_id
                dispatched += 1
                dispatched_list.append({
                    "id": str(customer.id),
                    "name": customer.name,
                    "phone": customer.phone_number
                })
            except VapiCallError as exc:
                logger.error("Dispatch failed for customer %s: %s", customer.id, exc)
                customer.status = LeadStatus.FAILED
                errors.append(f"{customer.name}: {exc}")

        db.commit()
    finally:
        db.close()

    return {**state, "dispatched_count": dispatched, "errors": errors, "dispatched_customers": dispatched_list}


def evaluate_node(state: OrchestratorState) -> OrchestratorState:
    """
    Calls the LLM evaluation interface against the transcript, scoped to the
    owning company's qualification criteria.
    """
    db: Session = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.id == state["customer_id"]).first()
        if not customer:
            return {**state, "evaluation_result": {
                "status": "NEEDS_REVIEW",
                "reasoning": "Customer not found for this webhook payload.",
                "summary": state.get("summary", ""),
            }}

        company = db.query(Company).filter(Company.id == customer.company_id).first()

        result = call_llm_evaluation(
            company_criteria=company.prompt_instructions,
            transcript=state.get("transcript", ""),
            vapi_summary=state.get("summary"),
        )
    finally:
        db.close()

    return {**state, "evaluation_result": dict(result)}


def state_update_node(state: OrchestratorState) -> OrchestratorState:
    """
    Updates the customer's status based on the evaluation result and writes
    a CallLog row with transcript, summary, and metadata.
    """
    db: Session = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.id == state["customer_id"]).first()
        if customer:
            result = state.get("evaluation_result") or {}
            new_status = result.get("status", "NEEDS_REVIEW")
            try:
                customer.status = LeadStatus(new_status)
            except ValueError:
                customer.status = LeadStatus.NEEDS_REVIEW

            log = CallLog(
                customer_id=customer.id,
                transcript=state.get("transcript", ""),
                summary=result.get("summary") or state.get("summary", ""),
                call_metadata={
                    "vapi_call_id": state.get("vapi_call_id"),
                    "reasoning": result.get("reasoning", ""),
                    **(state.get("call_metadata") or {}),
                },
            )
            db.add(log)
            db.commit()
    finally:
        db.close()

    return state


# --- Graph construction ------------------------------------------------

def build_graph():
    graph = StateGraph(OrchestratorState)

    graph.add_node("router", router_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("state_update", state_update_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {"dispatch": "dispatch", "evaluate": "evaluate", "end": END},
    )
    graph.add_edge("dispatch", END)
    graph.add_edge("evaluate", "state_update")
    graph.add_edge("state_update", END)

    return graph.compile()


orchestrator_graph = build_graph()


def run_dispatch(company_id: str) -> OrchestratorState:
    return orchestrator_graph.invoke({"company_id": company_id})


def run_evaluation(
    *,
    customer_id: str,
    vapi_call_id: Optional[str],
    transcript: str,
    summary: Optional[str],
    call_metadata: Optional[dict] = None,
) -> OrchestratorState:
    return orchestrator_graph.invoke(
        {
            "customer_id": customer_id,
            "vapi_call_id": vapi_call_id,
            "transcript": transcript,
            "summary": summary,
            "call_metadata": call_metadata or {},
        }
    )
