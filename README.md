# Ejercicio Docker — Auditoría, Refactor, CI/CD y Despliegue

> **Repositorio:** `beickerttorres/ejercicio-docker-audit` (fork de `BlackT1221/ejercicio-docker-audit`)
> **Fecha:** 2026-09-04
> **Rama de trabajo:** `feature/auditoria-refactor`

Este documento es la **evidencia de las 5 fases** del ejercicio:

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Fork del repositorio | ✅ |
| 2 | Auditoría de seguridad (Bandit) | ✅ |
| 3 | Arquitectura / Refactor (buenas prácticas) | ✅ |
| 4 | Pipeline CI/CD (pytest, bandit, trivy) | ✅ |
| 5 | Despliegue EC2 (proxy 80/443 + 3 subdominios) | 🔲 |

---

## Fase 1 — Fork del repositorio

**Repositorio original:** https://github.com/BlackT1221/ejercicio-docker-audit
**Fork creado en:** https://github.com/beickerttorres/ejercicio-docker-audit

```bash
git clone https://github.com/beickerttorres/ejercicio-docker-audit.git
git remote add upstream https://github.com/BlackT1221/ejercicio-docker-audit.git
git remote -v
```

Salida (evidencia de remotos `origin` = fork y `upstream` = original):

```
origin	https://github.com/beickerttorres/ejercicio-docker-audit.git (fetch)
origin	https://github.com/beickerttorres/ejercicio-docker-audit.git (push)
upstream	https://github.com/BlackT1221/ejercicio-docker-audit.git (fetch)
upstream	https://github.com/BlackT1221/ejercicio-docker-audit.git (push)
```

---

## Fase 2 — Auditoría de seguridad

### Herramientas

- **Bandit 1.9.4** (análisis estático de seguridad en Python)
- Revisión manual (CWE-209, CWE-250)
- **Trivy** (escaneo de imagen/CI, fase 4)

### Comandos ejecutados

```bash
bandit -r . -f txt -o docs/bandit_auditoria.txt   # resumen
bandit -r . -f json -o docs/bandit_auditoria.json # reporte completo
```

### Resultados del código original (6 hallazgos)

| Severidad | Cantidad |
|-----------|----------|
| Alta | 1 |
| Media | 2 |
| Baja | 3 |
| **Total** | **6** |

### Hallazgos principales

| # | Archivo | Herramienta | Severidad | Hallazgo |
|---|---------|-------------|-----------|----------|
| 1 | `app.py` | Bandit `B105` | Media | Credenciales de BD hardcodeadas |
| 2 | `app.py` | Bandit `B608` | Media | **SQL Injection** por concatenación |
| 3 | `app.py` | Bandit `B201` | **Alta** | `debug=True` → RCE por debugger Werkzeug |
| 4 | `app.py` | Bandit `B104` | Media | Bind a todas las interfaces |
| 5 | `app.py` | Manual (CWE-209) | Media | Fuga de detalles internos en excepciones |
| 6 | `Dockerfile` | Trivy / Manual | **Crítica** | Imagen `python:3.8` EOL, root, sin `.dockerignore` ni `HEALTHCHECK` |

**Tabla de auditoría completa:** [`docs/AUDITORIA.md`](docs/AUDITORIA.md)

---

## Fase 3 — Arquitectura / Refactor (buenas prácticas)

### Cambios aplicados

| Archivo | Antes | Después |
|---------|-------|---------|
| `app.py` | Credenciales hardcodeadas, SQL por concatenación, `debug=True`, health check con `1/0` aleatorio, excepciones filtradas | Variables de entorno, queries parametrizadas (`%s`), `debug` por env, health check determinista, errores genéricos |
| `Dockerfile` | `python:3.8`, root, `COPY . /app`, sin HEALTHCHECK | `python:3.12-alpine` multi-stage (runtime sin pip/setuptools), usuario no-root `appuser`, `.dockerignore`, `HEALTHCHECK`, gunicorn |
| `requirements.txt` | Pines obsoletos (Flask 1.1.2, PyMySQL 0.9.3) | Flask 3.x, PyMySQL 1.x, gunicorn + `requirements-dev.txt` |
| `.env.example` | — | Configuración por variables de entorno (secretos fuera del repo) |
| `docker-compose.yml` | — | 5 servicios en red interna, solo el proxy expone puertos |

### Servicios del `docker-compose.yml`

| Servicio | Imagen | Puerto interno | Expuesto al exterior |
|----------|--------|----------------|----------------------|
| `api` | build local (`3.12-slim`) | 5050 | ❌ (solo proxy) |
| `db` | `mysql:8.4` | 3306 | ❌ |
| `drizzle` | `ghcr.io/drizzle-team/gateway` | 4983 | ❌ (solo proxy) |
| `kuma` | `louislam/uptime-kuma:1` | 3001 | ❌ (solo proxy) |
| `npm` | `jc21/nginx-proxy-manager` | 80/443/81 | ✅ 80, 443 |

### Verificación local (evidencia)

