export type ModuleShape = {
  id: string;
  name: string;
  column: number;
  row: number;
  width: number;
  height: number;
};

export type ModuleDraft = Omit<ModuleShape, "id" | "name">;
