export const GRID_BASE_SIZE = 40;
export const GRID_META_MULTIPLIER = 3;
export const GRID_QUARTER_DIVISOR = 4;

export const GRID_SYSTEM = {
  base: GRID_BASE_SIZE,
  meta: GRID_BASE_SIZE * GRID_META_MULTIPLIER,
  quarter: GRID_BASE_SIZE / GRID_QUARTER_DIVISOR,
};

export type GridScaleKey = keyof typeof GRID_SYSTEM;

export const getGridSize = (key: GridScaleKey, zoom = 1) => {
  return GRID_SYSTEM[key] * zoom;
};

export const clampToGrid = (value: number, size: number) => {
  if (size <= 0) return 0;
  return Math.floor(value / size);
};
