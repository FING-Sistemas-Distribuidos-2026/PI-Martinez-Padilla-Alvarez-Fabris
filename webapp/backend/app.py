import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pika
import psycopg
from flask import Flask, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"glb"}
DEFAULT_QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "render_jobs")
DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/raytracer",
)

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_positive_int(value: str | None, field_name: str) -> int:
    if value is None or value == "":
        raise ValueError(f"{field_name} es requerido")

    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} debe ser un número válido") from error

    if parsed_value <= 0:
        raise ValueError(f"{field_name} debe ser mayor que 0")

    return parsed_value


def rabbitmq_parameters() -> pika.URLParameters:
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
    return pika.URLParameters(rabbitmq_url)


def database_url() -> str:
    return DEFAULT_DATABASE_URL


def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(database_url())


def wait_for_database(retries: int = 30, delay_seconds: float = 2.0) -> None:
    last_error: Exception | None = None

    for _ in range(retries):
        try:
            with get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            return
        except Exception as error:
            last_error = error
            time.sleep(delay_seconds)

    raise RuntimeError(f"No se pudo conectar a PostgreSQL: {last_error}")


def init_db() -> None:
    wait_for_database()

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS render_jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    resolution INTEGER NOT NULL,
                    samples INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    file_path TEXT NOT NULL,
                    error_message TEXT
                )
                """
            )
        connection.commit()


def row_to_job(row: tuple) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "originalFilename": row[2],
        "resolution": row[3],
        "samples": row[4],
        "status": row[5],
        "createdAt": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
        "filePath": row[7],
        "errorMessage": row[8],
    }


def insert_job(job: dict) -> None:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO render_jobs (
                    id,
                    name,
                    original_filename,
                    resolution,
                    samples,
                    status,
                    created_at,
                    file_path,
                    error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job["id"],
                    job["name"],
                    job["originalFilename"],
                    job["resolution"],
                    job["samples"],
                    job["status"],
                    job["createdAt"],
                    job["filePath"],
                    job.get("errorMessage"),
                ),
            )
        connection.commit()


def update_job_status(job_id: str, status: str, error_message: str | None = None) -> None:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE render_jobs
                SET status = %s,
                    error_message = %s
                WHERE id = %s
                """,
                (status, error_message, job_id),
            )
        connection.commit()


def fetch_jobs() -> list[dict]:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    original_filename,
                    resolution,
                    samples,
                    status,
                    created_at,
                    file_path,
                    error_message
                FROM render_jobs
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()

    return [row_to_job(row) for row in rows]


def publish_job(job: dict) -> None:
    connection = pika.BlockingConnection(rabbitmq_parameters())
    try:
        channel = connection.channel()
        channel.queue_declare(queue=DEFAULT_QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=DEFAULT_QUEUE_NAME,
            body=json.dumps(job).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
    finally:
        connection.close()


@app.route("/")
def index() -> str:
    return app.send_static_file("index.html")


@app.get("/api/health")
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.get("/api/jobs")
def list_jobs() -> tuple[dict, int]:
    return {"jobs": fetch_jobs()}, 200


@app.post("/api/renders")
def create_render_job() -> tuple[dict, int]:
    scene_file = request.files.get("sceneFile")
    if scene_file is None or scene_file.filename == "":
        return {"error": "Se requiere un archivo .glb"}, 400

    if not is_allowed_file(scene_file.filename):
        return {"error": "Solo se permiten archivos .glb"}, 400

    try:
        resolution = parse_positive_int(request.form.get("resolution"), "resolution")
        samples = parse_positive_int(request.form.get("samples"), "samples")
    except ValueError as error:
        return {"error": str(error)}, 400

    job_id = uuid4().hex
    filename = secure_filename(scene_file.filename)
    saved_filename = f"{job_id}_{filename}"
    file_path = UPLOAD_DIR / saved_filename
    scene_file.save(file_path)

    job = {
        "id": job_id,
        "name": request.form.get("jobName") or Path(filename).stem,
        "originalFilename": filename,
        "resolution": resolution,
        "samples": samples,
        "status": "pending",
        "createdAt": utc_now(),
        "filePath": str(file_path),
        "errorMessage": None,
    }

    try:
        insert_job(job)
    except Exception as error:
        if file_path.exists():
            file_path.unlink()
        return {"error": f"No se pudo persistir el trabajo en PostgreSQL: {error}"}, 500

    try:
        publish_job(job)
        job["status"] = "queued"
        update_job_status(job_id, "queued")
    except Exception as error:
        job["status"] = "failed"
        job["errorMessage"] = f"No se pudo publicar el trabajo en RabbitMQ: {error}"
        update_job_status(job_id, "failed", job["errorMessage"])
        return {"error": job["errorMessage"]}, 502

    return {"message": "Trabajo encolado", "job": job}, 202


@app.route("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)