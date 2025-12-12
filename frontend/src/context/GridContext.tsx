import { createContext, ReactNode, useContext, useMemo, useState } from "react";

type GridPan = { x: number; y: number };

type GridContextValue = {
  zoom: number;
  setZoom: (value: number) => void;
  pan: GridPan;
  setPan: (value: GridPan) => void;
};

const GridContext = createContext<GridContextValue | undefined>(undefined);

export const GridProvider = ({ children }: { children: ReactNode }) => {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<GridPan>({ x: 0, y: 0 });

  const value = useMemo(() => ({ zoom, setZoom, pan, setPan }), [zoom, pan]);

  return <GridContext.Provider value={value}>{children}</GridContext.Provider>;
};

export const useGridContext = () => {
  const context = useContext(GridContext);
  if (!context) {
    throw new Error("useGridContext must be used within a GridProvider");
  }
  return context;
};
