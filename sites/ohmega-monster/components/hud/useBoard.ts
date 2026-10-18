"use client";

// The board state with per-viewer persistence: the default board on the server render and first paint, then the viewer's saved board
// (localStorage, read after mount so the markup matches). Storage may be blocked or full; everything still works, the choice just
// lasts this visit. Only a change the viewer made is written (`dirty`), so loading never overwrites what was saved.

import { useCallback, useEffect, useRef, useState } from "react";

import { defaultBoard, fromSaved, toSaved, type Board } from "./board";

const KEY = "ohmega.globe.board.v1";

export function useBoard(): { board: Board; update: (f: (b: Board) => Board) => void; reset: () => void } {
  const [board, setBoard] = useState<Board>(defaultBoard);
  const dirty = useRef(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      const saved = raw ? fromSaved(JSON.parse(raw)) : null;
      if (saved && !dirty.current) setBoard(saved);
    } catch { /* blocked or malformed: keep the default board */ }
  }, []);

  useEffect(() => {
    if (!dirty.current) return;
    try { localStorage.setItem(KEY, JSON.stringify(toSaved(board))); } catch { /* storage blocked: the layout lasts this visit */ }
  }, [board]);

  const update = useCallback((f: (b: Board) => Board) => { dirty.current = true; setBoard(f); }, []);
  const reset = useCallback(() => { dirty.current = true; setBoard(defaultBoard()); }, []);
  return { board, update, reset };
}
