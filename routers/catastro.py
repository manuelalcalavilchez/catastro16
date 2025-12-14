"""
Router de consultas catastrales
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path

from database import get_db, SessionLocal
from auth.dependencies import get_current_active_user, check_query_limit
import models
import schemas
from services.catastro_engine import procesar_y_comprimir

router = APIRouter(prefix="/api/catastro", tags=["Catastro"])


def run_catastro_process(query_id: str, ref: str, output_dir: str):
    """Tarea en segundo plano para procesar la referencia catastral"""
    db = SessionLocal()
    try:
        print(f"🔄 Iniciando procesamiento para {ref}...")
        zip_path, results = procesar_y_comprimir(ref, output_dir)
        
        # Actualizar estado en BD
        query = db.query(models.Query).filter(models.Query.id == query_id).first()
        if query:
            query.has_pdf = results.get('informe_pdf', False)
            # Mapeamos 'capas_afecciones' a 'has_climate_data' como proxy temporal
            query.has_climate_data = results.get('capas_afecciones', False)
            
            # Si hay ZIP, podríamos guardar la URL si el modelo tuviera campo. 
            # Por ahora asumimos que el frontend construye la URL: /static/downloads/{ref}/{ref}_completo.zip
            
            db.commit()
            print(f"✅ Procesamiento finalizado para {ref}")
    except Exception as e:
        print(f"❌ Error procesando {ref}: {e}")
    finally:
        db.close()


@router.post("/query", response_model=schemas.QueryResponse)
async def create_query(
    query_data: schemas.QueryCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(check_query_limit),
    db: Session = Depends(get_db)
):
    """
    Crear nueva consulta catastral
    
    Este endpoint:
    1. Verifica que el usuario tenga consultas disponibles
    2. Crea el registro de consulta
    3. Incrementa el contador de consultas usadas
    4. Lanza el procesamiento en segundo plano
    5. Devuelve la información de la consulta
    """
    
    # Crear consulta
    new_query = models.Query(
        user_id=current_user.id,
        referencia_catastral=query_data.referencia_catastral,
        has_climate_data=False,
        has_socioeconomic_data=False,
        has_pdf=False
    )
    
    db.add(new_query)
    
    # Incrementar contador de consultas
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).first()
    
    subscription.queries_used += 1
    
    db.commit()
    db.refresh(new_query)
    
    # Directorio de salida (dentro de static para poder descargar)
    # IMPORTANTE: Asegurarse de que este directorio existe en el Dockerfile o se crea aquí
    output_dir = Path("static/downloads")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Lanzar tarea en segundo plano
    background_tasks.add_task(
        run_catastro_process,
        query_id=new_query.id,
        ref=query_data.referencia_catastral,
        output_dir=str(output_dir)
    )
    
    return new_query


@router.get("/queries", response_model=List[schemas.QueryResponse])
async def get_my_queries(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Obtener historial de consultas del usuario"""
    
    queries = db.query(models.Query).filter(
        models.Query.user_id == current_user.id
    ).order_by(models.Query.created_at.desc()).offset(skip).limit(limit).all()
    
    return queries


@router.get("/queries/{query_id}", response_model=schemas.QueryResponse)
async def get_query(
    query_id: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener detalles de una consulta específica"""
    
    query = db.query(models.Query).filter(
        models.Query.id == query_id,
        models.Query.user_id == current_user.id
    ).first()
    
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    
    return query


@router.get("/stats")
async def get_stats(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener estadísticas de uso del usuario"""
    
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).first()
    
    total_queries = db.query(models.Query).filter(
        models.Query.user_id == current_user.id
    ).count()
    
    return {
        "total_queries": total_queries,
        "queries_used_this_period": subscription.queries_used if subscription else 0,
        "queries_limit": subscription.queries_limit if subscription else 0,
        "queries_remaining": (subscription.queries_limit - subscription.queries_used) if subscription else 0,
        "plan_type": subscription.plan_type if subscription else None
    }
