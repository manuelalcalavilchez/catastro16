# Despliegue en Easypanel

Este documento detalla los pasos para desplegar **Catastro SaaS** en Easypanel utilizando Docker.

## 1. Crear Base de Datos (PostgreSQL)

1. En tu proyecto de Easypanel, crea un nuevo servicio de tipo **PostgreSQL**.
2. Nómbralo (ej. `catastro-db`).
3. Toma nota de las credenciales (Usuario, Contraseña, Nombre de BD) y el **Internal Host** (normalmente el nombre del servicio, ej. `catastro-db`).

## 2. Crear Servicio de Aplicación

1. Crea un nuevo servicio de tipo **App**.
2. Nómbralo (ej. `catastro-api`).
3. En **Source**, conecta tu repositorio (Github/GitLab) y selecciona la rama `main`.
4. En **Build**, selecciona **Dockerfile**.
   - Easypanel detectará automáticamente el archivo `Dockerfile` en la raíz.
5. En **Ports**, asegúrate de exponer el puerto interno `8001` hacia el puerto externo `80` (HTTP).

## 3. Configurar Variables de Entorno

Ve a la pestaña **Environment** de tu servicio `catastro-api` y añade las siguientes variables. Sustituye los valores según tu configuración:

```env
# Conexión a Base de Datos (Usa el Internal Host de tu servicio de DB)
DATABASE_URL=postgresql://<usuario>:<password>@<nombre-servicio-db>:5432/<nombre-db>

# Seguridad (Generar nuevos para producción)
SECRET_KEY=cambiar_esto_por_una_clave_segura_larga
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Configuración de App
APP_NAME="Catastro SaaS"
APP_URL=https://<tu-dominio-easypanel>
FRONTEND_URL=https://<tu-dominio-easypanel>

# Stripe (Credenciales de tu cuenta de Stripe)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (Configura tu servicio SMTP)
MAIL_USERNAME=apikey
MAIL_PASSWORD=...
MAIL_FROM=no-reply@tu-dominio.com
MAIL_PORT=587
MAIL_SERVER=smtp.sendgrid.net

# API Externas
AEMET_API_KEY=tu_api_key_aemet

# Configuración de Planes
PLAN_FREE_QUERIES=3
PLAN_PRO_QUERIES=100
PLAN_PRO_PRICE=24.99
PLAN_ENTERPRISE_PRICE=149.99
```

## 4. Desplegar

1. Dale al botón **Deploy**.
2. Easypanel construirá la imagen usando el `Dockerfile` actualizado.
3. El sistema incluye ahora generación automática de:
   - Informes PDF
   - Archivos KML (Google Earth)
   - Archivos GML (Catastro)
   - Descarga de planos y ortofotos
   - Todo comprimido en ZIP descargable
4. Una vez "Running", podrás acceder a tu dominio.
5. La documentación de la API estará disponible en `https://<tu-dominio>/docs`.

