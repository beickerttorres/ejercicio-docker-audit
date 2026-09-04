import logging
import os

import pymysql
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "db"),
        "user": os.getenv("DB_USER", "app"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "appdb"),
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "3")),
        "cursorclass": pymysql.cursors.DictCursor,
    }


def get_connection():
    return pymysql.connect(**get_db_config())


@app.get("/")
def home():
    try:
        connection = get_connection()
        connection.close()
        return "<h1>API TechNova - Funcionando</h1>", 200
    except Exception as exc:
        logger.error("Error conectando a la base de datos: %s", exc)
        return "<h1>Sistema no disponible</h1>", 503


@app.get("/buscar")
def buscar_usuario():
    usuario_id = request.args.get("id", "1")
    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
            resultado = cursor.fetchall()
        connection.close()
        return jsonify({"resultados": resultado}), 200
    except Exception as exc:
        logger.error("Error consultando usuarios: %s", exc)
        return jsonify({"error": "No se pudo completar la consulta"}), 500


@app.get("/health")
def health_check():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),  # nosec B104
        port=int(os.getenv("PORT", "5050")),
        debug=debug,
    )