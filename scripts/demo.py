"""
Classify one image from the command line (quick manual test).

    python scripts/demo.py path/to/photo.jpg
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waste_classification import ClassificationService  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/demo.py <image-file>")
    service = ClassificationService.from_settings()
    print(json.dumps(service.classify_file(sys.argv[1]).to_dict(), indent=2))
