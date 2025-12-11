import { useEffect, useRef, useState } from "react";
import { 
  generateTracePath, 
  calculateBranching, 
  evolveColor, 
  Point 
} from "../logic/trace-rules";

type Trace = {
  id: number;
  segments: Point[];
  startTime: number;
  duration: number;
  hue: number;
  generation: number;
};

// Grid settings (must match CSS)
const GRID_SIZE = 40;

const GridTraceLayer = () => {
  const [traces, setTraces] = useState<Trace[]>([]);
  const nextId = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const spawnTrace = (
    startPos?: Point, 
    forcedStartDir: number | null = null,
    parentHue: number | null = null,
    generation: number = 0
  ) => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    
    const cols = Math.floor(clientWidth / GRID_SIZE);
    const rows = Math.floor(clientHeight / GRID_SIZE);

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

    setTraces((prev) => [
      ...prev,
      {
        id: nextId.current++,
        segments: path,
        startTime: Date.now(),
        duration: path.length * 50 + 2000,
        hue,
        generation
      },
    ]);
  };

  const handleTraceComplete = (endPos: Point, arrivalDir: number | null, hue: number, generation: number) => {
    // Determine branches
    const newDirs = calculateBranching(arrivalDir);
    
    newDirs.forEach(dir => {
      spawnTrace(endPos, dir, hue, generation + 1);
    });
  };

  useEffect(() => {
    const activeSpawnLoop = setInterval(() => {
      if (Math.random() < 0.1) {
        spawnTrace();
      }
    }, 1000);

    const cleanupInterval = setInterval(() => {
      const now = Date.now();
      setTraces((prev) => prev.filter((t) => now - t.startTime < t.duration));
    }, 1000);

    return () => {
      clearInterval(activeSpawnLoop);
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
  onComplete: (endPos: Point, lastDir: number | null, hue: number, gen: number) => void 
}) => {
  const [visibleSegments, setVisibleSegments] = useState<number>(0);
  const hasCompletedRef = useRef(false);

  useEffect(() => {
    const stepInterval = setInterval(() => {
      setVisibleSegments((prev) => {
        if (prev < trace.segments.length) {
          return prev + 1;
        }
        
        clearInterval(stepInterval);
        
        if (!hasCompletedRef.current) {
          hasCompletedRef.current = true;
          let lastDir: number | null = null;
          if (trace.segments.length >= 2) {
            const last = trace.segments[trace.segments.length - 1];
            const secondLast = trace.segments[trace.segments.length - 2];
            
            if (last.y < secondLast.y) lastDir = 0; // N
            else if (last.x > secondLast.x) lastDir = 1; // E
            else if (last.y > secondLast.y) lastDir = 2; // S
            else if (last.x < secondLast.x) lastDir = 3; // W
          }
          
          const endPos = trace.segments[trace.segments.length - 1];
          onComplete(endPos, lastDir, trace.hue, trace.generation);
        }
        
        return prev;
      });
    }, 40); 

    return () => clearInterval(stepInterval);
  }, [trace.segments.length, onComplete, trace.segments, trace.hue, trace.generation]);

  return (
    <>
      {trace.segments.map((pt, idx) => {
        if (idx === 0) return null; 
        if (idx > visibleSegments) return null;

        const prev = trace.segments[idx - 1];
        const isVertical = prev.x === pt.x;
        const isHead = idx === visibleSegments;
        
        const left = Math.min(prev.x, pt.x) * GRID_SIZE;
        const top = Math.min(prev.y, pt.y) * GRID_SIZE;
        
        const dist = visibleSegments - idx;
        const opacity = Math.max(0, 1 - dist * 0.15); 

        if (opacity <= 0) return null;

        const colorHead = `hsl(${trace.hue}, 100%, 60%)`;
        const colorTail = `hsl(${trace.hue}, 60%, 30%)`;

        const style: React.CSSProperties = {
            position: 'absolute',
            left: `${left}px`,
            top: `${top}px`,
            background: isHead ? colorHead : colorTail,
            opacity: isHead ? 1 : opacity * 0.6,
            boxShadow: isHead ? `0 0 6px ${colorHead}` : 'none',
            pointerEvents: 'none',
            zIndex: isHead ? 2 : 1,
        };

        if (isVertical) {
            style.width = '1px';
            style.height = `${GRID_SIZE}px`;
            style.left = `${left}px`; 
        } else {
            style.width = `${GRID_SIZE}px`;
            style.height = '1px';
            style.top = `${top}px`;
        }

        return <div key={`seg-${idx}`} style={style} />;
      })}
      
      {visibleSegments > 0 && visibleSegments < trace.segments.length && (
        <div
          style={{
            position: "absolute",
            left: `${trace.segments[visibleSegments].x * GRID_SIZE - 1}px`,
            top: `${trace.segments[visibleSegments].y * GRID_SIZE - 1}px`,
            width: "3px",
            height: "3px",
            background: `hsl(${trace.hue}, 100%, 70%)`,
            borderRadius: "50%",
            boxShadow: `0 0 8px 2px hsl(${trace.hue}, 100%, 50%)`,
            zIndex: 3,
          }}
        />
      )}
    </>
  );
};

export default GridTraceLayer;
