import json
import os
import subprocess
import tempfile
from pathlib import Path

import pika
import requests
from minio import Minio


RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "render_jobs")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "renders")

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)


def update_job(job_id: str, status: str, error_message: str | None = None, result_object_key: str | None = None) -> None:
    payload = {"status": status}
    if error_message:
        payload["errorMessage"] = error_message
    if result_object_key:
        payload["resultObjectKey"] = result_object_key

    try:
        requests.patch(
            f"{API_BASE_URL}/api/jobs/{job_id}",
            json=payload,
            timeout=10
        )
    except requests.RequestException as error:
        print(f"No se pudo actualizar el trabajo {job_id}: {error}")


def render_job(job: dict) -> None:
    job_id = job["id"]
    object_key = job.get("filePath") or f"scenes/{job_id}_{job['originalFilename']}"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        scene_path = temp_path / "scene.glb"
        output_path = temp_path / f"{job_id}.png"

        minio_client.fget_object(MINIO_BUCKET, object_key, str(scene_path))
        update_job(job_id, "rendering")

        command = [
            "/usr/local/bin/raytracer",
            "--height", str(job["resolution"]),
            "--scene", str(scene_path),
            "--samples", str(job["samples"]),
            "--output", str(output_path),
        ]
        subprocess.run(command, check=True)

        result_object_key = f"renders/{job_id}.png"
        minio_client.fput_object(
            MINIO_BUCKET,
            result_object_key,
            str(output_path),
            content_type="image/png"
        )
        update_job(job_id, "completed", result_object_key=result_object_key)


def handle_message(channel, method, properties, body) -> None:
    job_id = None
    try:
        job = json.loads(body)
        job_id = job.get("id")
        render_job(job)
    except Exception as error:
        if job_id:
            update_job(job_id, "failed", error_message=str(error))
        print(f"Error procesando trabajo: {error}")
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)


def main() -> None:
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=handle_message)
    channel.start_consuming()


if __name__ == "__main__":
    main()

