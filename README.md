# Ejercicio Docker — Auditoría, Refactor, CI/CD y Despliegue

> **Repositorio:** `beickerttorres/ejercicio-docker-audit` (fork de `BlackT1221/ejercicio-docker-audit`)
> **Fecha:** 2026-09-04
> **Rama de trabajo:** `feature/auditoria-refactor`

Este documento es la **evidencia del ejercicio**, organizada por fases:

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Auditoría de seguridad (tabla de vulnerabilidades) | ✅ |
| 2 | Refactor / Arquitectura con buenas prácticas | ✅ |
| 3 | Pipeline CI/CD en verde (pytest, bandit, trivy, deploy) | ✅ |
| 4 | Despliegue EC2 + proxy 80/443 + 3 subdominios | ✅ |

---

## Fase 1 — Auditoría de seguridad

**Repositorio original:** https://github.com/BlackT1221/ejercicio-docker-audit
**Fork:** https://github.com/beickerttorres/ejercicio-docker-audit

```bash
git clone https://github.com/beickerttorres/ejercicio-docker-audit.git
git remote add upstream https://github.com/BlackT1221/ejercicio-docker-audit.git
git remote -v
```

### Comandos de auditoría

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

### Tabla de vulnerabilidades encontradas

| # | Archivo | Línea | Herramienta / ID | CWE | Severidad | Hallazgo |
|---|---------|-------|------------------|-----|-----------|----------|
| 1 | `app.py` | 10 | Bandit `B105` | CWE-259 | Media | Credenciales de BD hardcodeadas (`DB_PASS`) |
| 2 | `app.py` | 25 | Bandit `B608` | CWE-89 | Media | **SQL Injection** por concatenación de query |
| 3 | `app.py` | 30 | Bandit `B311` | CWE-330 | Baja | `random.random()` en el health check |
| 4 | `app.py` | 35 | Bandit `B201` | CWE-94 | **Alta** | `debug=True` → RCE por debugger Werkzeug |
| 5 | `app.py` | 35 | Bandit `B104` | CWE-605 | Media | Bind a todas las interfaces (`0.0.0.0`) |
| 6 | `app.py` | 16-18 | Manual | CWE-209 | Media | Fuga de detalles internos en excepciones |
| 7 | `test_app.py` | 7 | Bandit `B101` | CWE-703 | Baja | Test frágil dependiente del comportamiento aleatorio |
| 8 | `Dockerfile` | 1 | Trivy / Manual | CVE-* | **Crítica** | Imagen `python:3.8` EOL (CVEs), corre como root, sin `.dockerignore` ni `HEALTHCHECK` |

**Tabla de auditoría completa:** [`docs/AUDITORIA.md`](docs/AUDITORIA.md)
**Reporte Bandit:** [`docs/bandit_auditoria.txt`](docs/bandit_auditoria.txt)

---

## Fase 2 — Refactor del código con buenas prácticas

### Cambios aplicados

| Archivo | Antes | Después |
|---------|-------|---------|
| `app.py` | Credenciales hardcodeadas, SQL por concatenación, `debug=True`, health check con `1/0` aleatorio, excepciones filtradas | Variables de entorno, queries parametrizadas (`%s`), `debug` por env, health check determinista, errores genéricos |
| `Dockerfile` | `python:3.8`, root, `COPY . /app`, sin HEALTHCHECK | `python:3.12-alpine` multi-stage (runtime sin pip/setuptools), usuario no-root `appuser`, `.dockerignore`, `HEALTHCHECK`, gunicorn |
| `requirements.txt` | Pines obsoletos (Flask 1.1.2, PyMySQL 0.9.3) | Pines actuales (Flask 3.1.3, PyMySQL 1.2.0, gunicorn 22.0.0) + `requirements-dev.txt` |
| `.env.example` | — | Configuración por variables de entorno (secretos fuera del repo) |
| `docker-compose.yml` | — | 5 servicios en red interna, solo el proxy expone puertos |

### Servicios del `docker-compose.yml`

| Servicio | Imagen | Puerto interno | Expuesto al exterior |
|----------|--------|----------------|----------------------|
| `api` | build local (`3.12-alpine` multi-stage) | 5050 | ❌ (solo proxy) |
| `db` | `mysql:8.4` (memoria limitada) | 3306 | ❌ |
| `dozzle` | `amir20/dozzle:latest` | 8080 | ❌ (solo proxy) |
| `kuma` | `louislam/uptime-kuma:1` | 3001 | ❌ (solo proxy) |
| `npm` | `jc21/nginx-proxy-manager` | 80/443/81 | ✅ 80, 443 |

Buenas prácticas aplicadas: red interna con exposición únicamente vía proxy, usuario no-root, `mem_limit` por servicio (instancia de 1GB con swap), MySQL con `--performance-schema=OFF`, credenciales fuera del repo, dependencias pineadas.

### Verificación local (evidencia)

```bash
$ .venv/bin/pytest -v
============================== 4 passed in 0.44s ===============================

$ bandit app.py test_app.py
app.py -> 0 hallazgos   (tests: solo asserts B101, saltados en CI con -s B101)

$ docker build --no-cache -t ejercicio-docker-audit:test .
Successfully built 8d1ccd4eabfa
Successfully tagged ejercicio-docker-audit:test

$ docker compose config --quiet && echo OK
compose OK

$ docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy:0.74.0 image --severity CRITICAL,HIGH --exit-code 1 ejercicio-docker-audit:test
# Resultado: 0 vulnerabilidades CRITICAL/HIGH (antes: 54)
```

