# Ray Tracer RabbitMQ Worker

This is a Python worker that listens to RabbitMQ for rendering jobs and executes the C++ ray tracer renderer.

## Features

- **RabbitMQ Integration**: Listens to a queue for rendering jobs
- **GLB Scene Support**: Accepts GLB scene files (base64 encoded or file paths)
- **Configurable Rendering**: Supports custom samples, height, and timeout parameters
- **Response Handling**: Sends back rendered images to a reply queue
- **Error Handling**: Graceful error handling with automatic retry on failure
- **Logging**: Comprehensive logging for debugging and monitoring

## Message Format

### Render Job Request

Send a JSON message to the `render_jobs` queue:

```json
{
  "job_id": "unique_job_123",
  "scene_name": "my_scene",
  "scene_data": "base64_encoded_glb_or_file_path",
  "params": {
    "samples": 30,
    "height": 520,
    "timeout": 300
  }
}
```

**Fields:**
- `job_id` (string): Unique identifier for the job
- `scene_name` (string): Name of the scene
- `scene_data` (string): Either:
  - Base64 encoded GLB file content
  - Path to existing GLB file (e.g., `/path/to/scene.glb`)
- `params` (object, optional):
  - `samples` (int): Number of samples per pixel (default: 30)
  - `height` (int): Output image height in pixels (default: 520)
  - `timeout` (int): Maximum render time in seconds (default: 300)

### Success Response

If `reply_to` is set in message properties, the worker sends back:

```json
{
  "job_id": "unique_job_123",
  "status": "success",
  "output_path": "/app/renders/unique_job_123_my_scene_20240601_120000.png",
  "output_data": "base64_encoded_png",
  "timestamp": "2024-06-01T12:00:00.123456"
}
```

### Error Response

```json
{
  "status": "error",
  "error": "Error description",
  "timestamp": "2024-06-01T12:00:00.123456"
}
```

## Installation & Setup

### Using Docker Compose (Recommended)

```bash
# Build and start all services (including worker)
docker-compose up --build

# View worker logs
docker-compose logs -f worker
```

### Manual Installation (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Build the C++ renderer first (see renderer/README.md)
cd renderer
./vcpkg/bootstrap-vcpkg.sh
cmake --preset ninja-vcpkg-multi-config -DCMAKE_BUILD_TYPE=Release
cmake --build --preset ninja-vcpkg-multi-config --config Release
cd ..

# Set environment variables
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
export RABBITMQ_QUEUE=render_jobs
export RENDERER_PATH=./renderer/build/renderer
export SCENES_FOLDER=/tmp/scenes
export OUTPUT_FOLDER=/tmp/renders

# Run the worker
python3 worker.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/%2F` | RabbitMQ connection URL |
| `RABBITMQ_QUEUE` | `render_jobs` | Queue name for render jobs |
| `RENDERER_PATH` | `/app/renderer/renderer` | Path to compiled renderer binary |
| `SCENES_FOLDER` | `/tmp/scenes` | Directory to store downloaded scenes |
| `OUTPUT_FOLDER` | `/tmp/renders` | Directory to store rendered images |
| `TEMP_FOLDER` | `/tmp` | Temporary directory |

## Example Usage

### Python Client

```python
import pika
import json
import base64

def send_render_job(glb_file_path, output_queue=None):
    """Send a render job to the worker"""
    
    # Read GLB file
    with open(glb_file_path, 'rb') as f:
        glb_data = base64.b64encode(f.read()).decode('utf-8')
    
    # Connect to RabbitMQ
    connection = pika.BlockingConnection(
        pika.URLParameters('amqp://guest:guest@localhost:5672/%2F')
    )
    channel = connection.channel()
    
    # Prepare message
    job = {
        "job_id": "my_job_001",
        "scene_name": "my_scene",
        "scene_data": glb_data,
        "params": {
            "samples": 50,
            "height": 1080,
            "timeout": 600
        }
    }
    
    # Send job
    channel.basic_publish(
        exchange='',
        routing_key='render_jobs',
        body=json.dumps(job),
        properties=pika.BasicProperties(
            reply_to=output_queue if output_queue else '',
            correlation_id=job['job_id']
        )
    )
    
    connection.close()
    print("Job sent!")

# Usage
send_render_job('path/to/scene.glb', output_queue='render_results')
```

### Using File Paths

```python
job = {
    "job_id": "my_job_002",
    "scene_name": "sponza",
    "scene_data": "assets/sponza/scene.glb",
    "params": {
        "samples": 100,
        "height": 2160
    }
}
```

## Architecture

### Render Pipeline

```
RabbitMQ Queue (render_jobs)
         ↓
Worker receives message
         ↓
Save/Download GLB scene
         ↓
Execute C++ Renderer
         ↓
Generate PNG output
         ↓
Send response to reply queue
         ↓
Output stored in /app/renders/
```

## Troubleshooting

### Worker won't connect to RabbitMQ

- Ensure RabbitMQ is running: `docker-compose ps`
- Check connection string format
- Verify firewall rules (port 5672)

### Renderer not found

- Ensure C++ renderer is compiled: `ls -la renderer/build/renderer`
- Check `RENDERER_PATH` environment variable
- Look at Docker build logs: `docker-compose build --no-cache worker`

### Out of memory errors

- Reduce `height` or `samples` parameters
- Increase container memory limit in docker-compose.yml

### Slow rendering

- Increase timeout in `params.timeout`
- Reduce `samples` for faster preview renders
- Optimize scene complexity

## Performance Notes

- **Samples**: Higher samples = better quality but slower. Default 30 is good for testing.
- **Height**: Higher height = larger image but slower. 520p is default, 1080p+ for high quality.
- **Timeout**: Rendering complex scenes can take time. Increase if needed.
- **Concurrency**: Run multiple worker instances for parallel rendering

## Development

### Running tests

```bash
# Test renderer directly
./renderer/build/renderer --scene assets/Test.glb --output test.png --headless

# Test worker locally
RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F python3 worker.py
```

### Debugging

Enable verbose logging by modifying the logging level in worker.py:

```python
logging.basicConfig(level=logging.DEBUG)
```

## License

See main project LICENSE
