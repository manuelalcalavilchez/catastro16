"""
Servicio de integración con Stripe
"""
import stripe
from config import settings
from typing import Optional
import models

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """Servicio para manejar pagos con Stripe"""
    
    @staticmethod
    def create_customer(email: str, name: Optional[str] = None) -> str:
        """Crear cliente en Stripe"""
        customer = stripe.Customer.create(
            email=email,
            name=name
        )
        return customer.id
    
    @staticmethod
    def create_subscription(
        customer_id: str,
        price_id: str,
        payment_method_id: Optional[str] = None
    ):
        """Crear suscripción en Stripe"""
        
        params = {
            "customer": customer_id,
            "items": [{"price": price_id}],
            "expand": ["latest_invoice.payment_intent"]
        }
        
        if payment_method_id:
            params["default_payment_method"] = payment_method_id
        
        subscription = stripe.Subscription.create(**params)
        return subscription
    
    @staticmethod
    def cancel_subscription(subscription_id: str):
        """Cancelar suscripción en Stripe"""
        return stripe.Subscription.delete(subscription_id)
    
    @staticmethod
    def get_subscription(subscription_id: str):
        """Obtener información de suscripción"""
        return stripe.Subscription.retrieve(subscription_id)
    
    @staticmethod
    def create_checkout_session(
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str
    ):
        """Crear sesión de checkout"""
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url
        )
        return session
    
    @staticmethod
    def construct_webhook_event(payload: bytes, sig_header: str):
        """Construir evento de webhook"""
        return stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET
        )
    
    @staticmethod
    def get_price_id_for_plan(plan_type: models.PlanType) -> Optional[str]:
        """Obtener Stripe Price ID según el plan"""
        # TODO: Configurar estos IDs en Stripe Dashboard
        price_ids = {
            models.PlanType.PRO: "price_pro_monthly",  # Reemplazar con ID real
            models.PlanType.ENTERPRISE: "price_enterprise_monthly"  # Reemplazar con ID real
        }
        return price_ids.get(plan_type)


stripe_service = StripeService()
