"""
SQLAlchemy engine/session setup, ORM models, and startup seeding logic.

Models:
    Company  (Tenant)   -> name, prompt_instructions
    Customer (Lead)     -> belongs to Company, has status lifecycle
    CallLog             -> belongs to Customer, transcript + summary + metadata

Customer.company_id + Customer.status are composite-indexed since the
Dispatch Node's primary query is "all PENDING customers for company X."
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    TypeDecorator,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    relationship,
    sessionmaker,
)
from sqlalchemy.types import CHAR

from app.config import get_settings


class UUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID type in local/production (real Postgres),
    and falls back to CHAR(36) for SQLite so the automated test suite can
    run without a real database. No behavior difference in deployed
    environments, which always run against PostgreSQL.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(str(value))


class PortableJSON(TypeDecorator):
    """Uses JSONB on PostgreSQL, generic JSON elsewhere (e.g. SQLite in tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


settings = get_settings()


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    PENDING = "PENDING"
    CALL_INITIATED = "CALL_INITIATED"
    QUALIFIED = "QUALIFIED"
    NOT_INTERESTED = "NOT_INTERESTED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = Column(String, nullable=False)
    description: Mapped[str] = Column(Text, nullable=True)
    prompt_instructions: Mapped[str] = Column(Text, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)

    customers = relationship("Customer", back_populates="company", cascade="all, delete-orphan")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = Column(UUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = Column(UUID(), ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = Column(String, nullable=False)
    phone_number: Mapped[str] = Column(String, nullable=False)  # E.164 format
    status: Mapped[LeadStatus] = Column(Enum(LeadStatus), default=LeadStatus.PENDING, nullable=False)
    vapi_call_id: Mapped[str] = Column(String, nullable=True)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="customers")
    call_logs = relationship("CallLog", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_customers_company_status", "company_id", "status"),
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = Column(UUID(), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = Column(UUID(), ForeignKey("customers.id"), nullable=False)
    transcript: Mapped[str] = Column(Text, nullable=True)
    summary: Mapped[str] = Column(Text, nullable=True)
    call_metadata: Mapped[dict] = Column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="call_logs")


# --- Engine / Session ---------------------------------------------------

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# --- Seeding --------------------------------------------------------------

def seed_if_empty() -> None:
    """Seed two demo tenants with mock leads if the companies table is empty."""
    db: Session = SessionLocal()
    try:
        if db.query(Company).first() is not None:
            return  # already seeded

        apex = Company(
            name="Apex Properties",
            description="Campaign: Qualify leads looking to buy a residential home with a budget of $400,000 or more.",
            prompt_instructions=(
                "You are a real estate qualification agent for Apex Properties, "
                "which sells residential houses. Your goal is to determine if the "
                "lead is seriously looking to BUY a house with a budget of $400,000 "
                "or more. Ask about their budget, timeline, and preferred location. "
                "Be warm, concise, and respectful of their time."
            ),
        )
        elite = Company(
            name="Elite Rentals",
            description="Campaign: Qualify leads looking to rent a luxury apartment for a lease duration of 12 months or longer.",
            prompt_instructions=(
                "You are a leasing qualification agent for Elite Rentals, which "
                "rents luxury apartments. Your goal is to determine if the lead is "
                "seriously looking to RENT an apartment on a lease term of 12 months "
                "or longer. Ask about move-in timeline, budget, and lease length. "
                "Be warm, concise, and respectful of their time."
            ),
        )
        db.add_all([apex, elite])
        db.flush()  # get IDs without committing yet

        # Dynamically generate generic customer names
        first_names = ["John", "Jane", "Robert", "Emily", "Michael", "Sarah"]
        last_names = ["Smith", "Doe", "Johnson", "Williams", "Jones", "Brown"]

        apex_customers = [
            Customer(
                company_id=apex.id,
                name=f"{first_names[0]} {last_names[0]}",
                phone_number="+15550100001",
                status=LeadStatus.PENDING,
            ),
            Customer(
                company_id=apex.id,
                name=f"{first_names[1]} {last_names[1]}",
                phone_number="+15550100002",
                status=LeadStatus.PENDING,
            ),
            Customer(
                company_id=apex.id,
                name=f"{first_names[2]} {last_names[2]}",
                phone_number="+15550100003",
                status=LeadStatus.QUALIFIED,
            ),
        ]

        elite_customers = [
            Customer(
                company_id=elite.id,
                name=f"{first_names[3]} {last_names[3]}",
                phone_number="+15550200001",
                status=LeadStatus.PENDING,
            ),
            Customer(
                company_id=elite.id,
                name=f"{first_names[4]} {last_names[4]}",
                phone_number="+15550200002",
                status=LeadStatus.PENDING,
            ),
            Customer(
                company_id=elite.id,
                name=f"{first_names[5]} {last_names[5]}",
                phone_number="+15550200003",
                status=LeadStatus.NOT_INTERESTED,
            ),
        ]

        db.add_all(apex_customers + elite_customers)
        db.commit()
    finally:
        db.close()
