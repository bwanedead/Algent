import { useRef } from "react";
import { useTraceEngine } from "../hooks/useTraceEngine";

const GridTraceLayer = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const { canvasRef } = useTraceEngine(containerRef);

  return (
    <div className="hud-grid-layer trace-layer" ref={containerRef}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "100%", display: "block" }}
      />
    </div>
  );
};

export default GridTraceLayer;
