import json
import os
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from minio import Minio
from minio.error import S3Error
from flask import Response, stream_with_context
from minio.error import S3Error

import pika
import psycopg
from flask import Flask, request, send_from_directory, redirect
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("webapp")
 
logging.getLogger("pika").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("minio").setLevel(logging.WARNING)

# Config 

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

ALLOWED_EXTENSIONS = {"glb"}
DEFAULT_QUEUE_NAME = os.getenv("RABBITMQ_QUEUE")
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET = os.getenv("MINIO_BUCKET")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

#Req Logging middleware 

@app.before_request
def log_request():
    # No loguear el health check ni los archivos estáticos para no ensuciar
    if request.path == "/api/health" or not request.path.startswith("/api"):
        return
    log.info("→ %s %s  (from %s)", request.method, request.path, request.remote_addr)
 
 
@app.after_request
def log_response(response):
    if request.path == "/api/health" or not request.path.startswith("/api"):
        return response
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    log.log(level, "← %s %s  %s", request.method, request.path, response.status)
    return response

# ----

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_bucket() -> None:
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        log.info("[MinIO] bucket '%s' creado", MINIO_BUCKET)


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
    rabbitmq_url = os.getenv("RABBITMQ_URL")
    return pika.URLParameters(rabbitmq_url)


def database_url() -> str:
    return DEFAULT_DATABASE_URL


def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(database_url())


def wait_for_database(retries: int = 30, delay_seconds: float = 2.0) -> None:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            with get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            log.info("[DB] conectado a PostgreSQL (intento %d)", attempt)
            return
        except Exception as error:
            last_error = error
            log.warning("[DB] intento %d/%d fallido: %s", attempt, retries, error)
            time.sleep(delay_seconds)
 
    raise RuntimeError(f"No se pudo conectar a PostgreSQL: {last_error}")



def init_db() -> None:
    log.info("[DB] esperando PostgreSQL...")
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
                    error_message TEXT,
                    result_object_key TEXT
                )
                """
            )
            cursor.execute(
                """
                ALTER TABLE render_jobs
                ADD COLUMN IF NOT EXISTS result_object_key TEXT
                """
            )
        connection.commit()
    log.info("[DB] tabla render_jobs lista")


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
        "resultObjectKey": row[9],
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
                    error_message,
                    result_object_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    job.get("resultObjectKey"),
                ),
            )
        connection.commit()


def update_job_record(
    job_id: str,
    status: str,
    error_message: str | None = None,
    result_object_key: str | None = None,
) -> None:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE render_jobs
                SET status = %s,
                    error_message = %s,
                    result_object_key = %s
                WHERE id = %s
                """,
                (status, error_message, result_object_key, job_id),
            )
        connection.commit()


def fetch_job(job_id: str) -> dict | None:
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
                    error_message,
                    result_object_key
                FROM render_jobs
                WHERE id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()

    return row_to_job(row) if row else None


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
                    error_message,
                    result_object_key
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
        log.info("[RabbitMQ] job %s publicado en cola '%s'", job["id"], DEFAULT_QUEUE_NAME)
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
    jobs = fetch_jobs()
    log.info("[jobs] listando %d trabajos", len(jobs))
    return {"jobs": jobs}, 200


