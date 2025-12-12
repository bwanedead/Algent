import { useCallback, useEffect, useMemo, useState } from "react";
import { GRID_BASE_SIZE, GRID_SYSTEM } from "../constants/grid";
import { useGridContext } from "../context/GridContext";

type GridOrigin = { x: number; y: number };

type GridAlignment = { x: number; y: number };

type UseGridMetricsOptions = {
  cssVariable?: string;
  fallbackSize?: number;
};

export const useGridMetrics = (
  containerRef: React.RefObject<HTMLElement>,
  options: UseGridMetricsOptions = {},
) => {
  const cssVariable = options.cssVariable ?? "--s-grid";
  const fallback = options.fallbackSize ?? GRID_BASE_SIZE;
  const { zoom } = useGridContext();
  const [baseGridSize, setBaseGridSize] = useState(fallback);
  const [origin, setOrigin] = useState<GridOrigin>({ x: 0, y: 0 });

  const updateMetrics = useCallback(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    const computed = getComputedStyle(node);
    const sizeValue = computed.getPropertyValue(cssVariable);
    const parsed = parseFloat(sizeValue || "");
    if (!Number.isNaN(parsed) && parsed > 0) {
      setBaseGridSize(parsed);
    } else {
      setBaseGridSize(fallback);
    }

    const shell = node.closest(".hud-shell") as HTMLElement | null;
    const referenceRect = shell?.getBoundingClientRect();
    const nodeRect = node.getBoundingClientRect();
    if (referenceRect) {
      setOrigin({
        x: nodeRect.left - referenceRect.left,
        y: nodeRect.top - referenceRect.top,
      });
    }
  }, [containerRef, cssVariable, fallback]);

  useEffect(() => {
    updateMetrics();
    window.addEventListener("resize", updateMetrics);
    return () => window.removeEventListener("resize", updateMetrics);
  }, [updateMetrics]);

  const gridSize = useMemo(() => baseGridSize * zoom, [baseGridSize, zoom]);

  const alignment: GridAlignment = useMemo(() => {
    return {
      x: ((origin.x % gridSize) + gridSize) % gridSize,
      y: ((origin.y % gridSize) + gridSize) % gridSize,
    };
  }, [origin, gridSize]);

  const derived = useMemo(() => {
    return {
      base: gridSize,
      meta: (gridSize / GRID_SYSTEM.base) * GRID_SYSTEM.meta,
      quarter: gridSize / 4,
    };
  }, [gridSize]);

  return {
    gridSize,
    gridOrigin: origin,
    alignment,
    derived,
    refresh: updateMetrics,
  };
};
