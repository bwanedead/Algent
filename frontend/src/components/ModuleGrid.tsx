import { CSSProperties, useMemo, useRef } from "react";
import { useGridMetrics } from "../hooks/useGridMetrics";
import { useModuleContextMenu } from "../hooks/useModuleContextMenu";
import { useModulePlacement } from "../hooks/useModulePlacement";
import { ModuleDraft, ModuleShape } from "../types/modules";

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
  const { gridSize, gridOrigin, alignment } = useGridMetrics(containerRef, {
    fallbackSize: 40,
  });

  const {
    hoverCell,
    selectionRect,
    isDrawing,
    handleMouseMove,
    handleMouseDown,
    handleMouseUp,
  } = useModulePlacement({
    containerRef,
    gridSize,
    gridOrigin,
    placementMode,
    onModuleCreate,
    onCancelPlacement,
  });

  const { contextMenu, menuRef: contextMenuRef, openContextMenu, closeContextMenu } =
    useModuleContextMenu();

  const handleDeleteFromMenu = () => {
    if (!contextMenu) return;
    onModuleDelete(contextMenu.moduleId);
    closeContextMenu();
  };

  const selectionLabel = useMemo(() => {
    if (!selectionRect) return null;
    return `${selectionRect.width} A- ${selectionRect.height}`;
  }, [selectionRect]);

  return (
    <div
      className="module-grid"
      ref={containerRef}
      style={
        {
          "--module-grid-size": `${gridSize}px`,
          "--module-grid-origin-x": `${alignment.x}px`,
          "--module-grid-origin-y": `${alignment.y}px`,
        } as CSSProperties
      }
    >
      <div
        className={`module-grid__surface ${placementMode ? "is-placing" : ""}`}
        style={{
          backgroundSize: `${gridSize}px ${gridSize}px`,
          backgroundPosition: `-${alignment.x}px -${alignment.y}px`,
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
          <div
            key={module.id}
            className="module-shell"
            style={style}
            onContextMenu={(event) => openContextMenu(event, module.id)}
          >
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

      {placementMode && hoverCell && !isDrawing && (
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
          <span>{selectionLabel}</span>
        </div>
      )}

      {placementMode && (
        <div className="module-grid__instructions">
          Click and drag across the grid to allocate space. Press Esc to cancel.
        </div>
      )}

      {contextMenu && (
        <div
          className="module-context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          ref={contextMenuRef}
        >
          <button
            type="button"
            className="module-context-menu__item is-danger"
            onClick={handleDeleteFromMenu}
          >
            Delete module
          </button>
        </div>
      )}

      {!modules.length && !placementMode && (
        <div className="module-grid__empty-state">
          No modules yet. Use "New Module" to start assembling a loop.
        </div>
      )}
    </div>
  );
};

export default ModuleGrid;
