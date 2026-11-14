"""Generate public OpenAPI from the exact app DTOs. No external connections are made."""
from pathlib import Path

import yaml

from backend.app.main import create_app
from backend.app.config import ROOT, Settings


def main():
    contract = create_app(Settings(worker_enabled=False)).openapi()
    path = ROOT / "contracts" / "openapi.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
