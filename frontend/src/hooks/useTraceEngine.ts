import { useEffect, useMemo, useRef } from "react";
import { GRID_SYSTEM } from "../constants/grid";
import { useGridContext } from "../context/GridContext";
import { Point, evolveColor, generateTracePath } from "../logic/trace-rules";

export type TraceType = "standard" | "meta" | "micro";

export type Trace = {
  id: number;
  segments: Point[];
  startTime: number;
  duration: number;
  hue: number;
  generation: number;
  type: TraceType;
  gridScale: number;
  speed: number;
  tailLength: number;
  headRadius: number;
  nextLegDistance: number;
  maxDistance: number;
  hasTriggeredComplete?: boolean;
  completedAt?: number;
  columns: number;
  rows: number;
};

export type TraceRenderStyle = {
  lineWidth: number;
  shadowBlur: number;
  shadowAlpha: number;
  tailMaxOpacity: number;
  headSaturation: number;
  headLightness: number;
  headAlpha: number;
  tailSaturation: number;
  tailLightness: number;
};

const SPEED_STANDARD = 0.8;
const SPEED_META = 0.18;
const SPEED_MICRO = 0.85;

const TAIL_STANDARD = 160;
const TAIL_META = 360;
const TAIL_MICRO = 80;

const HEAD_RADIUS_STANDARD = 1.5;
const HEAD_RADIUS_META = 3;
const HEAD_RADIUS_MICRO = 0.9;

const HEAD_DECAY_MS = 260;
const TAIL_FADE_MS = 800;

const MICRO_SPAWN_CHANCE = 0.08;
const STANDARD_SPAWN_CHANCE = 0.24;
const META_SPAWN_CHANCE = 0.08;
const COMPLETION_BRANCH_PROBABILITY = 0.2;
const ENABLE_TRACE_DEBUG = true;
const BRANCH_DIRECTIONS: number[] = [0, 1, 2, 3];

const debugLog = (...args: unknown[]) => {
  if (ENABLE_TRACE_DEBUG) {
    console.info(...args);
  }
};

const TRACE_RENDER_STYLE: Record<TraceType, TraceRenderStyle> = {
  standard: {
    lineWidth: 1.2,
    shadowBlur: 8,
    shadowAlpha: 0.35,
    tailMaxOpacity: 0.6,
    headSaturation: 90,
    headLightness: 62,
    headAlpha: 0.85,
    tailSaturation: 82,
    tailLightness: 52,
  },
  meta: {
    lineWidth: 1.6,
    shadowBlur: 11,
    shadowAlpha: 0.28,
    tailMaxOpacity: 0.42,
    headSaturation: 28,
    headLightness: 66,
    headAlpha: 0.5,
    tailSaturation: 24,
    tailLightness: 60,
  },
  micro: {
    lineWidth: 0.9,
    shadowBlur: 5,
    shadowAlpha: 0.25,
    tailMaxOpacity: 0.75,
    headSaturation: 78,
    headLightness: 72,
    headAlpha: 0.7,
    tailSaturation: 74,
    tailLightness: 66,
  },
};

