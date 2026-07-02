import React, { useEffect, useMemo, useRef, useState } from "react";
import { Chessboard } from "react-chessboard";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const START_FEN = "start";

function lineMoves(line) {
  return line?.uci?.split(" ") ?? [];
}

function lineContainsMoves(line, moves) {
  const openingMoves = lineMoves(line);
  return moves.every((move, index) => openingMoves[index] === move);
}

function nextMoveForLine(line, moves) {
  if (!lineContainsMoves(line, moves)) return null;
  return lineMoves(line)[moves.length] ?? null;
}

function arrowForLine(line, moves) {
  const nextMove = nextMoveForLine(line, moves);
  if (!nextMove) return [];
  return [[nextMove.slice(0, 2), nextMove.slice(2, 4), "rgb(28, 108, 216)"]];
}

function continuationLabel(line) {
  if (!line.next_move) return "Named line reached";
  return line.next_san ? `${line.next_san} (${line.next_move})` : line.next_move;
}

export default function App() {
  const [moves, setMoves] = useState([]);
  const [fen, setFen] = useState(START_FEN);
  const [pgn, setPgn] = useState("");
  const [currentOpening, setCurrentOpening] = useState(null);
  const [candidateLines, setCandidateLines] = useState([]);
  const [selectedLine, setSelectedLine] = useState(null);
  const [searchText, setSearchText] = useState("");
  const [taxonomy, setTaxonomy] = useState(null);
  const [message, setMessage] = useState("");
  const [boardSize, setBoardSize] = useState(560);
  const boardWrapRef = useRef(null);

  const customArrows = useMemo(() => arrowForLine(selectedLine, moves), [moves, selectedLine]);
  const exactNextLines = useMemo(
    () => candidateLines.filter((line) => line.next_move && lineMoves(line).length === moves.length + 1),
    [candidateLines, moves.length]
  );
  const visibleLines = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    return exactNextLines.filter((line) => {
      if (!query) return true;
      return line.name.toLowerCase().startsWith(query);
    });
  }, [exactNextLines, searchText]);

  useEffect(() => {
    if (!boardWrapRef.current) return undefined;

    const resize = () => {
      const width = boardWrapRef.current?.clientWidth ?? 560;
      setBoardSize(Math.max(300, Math.min(640, width)));
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(boardWrapRef.current);
    return () => observer.disconnect();
  }, []);

  async function syncPosition(nextMoves, commit = false) {
    const response = await fetch(`${API_URL}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ moves: nextMoves }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail ?? "The backend rejected that move.");
    }

    if (commit) setMoves(nextMoves);
    setFen(data.fen);
    setPgn(data.pgn);
    setCurrentOpening(data.current_opening);
    setCandidateLines(data.candidate_lines);
    setTaxonomy(data.taxonomy);
    setSelectedLine((line) => (lineContainsMoves(line, nextMoves) ? line : null));
    setMessage(data.taxonomy.has_taxonomy ? "" : "Add Lichess TSV files to backend/openings, then reload.");
    return data;
  }

  useEffect(() => {
    syncPosition([], true).catch((error) => setMessage(error.message));
  }, []);

  async function onPieceDrop(sourceSquare, targetSquare, piece) {
    const promotion = piece?.[1]?.toLowerCase() === "p" && /[18]$/.test(targetSquare) ? "q" : "";
    const nextMoves = [...moves, `${sourceSquare}${targetSquare}${promotion}`];

    try {
      await syncPosition(nextMoves, true);
      return true;
    } catch (error) {
      setMessage(error.message);
      return false;
    }
  }

  function undoMove() {
    const nextMoves = moves.slice(0, -1);
    syncPosition(nextMoves, true).catch((error) => setMessage(error.message));
  }

  function resetBoard() {
    syncPosition([], true).catch((error) => setMessage(error.message));
  }

  async function reloadTaxonomy() {
    const response = await fetch(`${API_URL}/taxonomy/reload`, { method: "POST" });
    const data = await response.json();
    setTaxonomy(data);
    await syncPosition(moves, true);
  }

  return (
    <main className="shell">
      <section className="boardPane">
        <div className="openingKicker">
          <span>Current opening</span>
          <strong>{currentOpening ? `${currentOpening.eco} ${currentOpening.name}` : "Unclassified position"}</strong>
        </div>

        <div className="boardWrap" ref={boardWrapRef}>
          <Chessboard
            id="OpeningBoard"
            position={fen}
            onPieceDrop={onPieceDrop}
            customArrows={customArrows}
            boardWidth={boardSize}
          />
        </div>

        <div className="controls">
          <button type="button" onClick={undoMove} disabled={moves.length === 0}>
            Undo
          </button>
          <button type="button" onClick={resetBoard} disabled={moves.length === 0}>
            Reset
          </button>
          <button type="button" onClick={reloadTaxonomy}>
            Reload taxonomy
          </button>
        </div>

        <div className="pgnLine">{pgn || "Start position"}</div>
        {message && <div className="notice">{message}</div>}
      </section>

      <aside className="sidePane">
        <div className="sideHeader">
          <div>
            <h1>Continuations</h1>
            <p>
              {visibleLines.length} shown from {exactNextLines.length} continuations
            </p>
          </div>
          <span className={taxonomy?.has_taxonomy ? "status ready" : "status"}>
            {taxonomy?.has_taxonomy ? "local" : "missing"}
          </span>
        </div>

        <div className="continuationTable">
          <div className="tableSearch">
            <input
              aria-label="Search openings"
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search openings"
              type="search"
              value={searchText}
            />
          </div>

          <div className="tableHead">
            <span>Opening</span>
            <span>Next</span>
          </div>

          {visibleLines.length === 0 ? (
            <div className="emptyState">
              {taxonomy?.has_taxonomy
                ? "No matching continuations found from here."
                : "No local taxonomy loaded yet."}
            </div>
          ) : (
            visibleLines.map((line) => (
              <button
                className={selectedLine?.uci === line.uci ? "row selected" : "row"}
                key={`${line.eco}-${line.name}-${line.uci}`}
                type="button"
                onClick={() => setSelectedLine(line)}
              >
                <span>
                  <b>{line.eco}</b>
                  {line.name}
                </span>
                <small>{continuationLabel(line)}</small>
              </button>
            ))
          )}
        </div>
      </aside>
    </main>
  );
}
