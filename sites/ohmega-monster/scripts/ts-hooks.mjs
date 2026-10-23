// Node module-loader hooks that let a script run the site's TypeScript lib files directly: "@/..." resolves to this folder, extensionless relative imports find
// .ts / .tsx, and every .ts file is transpiled (types erased, NOT type-checked: `tsc` is still the type check) with the TypeScript package.
//
// Used by scripts/view-check.mjs. TypeScript comes from `typescript` (a devDependency: needs `npm install` once) or from the file named in TYPESCRIPT_PATH.
// `react` and `gray-matter` are stubbed only when they are not installed, because the lib files this script loads need nothing from them but import them.

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const ts = require(process.env.TYPESCRIPT_PATH || "typescript");
const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const STUBS = {
  react: "data:text/javascript,export const cache=(f)=>f;export default {};",
  "gray-matter": "data:text/javascript,export default (s)=>({data:{},content:String(s)});",
};

function tryFile(abs) {
  for (const c of [abs, `${abs}.ts`, `${abs}.tsx`, `${abs}/index.ts`]) {
    if (fs.existsSync(c) && fs.statSync(c).isFile()) return { url: pathToFileURL(c).href, shortCircuit: true };
  }
  return null;
}

export async function resolve(specifier, context, next) {
  if (specifier.startsWith("@/")) {
    const r = tryFile(path.join(SITE, specifier.slice(2)));
    if (r) return r;
  }
  if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL?.startsWith("file:")) {
    const r = tryFile(path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier));
    if (r) return r;
  }
  try {
    return await next(specifier, context);
  } catch (e) {
    if (STUBS[specifier] && e?.code === "ERR_MODULE_NOT_FOUND") return { url: STUBS[specifier], shortCircuit: true };
    throw e;
  }
}

export async function load(url, context, next) {
  if (url.startsWith("file:") && (url.endsWith(".ts") || url.endsWith(".tsx"))) {
    const src = fs.readFileSync(fileURLToPath(url), "utf8");
    const out = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX }, fileName: url });
    return { format: "module", source: out.outputText, shortCircuit: true };
  }
  return next(url, context);
}
