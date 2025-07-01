from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text
from sqlalchemy.orm import Session
from datetime import datetime
from src.database.connection import Base, SessionLocal


class ProcessedInvoice(Base):
    __tablename__ = "processed_invoices"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    vendor_name = Column(String(255))
    total_amount = Column(Float)
    invoice_date = Column(DateTime)
    invoice_number = Column(String(100))
    line_items = Column(JSON)
    confidence_scores = Column(JSON)
    raw_extraction = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    processing_time = Column(Float)  # seconds


class ConversationHistory(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False)
    user_message = Column(Text)
    agent_response = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    tools_used = Column(JSON)


# Remove these lines as they're now in connection.py

def save_invoice_to_db(invoice_data: dict, db: Session):
    """Save processed invoice to database"""
    db_invoice = ProcessedInvoice(
        filename=invoice_data.get('filename'),
        vendor_name=invoice_data.get('vendor_name'),
        total_amount=invoice_data.get('total_amount'),
        invoice_date=invoice_data.get('invoice_date'),
        invoice_number=invoice_data.get('invoice_number'),
        line_items=invoice_data.get('line_items'),
        confidence_scores=invoice_data.get('confidence_scores'),
        raw_extraction=invoice_data.get('raw_extraction'),
        processing_time=invoice_data.get('processing_time')
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice


def search_invoices_by_vendor(vendor: str, db: Session):
    """Search invoices by vendor name"""
    return db.query(ProcessedInvoice).filter(
        ProcessedInvoice.vendor_name.ilike(f"%{vendor}%")
    ).all()


def get_recent_invoices(limit: int, db: Session):
    """Get recent invoices"""
    return db.query(ProcessedInvoice).order_by(
        ProcessedInvoice.created_at.desc()
    ).limit(limit).all()


def get_invoices_by_amount_range(min_amount: float, max_amount: float, db: Session):
    """Get invoices in amount range"""
    return db.query(ProcessedInvoice).filter(
        ProcessedInvoice.total_amount >= min_amount,
        ProcessedInvoice.total_amount <= max_amount
    ).all()