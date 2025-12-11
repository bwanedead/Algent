export type Point = { x: number; y: number };

/**
 * Returns available neighbor directions [0=N, 1=E, 2=S, 3=W]
 * excluding the immediate reverse of the arrival direction.
 */
export const getValidDirections = (
  arrivalDir: number | null
): number[] => {
  const allDirs = [0, 1, 2, 3];
  if (arrivalDir === null) return allDirs;
  
  // arrivalDir is the direction we were moving.
  // To reverse, we would move (arrivalDir + 2) % 4
  const forbidden = (arrivalDir + 2) % 4;
  return allDirs.filter(d => d !== forbidden);
};

/**
 * Calculates which neighbors trigger a new pulse.
 * 30% chance per valid neighbor.
 */
export const calculateBranching = (arrivalDir: number | null): number[] => {
  const candidates = getValidDirections(arrivalDir);
  return candidates.filter(() => Math.random() < 0.3);
};

/**
 * Evolves the hue by shifting it slightly.
 * Base Amber is ~38 deg.
 */
export const evolveColor = (parentHue: number | null): number => {
  if (parentHue === null) return 38; // Base Amber
  
  // Shift by -15 to +15 degrees
  const shift = Math.floor(Math.random() * 31) - 15;
  return (parentHue + shift + 360) % 360;
};

/**
 * Generates a random walk path.
 */
export const generateTracePath = (
  start: Point, 
  cols: number, 
  rows: number, 
  forbiddenStartDir: number | null = null, // Deprecated in favor of internal check but kept for compat
  forceStartDir: number | null = null
): { path: Point[]; lastDir: number | null } => {
  
  let { x: cx, y: cy } = start;
  // Clamp start
  cx = Math.max(0, Math.min(cols, cx));
  cy = Math.max(0, Math.min(rows, cy));

  const path = [{ x: cx, y: cy }];
  const steps = Math.floor(Math.random() * 30) + 1;
  
  // Track direction we are MOVING in (0=N, etc)
  let currentDir: number | null = forceStartDir; 

  // If forceStartDir provided, execute first step immediately
  if (forceStartDir !== null) {
    switch (forceStartDir) {
        case 0: cy--; break;
        case 1: cx++; break;
        case 2: cy++; break;
        case 3: cx--; break;
    }
    // Check bounds after forced step
    if (cx >= 0 && cx <= cols && cy >= 0 && cy <= rows) {
        path.push({ x: cx, y: cy });
    } else {
        // Wall hit immediately
        return { path, lastDir: null };
    }
  }

  for (let i = (forceStartDir !== null ? 1 : 0); i < steps; i++) {
    // Determine valid moves based on currentDir (to avoid 180 reverse)
    const validMoves = [0, 1, 2, 3].filter(dir => {
        // If we have a current moving direction, don't reverse
        if (currentDir !== null && dir === (currentDir + 2) % 4) return false;
        
        // Bounds check
        switch (dir) {
            case 0: return cy > 0;
            case 1: return cx < cols;
            case 2: return cy < rows;
            case 3: return cx > 0;
        }
        return false;
    });

    if (validMoves.length === 0) break;

    const nextDir = validMoves[Math.floor(Math.random() * validMoves.length)];
    
    switch (nextDir) {
        case 0: cy--; break;
        case 1: cx++; break;
        case 2: cy++; break;
        case 3: cx--; break;
    }
    path.push({ x: cx, y: cy });
    currentDir = nextDir;
  }

  return { path, lastDir: currentDir };
};
