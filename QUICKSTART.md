# 🚀 Guía de Inicio Rápido - Catastro SaaS

## ⚡ Inicio en 5 Minutos

### 1. Instalar Dependencias

```bash
cd H:\CatastroSaaS
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar Base de Datos

**Opción A: PostgreSQL (Recomendado para producción)**
```bash
# Instalar PostgreSQL desde https://www.postgresql.org/download/
# Crear base de datos
createdb catastro_saas
```

**Opción B: SQLite (Para desarrollo rápido)**
```bash
# Editar config.py y cambiar DATABASE_URL a:
# DATABASE_URL = "sqlite:///./catastro_saas.db"
```

### 3. Configurar Variables de Entorno

```bash
# Copiar template
copy .env.example .env

# Editar .env y configurar:
```

**Mínimo requerido para empezar:**
```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/catastro_saas
SECRET_KEY=tu-clave-secreta-aqui-cambiar-en-produccion
STRIPE_SECRET_KEY=sk_test_tu_clave_de_stripe
STRIPE_PUBLISHABLE_KEY=pk_test_tu_clave_de_stripe
STRIPE_WEBHOOK_SECRET=whsec_tu_webhook_secret
AEMET_API_KEY=tu_api_key_de_aemet
```

**Generar SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Iniciar Aplicación

```bash
python app.py
```

### 5. Acceder

Abre tu navegador en: **http://localhost:8000**

---

## 📝 Primeros Pasos

### Crear Usuario

1. Ve a http://localhost:8000
2. Click en "Registrarse Gratis"
3. Completa el formulario
4. Recibirás plan Free con 3 consultas

### Hacer Primera Consulta

1. Login con tu cuenta
2. En el dashboard, ingresa una referencia catastral
3. Click en "Procesar Consulta"
4. Ver resultados en historial

---

## 🔧 Configuración de Stripe (Opcional)

### Modo Test

1. Crear cuenta en https://dashboard.stripe.com/register
2. Ir a Developers → API keys
3. Copiar "Secret key" y "Publishable key"
4. Pegar en `.env`

### Crear Productos

1. Dashboard → Products → Add product
2. Crear "Professional Plan" - €24.99/mes
3. Crear "Enterprise Plan" - €149.99/mes
4. Copiar Price IDs
5. Actualizar en `services/stripe_service.py`:

```python
price_ids = {
    models.PlanType.PRO: "price_XXXXX",  # Tu Price ID
    models.PlanType.ENTERPRISE: "price_YYYYY"
}
```

---

## 🧪 Probar la API

### Con Swagger UI

http://localhost:8000/docs

### Con cURL

**Registrar usuario:**
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test@example.com\",\"password\":\"password123\",\"full_name\":\"Test User\"}"
```

**Login:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -d "username=test@example.com&password=password123"
```

**Hacer consulta (con token):**
```bash
curl -X POST http://localhost:8000/api/catastro/query \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d "{\"referencia_catastral\":\"30037A008002060000UZ\"}"
```

---

## 🐛 Solución de Problemas

### Error: "No module named 'psycopg2'"
```bash
pip install psycopg2-binary
```

### Error: "Database connection failed"
- Verificar que PostgreSQL esté corriendo
- Verificar DATABASE_URL en .env
- Verificar credenciales de BD

### Error: "Stripe error"
- Verificar que las API keys sean correctas
- Usar keys de test (sk_test_...)
- Verificar que Stripe esté en modo test

### Puerto 8000 en uso
```bash
# Cambiar puerto en app.py:
uvicorn.run(app, host="0.0.0.0", port=8001)
```

---

## 📚 Próximos Pasos

1. ✅ Configurar Stripe en modo producción
2. ✅ Integrar con sistema catastral original
3. ✅ Configurar emails (bienvenida, facturas)
4. ✅ Deploy en Railway/Heroku
5. ✅ Configurar dominio personalizado

---

## 💡 Consejos

- **Desarrollo:** Usa SQLite para empezar rápido
- **Producción:** Usa PostgreSQL siempre
- **Stripe:** Usa modo test hasta estar listo
- **Logs:** Revisa la consola para errores
- **API Docs:** http://localhost:8000/docs es tu amigo

---

## 🆘 Ayuda

- **Documentación:** Ver README.md
- **API Docs:** http://localhost:8000/docs
- **Errores:** Revisar logs en consola
