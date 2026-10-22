// Basemap choice and quieting. OpenFreeMap (free, no key, no limits) serves the vector tiles; we pick its calm
// "positron" style for the paper theme and "dark" for dark-amber, then mute everything that is not geography
// (roads, rails, buildings, shields, one-way arrows) so our data layers dominate and country borders read clearly.
// Layer ids are matched by pattern so a style revision that renames a layer degrades to "left as it was", never an error.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

export type MapTheme = "paper" | "dark";

export const STYLE_URL: Record<MapTheme, string> = {
  paper: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

/** The site theme from <html data-theme>: only "paper" is light; dark-amber (the default) and anything else is dark. */
export function currentTheme(): MapTheme {
  return document.documentElement.getAttribute("data-theme") === "paper" ? "paper" : "dark";
}

// Colours shared with the static SVG map (app/daily/daily.css) on paper, so both read as one map.
const PALETTE = {
  paper: { background: "#f4f1e8", water: "#cfe3f1", border: "#7d8793", borderStrong: "#37424f", label: "#2b3440", halo: "#ffffff", quiet: "#c9c6bc" },
  dark: { background: "#1d2321", water: "#0a1217", border: "#6c7773", borderStrong: "#c4ccc7", label: "#a9b0ab", halo: "#0c0f0e", quiet: "#2a302e" },
};

const HIDE = /^(building|aeroway|railway|road_oneway|road_pier|road_area_pier|highway[-_]shield|road_shield|highway[-_]name|airport|landuse_residential|landcover_wood|park|landuse_park)/;
const ROAD = /^(highway_|tunnel_|road_)/;
const BORDER_COUNTRY = /^(boundary_2|boundary_country)/;
const BORDER_REGION = /^(boundary_3|boundary_state|boundary_disputed)/;
const SMALL_PLACE = /^(label_other|label_village|place_other|place_suburb|place_village)/;
const SOFT_LABEL = /^(waterway_line_label|water_name|water_name_point_label|water_name_line_label)/;

function paint(map: any, id: string, prop: string, value: unknown) {
  try {
    map.setPaintProperty(id, prop, value);
  } catch {
    /* this style revision lacks the property: leave it */
  }
}

export type QuietOptions = {
  /** Theater and dossier maps: country borders clearly stronger, internal subdivisions (oblasts, states) faint and thin. /live leaves this off. */
  theater?: boolean;
};

const BORDER_SUBDIVISION = /^(boundary_3|boundary_state)/; // admin_level 3-6 / 4: dashed in both styles, quieted on theater maps
const DISPUTED_LINE = /^boundary_disputed/; // keeps its own dashed style everywhere

/** Mute and recolour the loaded basemap style in place. */
export function quietBasemap(map: any, theme: MapTheme, opts: QuietOptions = {}) {
  const c = PALETTE[theme];
  const layers: { id: string; type: string }[] = map.getStyle()?.layers ?? [];
  for (const l of layers) {
    const { id, type } = l;
    try {
      if (id === "background") paint(map, id, "background-color", c.background);
      else if (id === "water") paint(map, id, "fill-color", c.water);
      else if (HIDE.test(id)) map.setLayoutProperty(id, "visibility", "none");
      else if (ROAD.test(id) && type === "line") {
        map.setLayerZoomRange(id, 7, 24);
        paint(map, id, "line-opacity", 0.45);
        paint(map, id, "line-color", c.quiet);
      } else if (BORDER_COUNTRY.test(id)) {
        paint(map, id, "line-color", c.border);
        paint(map, id, "line-opacity", 1);
        paint(map, id, "line-width", ["interpolate", ["linear"], ["zoom"], 2, 0.8, 6, 1.4, 12, 2.4]);
      } else if (BORDER_REGION.test(id)) {
        paint(map, id, "line-color", c.border);
        paint(map, id, "line-opacity", 0.5);
      } else if (SMALL_PLACE.test(id)) map.setLayerZoomRange(id, 8, 24);
      else if (type === "symbol") {
        paint(map, id, "text-color", SOFT_LABEL.test(id) ? c.border : c.label);
        paint(map, id, "text-halo-color", c.halo);
        paint(map, id, "text-halo-width", 1.4);
      }
    } catch {
      /* one odd layer must not stop the rest */
    }
  }
}

/** Free keyless elevation tiles (AWS Terrain Tiles, Terrarium encoding) for the 3D tilt. Optional: failure only means a flat tilt. */
export const TERRAIN_SOURCE = {
  type: "raster-dem",
  tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
  encoding: "terrarium",
  tileSize: 256,
  maxzoom: 14,
  attribution: "Terrain: Mapzen, AWS Terrain Tiles",
};
