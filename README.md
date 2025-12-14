# 🏘️ Catastro SaaS

Sistema SaaS completo para análisis catastral integral con datos ambientales y socioeconómicos.

## 🚀 Características

- ✅ **Autenticación completa** (JWT, registro, login)
- ✅ **Sistema de suscripciones** (Free, Pro, Enterprise)
- ✅ **Integración con Stripe** para pagos
- ✅ **Gestión de consultas** catastrales
- ✅ **Límites por plan** (3, 100, ilimitado)
- ✅ **API REST completa** con documentación automática
- ✅ **Base de datos PostgreSQL**

## 📋 Requisitos

- Python 3.11+
- PostgreSQL 14+
- Cuenta de Stripe (para pagos)

## 🔧 Instalación

### 1. Clonar repositorio

```bash
git clone <repo-url>
cd CatastroSaaS
```

### 2. Crear entorno virtual

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y configura:
- `DATABASE_URL`: URL de PostgreSQL
- `SECRET_KEY`: Genera con `openssl rand -hex 32`
- `STRIPE_SECRET_KEY`: De tu dashboard de Stripe
- `STRIPE_PUBLISHABLE_KEY`: De tu dashboard de Stripe
- `STRIPE_WEBHOOK_SECRET`: Después de configurar webhook

### 5. Crear base de datos

```bash
# Crear base de datos en PostgreSQL
createdb catastro_saas

# Las tablas se crean automáticamente al iniciar la app
```

### 6. Iniciar aplicación

```bash
python app.py
```

La aplicación estará disponible en: `http://localhost:8000`

## 📚 Documentación API

Una vez iniciada la aplicación, accede a:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔐 Endpoints Principales

### Autenticación

- `POST /api/auth/register` - Registrar usuario
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Obtener usuario actual

### Suscripciones

- `GET /api/subscriptions/plans` - Listar planes
- `POST /api/subscriptions/create` - Crear suscripción
- `POST /api/subscriptions/cancel` - Cancelar suscripción
- `POST /api/subscriptions/webhook` - Webhook de Stripe

### Catastro

- `POST /api/catastro/query` - Crear consulta
- `GET /api/catastro/queries` - Listar consultas
- `GET /api/catastro/stats` - Estadísticas de uso

## 💳 Configuración de Stripe

### 1. Crear cuenta en Stripe

Visita https://dashboard.stripe.com/register

### 2. Obtener API Keys

Dashboard → Developers → API keys

### 3. Crear productos y precios

Dashboard → Products → Add product

Crea dos productos:
- **Professional**: €24.99/mes
- **Enterprise**: €149.99/mes

Copia los Price IDs y actualiza en `services/stripe_service.py`

### 4. Configurar Webhook

Dashboard → Developers → Webhooks → Add endpoint

URL: `https://tu-dominio.com/api/subscriptions/webhook`

Eventos a escuchar:
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

Copia el Webhook Secret a `.env`

## 🗄️ Estructura de Base de Datos

### Tablas

- `users` - Usuarios del sistema
- `subscriptions` - Suscripciones activas
- `queries` - Historial de consultas
- `payments` - Historial de pagos

## 🔄 Flujo de Usuario

1. Usuario se registra → Plan Free (3 consultas)
2. Usuario hace login → Recibe JWT token
3. Usuario selecciona plan Pro/Enterprise
4. Pago con Stripe → Suscripción activada
5. Usuario hace consultas → Contador se incrementa
6. Al llegar al límite → Debe renovar/upgrade

## 🧪 Testing

```bash
# Instalar dependencias de testing
pip install pytest pytest-asyncio httpx

# Ejecutar tests
pytest
```

## 🚀 Despliegue

### Railway.app (Recomendado)

1. Conecta tu repositorio GitHub
2. Railway detecta Python automáticamente
3. Añade PostgreSQL desde Add-ons
4. Configura variables de entorno
5. Deploy automático

### Heroku

```bash
# Login
heroku login

# Crear app
heroku create mi-catastro-saas

# Añadir PostgreSQL
heroku addons:create heroku-postgresql:hobby-dev

# Configurar variables
heroku config:set SECRET_KEY=xxx
heroku config:set STRIPE_SECRET_KEY=xxx

# Deploy
git push heroku main
```

## 📝 Próximos Pasos

- [ ] Implementar procesamiento real de consultas catastrales
- [ ] Añadir sistema de emails (bienvenida, facturas)
- [ ] Crear frontend completo con React/Vue
- [ ] Implementar worker asíncrono (Celery)
- [ ] Añadir analytics y métricas
- [ ] Sistema de facturación automática
- [ ] Multi-idioma (i18n)

## 🤝 Contribuir

1. Fork el proyecto
2. Crea tu rama (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo licencia MIT.

## 📞 Soporte

Para soporte, contacta a: support@catastrosaaS.com
