"""
Router de suscripciones
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from database import get_db
from auth.dependencies import get_current_active_user
from services.stripe_service import stripe_service
import models
import schemas
from config import settings

router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=List[schemas.PlanInfo])
async def get_plans():
    """Obtener planes disponibles"""
    plans = [
        schemas.PlanInfo(
            name="Free",
            price=0,
            queries_limit=settings.PLAN_FREE_QUERIES,
            features=[
                f"{settings.PLAN_FREE_QUERIES} consultas/mes",
                "Datos catastrales básicos",
                "Mapas WMS"
            ]
        ),
        schemas.PlanInfo(
            name="Professional",
            price=settings.PLAN_PRO_PRICE,
            queries_limit=settings.PLAN_PRO_QUERIES,
            features=[
                f"{settings.PLAN_PRO_QUERIES} consultas/mes",
                "Todos los datos catastrales",
                "Datos climáticos (AEMET)",
                "Datos socioeconómicos (INE)",
                "Informes PDF completos",
                "Soporte prioritario"
            ],
            stripe_price_id=stripe_service.get_price_id_for_plan(models.PlanType.PRO)
        ),
        schemas.PlanInfo(
            name="Enterprise",
            price=settings.PLAN_ENTERPRISE_PRICE,
            queries_limit=-1,  # Ilimitado
            features=[
                "Consultas ilimitadas",
                "Todos los datos Professional",
                "API access",
                "Multi-usuario",
                "Soporte dedicado",
                "SLA garantizado"
            ],
            stripe_price_id=stripe_service.get_price_id_for_plan(models.PlanType.ENTERPRISE)
        )
    ]
    return plans


@router.post("/create", response_model=schemas.SubscriptionResponse)
async def create_subscription(
    subscription_data: schemas.SubscriptionCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Crear o actualizar suscripción"""
    
    # Verificar que no sea plan gratuito
    if subscription_data.plan_type == models.PlanType.FREE:
        raise HTTPException(status_code=400, detail="Cannot create free subscription")
    
    # Obtener suscripción actual
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Crear cliente en Stripe si no existe
    if not subscription.stripe_customer_id:
        stripe_customer_id = stripe_service.create_customer(
            email=current_user.email,
            name=current_user.full_name
        )
        subscription.stripe_customer_id = stripe_customer_id
    
    # Obtener Price ID de Stripe
    price_id = stripe_service.get_price_id_for_plan(subscription_data.plan_type)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan type")
    
    # Crear suscripción en Stripe
    try:
        stripe_subscription = stripe_service.create_subscription(
            customer_id=subscription.stripe_customer_id,
            price_id=price_id,
            payment_method_id=subscription_data.payment_method_id
        )
        
        # Actualizar en BD
        subscription.plan_type = subscription_data.plan_type
        subscription.status = models.SubscriptionStatus.ACTIVE
        subscription.stripe_subscription_id = stripe_subscription.id
        subscription.stripe_price_id = price_id
        
        # Actualizar límites
        if subscription_data.plan_type == models.PlanType.PRO:
            subscription.queries_limit = settings.PLAN_PRO_QUERIES
        elif subscription_data.plan_type == models.PlanType.ENTERPRISE:
            subscription.queries_limit = 999999  # "Ilimitado"
        
        # Actualizar fechas
        subscription.current_period_start = datetime.fromtimestamp(
            stripe_subscription.current_period_start
        )
        subscription.current_period_end = datetime.fromtimestamp(
            stripe_subscription.current_period_end
        )
        
        db.commit()
        db.refresh(subscription)
        
        return subscription
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")


@router.post("/cancel")
async def cancel_subscription(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cancelar suscripción"""
    
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).first()
    
    if not subscription or not subscription.stripe_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    try:
        # Cancelar en Stripe
        stripe_service.cancel_subscription(subscription.stripe_subscription_id)
        
        # Actualizar en BD
        subscription.status = models.SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        
        db.commit()
        
        return {"message": "Subscription cancelled successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error cancelling subscription: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook de Stripe para eventos de suscripción"""
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Manejar eventos
    if event.type == "customer.subscription.updated":
        subscription_data = event.data.object
        
        # Buscar suscripción en BD
        subscription = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == subscription_data.id
        ).first()
        
        if subscription:
            # Actualizar estado
            subscription.status = models.SubscriptionStatus(subscription_data.status)
            subscription.current_period_end = datetime.fromtimestamp(
                subscription_data.current_period_end
            )
            db.commit()
    
    elif event.type == "customer.subscription.deleted":
        subscription_data = event.data.object
        
        subscription = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == subscription_data.id
        ).first()
        
        if subscription:
            subscription.status = models.SubscriptionStatus.CANCELLED
            db.commit()
    
    return {"status": "success"}
