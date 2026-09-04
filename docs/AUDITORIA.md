# Auditoría de Seguridad — ejercicio-docker-audit

**Fecha:** 2026-09-04
**Alcance:** `app.py`, `Dockerfile`, `test_app.py`
**Herramientas:** Bandit 1.9.4 (local), revisión manual, Trivy (CI/CD)

Reporte Bandit completo: [`bandit_auditoria.txt`](bandit_auditoria.txt) / [`bandit_auditoria.json`](bandit_auditoria.json)

## Resumen ejecutivo

La aplicación "legacy" contiene vulnerabilidades críticas que permiten **inyección SQL**,
**fuga de credenciales**, **ejecución remota de código** (debugger de Flask activo en
producción) y **exposición de información interna**. La imagen base `python:3.8` está en
**End of Life** y acumula CVEs críticos. Se recomienda aplicar los cambios descritos en la
sección de remediación antes de cualquier despliegue.

## Tabla de Auditoría

| # | Archivo | Línea | Herramienta / ID | CWE | Severidad | Hallazgo | Recomendación |
|---|---------|-------|------------------|-----|-----------|----------|---------------|
| 1 | `app.py` | 5-11 | Bandit `B105` | CWE-259 | Media | Credenciales de base de datos hardcodeadas en el código fuente (`DB_PASS = "admin_adso_2026_secreto"`). | Mover a variables de entorno / `.env` y usar secretos del orquestador. |
| 2 | `app.py` | 25 | Bandit `B608` | CWE-89 | Media | **SQL Injection**: el parámetro `id` se concatena directamente en el query SQL. | Usar consultas parametrizadas con `%s` y el driver `PyMySQL`. |
| 3 | `app.py` | 30 | Bandit `B311` | CWE-330 | Baja | Uso de `random.random()` en el health check (pseudo-aleatorio, inestable y no apto para seguridad). | Health check determinista sin aleatoriedad. |
| 4 | `app.py` | 35 | Bandit `B201` | CWE-94 | **Alta** | `debug=True` en producción: expone el debugger de Werkzeug y permite **ejecución remota de código**. | Controlar con variable de entorno `FLASK_DEBUG`, `False` por defecto. |
| 5 | `app.py` | 35 | Bandit `B104` | CWE-605 | Media | Binding a todas las interfaces (`0.0.0.0`). | Exponer solo en red interna del contenedor; el proxy reverse publica el servicio. |
| 6 | `app.py` | 16-18 | Manual | CWE-209 | Media | La excepción devuelve `str(e)` al cliente: fuga de detalles internos de la infraestructura. | Loguear el error y devolver mensaje genérico al cliente. |
| 7 | `test_app.py` | 7 | Bandit `B101` | CWE-703 | Baja | `assert` usado en código no test (test dependiente del comportamiento aleatorio). | Usar `pytest.raises`/mocks y eliminar aleatoriedad del endpoint. |
| 8 | `Dockerfile` | 1 | Trivy (CI) | CVE-* | **Crítica** | Imagen base `python:3.8` en **End of Life** con múltiples CVEs críticos en la cadena de dependencias del sistema. | Migrado a `python:3.12-alpine` con build multi-stage (runtime sin pip/setuptools): **0 hallazgos** HIGH/CRITICAL en Trivy. |
| 9 | `Dockerfile` | 1-8 | Manual | CWE-250 | Media | El contenedor corre como **root**; sin `USER` no privilegiado. | Crear usuario no-root (`appuser`) y usar `USER`. |
| 10 | `Dockerfile` | 2-8 | Manual | — | Media | Se copia todo el contexto (`COPY . /app`) sin `.dockerignore`; riesgo de copiar secretos al build. | Añadir `.dockerignore` y copiar solo lo necesario. |
| 11 | `Dockerfile` | — | Manual | — | Baja | Sin `HEALTHCHECK` y dependencias sin pinear/actualizar (Flask 1.1.2, PyMySQL 0.9.3, obsoletas y con CVEs). | `HEALTHCHECK` del contenedor, `requirements.txt` con versiones actualizadas. |

## Resultados Bandit

| Severidad | Cantidad |
|-----------|----------|
| Alta | 1 |
| Media | 2 |
| Baja | 3 |
| **Total** | **6** |

## Plan de remediación

1. Credenciales y configuración → variables de entorno (`.env`, no versionado).
2. SQL → consultas parametrizadas.
3. `debug` y bind → controlados por entorno, expuestos solo en red interna.
4. Imagen base → `python:3.12-slim`, usuario no-root, `HEALTHCHECK`, `.dockerignore`.
5. Orquestación → `docker-compose.yml` con red interna y proxy reverse (`nginx-proxy-manager`).
6. CI/CD → GitHub Actions con `pytest`, `bandit` y `trivy`.