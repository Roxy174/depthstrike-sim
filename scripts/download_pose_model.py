"""Explicit download from the official versioned Google model endpoint."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def download_model(destination: Path, *, opener=urlopen) -> dict:
    destination = Path(destination)
    sidecar = destination.with_suffix(".task.json")
    for output in (destination, sidecar):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite {output}; verify or rename it first")
    with opener(MODEL_URL, timeout=60) as response:
        data = response.read(50*1024*1024+1)
    if not data or len(data) > 50*1024*1024:
        raise ValueError("Empty or oversized model response")
    metadata = {"url": MODEL_URL, "model": "Pose Landmarker Lite", "version": 1,
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Recheck atomically through exclusive creation, including a sidecar that
    # might appear during download. Never truncate either user's existing file.
    with sidecar.open("x", encoding="utf-8") as metadata_stream:
        with destination.open("xb") as stream:
            stream.write(data)
        metadata_stream.write(json.dumps(metadata, indent=2)+"\n")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/pose_landmarker_lite.task"))
    args = parser.parse_args()
    try:
        print(json.dumps(download_model(args.output), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Model download failed: {exc}\n")


if __name__ == "__main__":
    main()
