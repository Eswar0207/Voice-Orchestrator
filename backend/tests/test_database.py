"""Tests for database models, CRUD operations, and seeding logic."""
from app.database import CallLog, Company, Customer, LeadStatus, seed_if_empty


def test_seed_creates_two_companies(_isolated_test_db):
    seed_if_empty()
    db = _isolated_test_db()
    try:
        companies = db.query(Company).all()
        assert len(companies) == 2
        names = {c.name for c in companies}
        assert names == {"Apex Properties", "Elite Rentals"}
    finally:
        db.close()


def test_seed_creates_three_customers_per_company(_isolated_test_db):
    seed_if_empty()
    db = _isolated_test_db()
    try:
        for company in db.query(Company).all():
            customers = db.query(Customer).filter(Customer.company_id == company.id).all()
            assert len(customers) == 3
    finally:
        db.close()


def test_seed_is_idempotent(_isolated_test_db):
    seed_if_empty()
    seed_if_empty()  # second call should be a no-op
    db = _isolated_test_db()
    try:
        assert db.query(Company).count() == 2
    finally:
        db.close()


def test_customer_crud(_isolated_test_db):
    db = _isolated_test_db()
    try:
        company = Company(name="Test Co", prompt_instructions="Qualify everyone.")
        db.add(company)
        db.flush()

        customer = Customer(
            company_id=company.id,
            name="Jane Doe",
            phone_number="+15551234567",
            status=LeadStatus.PENDING,
        )
        db.add(customer)
        db.commit()

        fetched = db.query(Customer).filter(Customer.name == "Jane Doe").first()
        assert fetched is not None
        assert fetched.status == LeadStatus.PENDING

        fetched.status = LeadStatus.QUALIFIED
        db.commit()

        refetched = db.query(Customer).filter(Customer.id == fetched.id).first()
        assert refetched.status == LeadStatus.QUALIFIED
    finally:
        db.close()


def test_call_log_foreign_key_to_customer(_isolated_test_db):
    db = _isolated_test_db()
    try:
        company = Company(name="Test Co", prompt_instructions="Qualify everyone.")
        db.add(company)
        db.flush()

        customer = Customer(
            company_id=company.id,
            name="Jane Doe",
            phone_number="+15551234567",
            status=LeadStatus.QUALIFIED,
        )
        db.add(customer)
        db.flush()

        log = CallLog(
            customer_id=customer.id,
            transcript="Agent: Hi! User: Hello.",
            summary="Lead qualified.",
            call_metadata={"duration_seconds": 120},
        )
        db.add(log)
        db.commit()

        fetched_logs = db.query(CallLog).filter(CallLog.customer_id == customer.id).all()
        assert len(fetched_logs) == 1
        assert fetched_logs[0].call_metadata["duration_seconds"] == 120
    finally:
        db.close()
