"""
Modelos de base de datos
"""
from sqlalchemy import Boolean, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class PlanType(str, enum.Enum):
    """Tipos de plan"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    """Estados de suscripción"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAST_DUE = "past_due"


class User(Base):
    """Modelo de Usuario"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    queries = relationship("Query", back_populates="user")
    payments = relationship("Payment", back_populates="user")


class Subscription(Base):
    """Modelo de Suscripción"""
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True)
    plan_type = Column(SQLEnum(PlanType), default=PlanType.FREE)
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    
    # Stripe
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    stripe_price_id = Column(String)
    
    # Límites
    queries_used = Column(Integer, default=0)
    queries_limit = Column(Integer, default=3)  # Free plan default
    
    # Fechas
    current_period_start = Column(DateTime(timezone=True))
    current_period_end = Column(DateTime(timezone=True))
    cancel_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="subscription")


class Query(Base):
    """Modelo de Consulta Catastral"""
    __tablename__ = "queries"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"))
    referencia_catastral = Column(String, nullable=False)
    
    # Datos generados
    has_climate_data = Column(Boolean, default=False)
    has_socioeconomic_data = Column(Boolean, default=False)
    has_pdf = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="queries")


class Payment(Base):
    """Modelo de Pago"""
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"))
    
    # Stripe
    stripe_payment_intent_id = Column(String)
    stripe_invoice_id = Column(String)
    
    # Detalles
    amount = Column(Float)
    currency = Column(String, default="eur")
    status = Column(String)  # succeeded, failed, pending
    
    # Metadata
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="payments")
