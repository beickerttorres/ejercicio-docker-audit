import os

os.environ.setdefault("DB_HOST", "db-no-disponible")

from app import app


def test_health_check_determinista():
    cliente = app.test_client()
    for _ in range(5):
        respuesta = cliente.get("/health")
        assert respuesta.status_code == 200
        assert respuesta.get_json()["status"] == "ok"


def test_buscar_no_expone_consulta_sql():
    cliente = app.test_client()
    payload = "1' OR '1'='1"
    respuesta = cliente.get(f"/buscar?id={payload}")
    assert respuesta.status_code in (200, 500)
    assert "SELECT * FROM usuarios" not in respuesta.get_data(as_text=True)


def test_buscar_sin_db_responde_error_generico():
    cliente = app.test_client()
    respuesta = cliente.get("/buscar?id=1")
    assert respuesta.status_code == 500
    body = respuesta.get_json()
    assert "error" in body
    assert "Traceback" not in respuesta.get_data(as_text=True)


def test_home_sin_db_no_filtra_detalles_internos():
    cliente = app.test_client()
    respuesta = cliente.get("/")
    assert respuesta.status_code == 503
    assert "pymysql" not in respuesta.get_data(as_text=True)
    assert "Traceback" not in respuesta.get_data(as_text=True)