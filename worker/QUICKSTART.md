# Quick Start Guide - Ray Tracer Worker

## What Has Been Created

A complete RabbitMQ-based worker system that:
1. **Listens to RabbitMQ** for render job requests
2. **Accepts GLB scene files** (base64 encoded or file paths)
3. **Executes the C++ renderer** with the provided scene
4. **Returns rendered images** to a response queue
5. **Handles errors gracefully** with automatic retries

## Files Created/Modified

```
worker/
├── worker.py              ← Main worker service (listens to RabbitMQ)
├── client.py              ← Client to send render jobs
├── example.py             ← Usage examples
├── requirements.txt       ← Python dependencies (pika)
├── Dockerfile             ← Multi-stage Docker build
├── WORKER_README.md       ← Detailed documentation
└── QUICKSTART.md          ← This file

docker-compose.yml        ← Updated with worker service
```

## Quick Start (Docker)

### 1. Start All Services

```bash
cd /path/to/project
docker-compose up --build
```

This will:
- Build and start PostgreSQL database
- Build and start RabbitMQ message broker
- Build and start the web application
- Build and start the ray tracer worker

Wait for all services to be healthy (you'll see health check messages).

### 2. Send a Render Job

**Using the client script:**

```bash
# From the worker directory
python3 client.py assets/Test.glb --samples 30 --height 520
```

**Or wait for the result:**

```bash
python3 client.py assets/Test.glb --samples 50 --height 720 --wait
```

**Or use the command-line tool directly:**

```bash
docker-compose exec worker python3 client.py assets/Test.glb --wait
```

### 3. Monitor Worker Activity

```bash
# View worker logs
docker-compose logs -f worker

# View all logs
docker-compose logs -f
```

## Worker Architecture

```
┌─────────────────────┐
│   RabbitMQ Broker   │
│  (render_jobs)      │
└──────────┬──────────┘
           │ (receives job)
           ↓
┌─────────────────────┐
│  Python Worker      │
│  1. Receive message │
│  2. Save GLB scene  │
│  3. Run C++ renderer
│  4. Save PNG output │
│  5. Send response   │
└─────────────────────┘
           │ (sends result)
           ↓
┌─────────────────────┐
│   Response Queue    │
│ (render_results)    │
└─────────────────────┘
```

## Message Format (Minimal Example)

```json
{
  "job_id": "job_001",
  "scene_name": "test_scene",
  "scene_data": "assets/Test.glb",
  "params": {
    "samples": 30,
    "height": 520
  }
}
```

**Using curl (if you want to test manually):**

```bash
# You'll need a script to format this as RabbitMQ expects
# Use the Python client instead - it handles this
```

## Development Setup (Local)

If you want to test without Docker:

```bash
# 1. Install Python dependencies
pip install -r worker/requirements.txt

# 2. Build the C++ renderer (see renderer/README.md)
cd worker/renderer
./vcpkg/bootstrap-vcpkg.sh
cmake --preset ninja-vcpkg-multi-config -DCMAKE_BUILD_TYPE=Release
cmake --build --preset ninja-vcpkg-multi-config --config Release
cd ../..

# 3. Start RabbitMQ (if not already running)
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3-management-alpine

# 4. Set environment variables
export RENDERER_PATH=$(pwd)/worker/renderer/build/renderer
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
export SCENES_FOLDER=/tmp/scenes
export OUTPUT_FOLDER=/tmp/renders

# 5. Start the worker
python3 worker/worker.py

# 6. In another terminal, send jobs
python3 worker/client.py worker/renderer/assets/Test.glb --wait
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `RABBITMQ_URL` | Connection string for RabbitMQ |
| `RABBITMQ_QUEUE` | Queue name for render jobs |
| `RENDERER_PATH` | Path to compiled C++ renderer binary |
| `SCENES_FOLDER` | Where to store downloaded GLB files |
| `OUTPUT_FOLDER` | Where to save rendered PNG images |

## Troubleshooting

### Worker won't start
```bash
# Check logs
docker-compose logs worker

# Verify RabbitMQ is healthy
docker-compose ps
docker-compose logs rabbitmq
```

### Renderer not found
```bash
# Check if Docker build succeeded
docker-compose build --no-cache worker

# Verify renderer binary exists
docker-compose exec worker ls -la /app/renderer/
```

### Jobs not being processed
```bash
# Check worker logs
docker-compose logs -f worker

# Verify job in queue (RabbitMQ management)
# Visit http://localhost:15672
# Username/Password: guest/guest
# Check Queues tab
```

### Slow rendering
- Reduce `--samples` parameter for faster previews
- Reduce `--height` for smaller images
- Check system resources: `docker stats`

## Common Commands

```bash
# Send quick test render
python3 worker/client.py worker/renderer/assets/Test.glb

# High-quality render (takes longer)
python3 worker/client.py worker/renderer/assets/Test.glb --samples 100 --height 1080 --timeout 900

# Send and wait for result
python3 worker/client.py worker/renderer/assets/Test.glb --wait

# View RabbitMQ management UI
# Open http://localhost:15672 (guest/guest)

# Stop all services
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

## Performance Tips

1. **For Quick Tests**: Use `--samples 10 --height 256`
2. **For Production**: Use `--samples 100+ --height 1080+`
3. **Multiple Workers**: Run multiple worker containers for parallel rendering
4. **Scene Optimization**: Optimize GLB files for faster loading

## Next Steps

1. Integrate with your web application to send render jobs
2. Store render results in the database
3. Set up a results retrieval endpoint
4. Add user authentication for job submission
5. Implement job status tracking
6. Add queue monitoring and metrics

## Documentation Files

- **WORKER_README.md** - Detailed documentation and API reference
- **example.py** - Code examples for different use cases
- **client.py** - Standalone client tool and library

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f worker`
2. Review WORKER_README.md for detailed documentation
3. Check RabbitMQ management UI: http://localhost:15672
4. Verify all services are healthy: `docker-compose ps`