```bash
$ .venv/bin/pytest -v
============================== 4 passed in 0.41s ===============================

$ bandit app.py test_app.py -f json -o docs/bandit_refactor.json
app.py -> 0 hallazgos   (tests: solo asserts B101 LOW)

$ docker build -t ejercicio-docker-audit:test .
Successfully built 7805d7d13252
Successfully tagged ejercicio-docker-audit:test

$ docker compose config --quiet && echo OK
compose OK

$ curl http://127.0.0.1:5070/health
{"status":"ok"}
```

---

## Fase 4 — Pipeline CI/CD (GitHub Actions)

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

| Job | Herramienta | Disparador |
|-----|-------------|------------|
| `test` | Python 3.12 + `pytest -v` | push a `main` / PR |
| `bandit` | `bandit -r . -x .venv,.git,docs -s B101 -f json` | push a `main` / PR |
| `trivy` | imagen oficial `aquasec/trivy:0.74.0` (filesystem + imagen) | push a `main` / PR |
| `deploy` | `appleboy/ssh-action` → EC2 | push a `main` (necesita secrets) |

Notas sobre Trivy (v0.74.0 pineada):
- El pipeline **falla** ante cualquier vulnerabilidad **CRITICAL o HIGH** (sin `--ignore-unfixed` ni `.trivyignore`).
- La imagen base `python:3.12-alpine` con **build multi-stage** (el runtime final no incluye `pip` ni `setuptools`) reduce el scan de imagen de **54 hallazgos HIGH/CRITICAL a 0**.
- Los CVEs del sistema (`perl-base`, `util-linux`, `ncurses`, `libc6`, etc.) en Debian `slim` no tenían parche publicado todavía; Alpine elimina ese conjunto de paquetes.
- Dependencias pineadas en `requirements.txt` para un escaneo determinista.
- Escaneo local:
  ```bash
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy:0.74.0 image --severity CRITICAL,HIGH --exit-code 1 ejercicio-docker-audit:ci
  ```

### Secrets requeridos en GitHub (`Settings → Secrets and variables → Actions`)

| Secret | Descripción |
|--------|-------------|
| `EC2_HOST` | IP pública de la instancia |
| `EC2_USER` | Usuario SSH (Debian 12 = `admin`) |
| `EC2_SSH_KEY` | Llave privada SSH de la instancia |

---

## Fase 5 — Despliegue EC2 + proxy 80/443 + 3 subdominios

### Arquitectura de despliegue

```
                         Internet
                            |
                     EC2 (Debian 12)
                  +-------------------------+
                  |  Nginx Proxy Manager     |   puertos 80/443 (público)
                  |   (panel admin :81)      |
                  +------------+-------------+
                               | red interna "internal"
        +----------------------+---------------------+
        |                      |                     |
   api:5050              drizzle:4983           kuma:3001
   (Flask)               (Drizzle Gateway)      (Uptime Kuma)
        |                      |                     |
   db:3306 (mysql:8.4)                              |
        +-------------------------------------------+
```

- Los 3 servicios corren **en la instancia** vía `docker-compose`, en red interna.
- **Solo** Nginx Proxy Manager publica puertos al exterior (80/443).
- Los subdominios apuntan a la IP de la instancia vía **DuckDNS**.

### Subdominios DuckDNS

| Subdominio | Servicio | Reenviado a |
|------------|----------|-------------|
| `api.<dominio>.duckdns.org` | API Flask | `http://api:5050` |
| `drizzle.<dominio>.duckdns.org` | Drizzle Gateway | `http://drizzle:4983` |
| `kuma.<dominio>.duckdns.org` | Uptime Kuma | `http://kuma:3001` |

### Pasos de despliegue

1. **EC2:** instancia Debian 12, Security Group abriendo **22, 80, 443** (+81 solo a tu IP), Elastic IP.
2. **Docker en la instancia:**
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2
   sudo usermod -aG docker $USER
   ```
3. **Clonar y levantar:**
   ```bash
   sudo mkdir -p /opt/ejercicio-docker-audit
   sudo git clone https://github.com/beickerttorres/ejercicio-docker-audit.git /opt/ejercicio-docker-audit
   cd /opt/ejercicio-docker-audit
   sudo cp .env.example .env   # editar credenciales reales
   docker compose up -d --build
   ```
4. **DuckDNS:** crear los 3 registros A → IP de la instancia y configurar auto-actualización (cron).
5. **Nginx Proxy Manager** (`http://IP:81`, credenciales iniciales `admin@example.com / changeme`):
   - Crear 3 *Proxy Hosts*: `api.*`, `drizzle.*`, `kuma.*` apuntando a los servicios internos.
   - Activar **Let's Encrypt SSL** en cada uno.
6. **Verificar:**
   ```bash
   curl https://api.<dominio>.duckdns.org/health   # {"status":"ok"}
   ```

---

## Cómo ejecutar en local

```bash
cp .env.example .env        # ajustar credenciales
docker compose up -d --build
# NPM: http://localhost:81   API: http://localhost:5050/health
```

Para solo las pruebas:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -v
bandit app.py test_app.py -f json -o docs/bandit_refactor.json
```