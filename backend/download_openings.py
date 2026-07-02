from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen


BASE_URL = "https://raw.githubusercontent.com/lichess-org/chess-openings/master"
FILES = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]
OPENINGS_DIR = Path(__file__).resolve().parent / "openings"


def main() -> None:
    OPENINGS_DIR.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        target = OPENINGS_DIR / name
        url = f"{BASE_URL}/{name}"
        print(f"Downloading {url}")
        with urlopen(url, timeout=30) as response:
            target.write_bytes(response.read())
        print(f"Wrote {target}")


if __name__ == "__main__":
    main()
