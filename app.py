"""
Aplicación principal FastAPI - Sistema SaaS Catastro
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pathlib import Path

from config import settings
from database import Base, engine
from routers import auth, subscriptions, catastro, analysis, urban


# ============================
#   Inicializar Base de Datos
# ============================
# Crear todas las tablas declaradas en los modelos
Base.metadata.create_all(bind=engine)


# ============================
#   Crear Aplicación FastAPI
# ============================
app = FastAPI(
    title=settings.APP_NAME,
    description="Sistema SaaS para análisis catastral integral",
    version="1.0.0",
    contact={
        "name": "Catastro SaaS",
        "url": settings.APP_URL
    },
)


# ============================
#   CORS
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # → En producción, reemplazar con tu dominio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================
#   Routers
# ============================
app.include_router(auth.router)
app.include_router(subscriptions.router)
app.include_router(catastro.router)
app.include_router(analysis.router)
app.include_router(urban.router)


# ============================
#   Archivos estáticos
# ============================
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ============================
#   Templates (HTML)
# ============================
templates_path = Path(__file__).parent / "templates"


@app.get("/", response_class=HTMLResponse)
async def root():
    """Página principal del SaaS"""
    landing_page = templates_path / "pages" / "landing.html"

    if landing_page.exists():
        return landing_page.read_text(encoding="utf-8")

    return """
    <html>
        <head><title>Catastro SaaS</title></head>
        <body>
            <h1>🏘️ Catastro SaaS</h1>
            <p>Sistema de análisis catastral integral</p>
            <ul>
                <li><a href="/docs">API Documentation</a></li>
                <li><a href="/static/login.html">Login</a></li>
                <li><a href="/static/register.html">Register</a></li>
            </ul>
        </body>
    </html>
    """


# ============================
#   Health Check
# ============================
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


# ============================
#   Ejecución directa
# ============================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",     # En producción es preferible usar "app:app"
        host="0.0.0.0",
        port=8001,
        reload=True     # Para desarrollo
    )
