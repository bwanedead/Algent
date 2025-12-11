import { useEffect, useRef, useState } from "react";
import { 
  generateTracePath, 
  calculateBranching, 
  evolveColor, 
  Point 
} from "../logic/trace-rules";

type TraceType = 'standard' | 'meta';

type Trace = {
  id: number;
  segments: Point[];
  startTime: number;
  duration: number;
  hue: number;
  generation: number;
  type: TraceType;
};

// Grid settings (must match CSS)
const BASE_GRID = 40;
const META_GRID = 120; 

// Pixel speeds (pixels per millisecond)
const SPEED_STANDARD = 0.8; // e.g. 40px in 50ms = 0.8px/ms
const SPEED_META = 0.15;    // e.g. 120px in 800ms = 0.15px/ms

const GridTraceLayer = () => {
  const [traces, setTraces] = useState<Trace[]>([]);
  const nextId = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Ref to canvas for drawing
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  // Store traces in ref for animation loop
  const tracesRef = useRef<Trace[]>([]);

  // Helper to add trace
  const addTrace = (t: Trace) => {
    tracesRef.current.push(t);
    // Trigger React render? Only if we need to visualize something via React.
    // Here we draw via canvas, so no react state needed for rendering.
    // BUT we might want to debug or track count.
  };

  const spawnTrace = (
    startPos?: Point, 
    forcedStartDir: number | null = null,
    parentHue: number | null = null,
    generation: number = 0,
    type: TraceType = 'standard'
  ) => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    
    const gridScale = type === 'meta' ? META_GRID : BASE_GRID;
    const cols = Math.floor(clientWidth / gridScale);
    const rows = Math.floor(clientHeight / gridScale);

    let origin = startPos;
    if (!origin) {
      origin = {
        x: Math.floor(Math.random() * cols),
        y: Math.floor(Math.random() * rows)
      };
    }

    const { path } = generateTracePath(
      origin, 
      cols, 
      rows, 
      null, 
      forcedStartDir
    );

    if (path.length < 2) return; 

    // Meta Color Override: Cool Blue/Grey/Pale
    const hue = type === 'meta' 
      ? 210 + (Math.floor(Math.random() * 20) - 10) 
      : evolveColor(parentHue);

    // Calculate total distance in pixels
    // path is segments of grid units.
    // Total length = (path.length - 1) * gridScale
    const totalLength = (path.length - 1) * gridScale;
    
    // Duration
    const speed = type === 'meta' ? SPEED_META : SPEED_STANDARD;
    const duration = totalLength / speed + 2000; // + decay time

    addTrace({
      id: nextId.current++,
      segments: path,
      startTime: Date.now(),
      duration,
      hue,
      generation,
      type
    });
  };

  const handleTraceComplete = (trace: Trace, endPos: Point, arrivalDir: number | null) => {
    const newDirs = calculateBranching(arrivalDir);
    newDirs.forEach(dir => {
      spawnTrace(endPos, dir, trace.hue, trace.generation + 1, trace.type);
    });
  };

  useEffect(() => {
    // Canvas Sizing
    const handleResize = () => {
      if (containerRef.current && canvasRef.current) {
        canvasRef.current.width = containerRef.current.clientWidth;
        canvasRef.current.height = containerRef.current.clientHeight;
      }
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    // Spawn Loops
    const standardLoop = setInterval(() => {
      if (Math.random() < 0.1) spawnTrace(undefined, null, null, 0, 'standard');
    }, 1000);

    const metaLoop = setInterval(() => {
      if (Math.random() < 0.03) spawnTrace(undefined, null, null, 0, 'meta');
    }, 900);

    // Animation Loop
    let animationFrameId: number;
    
    const render = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Clear
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      const now = Date.now();
      const activeTraces: Trace[] = [];

      tracesRef.current.forEach(trace => {
        const isMeta = trace.type === 'meta';
        const gridScale = isMeta ? META_GRID : BASE_GRID;
        const speed = isMeta ? SPEED_META : SPEED_STANDARD;
        
        // Calculate progress in pixels
        const age = now - trace.startTime;
        const dist = age * speed;
        
        const totalPathLen = (trace.segments.length - 1) * gridScale;
        
        // Check if finished path (just reached end)
        // We use a flag on the trace object to avoid double triggering?
        // Or just trigger once active
        // Simplification: We don't store 'completed' flag in ref object here, 
        // we can assume if dist > totalPathLen it's done moving.
        // But we need to trigger callback exactly once.
        // Let's add a property to the trace object in the ref.
        const tAny = trace as any;
        if (dist >= totalPathLen && !tAny.hasTriggeredComplete) {
            tAny.hasTriggeredComplete = true;
            // Calculate final dir
            if (trace.segments.length >= 2) {
                const last = trace.segments[trace.segments.length - 1];
                const prev = trace.segments[trace.segments.length - 2];
                let dir = null;
                if (last.y < prev.y) dir = 0;
                else if (last.x > prev.x) dir = 1;
                else if (last.y > prev.y) dir = 2;
                else if (last.x < prev.x) dir = 3;
                handleTraceComplete(trace, last, dir);
            }
        }

        // Cleanup condition
        // Fade out happens after tail passes end?
        // Or strictly duration based.
        if (age > trace.duration) return; // Drop trace
        activeTraces.push(trace);

        // Draw Trace
        const tailLength = isMeta ? 300 : 150; // pixels
        const headPos = Math.min(dist, totalPathLen);
        const tailPos = Math.max(0, headPos - tailLength);
        
        if (tailPos >= totalPathLen) return; // Completely finished

        // Color
        const hue = trace.hue;
        const colorHead = isMeta ? `hsla(${hue}, 40%, 60%, 1)` : `hsla(${hue}, 100%, 60%, 1)`;
        const colorTail = isMeta ? `hsla(${hue}, 20%, 40%, 0)` : `hsla(${hue}, 60%, 30%, 0)`;
        const lineWidth = isMeta ? 3 : 1;
        const shadowBlur = isMeta ? 15 : 6;
        const shadowColor = isMeta ? `hsla(${hue}, 40%, 60%, 0.5)` : `hsla(${hue}, 100%, 60%, 0.5)`;

        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.lineWidth = lineWidth;
        ctx.shadowBlur = shadowBlur;
        ctx.shadowColor = shadowColor;

        // We need to draw the path segment from tailPos to headPos.
        // Since gradients along a path are hard, we use a simple linear gradient 
        // from tail start point to head point? No, path bends.
        
        // Strategy: Draw segments.
        // Iterate segments.
        // Map segment i to distance range [d_start, d_end].
        // Intersection with [tailPos, headPos].
        
        let currentD = 0;
        for (let i = 0; i < trace.segments.length - 1; i++) {
            const p1 = trace.segments[i];
            const p2 = trace.segments[i+1];
            
            // Segment distance
            const segLen = gridScale; // Orthogonal, always 1 unit
            const segStart = currentD;
            const segEnd = currentD + segLen;
            
            // Check overlap
            const startOverlap = Math.max(segStart, tailPos);
            const endOverlap = Math.min(segEnd, headPos);
            
            if (startOverlap < endOverlap) {
                // Determine coordinates for start/end of the visible part of this segment
                // fraction 0..1 along segment
                const f1 = (startOverlap - segStart) / segLen;
                const f2 = (endOverlap - segStart) / segLen;
                
                const x1 = (p1.x + (p2.x - p1.x) * f1) * gridScale;
                const y1 = (p1.y + (p2.y - p1.y) * f1) * gridScale;
                const x2 = (p1.x + (p2.x - p1.x) * f2) * gridScale;
                const y2 = (p1.y + (p2.y - p1.y) * f2) * gridScale;

                // Opacity Gradient
                // Head is at headPos (opacity 1). Tail is at tailPos (opacity 0).
                // Distance from head:
                // Point 1 dist: headPos - startOverlap
                // Point 2 dist: headPos - endOverlap
                
                // Map distance to opacity 0..1
                // Opacity = 1 - (dist / tailLength)
                // Note: Gradient must be Linear.
                
                const grad = ctx.createLinearGradient(x1, y1, x2, y2);
                
                const op1 = Math.max(0, 1 - (headPos - startOverlap) / tailLength);
                const op2 = Math.max(0, 1 - (headPos - endOverlap) / tailLength);
                
                // Standard pulse needs to be faint.
                const maxOp = isMeta ? 0.6 : 0.4;
                
                grad.addColorStop(0, isMeta ? `hsla(${hue}, 40%, 60%, ${op1 * maxOp})` : `hsla(${hue}, 100%, 60%, ${op1 * maxOp})`);
                grad.addColorStop(1, isMeta ? `hsla(${hue}, 40%, 60%, ${op2 * maxOp})` : `hsla(${hue}, 100%, 60%, ${op2 * maxOp})`);
                
                ctx.strokeStyle = grad;
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.stroke();
            }
            
            currentD += segLen;
        }
        
        // Draw Head Dot
        // Only if head is within path bounds (or very close)
        if (headPos > 0 && headPos <= totalPathLen) {
             // Find head segment
             // We can just interpolate headPos
             // headPos is pixel distance.
             // segment index = floor(headPos / gridScale)
             const segIdx = Math.min(Math.floor(headPos / gridScale), trace.segments.length - 2);
             const fraction = (headPos % gridScale) / gridScale;
             
             const p1 = trace.segments[segIdx];
             const p2 = trace.segments[segIdx+1];
             
             const hx = (p1.x + (p2.x - p1.x) * fraction) * gridScale;
             const hy = (p1.y + (p2.y - p1.y) * fraction) * gridScale;
             
             ctx.fillStyle = colorHead;
             ctx.beginPath();
             ctx.arc(hx, hy, isMeta ? 3 : 1.5, 0, Math.PI * 2);
             ctx.fill();
        }

      });

      tracesRef.current = activeTraces;
      animationFrameId = requestAnimationFrame(render);
    };
    
    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      clearInterval(standardLoop);
      clearInterval(metaLoop);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="hud-grid-layer trace-layer" ref={containerRef}>
      <canvas 
        ref={canvasRef} 
        style={{ width: '100%', height: '100%', display: 'block' }}
      />
    </div>
  );
};

export default GridTraceLayer;
