import { useEffect, useRef } from "react";
import { GRID_SYSTEM } from "../constants/grid";
import {
  Point,
  evolveColor,
  generateTracePath,
  getValidDirections,
} from "../logic/trace-rules";

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

const BASE_GRID = GRID_SYSTEM.base;
const META_GRID = GRID_SYSTEM.meta;
const MICRO_GRID = GRID_SYSTEM.quarter;

const SPEED_STANDARD = 0.8;
const SPEED_META = 0.18;
const SPEED_MICRO = 0.85;

const TAIL_STANDARD = 160;
const TAIL_META = 360;
const TAIL_MICRO = 80;

const HEAD_DECAY_MS = 260;
const TAIL_FADE_MS = 800;

const MICRO_MAX_LEGS = 10;
const MICRO_SPAWN_CHANCE = 0.03;
const STANDARD_SPAWN_CHANCE = 0.24;
const META_SPAWN_CHANCE = 0.08;
const COMPLETION_BRANCH_PROBABILITY = 0.2;
const ENABLE_TRACE_DEBUG = true;

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
    lineWidth: 0.75,
    shadowBlur: 4,
    shadowAlpha: 0.22,
    tailMaxOpacity: 0.6,
    headSaturation: 75,
    headLightness: 68,
    headAlpha: 0.55,
    tailSaturation: 72,
    tailLightness: 60,
  },
};

export const useTraceEngine = (containerRef: React.RefObject<HTMLDivElement>) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tracesRef = useRef<Trace[]>([]);
  const nextId = useRef(0);

  useEffect(() => {
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
      let path = generated.path;
      if (type === "micro" && path.length > MICRO_MAX_LEGS + 1) {
        path = path.slice(0, MICRO_MAX_LEGS + 1);
      }

      if (path.length < 2) {
        return;
      }

      const hue = pickHue(type, parentHue);
      const totalLength = (path.length - 1) * config.gridScale;
      const duration = totalLength / config.speed + 1200;

      tracesRef.current.push({
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
      });

      if (ENABLE_TRACE_DEBUG) {
        console.info(
          `[trace] spawned ${type}#${nextId.current - 1} len=${path.length - 1} cells hue=${Math.round(
            hue,
          )} grid=${config.gridScale}px`,
        );
      }
    };

    const handleTraceComplete = (
      trace: Trace,
      endPos: Point,
      arrivalDir: number | null,
    ) => {
      if (trace.type === "micro") {
        return;
      }
      const candidates = getValidDirections(arrivalDir);
      candidates.forEach((dir) => {
        if (Math.random() < COMPLETION_BRANCH_PROBABILITY) {
          const hueSeed = shiftHue(trace.hue);
          spawnTrace(endPos, dir, hueSeed, trace.generation + 1, trace.type);
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

      tracesRef.current.forEach((trace) => {
        const age = now - trace.startTime;
        const dist = age * trace.speed;
        const totalPathLen = trace.maxDistance;

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
              spawnTrace(node, dir, shiftHue(trace.hue, 12), trace.generation + 1, "micro");
            }
          }
          trace.nextLegDistance += trace.gridScale;
        }

        const isFadedOut =
          trace.completedAt !== undefined && now - trace.completedAt > TAIL_FADE_MS;
        if (isFadedOut) {
          return;
        }

        drawTrace(ctx, trace, dist, now);
        activeTraces.push(trace);
      });

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
  }, [containerRef]);

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

  let currentD = 0;
  for (let i = 0; i < trace.segments.length - 1; i++) {
    const p1 = trace.segments[i];
    const p2 = trace.segments[i + 1];
    const segStart = currentD;
    const segEnd = segStart + gridScale;
    const startOverlap = Math.max(segStart, tailPos);
    const endOverlap = Math.min(segEnd, headPos);

    if (startOverlap < endOverlap) {
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

  const { x: hx, y: hy } = getHeadCoordinates(trace, headPos);
  const overrun = Math.max(0, dist - totalPathLen);
  const fade = clamp(1 - overrun / HEAD_DECAY_MS);
  const radius = trace.headRadius * fade;
  const headOpacity = style.headAlpha * fade * decayFactor;

  if (radius > 0.05 && headOpacity > 0.01) {
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

function resolveTraceConfig(type: TraceType) {
  if (type === "meta") {
    return {
      gridScale: META_GRID,
      speed: SPEED_META,
      tailLength: TAIL_META,
      headRadius: 3,
    };
  }
  if (type === "micro") {
    return {
      gridScale: MICRO_GRID,
      speed: SPEED_MICRO,
      tailLength: TAIL_MICRO,
      headRadius: 0.9,
    };
  }
  return {
    gridScale: BASE_GRID,
    speed: SPEED_STANDARD,
    tailLength: TAIL_STANDARD,
    headRadius: 1.5,
  };
}

function pickHue(type: TraceType, parentHue: number | null) {
  if (type === "meta") {
    return 260 + (Math.floor(Math.random() * 14) - 7);
  }
  if (type === "micro") {
    const base = parentHue ?? evolveColor(null);
    return base + (Math.random() * 20 - 10);
  }
  return evolveColor(parentHue);
}

function shiftHue(baseHue: number | null, variance = 18) {
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
