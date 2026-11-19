import csv
import json
from datetime import datetime
from pathlib import Path


ACCEL_HEADERS = ["timestamp", "ax_g", "ay_g", "az_g", "magnitude_g"]


def timestamp_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]



def setup_csv_logging(file_path: str):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(ACCEL_HEADERS)



def log_accelerometer_to_csv(file_path: str, ax: float, ay: float, az: float, mag: float):
    path = Path(file_path)
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp_now(),
            f"{ax:.4f}",
            f"{ay:.4f}",
            f"{az:.4f}",
            f"{mag:.4f}",
        ])



def write_session_metadata(file_path: str, metadata: dict):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {**metadata, "saved_at": timestamp_now()}
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
