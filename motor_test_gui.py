"""Launch the relocated LoRa test tool from its original entry point."""
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    test_dir = Path(__file__).resolve().parent / "lora-test"
    sys.path.insert(0, str(test_dir))
    runpy.run_path(str(test_dir / 'motor_test_gui.py'), run_name="__main__")
