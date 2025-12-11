import { CSSProperties, useEffect, useMemo, useRef, useState } from "react";

export type ModuleShape = {
  id: string;
  name: string;
  column: number;
  row: number;
  width: number;
  height: number;
};

export type ModuleDraft = Omit<ModuleShape, "id" | "name">;

type ModuleGridProps = {
  modules: ModuleShape[];
  placementMode: boolean;
  onModuleCreate: (draft: ModuleDraft) => void;
  onCancelPlacement: () => void;
};

const GRID_SIZE = 40;

const ModuleGrid = ({
  modules,
  placementMode,
  onModuleCreate,
  onCancelPlacement,
}: ModuleGridProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoverCell, setHoverCell] = useState<{ column: number; row: number } | null>(null);
  const [dragStart, setDragStart] = useState<{ column: number; row: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ column: number; row: number } | null>(null);

  useEffect(() => {
    if (!placementMode) {
      setHoverCell(null);
      setDragStart(null);
      setDragCurrent(null);
    }
  }, [placementMode]);

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

  const getCellFromEvent = (event: React.MouseEvent) => {
    const bounds = containerRef.current?.getBoundingClientRect();
    if (!bounds) return null;
    const column = Math.floor((event.clientX - bounds.left) / GRID_SIZE);
    const row = Math.floor((event.clientY - bounds.top) / GRID_SIZE);
    if (column < 0 || row < 0) return null;
    return { column, row };
  };

  const commitSelection = () => {
    if (!dragStart || !dragCurrent) return;
    const minColumn = Math.min(dragStart.column, dragCurrent.column);
    const minRow = Math.min(dragStart.row, dragCurrent.row);
    const width = Math.abs(dragStart.column - dragCurrent.column) + 1;
    const height = Math.abs(dragStart.row - dragCurrent.row) + 1;
    onModuleCreate({
      column: minColumn,
      row: minRow,
      width,
      height,
    });
    setDragStart(null);
    setDragCurrent(null);
    setHoverCell(null);
  };

  const handleMouseMove = (event: React.MouseEvent) => {
    if (!placementMode) return;
    const cell = getCellFromEvent(event);
    setHoverCell(cell);
    if (dragStart && cell) {
      setDragCurrent(cell);
    }
  };

  const handleMouseDown = (event: React.MouseEvent) => {
    if (!placementMode) return;
    event.preventDefault();
    const cell = getCellFromEvent(event);
    if (!cell) return;
    setDragStart(cell);
    setDragCurrent(cell);
  };

  const handleMouseUp = (event: React.MouseEvent) => {
    if (!placementMode) return;
    event.preventDefault();
    if (dragStart && dragCurrent) {
      commitSelection();
    }
  };

  const selectionRect = useMemo(() => {
    if (!dragStart || !dragCurrent) return null;
    const minColumn = Math.min(dragStart.column, dragCurrent.column);
    const minRow = Math.min(dragStart.row, dragCurrent.row);
    const width = Math.abs(dragStart.column - dragCurrent.column) + 1;
    const height = Math.abs(dragStart.row - dragCurrent.row) + 1;
    return {
      column: minColumn,
      row: minRow,
      width,
      height,
    };
  }, [dragStart, dragCurrent]);

  return (
    <div className="module-grid" ref={containerRef}>
      <div
        className={`module-grid__surface ${placementMode ? "is-placing" : ""}`}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
      />

      {modules.map((module) => {
        const style: CSSProperties = {
          left: module.column * GRID_SIZE,
          top: module.row * GRID_SIZE,
          width: module.width * GRID_SIZE,
          height: module.height * GRID_SIZE,
        };
        return (
          <div key={module.id} className="module-shell" style={style}>
            <div className="module-shell__header">
              <span className="module-shell__eyebrow">module</span>
              <strong>{module.name}</strong>
            </div>
            <div className="module-shell__body">
              <span className="module-shell__placeholder">content pending</span>
            </div>
            <button className="module-shell__resize-handle" aria-label="resize module" />
          </div>
        );
      })}

      {placementMode && hoverCell && !dragStart && (
        <div
          className="module-grid__probe"
          style={{
            left: hoverCell.column * GRID_SIZE,
            top: hoverCell.row * GRID_SIZE,
            width: GRID_SIZE,
            height: GRID_SIZE,
          }}
        >
          <span>+</span>
        </div>
      )}

      {placementMode && selectionRect && (
        <div
          className="module-grid__selection"
          style={{
            left: selectionRect.column * GRID_SIZE,
            top: selectionRect.row * GRID_SIZE,
            width: selectionRect.width * GRID_SIZE,
            height: selectionRect.height * GRID_SIZE,
          }}
        >
          <span>
            {selectionRect.width} × {selectionRect.height}
          </span>
        </div>
      )}

      {placementMode && (
        <div className="module-grid__instructions">
          Click and drag across the grid to allocate space. Press Esc to cancel.
        </div>
      )}

      {!modules.length && !placementMode && (
        <div className="module-grid__empty-state">
          No modules yet. Use “New Module” to start assembling a loop.
        </div>
      )}
    </div>
  );
};

export default ModuleGrid;
