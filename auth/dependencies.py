"""
Dependencias de autenticación para FastAPI
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from auth.jwt import verify_token
import models

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    """Obtener usuario actual desde token"""
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    email = verify_token(token)
    
    if email is None:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == email).first()
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """Verificar que el usuario esté activo"""
    
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return current_user


async def check_subscription_active(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> models.User:
    """Verificar que el usuario tenga suscripción activa"""
    
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).first()
    
    if not subscription:
        raise HTTPException(
            status_code=403,
            detail="No active subscription found"
        )
    
    if subscription.status != models.SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail="Subscription is not active"
        )
    
    return current_user


async def check_query_limit(
    current_user: models.User = Depends(check_subscription_active),
    db: Session = Depends(get_db)
) -> models.User:
    """Verificar que el usuario no haya excedido su límite de consultas"""
    
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).first()
    
    if subscription.queries_used >= subscription.queries_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Query limit reached ({subscription.queries_limit}). Please upgrade your plan."
        )
    
    return current_user
