FROM gcc:latest AS renderer-builder

RUN apt-get update && apt-get install -y \
    build-essential cmake curl zip unzip tar

COPY renderer/ /src/renderer

WORKDIR /src/renderer

RUN ./vcpkg/bootstrap-vcpkg.sh
RUN cmake --preset release
RUN cmake --build build/release/

FROM python:3.12-slim

COPY --from=renderer-builder \
    /src/renderer/build/release/raytracer \
    /usr/local/bin/raytracer

COPY worker.py app/worker.py
COPY requirements.txt app/requirements.txt

RUN pip install -r /app/requirements.txt

CMD ["python", "/app/worker.py"]