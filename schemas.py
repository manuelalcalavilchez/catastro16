"""
Schemas de Pydantic para validación
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from models import PlanType, SubscriptionStatus


# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserWithSubscription(UserResponse):
    subscription: Optional["SubscriptionResponse"] = None


# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


# Subscription Schemas
class SubscriptionBase(BaseModel):
    plan_type: PlanType


class SubscriptionResponse(SubscriptionBase):
    id: str
    status: SubscriptionStatus
    queries_used: int
    queries_limit: int
    current_period_end: Optional[datetime]
    
    class Config:
        from_attributes = True


class SubscriptionCreate(BaseModel):
    plan_type: PlanType
    payment_method_id: Optional[str] = None


# Query Schemas
class QueryCreate(BaseModel):
    referencia_catastral: str


class QueryResponse(BaseModel):
    id: str
    referencia_catastral: str
    has_climate_data: bool
    has_socioeconomic_data: bool
    has_pdf: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Payment Schemas
class PaymentResponse(BaseModel):
    id: str
    amount: float
    currency: str
    status: str
    description: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# Plan Schemas
class PlanInfo(BaseModel):
    name: str
    price: float
    queries_limit: int
    features: list[str]
    stripe_price_id: Optional[str] = None
