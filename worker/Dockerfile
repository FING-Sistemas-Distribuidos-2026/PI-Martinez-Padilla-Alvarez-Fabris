# Multi-stage build: Compile C++ renderer and set up Python worker

# Stage 1: Build the C++ renderer
FROM ubuntu:22.04 as builder

WORKDIR /build

# Install dependencies for C++ build
RUN apt-get update && apt-get install -y \
    build-essential git make clang clangd \
    pkg-config cmake ninja-build \
    libasound2-dev libpulse-dev \
    libaudio-dev libfribidi-dev libjack-dev libsndio-dev libx11-dev libxext-dev \
    libxrandr-dev libxcursor-dev libxfixes-dev libxi-dev libxss-dev libxtst-dev \
    libxkbcommon-dev libdrm-dev libgbm-dev libgl1-mesa-dev libgles2-mesa-dev \
    libegl1-mesa-dev libdbus-1-dev libibus-1.0-dev libudev-dev libthai-dev \
    libpipewire-0.3-dev libwayland-dev libdecor-0-dev liburing-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy renderer source
COPY renderer /build/renderer

WORKDIR /build/renderer

# Bootstrap vcpkg
RUN ./vcpkg/bootstrap-vcpkg.sh

# Configure and build with CMake
RUN cmake --preset ninja-vcpkg-multi-config -DCMAKE_BUILD_TYPE=Release \
    && cmake --build --preset ninja-vcpkg-multi-config --config Release

# Stage 2: Runtime image with Python and compiled renderer
FROM ubuntu:22.04

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    libx11-6 libxext6 libxrandr2 libxcursor1 libxfixes3 \
    libxi6 libxss1 libxtst6 libxkbcommon0 libdrm2 libgbm1 \
    libgl1-mesa-glx libgles2-mesa libegl1-mesa \
    libdbus-1-3 libudev1 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and worker code
COPY requirements.txt /app/
COPY worker.py /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy compiled renderer from builder stage
COPY --from=builder /build/renderer/build /app/renderer/

# Create necessary directories
RUN mkdir -p /tmp/scenes /tmp/renders /app/renders

# Set environment variables
ENV RENDERER_PATH=/app/renderer/renderer
ENV SCENES_FOLDER=/tmp/scenes
ENV OUTPUT_FOLDER=/tmp/renders
ENV RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/%2F
ENV RABBITMQ_QUEUE=render_jobs

# Make worker executable
RUN chmod +x /app/worker.py

# Run the worker
CMD ["python3", "/app/worker.py"]