---

## Fase 3 — Pipeline CI/CD en verde

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

| Job | Herramienta | Disparador |
|-----|-------------|------------|
| `test` | Python 3.12 + `pytest -v` | push a cualquier rama / PR |
| `bandit` | `bandit -r . -x .venv,.git,docs -s B101 -f json` | push a cualquier rama / PR |
| `trivy` | imagen oficial `aquasec/trivy:0.74.0` (filesystem + imagen) | push a cualquier rama / PR |
| `deploy` | `appleboy/ssh-action` → EC2 (rama actual) | push a cualquier rama con `DEPLOY_ENABLED=true` |

### Resultado del pipeline (verde)

Último run (`prueba 8`, commit `c197c7e`):

| Job | Resultado |
|-----|-----------|
| `test` | ✅ success |
| `bandit` | ✅ success |
| `trivy` | ✅ success |
| `deploy` | ✅ / activado con la variable `DEPLOY_ENABLED=true` |

Notas sobre Trivy (v0.74.0 pineada):
- El pipeline **falla** ante cualquier vulnerabilidad **CRITICAL o HIGH** (sin `--ignore-unfixed` ni `.trivyignore`).
- La imagen `python:3.12-alpine` multi-stage (runtime sin pip/setuptools) reduce el scan de imagen de **54 hallazgos HIGH/CRITICAL a 0**.
- Los CVEs de Debian `slim` (`perl-base`, `util-linux`, `ncurses`, `libc6`, etc.) no tenían parche publicado todavía; Alpine elimina ese conjunto de paquetes.

### Secrets y variables requeridos en GitHub (`Settings → Secrets and variables → Actions`)

| Nombre | Tipo | Descripción |
|--------|------|-------------|
| `EC2_HOST` | Secret | IP pública de la instancia (`3.19.218.247`) |
| `EC2_USER` | Secret | Usuario SSH (Debian = `admin`) |
| `EC2_SSH_KEY` | Secret | Llave privada SSH del deploy |
| `DEPLOY_ENABLED` | Variable | `true` para activar el job `deploy` |

---

## Fase 4 — Despliegue EC2 + proxy 80/443 + 3 subdominios

### Arquitectura de despliegue

```
                         Internet
                            |
                     EC2 (Debian 13)
                  +-------------------------+
                  |  Nginx Proxy Manager     |   puertos 80/443 (público)
                  |   (panel admin :81, túnel)|
                  +------------+-------------+
                               | red interna "internal"
        +----------------------+---------------------+
        |                      |                     |
   api:5050              dozzle:8080           kuma:3001
   (Flask)               (Dozzle logs)         (Uptime Kuma)
        |                                         |
   db:3306 (mysql:8.4)                            |
        +-----------------------------------------+
```

- Los 3 servicios corren **en la instancia** vía `docker-compose`, en red interna.
- **Solo** Nginx Proxy Manager publica puertos al exterior (80/443); el panel admin (81) se accede por túnel SSH.
- Los subdominios apuntan a la IP de la instancia vía **DuckDNS** (con auto-actualización por cron cada 5 min).

### Subdominios DuckDNS (real)

| Subdominio | Servicio | Reenviado a | HTTPS |
|------------|----------|-------------|-------|
| `api-beickert.duckdns.org` | API Flask | `http://api:5050` | ✅ 200 |
| `dozzle-beickert.duckdns.org` | Dozzle (logs) | `http://dozzle:8080` | ✅ 200 (login) |
| `kuma-beickert.duckdns.org` | Uptime Kuma | `http://kuma:3001` | ✅ 302 (setup) |

### Verificación del despliegue

```bash
$ curl -sk https://api-beickert.duckdns.org/health
{"status":"ok"}

$ curl -sk -o /dev/null -w "%{http_code}" https://api-beickert.duckdns.org/
200

$ curl -sk -o /dev/null -w "%{http_code}" https://dozzle-beickert.duckdns.org/
200   # login: admin / Dozzle2026Segura

$ curl -sk -o /dev/null -w "%{http_code}" https://kuma-beickert.duckdns.org/
302   # setup inicial de Uptime Kuma
```

### Pasos de despliegue

1. **EC2:** instancia Debian 13, Security Group abriendo **22, 80, 443** (el 81 solo por túnel SSH).
2. **Docker en la instancia** (repositorio oficial Docker CE + compose plugin).
3. **Clonar y levantar:**
   ```bash
   sudo mkdir -p /opt/ejercicio-docker-audit
   sudo git clone https://github.com/beickerttorres/ejercicio-docker-audit.git /opt/ejercicio-docker-audit
   cd /opt/ejercicio-docker-audit
   sudo cp .env.example .env   # editar credenciales reales
   docker compose up -d --build
   ```
4. **Swap** de 2GB para que el stack corra en una instancia de 1GB de RAM.
5. **DuckDNS:** crear los 3 registros A → IP de la instancia + auto-actualización (cron).
6. **Nginx Proxy Manager:** 3 *Proxy Hosts* (`api.*`, `dozzle.*`, `kuma.*`) con **Let's Encrypt SSL** hacia los servicios internos.

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