export const useTraceEngine = (containerRef: React.RefObject<HTMLDivElement>) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tracesRef = useRef<Trace[]>([]);
  const pendingSpawnsRef = useRef<Trace[]>([]);
  const isRenderingRef = useRef(false);
  const nextId = useRef(0);
  const { zoom } = useGridContext();

  const gridScales = useMemo(
    () => ({
      standard: GRID_SYSTEM.base * zoom,
      meta: GRID_SYSTEM.meta * zoom,
      micro: GRID_SYSTEM.quarter * zoom,
    }),
    [zoom],
  );

  const tailLengths = useMemo(
    () => ({
      standard: TAIL_STANDARD * zoom,
      meta: TAIL_META * zoom,
      micro: TAIL_MICRO * zoom,
    }),
    [zoom],
  );

  const headRadii = useMemo(
    () => ({
      standard: HEAD_RADIUS_STANDARD * zoom,
      meta: HEAD_RADIUS_META * zoom,
      micro: HEAD_RADIUS_MICRO * zoom,
    }),
    [zoom],
  );

  useEffect(() => {
    const resolveTraceConfig = (type: TraceType) => {
      if (type === "meta") {
        return {
          gridScale: gridScales.meta,
          speed: SPEED_META,
          tailLength: tailLengths.meta,
          headRadius: headRadii.meta,
        };
      }
      if (type === "micro") {
        return {
          gridScale: gridScales.micro,
          speed: SPEED_MICRO,
          tailLength: tailLengths.micro,
          headRadius: headRadii.micro,
        };
      }
      return {
        gridScale: gridScales.standard,
        speed: SPEED_STANDARD,
        tailLength: tailLengths.standard,
        headRadius: headRadii.standard,
      };
    };

    const resizeCanvas = () => {
      if (containerRef.current && canvasRef.current) {
        canvasRef.current.width = containerRef.current.clientWidth;
        canvasRef.current.height = containerRef.current.clientHeight;
      }
    };

    const spawnTrace = (
      startPos?: Point,
      forcedStartDir: number | null = null,
      parentHue: number | null = null,
      generation = 0,
      type: TraceType = "standard",
    ) => {
      if (!containerRef.current) return;

      const { clientWidth, clientHeight } = containerRef.current;
      if (clientWidth === 0 || clientHeight === 0) return;

      const config = resolveTraceConfig(type);
      const cols = Math.max(1, Math.floor(clientWidth / config.gridScale));
      const rows = Math.max(1, Math.floor(clientHeight / config.gridScale));

      let origin: Point = startPos
        ? { x: startPos.x, y: startPos.y }
        : {
            x: Math.floor(Math.random() * cols),
            y: Math.floor(Math.random() * rows),
          };

      origin = {
        x: clamp(origin.x, 0, cols),
        y: clamp(origin.y, 0, rows),
      };

      const generated = generateTracePath(origin, cols, rows, null, forcedStartDir);
      const path = generated.path;

      if (path.length < 2) {
        return;
      }

      const hue = pickHue(type, parentHue);
      const totalLength = (path.length - 1) * config.gridScale;
      const duration = totalLength / config.speed + 1200;

      const traceRecord: Trace = {
        id: nextId.current++,
        segments: path,
        startTime: Date.now(),
        duration,
        hue,
        generation,
        type,
        gridScale: config.gridScale,
        speed: config.speed,
        tailLength: config.tailLength,
        headRadius: config.headRadius,
        nextLegDistance: config.gridScale,
        maxDistance: totalLength,
        columns: cols,
        rows: rows,
      };

      if (isRenderingRef.current) {
        pendingSpawnsRef.current.push(traceRecord);
      } else {
        tracesRef.current.push(traceRecord);
      }

      debugLog(
        `[trace] spawn ${type}#${traceRecord.id} len=${path.length - 1} hue=${Math.round(
          hue,
        )} grid=${config.gridScale.toFixed(1)} cols=${cols} rows=${rows}`,
      );
    };

    const handleTraceComplete = (
      trace: Trace,
      endPos: Point,
      _arrivalDir: number | null,
    ) => {
      BRANCH_DIRECTIONS.forEach((dir) => {
        const neighbor = getNeighbor(endPos, dir);
        if (
          neighbor.x < 0 ||
          neighbor.y < 0 ||
          neighbor.x > trace.columns ||
          neighbor.y > trace.rows
        ) {
          debugLog(
            `[trace] skip child (out of bounds) type=${trace.type} parent=${trace.id} neighbor=(${neighbor.x},${neighbor.y})`,
          );
          return;
        }
        if (Math.random() < COMPLETION_BRANCH_PROBABILITY) {
          const hueSeed = shiftHue(trace.hue, trace.type === "micro" ? 48 : 28);
          spawnTrace(endPos, dir, hueSeed, trace.generation + 1, trace.type);
          debugLog(
            `[trace] child spawn type=${trace.type} parent=${trace.id} dir=${dir} hue=${Math.round(
              hueSeed,
            )}`,
          );
        } else {
          debugLog(
            `[trace] child roll failed type=${trace.type} parent=${trace.id} dir=${dir}`,
          );
        }
      });
    };

    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    const standardLoop = setInterval(() => {
      if (Math.random() < STANDARD_SPAWN_CHANCE) {
        spawnTrace();
      }
    }, 1000);

    const metaLoop = setInterval(() => {
      if (Math.random() < META_SPAWN_CHANCE) {
        spawnTrace(undefined, null, null, 0, "meta");
      }
    }, 1800);

    let animationFrameId: number;

    const render = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const now = Date.now();
      const activeTraces: Trace[] = [];
      isRenderingRef.current = true;

      tracesRef.current.forEach((trace) => {
        const age = now - trace.startTime;
        const dist = age * trace.speed;
        const totalPathLen = trace.maxDistance;

        if (trace.type === "micro") {
          debugLog(
            `[render] micro tick ${trace.id} age=${age.toFixed(
              1,
            )} dist=${dist.toFixed(1)} total=${totalPathLen.toFixed(1)}`,
          );
        }

        if (dist >= totalPathLen && !trace.hasTriggeredComplete) {
          trace.hasTriggeredComplete = true;
          trace.completedAt = trace.completedAt ?? now;
          const last = trace.segments[trace.segments.length - 1];
          const prev = trace.segments[trace.segments.length - 2];
          const dir = deriveDirection(prev, last);
          handleTraceComplete(trace, last, dir);
        }

        while (dist >= trace.nextLegDistance && trace.nextLegDistance < totalPathLen) {
          const nodeIndex = Math.min(
            Math.round(trace.nextLegDistance / trace.gridScale),
            trace.segments.length - 1,
          );
          if (nodeIndex > 0) {
            const node = trace.segments[nodeIndex];
            const prev = trace.segments[nodeIndex - 1];
            const dir = deriveDirection(prev, node);
            if (
              (trace.type === "standard" || trace.type === "meta") &&
              Math.random() < MICRO_SPAWN_CHANCE
            ) {
              const microHue = shiftHue(trace.hue, 48);
              spawnTrace(node, dir, microHue, trace.generation + 1, "micro");
              debugLog(
                `[trace] micro spawn from ${trace.type}#${trace.id} dir=${dir} hue=${Math.round(
                  microHue,
                )}`,
              );
            }
          }
          trace.nextLegDistance += trace.gridScale;
        }

        const isFadedOut =
          trace.completedAt !== undefined && now - trace.completedAt > TAIL_FADE_MS;
        if (isFadedOut) {
          debugLog(`[render] cull faded ${trace.type}#${trace.id}`);
          return;
        }

        const tailPos = Math.max(0, Math.min(dist, totalPathLen) - trace.tailLength);
        if (trace.type === "micro") {
          debugLog(
            `[render] micro candidate ${trace.id} dist=${dist.toFixed(
              1,
            )} head=${Math.min(dist, totalPathLen).toFixed(1)} tailStart=${tailPos.toFixed(
              1,
            )} max=${totalPathLen.toFixed(1)}`,
          );
        }
        if (tailPos >= totalPathLen) {
          debugLog(
            `[render] skip tail>len ${trace.type}#${trace.id} tail=${tailPos} len=${totalPathLen}`,
          );
          return;
        }

        drawTrace(ctx, trace, dist, now);
        activeTraces.push(trace);
      });
      isRenderingRef.current = false;

      if (pendingSpawnsRef.current.length > 0) {
        debugLog(
          `[trace] flush pending ${pendingSpawnsRef.current.length} traces`,
        );
        activeTraces.push(...pendingSpawnsRef.current);
        pendingSpawnsRef.current = [];
      }

      tracesRef.current = activeTraces;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", resizeCanvas);
      clearInterval(standardLoop);
      clearInterval(metaLoop);
      cancelAnimationFrame(animationFrameId);
    };
  }, [containerRef, gridScales, headRadii, tailLengths]);

  return { canvasRef };
};

