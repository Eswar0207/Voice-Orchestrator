"""Tests for LangGraph routing and state transitions."""
from unittest.mock import patch

from app.database import CallLog, Company, Customer, LeadStatus
from app.orchestrator import route_decision, run_dispatch, run_evaluation


def test_route_decision_picks_dispatch_when_company_id_present():
    assert route_decision({"company_id": "abc"}) == "dispatch"


def test_route_decision_picks_evaluate_when_transcript_present():
    assert route_decision({"transcript": "hello"}) == "evaluate"


def test_route_decision_ends_when_nothing_actionable():
    assert route_decision({}) == "end"


def test_dispatch_node_updates_status_and_records_call_id(_isolated_test_db):
    db = _isolated_test_db()
    try:
        company = Company(name="Apex Properties", prompt_instructions="Qualify buyers $400k+.")
        db.add(company)
        db.flush()

        customer = Customer(
            company_id=company.id,
            name="Rohan Mehta",
            phone_number="+15550100001",
            status=LeadStatus.PENDING,
        )
        db.add(customer)
        db.commit()
        company_id = str(company.id)
    finally:
        db.close()

    with patch("app.orchestrator.trigger_outbound_call", return_value="vapi_call_123"):
        result = run_dispatch(company_id)

    assert result["dispatched_count"] == 1
    assert result["errors"] == []

    db = _isolated_test_db()
    try:
        updated = db.query(Customer).filter(Customer.name == "Rohan Mehta").first()
        assert updated.status == LeadStatus.CALL_INITIATED
        assert updated.vapi_call_id == "vapi_call_123"
    finally:
        db.close()


def test_dispatch_node_marks_failed_on_vapi_error(_isolated_test_db):
    from app.vapi_client import VapiCallError

    db = _isolated_test_db()
    try:
        company = Company(name="Apex Properties", prompt_instructions="Qualify buyers $400k+.")
        db.add(company)
        db.flush()

        customer = Customer(
            company_id=company.id,
            name="Rohan Mehta",
            phone_number="+15550100001",
            status=LeadStatus.PENDING,
        )
        db.add(customer)
        db.commit()
        company_id = str(company.id)
    finally:
        db.close()

    with patch("app.orchestrator.trigger_outbound_call", side_effect=VapiCallError("boom")):
        result = run_dispatch(company_id)

    assert result["dispatched_count"] == 0
    assert len(result["errors"]) == 1

    db = _isolated_test_db()
    try:
        updated = db.query(Customer).filter(Customer.name == "Rohan Mehta").first()
        assert updated.status == LeadStatus.FAILED
    finally:
        db.close()


def test_evaluation_node_maps_qualified_status(_isolated_test_db):
    db = _isolated_test_db()
    try:
        company = Company(name="Apex Properties", prompt_instructions="Qualify buyers $400k+.")
        db.add(company)
        db.flush()

        customer = Customer(
            company_id=company.id,
            name="Rohan Mehta",
            phone_number="+15550100001",
            status=LeadStatus.CALL_INITIATED,
        )
        db.add(customer)
        db.commit()
        customer_id = str(customer.id)
    finally:
        db.close()

    fake_result = {
        "status": "QUALIFIED",
        "reasoning": "Lead confirmed budget of $500k and wants to buy within 3 months.",
        "summary": "Lead is ready to buy.",
    }
    with patch("app.orchestrator.call_llm_evaluation", return_value=fake_result):
        run_evaluation(
            customer_id=customer_id,
            vapi_call_id="call_abc",
            transcript="Agent: Hi! User: Yes I want to buy.",
            summary="Lead is ready to buy.",
        )

    db = _isolated_test_db()
    try:
        updated = db.query(Customer).filter(Customer.id == customer_id).first()
        assert updated.status == LeadStatus.QUALIFIED

        logs = db.query(CallLog).filter(CallLog.customer_id == customer_id).all()
        assert len(logs) == 1
        assert logs[0].call_metadata["reasoning"].startswith("Lead confirmed budget")
    finally:
        db.close()


def test_evaluation_node_needs_review_abstention_path(_isolated_test_db):
    db = _isolated_test_db()
    try:
        company = Company(name="Apex Properties", prompt_instructions="Qualify buyers $400k+.")
        db.add(company)
        db.flush()

        customer = Customer(
            company_id=company.id,
            name="Ambiguous Lead",
            phone_number="+15550199999",
            status=LeadStatus.CALL_INITIATED,
        )
        db.add(customer)
        db.commit()
        customer_id = str(customer.id)
    finally:
        db.close()

    fake_result = {
        "status": "NEEDS_REVIEW",
        "reasoning": "Call cut off before budget was discussed.",
        "summary": "Inconclusive call.",
    }
    with patch("app.orchestrator.call_llm_evaluation", return_value=fake_result):
        run_evaluation(
            customer_id=customer_id,
            vapi_call_id="call_xyz",
            transcript="Agent: Hi, are you...",
            summary="Inconclusive call.",
        )

    db = _isolated_test_db()
    try:
        updated = db.query(Customer).filter(Customer.id == customer_id).first()
        assert updated.status == LeadStatus.NEEDS_REVIEW
    finally:
        db.close()