@app.post("/api/renders")
def create_render_job() -> tuple[dict, int]:
    scene_file = request.files.get("sceneFile")
    if scene_file is None or scene_file.filename == "":
        log.warning("[renders] solicitud rechazada: falta archivo .glb")
        return {"error": "Se requiere un archivo .glb"}, 400

    if not is_allowed_file(scene_file.filename):
        log.warning("[renders] solicitud rechazada: archivo .glb no permitido")
        return {"error": "Solo se permiten archivos .glb"}, 400

    try:
        resolution = parse_positive_int(request.form.get("resolution"), "resolution")
        samples = parse_positive_int(request.form.get("samples"), "samples")
    except ValueError as error:
        log.warning("[renders] solicitud rechazada: %s", error)
        return {"error": str(error)}, 400

    job_id = uuid4().hex
    filename = secure_filename(scene_file.filename)
    saved_filename = f"{job_id}_{filename}"
    object_key = f"scenes/{saved_filename}"

    try:
        ensure_bucket()
        scene_file.stream.seek(0)

        minio_client.put_object(
            MINIO_BUCKET,
            object_key,
            scene_file.stream,
            length=scene_file.content_length or -1,
            part_size=10 * 1024 * 1024,
            content_type=scene_file.content_type
        )
        log.info("[MinIO] archivo subido: %s", object_key)

    except S3Error as error:
        log.error("[MinIO] error al subir archivo: %s", error)
        return {"error": f"Error al subir archivo a MinIO: {error}"}, 500

    job = {
        "id": job_id,
        "name": request.form.get("jobName") or Path(filename).stem,
        "originalFilename": filename,
        "resolution": resolution,
        "samples": samples,
        "status": "pending",
        "createdAt": utc_now(),
        "filePath": object_key,
        "errorMessage": None,
        "resultObjectKey": None,
    }

    try:
        insert_job(job)
        log.info("[DB] job %s insertado con status 'pending'", job_id)
    except Exception as error:
        log.error("[DB] error al persistir trabajo: %s", error)
        return {"error": f"No se pudo persistir el trabajo en PostgreSQL: {error}"}, 500

    try:
        publish_job(job)
        job["status"] = "queued"
        update_job_record(job_id, "queued")
        log.info("[renders] job %s encolado exitosamente", job_id)
    except Exception as error:
        job["status"] = "failed"
        job["errorMessage"] = f"No se pudo publicar el trabajo en RabbitMQ: {error}"
        update_job_record(job_id, "failed", job["errorMessage"])
        log.error("[RabbitMQ] error al publicar job %s: %s", job_id, error)
        return {"error": job["errorMessage"]}, 502

    return {"message": "Trabajo encolado", "job": job}, 202


@app.patch("/api/jobs/<job_id>")
def update_job(job_id: str) -> tuple[dict, int]:
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if not status:
        log.warning("[jobs] PATCH %s sin campo 'status'", job_id)
        return {"error": "status es requerido"}, 400
    
    error_message = payload.get("errorMessage")
    result_object_key = payload.get("resultObjectKey")

    update_job_record(job_id, status, error_message, result_object_key)
    job = fetch_job(job_id)
    if not job:
        log.warning("[jobs] job %s no encontrado al actualizar", job_id)
        return {"error": "Trabajo no encontrado"}, 404
    
    if error_message:
        log.error("[jobs] job %s → %s | error: %s", job_id, status, error_message)
    else:
        log.info("[jobs] job %s → %s", job_id, status)

    return {"job": job}, 200


from flask import Response, stream_with_context
from minio.error import S3Error


@app.get("/api/jobs/<job_id>/download")
def download_job(job_id: str):
    job = fetch_job(job_id)
    if not job:
        log.warning("[download] job %s no encontrado", job_id)
        return {"error": "Trabajo no encontrado"}, 404

    result_object_key = job.get("resultObjectKey")
    if not result_object_key:
        log.warning("[download] job %s todavía no tiene resultado", job_id)
        return {"error": "El trabajo todavía no está listo"}, 409

    try:
        stat = minio_client.stat_object(MINIO_BUCKET, result_object_key)
        response = minio_client.get_object(MINIO_BUCKET, result_object_key)
        log.info("[download] iniciando descarga de job %s (%s bytes)", job_id, stat.size)

        def generate():
            try:
                for chunk in response.stream(32 * 1024):
                    yield chunk
            finally:
                response.close()
                response.release_conn()

        return Response(
            stream_with_context(generate()),
            status=200,
            content_type=stat.content_type or "application/octet-stream",
            headers={
                "Content-Length": str(stat.size),
                "Content-Disposition": f'inline; filename="{result_object_key.split("/")[-1]}"',
            },
        )

    except S3Error as error:
        log.error("[download] error al descargar job %s desde MinIO: %s", job_id, error)
        return {"error": f"Error al descargar desde MinIO: {error}"}, 500


@app.route("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT"))
    log.info("Iniciando webapp en puerto %d", port)
    app.run(host="0.0.0.0", port=port, debug=True)