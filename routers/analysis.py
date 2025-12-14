"""
Router para análisis catastrales avanzados (KML, GeoJSON)
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import shutil
import uuid
import os
import json

from auth.dependencies import get_current_active_user, check_query_limit
import models
from services.advanced_analysis import AnalizadorAfeccionesAmbientales

router = APIRouter(prefix="/api/analysis", tags=["Análisis Avanzado"])

# Directorio temporal para procesamiento
TEMP_DIR = Path("temp_analysis")
OUTPUT_DIR = Path("static/analysis_results")

# Asegurar directorios
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/kml")
async def analyze_kml(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: models.User = Depends(check_query_limit)
):
    """
    Sube un archivo KML para realizar un análisis de afecciones ambientales detallado.
    
    El proceso:
    1. Guarda el KML temporalmente.
    2. Ejecuta el AnalizadorAfeccionesAmbientales.
    3. Genera PDF, JSON e imágenes.
    4. Devuelve los resultados JSON y enlaces de descarga.
    """
    
    if not file.filename.lower().endswith('.kml'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un KML (.kml)")

    # Generar ID único para este análisis
    analysis_id = str(uuid.uuid4())
    job_dir = OUTPUT_DIR / analysis_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Guardar archivo subido
    kml_path = job_dir / "parcela.kml"
    try:
        with open(kml_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        shutil.rmtree(job_dir)
        raise HTTPException(status_code=500, detail=f"Error guardando archivo: {e}")

    # Ejecutar análisis (síncrono por ahora para devolver resultado inmediato, 
    # aunque idealmente debería ser background tarea para archivos grandes)
    try:
        # Instanciar analizador
        analizador = AnalizadorAfeccionesAmbientales(str(kml_path))
        
        # Ejecutar pipeline
        analizador.parsear_kml()
        analizador.validar_con_catastro() # Intenta obtener referencia oficial
        analizador.analizar_todas_capas(width=1000, height=1000)
        
        # Generar salidas
        output_imgs_dir = job_dir / "imagenes"
        analizador.guardar_imagenes(str(output_imgs_dir))
        
        json_path = job_dir / "informe.json"
        analizador.exportar_json(str(json_path))
        
        pdf_path = job_dir / "informe_completo.pdf"
        analizador.generar_pdf(str(pdf_path))
        
        # Leer resultado JSON para devolverlo
        with open(json_path, 'r', encoding='utf-8') as f:
            resultados = json.load(f)
            
        # Construir URLs de descarga (asumiendo que static está montado)
        base_url = "/static/analysis_results/" + analysis_id
        
        return {
            "status": "success",
            "analysis_id": analysis_id,
            "summary": resultados.get("afecciones", {}),
            "catastro_data": resultados.get("catastro", {}),
            "download_urls": {
                "pdf": f"{base_url}/informe_completo.pdf",
                "json": f"{base_url}/informe.json",
                "kml": f"{base_url}/parcela.kml"
            }
        }

    except Exception as e:
        # Limpiar en caso de error grave
        # shutil.rmtree(job_dir) 
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error durante el análisis: {str(e)}")


@router.get("/download/{analysis_id}/{filename}")
async def download_result(analysis_id: str, filename: str):
    """Descargar un archivo específico de un análisis previo"""
    file_path = OUTPUT_DIR / analysis_id / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
    return FileResponse(file_path)