function drawTrace(
  ctx: CanvasRenderingContext2D,
  trace: Trace,
  dist: number,
  now: number,
) {
  const totalPathLen = trace.maxDistance;
  const headPos = Math.min(dist, totalPathLen);
  const tailPos = Math.max(0, headPos - trace.tailLength);
  if (tailPos >= totalPathLen) {
    return;
  }

  const style = TRACE_RENDER_STYLE[trace.type];
  const gridScale = trace.gridScale;

  const decayFactor =
    trace.completedAt !== undefined
      ? clamp(1 - (now - trace.completedAt) / TAIL_FADE_MS)
      : 1;

  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = style.lineWidth;
  ctx.shadowBlur = style.shadowBlur;
  ctx.shadowColor = hsla(
    trace.hue,
    style.tailSaturation,
    style.tailLightness + 5,
    style.shadowAlpha,
  );

  if (trace.type === "micro") {
    debugLog(
      `[render] micro draw start ${trace.id} head=${headPos.toFixed(2)} tail=${tailPos.toFixed(
        2,
      )} segments=${trace.segments.length}`,
    );
  }

  let drewSegment = false;
  let currentD = 0;
  for (let i = 0; i < trace.segments.length - 1; i++) {
    const p1 = trace.segments[i];
    const p2 = trace.segments[i + 1];
    const segStart = currentD;
    const segEnd = segStart + gridScale;
    const startOverlap = Math.max(segStart, tailPos);
    const endOverlap = Math.min(segEnd, headPos);

    if (startOverlap < endOverlap) {
      drewSegment = true;
      const f1 = (startOverlap - segStart) / gridScale;
      const f2 = (endOverlap - segStart) / gridScale;

      const x1 = (p1.x + (p2.x - p1.x) * f1) * gridScale;
      const y1 = (p1.y + (p2.y - p1.y) * f1) * gridScale;
      const x2 = (p1.x + (p2.x - p1.x) * f2) * gridScale;
      const y2 = (p1.y + (p2.y - p1.y) * f2) * gridScale;

      const fadeStart = clamp(1 - (headPos - startOverlap) / trace.tailLength);
      const fadeEnd = clamp(1 - (headPos - endOverlap) / trace.tailLength);
      const opacityStart = fadeStart * style.tailMaxOpacity * decayFactor;
      const opacityEnd = fadeEnd * style.tailMaxOpacity * decayFactor;

      const grad = ctx.createLinearGradient(x1, y1, x2, y2);
      grad.addColorStop(
        0,
        hsla(trace.hue, style.tailSaturation, style.tailLightness, opacityStart),
      );
      grad.addColorStop(
        1,
        hsla(trace.hue, style.tailSaturation, style.tailLightness, opacityEnd),
      );

      ctx.strokeStyle = grad;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    currentD += gridScale;
  }

  if (!drewSegment) {
    debugLog(`[render] no segments drawn ${trace.type}#${trace.id}`);
  } else if (trace.type === "micro") {
    debugLog(
      `[render] micro segments ${trace.id} tailStart=${tailPos.toFixed(2)} head=${headPos.toFixed(
        2,
      )}`,
    );
  }

  const { x: hx, y: hy } = getHeadCoordinates(trace, headPos);
  const overrun = Math.max(0, dist - totalPathLen);
  const fade = clamp(1 - overrun / HEAD_DECAY_MS);
  const radius = trace.headRadius * fade;
  const headOpacity = style.headAlpha * fade * decayFactor;

  if (radius > 0.05 && headOpacity > 0.01) {
    if (
      hx < 0 ||
      hy < 0 ||
      hx > ctx.canvas.width ||
      hy > ctx.canvas.height
    ) {
      debugLog(
        `[render] head offscreen ${trace.type}#${trace.id} hx=${hx} hy=${hy} canvas=${ctx.canvas.width}x${ctx.canvas.height}`,
      );
    }
    if (trace.type === "micro") {
      debugLog(
        `[render] micro head ${trace.id} hx=${hx.toFixed(1)} hy=${hy.toFixed(
          1,
        )} radius=${radius.toFixed(2)} opacity=${headOpacity.toFixed(2)}`,
      );
    }
    ctx.fillStyle = hsla(
      trace.hue,
      style.headSaturation,
      style.headLightness,
      headOpacity,
    );
    ctx.beginPath();
    ctx.arc(hx, hy, radius, 0, Math.PI * 2);
    ctx.fill();
  }
}
function pickHue(type: TraceType, parentHue: number | null) {
  if (type === "meta") {
    return 260 + (Math.floor(Math.random() * 14) - 7);
  }
  if (type === "micro") {
    const base = parentHue ?? 205;
    const jitter = Math.random() * 20 - 10;
    return (base + jitter + 360) % 360;
  }
  return evolveColor(parentHue);
}

function shiftHue(baseHue: number | null, variance = 28) {
  if (baseHue === null) {
    return evolveColor(null);
  }
  const delta = Math.random() * variance * 2 - variance;
  return (baseHue + delta + 360) % 360;
}

function deriveDirection(from: Point, to: Point): number | null {
  if (to.y < from.y) return 0;
  if (to.x > from.x) return 1;
  if (to.y > from.y) return 2;
  if (to.x < from.x) return 3;
  return null;
}

function getNeighbor(point: Point, dir: number): Point {
  switch (dir) {
    case 0:
      return { x: point.x, y: point.y - 1 };
    case 1:
      return { x: point.x + 1, y: point.y };
    case 2:
      return { x: point.x, y: point.y + 1 };
    case 3:
      return { x: point.x - 1, y: point.y };
    default:
      return point;
  }
}

function getHeadCoordinates(trace: Trace, headPos: number) {
  const gridScale = trace.gridScale;
  const totalPathLen = trace.maxDistance;

  if (headPos >= totalPathLen) {
    const last = trace.segments[trace.segments.length - 1];
    return {
      x: last.x * gridScale,
      y: last.y * gridScale,
    };
  }

  const segIdx = Math.min(
    Math.floor(headPos / gridScale),
    trace.segments.length - 2,
  );
  const fraction = (headPos % gridScale) / gridScale;
  const p1 = trace.segments[segIdx];
  const p2 = trace.segments[segIdx + 1];

  return {
    x: (p1.x + (p2.x - p1.x) * fraction) * gridScale,
    y: (p1.y + (p2.y - p1.y) * fraction) * gridScale,
  };
}

function hsla(h: number, s: number, l: number, a: number) {
  return `hsla(${h}, ${s}%, ${l}%, ${a})`;
}

function clamp(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value));
}

