"""
Router para análisis urbanísticos (GeoJSON) - Integración 16.py
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from pathlib import Path
import shutil
import uuid
import os
import json

from auth.dependencies import get_current_active_user, check_query_limit
import models
from services.urban_analysis import AnalizadorUrbanistico

router = APIRouter(prefix="/api/urban", tags=["Análisis Urbanístico"])

# Directorio temporal y de salida (debe ser accesible estáticamente para descargas)
OUTPUT_DIR = Path("static/urban_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/geojson")
async def analyze_urban_geojson(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: models.User = Depends(check_query_limit)
):
    """
    Sube un archivo GeoJSON para realizar un análisis urbanístico (Plan General, etc).
    """
    
    if not (file.filename.lower().endswith('.geojson') or file.filename.lower().endswith('.json')):
         raise HTTPException(status_code=400, detail="El archivo debe ser un GeoJSON (.geojson/.json)")

    # ID Único
    analysis_id = str(uuid.uuid4())
    job_dir = OUTPUT_DIR / analysis_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Guardar archivo
    geojson_path = job_dir / "parcela.geojson"
    try:
        with open(geojson_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        shutil.rmtree(job_dir)
        raise HTTPException(status_code=500, detail=f"Error guardando archivo: {e}")

    try:
        # Instanciar servicio
        analizador = AnalizadorUrbanistico(str(geojson_path), str(job_dir))
        
        # Ejecutar análisis (síncrono por simplicidad, mover a celery/background idealmente)
        resultado = analizador.ejecutar_analisis()
        
        base_url = f"/static/urban_results/{analysis_id}"
        
        return {
            "status": "success",
            "analysis_id": analysis_id,
            "data": resultado["data"],
            "files": {
                k: f"{base_url}/{v}" if v else None for k, v in resultado["files"].items()
            },
            "summary_json": f"{base_url}/resultados_urbanismo.json"
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error durante el análisis urbanístico: {str(e)}")

@router.get("/download/{analysis_id}/{filename}")
async def download_urban_result(analysis_id: str, filename: str):
    """Descarga de archivos generados"""
    file_path = OUTPUT_DIR / analysis_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(file_path)
