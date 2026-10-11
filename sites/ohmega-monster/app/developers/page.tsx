import type { Metadata } from "next";

import { TOOLS } from "@/lib/api/mcp-tools";
import { ROUTES } from "@/lib/api/router";
import { SITE_URL } from "@/lib/site";

import "./developers.css";

export const metadata: Metadata = {
  title: "Developers and agents",
  description: "A read-only JSON API and a remote MCP server over Ohmega's reports, Pulses, statements and measured series.",
  alternates: { canonical: "/developers", types: { "application/json": "/api/v1/openapi.json" } },
};

export const dynamic = "force-static";

const API = `${SITE_URL}/api/v1`;
const MCP = `${SITE_URL}/api/mcp`;

const RPC = `curl -s ${MCP} \\
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_daily","arguments":{}}}'`;

export default function DevelopersPage() {
  return (
    <div className="intel-page dev-page">
      <h1>Developers and agents</h1>
      <p className="dev-lede">
        Everything the site shows is also data. A read-only JSON API, a remote MCP server and static feeds serve the same documents the pages
        read, so they never disagree. Public, no key, CORS open. Please cache: responses are good for about five minutes.
      </p>

      <h2 id="start">Start here</h2>
      <pre>{`curl ${API}/index
curl ${API}/daily/geopolitics/latest
curl "${API}/pulses?band=severe"
curl "${API}/statements?actor=IR&since=2026-10-01"
curl "${API}/search?q=hormuz"`}</pre>
      <p>
        Every response is <code>{"{data, meta}"}</code>. <code>meta.as_of</code> is how fresh the data is, <code>meta.cite_as</code> the canonical
        page to cite, <code>meta.source</code> the document schema, <code>meta.license</code> the terms. Lists take <code>limit</code> (max 200)
        and <code>cursor</code>; <code>meta.next</code> is the next page&apos;s URL. Errors are <code>{"{error:{code,message}}"}</code> with a 4xx status.
      </p>
      <p>
        Spec: <a href={`${API}/openapi.json`}>OpenAPI 3.1</a>. Machine guides: <a href="/llms.txt">llms.txt</a> and <a href="/llms-full.txt">llms-full.txt</a>.
        Poll <code>/api/v1/changes</code> (or <a href="/data/changes.json">/data/changes.json</a>) to see what moved without re-reading everything.
      </p>

      <h2 id="endpoints">Endpoints</h2>
      <table>
        <thead>
          <tr><th>GET</th><th>What it returns</th></tr>
        </thead>
        <tbody>
          {ROUTES.map((r) => (
            <tr key={r.path}>
              <td><code>/api/v1{r.path}</code></td>
              <td>
                {r.summary}
                {r.query && r.query.length > 0 ? (
                  <span className="dev-params"> Params: {r.query.map((q) => q.name).join(", ")}{r.paged ? ", limit, cursor" : ""}.</span>
                ) : r.paged ? (
                  <span className="dev-params"> Params: limit, cursor.</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 id="read">How to read it</h2>
      <ul>
        <li><strong>verification</strong>: <code>researched</code> means our research established it; <code>reported</code> means another outlet reported it, a lead and not a finding.</li>
        <li><strong>Pulses</strong> are 0-100 readings of one question (0 the calm end, 100 the extreme end). Our reading as of <code>last_assessed</code>, still calibrating, not a measurement.</li>
        <li><strong>Statements</strong> prove something was said, not that it is true. <code>quote</code> is exact words; otherwise a paraphrase.</li>
        <li><strong>Live events</strong> come from public feeds and are relayed with their source URL, not verified by us.</li>
        <li><strong>Article claims</strong> carry a grade: confirmed, likely, contested, unconfirmed or speculative (a lead), opinion (attributed).</li>
      </ul>

      <h2 id="mcp">MCP server</h2>
      <p>
        A remote <a href="https://modelcontextprotocol.io">Model Context Protocol</a> server at <code>{MCP}</code> (Streamable HTTP, stateless,
        JSON replies, no sessions). Nine read-only tools; each result is compact JSON with <code>as_of</code>, <code>cite_as</code> and the license.
      </p>
      <h3>Add it to a client</h3>
      <ul>
        <li><strong>Claude Code</strong>: <code>claude mcp add --transport http ohmega {MCP}</code></li>
        <li><strong>Claude (web, desktop)</strong>: Settings, Connectors, Add custom connector, paste <code>{MCP}</code>.</li>
        <li><strong>Other clients with Streamable HTTP</strong> (Cursor, VS Code and others): add a server of type <code>http</code> with that URL.</li>
        <li><strong>Stdio-only clients</strong>: bridge it with <code>npx mcp-remote {MCP}</code>.</li>
      </ul>
      <pre>{`{ "mcpServers": { "ohmega": { "type": "http", "url": "${MCP}" } } }`}</pre>
      <p>Try it without a client:</p>
      <pre>{RPC}</pre>
      <h3>Tools</h3>
      <table>
        <thead>
          <tr><th>Tool</th><th>What it does</th></tr>
        </thead>
        <tbody>
          {TOOLS.map((t) => (
            <tr key={t.name}>
              <td><code>{t.name}</code></td>
              <td>{t.description}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 id="cite">Citing</h2>
      <p>
        Give <code>cite_as</code> and the <code>as_of</code> date. Article claim: article URL and claim id. Pulse: id and reading date. Forecast: its{" "}
        <code>fc_</code> id.
      </p>

      <h2 id="terms">Terms</h2>
      <p>
        Our claims, summaries, grades, Pulses and forecasts may be quoted with a link. Source texts belong to their publishers: follow the source URLs,
        we do not republish them. No warranty. Today the API is open with no key; heavy use may be rate limited, and a keyed tier may follow.
      </p>
    </div>
  );
}
