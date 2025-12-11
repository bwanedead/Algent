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
const META_GRID = 120; // 3 * BASE_GRID

const GridTraceLayer = () => {
  const [traces, setTraces] = useState<Trace[]>([]);
  const nextId = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const spawnTrace = (
    startPos?: Point, 
    forcedStartDir: number | null = null,
    parentHue: number | null = null,
    generation: number = 0,
    type: TraceType = 'standard'
  ) => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    
    // Scale depends on trace type
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

    const hue = evolveColor(parentHue);

    // Calculate duration to ensure full fade out
    // standard: 40ms/step, meta: 300ms/step
    const stepSpeed = type === 'meta' ? 300 : 40;
    const tailLength = 15; // approx max fade distance
    const totalSteps = path.length + tailLength;
    const duration = totalSteps * stepSpeed + 500; // buffer

    setTraces((prev) => [
      ...prev,
      {
        id: nextId.current++,
        segments: path,
        startTime: Date.now(),
        duration,
        hue,
        generation,
        type
      },
    ]);
  };

  const handleTraceComplete = (endPos: Point, arrivalDir: number | null, hue: number, generation: number, type: TraceType) => {
    const newDirs = calculateBranching(arrivalDir);
    
    newDirs.forEach(dir => {
      // Pass the same type to children
      spawnTrace(endPos, dir, hue, generation + 1, type);
    });
  };

  useEffect(() => {
    // Separate loop for Standard traces (10% chance every 1s)
    const standardLoop = setInterval(() => {
      if (Math.random() < 0.1) {
        spawnTrace(undefined, null, null, 0, 'standard');
      }
    }, 1000);

    // Separate loop for Meta traces (staggered, 3% chance every 0.9s)
    const metaLoop = setInterval(() => {
      if (Math.random() < 0.03) {
        spawnTrace(undefined, null, null, 0, 'meta');
      }
    }, 900);

    const cleanupInterval = setInterval(() => {
      const now = Date.now();
      setTraces((prev) => prev.filter((t) => now - t.startTime < t.duration));
    }, 1000);

    return () => {
      clearInterval(standardLoop);
      clearInterval(metaLoop);
      clearInterval(cleanupInterval);
    };
  }, []);

  return (
    <div className="hud-grid-layer trace-layer" ref={containerRef}>
      {traces.map((trace) => (
        <TraceRenderer 
          key={trace.id} 
          trace={trace} 
          onComplete={handleTraceComplete}
        />
      ))}
    </div>
  );
};

const TraceRenderer = ({ 
  trace, 
  onComplete 
}: { 
  trace: Trace; 
  onComplete: (endPos: Point, lastDir: number | null, hue: number, gen: number, type: TraceType) => void 
}) => {
  const [visibleSegments, setVisibleSegments] = useState<number>(0);
  const hasCompletedRef = useRef(false);

  // Styling / Timing based on type
  const isMeta = trace.type === 'meta';
  const gridScale = isMeta ? META_GRID : BASE_GRID;
  const tickRate = isMeta ? 300 : 40; // Slower tick for meta
  const traceWidth = isMeta ? '3px' : '1px';
  const headSize = isMeta ? '6px' : '3px';
  const maxOpacity = isMeta ? 0.4 : 0.5; // Even fainter standard, meta is also faint
  const fadeRate = isMeta ? 0.05 : 0.15; // Meta fades very slowly (long tail)

  useEffect(() => {
    const stepInterval = setInterval(() => {
      setVisibleSegments((prev) => {
        // Trigger completion callback ONCE when head hits end
        if (!hasCompletedRef.current && prev >= trace.segments.length - 1) {
          hasCompletedRef.current = true;
          
          let lastDir: number | null = null;
          if (trace.segments.length >= 2) {
            const last = trace.segments[trace.segments.length - 1];
            const secondLast = trace.segments[trace.segments.length - 2];
            
            if (last.y < secondLast.y) lastDir = 0; 
            else if (last.x > secondLast.x) lastDir = 1; 
            else if (last.y > secondLast.y) lastDir = 2; 
            else if (last.x < secondLast.x) lastDir = 3; 
          }
          
          const endPos = trace.segments[trace.segments.length - 1];
          onComplete(endPos, lastDir, trace.hue, trace.generation, trace.type);
        }
        
        return prev + 1;
      });
    }, tickRate); 

    return () => clearInterval(stepInterval);
  }, [trace.segments.length, onComplete, trace.segments, trace.hue, trace.generation, trace.type, tickRate]);

  return (
    <>
      {trace.segments.map((pt, idx) => {
        if (idx === 0) return null; 
        
        // Don't render segments that haven't been reached
        if (idx > visibleSegments) return null;

        const prev = trace.segments[idx - 1];
        const isVertical = prev.x === pt.x;
        const isHead = idx === visibleSegments;
        
        const left = Math.min(prev.x, pt.x) * gridScale;
        const top = Math.min(prev.y, pt.y) * gridScale;
        
        const dist = visibleSegments - idx;
        
        // Tail fade logic
        const rawOpacity = 1 - dist * fadeRate;
        
        if (rawOpacity <= 0) return null;

        const baseOpacity = isHead ? 1 : rawOpacity * maxOpacity;
        const colorHead = `hsl(${trace.hue}, 100%, 60%)`;
        const colorTail = `hsl(${trace.hue}, 60%, 30%)`;

        const style: React.CSSProperties = {
            position: 'absolute',
            left: `${left}px`,
            top: `${top}px`,
            background: isHead ? colorHead : colorTail,
            opacity: baseOpacity,
            boxShadow: isHead 
              ? `0 0 ${isMeta ? '12px' : '6px'} ${colorHead}` 
              : 'none',
            pointerEvents: 'none',
            zIndex: isHead ? 2 : 1,
            // Meta pulse is diffuse
            filter: isMeta ? 'blur(2px)' : 'none',
        };

        if (isVertical) {
            style.width = traceWidth;
            style.height = `${gridScale}px`;
            // Center on grid line
            style.left = `${left - (isMeta ? 1 : 0)}px`; 
        } else {
            style.width = `${gridScale}px`;
            style.height = traceWidth;
            style.top = `${top - (isMeta ? 1 : 0)}px`;
        }

        return <div key={`seg-${idx}`} style={style} />;
      })}
      
      {/* Node Flash (Head) */}
      {visibleSegments > 0 && visibleSegments < trace.segments.length && (
        <div
          style={{
            position: "absolute",
            left: `${trace.segments[visibleSegments].x * gridScale - (isMeta ? 2 : 1)}px`,
            top: `${trace.segments[visibleSegments].y * gridScale - (isMeta ? 2 : 1)}px`,
            width: headSize,
            height: headSize,
            background: `hsl(${trace.hue}, 100%, 70%)`,
            borderRadius: "50%",
            boxShadow: `0 0 ${isMeta ? '16px 4px' : '8px 2px'} hsl(${trace.hue}, 100%, 50%)`,
            zIndex: 3,
            opacity: isMeta ? 0.8 : 1,
          }}
        />
      )}
    </>
  );
};

export default GridTraceLayer;
