from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Any

import chess
import chess.pgn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
OPENINGS_DIR = BASE_DIR / "openings"
CACHE_DIR = BASE_DIR / "data"
PREFIX_CACHE_PATH = CACHE_DIR / "prefix_cache.json"
EXACT_CACHE_PATH = CACHE_DIR / "exact_cache.json"
PREFIX_CACHE_VERSION = "next-v1"
CACHE_WRITES_ENABLED = os.getenv("OPENINGS_WRITE_CACHE", "0" if os.getenv("VERCEL") else "1").lower() not in {
    "0",
    "false",
    "no",
}
DEFAULT_FRONTEND_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", DEFAULT_FRONTEND_ORIGINS).split(",")
    if origin.strip()
]


app = FastAPI(title="Chess Openings Explorer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PositionRequest(BaseModel):
    moves: list[str]


class OpeningTaxonomy:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.prefix_cache: dict[str, list[dict[str, Any]]] = {}
        self.exact_cache: dict[str, list[dict[str, Any]]] = {}
        self.loaded_files: list[str] = []
        self.reload()

    def reload(self) -> None:
        OPENINGS_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.entries = self._load_entries()
        self.prefix_cache = self._read_json(PREFIX_CACHE_PATH)
        self.exact_cache = self._read_json(EXACT_CACHE_PATH)
        if not self.exact_cache and self.entries:
            self.exact_cache = self._build_exact_cache()
            self._write_json(EXACT_CACHE_PATH, self.exact_cache)

    def status(self) -> dict[str, Any]:
        return {
            "openings_dir": str(OPENINGS_DIR),
            "loaded_files": self.loaded_files,
            "opening_count": len(self.entries),
            "prefix_cache_count": len(self.prefix_cache),
            "exact_cache_count": len(self.exact_cache),
            "has_taxonomy": bool(self.entries),
        }

    def current_openings(self, board: chess.Board) -> list[dict[str, Any]]:
        if not self.entries:
            return []
        return self.exact_cache.get(board.epd(), [])

    def continuations(self, moves: list[str]) -> list[dict[str, Any]]:
        if not self.entries:
            return []

        key = self._prefix_key(moves)
        cached = self.prefix_cache.get(key)
        if cached is not None:
            return cached

        depth = len(moves)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str | None, str]] = set()

        for entry in self.entries:
            line = entry["uci_moves"]
            if line[:depth] != moves:
                continue
            if len(line) != depth + 1:
                continue

            next_move = line[depth]
            marker = (entry["name"], next_move, entry["uci"])
            if marker in seen:
                continue
            seen.add(marker)

            candidates.append(
                {
                    "eco": entry["eco"],
                    "name": entry["name"],
                    "pgn": entry["pgn"],
                    "uci": entry["uci"],
                    "next_move": next_move,
                    "next_san": self._next_san(moves, next_move),
                }
            )

        candidates.sort(key=lambda row: (row["next_move"] is None, row["name"], row["uci"]))
        self.prefix_cache[key] = candidates
        self._write_json(PREFIX_CACHE_PATH, self.prefix_cache)
        return candidates

    def _load_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        self.loaded_files = []

        for path in sorted(OPENINGS_DIR.glob("*.tsv")):
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                for row in reader:
                    pgn = row.get("pgn", "").strip()
                    derived = self._derive_line(pgn)
                    uci = row.get("uci", "").strip() or derived["uci"]
                    epd = row.get("epd", "").strip() or derived["epd"]
                    if not uci or not epd:
                        continue

                    entries.append(
                        {
                            "eco": row.get("eco", "").strip(),
                            "name": row.get("name", "").strip(),
                            "pgn": pgn,
                            "uci": uci,
                            "epd": epd,
                            "uci_moves": uci.split(),
                        }
                    )
            self.loaded_files.append(path.name)

        return entries

    def _derive_line(self, pgn: str) -> dict[str, str]:
        if not pgn:
            return {"uci": "", "epd": ""}

        game = chess.pgn.read_game(io.StringIO(pgn))
        if game is None:
            return {"uci": "", "epd": ""}

        board = chess.Board()
        uci_moves: list[str] = []
        for move in game.mainline_moves():
            uci_moves.append(move.uci())
            board.push(move)

        return {"uci": " ".join(uci_moves), "epd": board.epd()}

    def _build_exact_cache(self) -> dict[str, list[dict[str, Any]]]:
        exact: dict[str, list[dict[str, Any]]] = {}
        for entry in self.entries:
            if not entry["epd"]:
                continue
            exact.setdefault(entry["epd"], []).append(
                {
                    "eco": entry["eco"],
                    "name": entry["name"],
                    "pgn": entry["pgn"],
                    "uci": entry["uci"],
                }
            )
        return exact

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        if not CACHE_WRITES_ENABLED:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def _prefix_key(self, moves: list[str]) -> str:
        return f"{PREFIX_CACHE_VERSION}|{' '.join(moves)}"

    def _next_san(self, moves: list[str], next_move: str | None) -> str | None:
        if next_move is None:
            return None
        try:
            board = make_board(moves)
            return board.san(chess.Move.from_uci(next_move))
        except ValueError:
            return next_move


taxonomy = OpeningTaxonomy()


def make_board(moves: list[str]) -> chess.Board:
    board = chess.Board()
    for uci in moves:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid UCI move: {uci}") from exc
        if move not in board.legal_moves:
            raise HTTPException(status_code=400, detail=f"Illegal move: {uci}")
        board.push(move)
    return board


def make_pgn(moves: list[str]) -> str:
    game = chess.pgn.Game()
    board = chess.Board()
    node = game

    for uci in moves:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
        board.push(move)

    exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
    return re.sub(r"\s+", " ", game.accept(exporter)).strip()


@app.get("/taxonomy/status")
def taxonomy_status() -> dict[str, Any]:
    return taxonomy.status()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Chess Openings API",
        "status": "ok",
        "docs": "/docs",
        "taxonomy_status": "/taxonomy/status",
    }


@app.post("/taxonomy/reload")
def reload_taxonomy() -> dict[str, Any]:
    taxonomy.reload()
    return taxonomy.status()


@app.post("/position")
def position(req: PositionRequest) -> dict[str, Any]:
    board = make_board(req.moves)
    exact_openings = taxonomy.current_openings(board)

    return {
        "fen": board.fen(),
        "pgn": make_pgn(req.moves),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "legal_moves": [move.uci() for move in board.legal_moves],
        "current_opening": exact_openings[0] if exact_openings else None,
        "exact_openings": exact_openings,
        "candidate_lines": taxonomy.continuations(req.moves),
        "taxonomy": taxonomy.status(),
    }
