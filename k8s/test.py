import requests
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "http://10.66.1.11:8000/api/renders"

FILE_PATH = Path(
    "/home/adriano/repos/PI-Martinez-Padilla-Alvarez-Fabris/dev/worker/renderer/assets/Box.glb"
)

def send_request():
    with FILE_PATH.open("rb") as f:
        files = {"sceneFile": ("Box.glb", f, "model/gltf-binary")}
        data = {
            "resolution": "1080",
            "samples": "100"
        }
        return requests.post(URL, files=files, data=data)

def test():
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(send_request) for _ in range(10)]
        return [f.result().status_code for f in futures]

if __name__ == "__main__":
    print(test())