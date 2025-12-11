import { MouseEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ModuleDraft } from "../types/modules";

type GridCell = { column: number; row: number };

type UseModulePlacementArgs = {
  containerRef: React.RefObject<HTMLDivElement>;
  gridSize: number;
  gridOrigin: { x: number; y: number };
  placementMode: boolean;
  onModuleCreate: (draft: ModuleDraft) => void;
  onCancelPlacement: () => void;
};

export const useModulePlacement = ({
  containerRef,
  gridSize,
  gridOrigin,
  placementMode,
  onModuleCreate,
  onCancelPlacement,
}: UseModulePlacementArgs) => {
  const [hoverCell, setHoverCell] = useState<GridCell | null>(null);
  const [dragStart, setDragStart] = useState<GridCell | null>(null);
  const [dragCurrent, setDragCurrent] = useState<GridCell | null>(null);

  useEffect(() => {
    if (!placementMode) {
      setHoverCell(null);
      setDragStart(null);
      setDragCurrent(null);
    }
  }, [placementMode]);

  const getCellFromEvent = useCallback(
    (event: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return null;
      const bounds = container.getBoundingClientRect();
      const shell = container.closest(".hud-shell") as HTMLElement | null;
      const shellRect = shell?.getBoundingClientRect();
      if (!bounds || !shellRect) return null;

      const globalX = event.clientX - shellRect.left;
      const globalY = event.clientY - shellRect.top;
      const column = Math.floor(globalX / gridSize);
      const row = Math.floor(globalY / gridSize);
      if (column < 0 || row < 0) return null;

      const localX = column * gridSize - gridOrigin.x;
      const localY = row * gridSize - gridOrigin.y;
      if (
        localX + gridSize < 0 ||
        localY + gridSize < 0 ||
        localX > bounds.width ||
        localY > bounds.height
      ) {
        return null;
      }

      return { column, row };
    },
    [containerRef, gridOrigin.x, gridOrigin.y, gridSize],
  );

  const commitSelection = useCallback(() => {
    if (!dragStart || !dragCurrent) return;
    const minColumn = Math.min(dragStart.column, dragCurrent.column);
    const minRow = Math.min(dragStart.row, dragCurrent.row);
    const width = Math.abs(dragStart.column - dragCurrent.column) + 1;
    const height = Math.abs(dragStart.row - dragCurrent.row) + 1;
    onModuleCreate({ column: minColumn, row: minRow, width, height });
    setDragStart(null);
    setDragCurrent(null);
    setHoverCell(null);
  }, [dragCurrent, dragStart, onModuleCreate]);

  useEffect(() => {
    if (!placementMode) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setDragStart(null);
        setDragCurrent(null);
        setHoverCell(null);
        onCancelPlacement();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [placementMode, onCancelPlacement]);

  const handleMouseMove = useCallback(
    (event: MouseEvent) => {
      if (!placementMode) return;
      const cell = getCellFromEvent(event);
      setHoverCell(cell);
      if (dragStart && cell) {
        setDragCurrent(cell);
      }
    },
    [dragStart, getCellFromEvent, placementMode],
  );

  const handleMouseDown = useCallback(
    (event: MouseEvent) => {
      if (!placementMode) return;
      event.preventDefault();
      const cell = getCellFromEvent(event);
      if (!cell) return;
      setDragStart(cell);
      setDragCurrent(cell);
    },
    [getCellFromEvent, placementMode],
  );

  const handleMouseUp = useCallback(
    (event: MouseEvent) => {
      if (!placementMode) return;
      event.preventDefault();
      if (dragStart && dragCurrent) {
        commitSelection();
      }
    },
    [commitSelection, dragCurrent, dragStart, placementMode],
  );

  const selectionRect = useMemo(() => {
    if (!dragStart || !dragCurrent) return null;
    const minColumn = Math.min(dragStart.column, dragCurrent.column);
    const minRow = Math.min(dragStart.row, dragCurrent.row);
    const width = Math.abs(dragStart.column - dragCurrent.column) + 1;
    const height = Math.abs(dragStart.row - dragCurrent.row) + 1;
    return { column: minColumn, row: minRow, width, height };
  }, [dragCurrent, dragStart]);

  return {
    hoverCell,
    selectionRect,
    isDrawing: Boolean(dragStart),
    handleMouseMove,
    handleMouseDown,
    handleMouseUp,
  };
};
