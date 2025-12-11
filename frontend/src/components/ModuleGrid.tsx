import {
  CSSProperties,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
  onModuleDelete: (id: string) => void;
};

const ModuleGrid = ({
  modules,
  placementMode,
  onModuleCreate,
  onCancelPlacement,
  onModuleDelete,
}: ModuleGridProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoverCell, setHoverCell] = useState<{ column: number; row: number } | null>(null);
  const [dragStart, setDragStart] = useState<{ column: number; row: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ column: number; row: number } | null>(null);
  const [gridSize, setGridSize] = useState(40);
  const [gridOrigin, setGridOrigin] = useState({ x: 0, y: 0 });
  const [contextTarget, setContextTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!placementMode) {
      setHoverCell(null);
      setDragStart(null);
      setDragCurrent(null);
    }
  }, [placementMode]);

  useEffect(() => {
    const updateGridMetrics = () => {
      const node = containerRef.current;
      if (!node) {
        return;
      }
      const computed = getComputedStyle(node);
      const sizeValue = computed.getPropertyValue("--s-grid");
      const parsed = parseFloat(sizeValue || "");
      if (!Number.isNaN(parsed) && parsed > 0) {
        setGridSize(parsed);
      }
      const shell = node.closest(".hud-shell") as HTMLElement | null;
      const referenceRect = shell?.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      if (referenceRect) {
        setGridOrigin({
          x: nodeRect.left - referenceRect.left,
          y: nodeRect.top - referenceRect.top,
        });
      }
    };
    updateGridMetrics();
    window.addEventListener("resize", updateGridMetrics);
    return () => window.removeEventListener("resize", updateGridMetrics);
  }, []);

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
    const shell = containerRef.current?.closest(".hud-shell") as HTMLElement | null;
    const shellRect = shell?.getBoundingClientRect();
    if (!bounds || !shellRect) return null;
    const globalX = event.clientX - shellRect.left;
    const globalY = event.clientY - shellRect.top;
    const column = Math.floor(globalX / gridSize);
    const row = Math.floor(globalY / gridSize);
    if (column < 0 || row < 0) return null;
    // Ensure inside canvas bounds
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

  const alignmentX = ((gridOrigin.x % gridSize) + gridSize) % gridSize;
  const alignmentY = ((gridOrigin.y % gridSize) + gridSize) % gridSize;

  useEffect(() => {
    if (!contextTarget) return;
    const timer = window.setTimeout(() => {
      const confirmed = window.confirm("Delete this module?");
      if (confirmed) {
        onModuleDelete(contextTarget);
      }
      setContextTarget(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [contextTarget, onModuleDelete]);

  return (
    <div
      className="module-grid"
      ref={containerRef}
      style={
        {
          "--module-grid-size": `${gridSize}px`,
          "--module-grid-origin-x": `${alignmentX}px`,
          "--module-grid-origin-y": `${alignmentY}px`,
        } as CSSProperties
      }
    >
      <div
        className={`module-grid__surface ${placementMode ? "is-placing" : ""}`}
        style={{
          backgroundSize: `${gridSize}px ${gridSize}px`,
          backgroundPosition: `-${alignmentX}px -${alignmentY}px`,
        }}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
      />

      {modules.map((module) => {
        const style: CSSProperties = {
          left: module.column * gridSize - gridOrigin.x,
          top: module.row * gridSize - gridOrigin.y,
          width: module.width * gridSize,
          height: module.height * gridSize,
        };
        return (
          <div key={module.id} className="module-shell" style={style}>
            <div
              className="module-shell__header"
              onContextMenu={(event) => {
                event.preventDefault();
                setContextTarget(module.id);
              }}
            >
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
            left: hoverCell.column * gridSize - gridOrigin.x,
            top: hoverCell.row * gridSize - gridOrigin.y,
            width: gridSize,
            height: gridSize,
          }}
        >
          <span>+</span>
        </div>
      )}

      {placementMode && selectionRect && (
        <div
          className="module-grid__selection"
          style={{
            left: selectionRect.column * gridSize - gridOrigin.x,
            top: selectionRect.row * gridSize - gridOrigin.y,
            width: selectionRect.width * gridSize,
            height: selectionRect.height * gridSize,
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
