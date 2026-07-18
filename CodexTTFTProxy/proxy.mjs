import http from "node:http";
import https from "node:https";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { StringDecoder } from "node:string_decoder";

const HOST = "127.0.0.1";
const PORT = Number(process.env.PORT || 43181);
const CONFIG_PATH = process.env.TTFT_CONFIG_PATH || path.join(os.homedir(), ".codex", "local-ttft-proxy", "proxy-config.json");
const DEFAULT_UPSTREAM = "https://api.020s.com/";
let UPSTREAM = new URL(process.env.UPSTREAM_BASE_URL || DEFAULT_UPSTREAM);
let UPSTREAM_API_KEY = process.env.UPSTREAM_API_KEY || null;
let TTFT_TIMEOUT_MS = Number(process.env.TTFT_TIMEOUT_MS || 120_000);
let TTFT_RETRIES = Number(process.env.TTFT_RETRIES || 4);
let HEARTBEAT_MS = Number(process.env.HEARTBEAT_MS || 15_000);
let configReloadMs = 60_000;
let configTimer = null;

function readConfig() {
  try {
    const raw = fs.readFileSync(CONFIG_PATH, "utf8");
    const cfg = JSON.parse(raw);
    if (!process.env.UPSTREAM_BASE_URL && cfg.upstream && typeof cfg.upstream === "string") {
      const next = new URL(cfg.upstream);
      if (next.origin !== UPSTREAM.origin) {
        log(`config upstream changed: ${UPSTREAM.origin} → ${next.origin}`);
        UPSTREAM = next;
      }
    }
    if (!process.env.UPSTREAM_API_KEY && Object.hasOwn(cfg, "apiKey") && typeof cfg.apiKey === "string") {
      const next = cfg.apiKey.trim() || null;
      if (next !== UPSTREAM_API_KEY) log(`config API key ${next ? "changed" : "override disabled"}`);
      UPSTREAM_API_KEY = next;
    }
    if (!process.env.TTFT_TIMEOUT_MS && typeof cfg.ttftTimeoutSeconds === "number" && cfg.ttftTimeoutSeconds >= 1 && cfg.ttftTimeoutSeconds <= 3600) {
      const ms = cfg.ttftTimeoutSeconds * 1000;
      if (ms !== TTFT_TIMEOUT_MS) log(`config TTFT changed: ${TTFT_TIMEOUT_MS / 1000}s → ${cfg.ttftTimeoutSeconds}s`);
      TTFT_TIMEOUT_MS = ms;
    }
    if (!process.env.TTFT_RETRIES && Number.isInteger(cfg.ttftRetries) && cfg.ttftRetries >= 0 && cfg.ttftRetries <= 10) {
      if (cfg.ttftRetries !== TTFT_RETRIES) log(`config retries changed: ${TTFT_RETRIES} → ${cfg.ttftRetries}`);
      TTFT_RETRIES = cfg.ttftRetries;
    }
    if (!process.env.HEARTBEAT_MS && typeof cfg.heartbeatSeconds === "number" && cfg.heartbeatSeconds >= 1 && cfg.heartbeatSeconds <= 300) {
      const ms = cfg.heartbeatSeconds * 1000;
      if (ms !== HEARTBEAT_MS) log(`config heartbeat changed: ${HEARTBEAT_MS / 1000}s → ${cfg.heartbeatSeconds}s`);
      HEARTBEAT_MS = ms;
    }
    if (typeof cfg.interval === "number" && cfg.interval >= 5 && cfg.interval <= 3600) {
      const ms = cfg.interval * 1000;
      if (ms !== configReloadMs) {
        log(`config reload interval changed: ${(configReloadMs / 1000).toFixed(0)}s → ${cfg.interval}s`);
        configReloadMs = ms;
      }
    }
  } catch (error) {
    if (error.code !== "ENOENT") {
      log(`config read warning: ${error.message}`);
    }
  }
  // Re-schedule with current interval so dynamic interval changes take effect.
  configTimer = setTimeout(readConfig, configReloadMs).unref();
}

const MAX_BODY_BYTES = Number(process.env.MAX_BODY_BYTES || 128 * 1024 * 1024);
const MAX_BUFFER_BYTES = Number(process.env.MAX_BUFFER_BYTES || 8 * 1024 * 1024);
const STATE_DB = process.env.CODEX_STATE_DB || path.join(os.homedir(), ".codex", "state_5.sqlite");
const SESSION_INDEX = process.env.CODEX_SESSION_INDEX || path.join(os.homedir(), ".codex", "session_index.jsonl");

if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) throw new Error("Invalid PORT");
if (!Number.isFinite(TTFT_TIMEOUT_MS) || TTFT_TIMEOUT_MS < 1_000) throw new Error("Invalid TTFT_TIMEOUT_MS");
if (!Number.isInteger(TTFT_RETRIES) || TTFT_RETRIES < 0 || TTFT_RETRIES > 10) throw new Error("Invalid TTFT_RETRIES");

const agents = {
  "http:": new http.Agent({ keepAlive: true }),
  "https:": new https.Agent({ keepAlive: true }),
};
let requestSequence = 0;
let findThread = null;
try {
  const stateDb = new DatabaseSync(STATE_DB, { readOnly: true });
  findThread = stateDb.prepare("SELECT title FROM threads WHERE id = ?");
} catch (error) {
  console.error(`Session title lookup disabled: ${error.message}`);
}
const logTime = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function log(message) {
  console.log(`${logTime.format(new Date())} +08:00 ${message}`);
}

// Load after the logger is initialized; later reads hot-reload new requests.
readConfig();

function currentUiTitle(threadId) {
  try {
    let title = null;
    for (const line of fs.readFileSync(SESSION_INDEX, "utf8").split(/\r?\n/)) {
      if (!line) continue;
      const entry = JSON.parse(line);
      if (entry.id === threadId && entry.thread_name) title = entry.thread_name;
    }
    return title;
  } catch {
    return null;
  }
}

function requestLabel(req, id) {
  const raw = Array.isArray(req.headers["x-codex-turn-metadata"])
    ? req.headers["x-codex-turn-metadata"][0]
    : req.headers["x-codex-turn-metadata"];
  let metadata = {};
  try {
    metadata = raw ? JSON.parse(raw) : {};
  } catch {
    // Fall back to an unlabeled request if Codex changes this metadata format.
  }
  const threadId = metadata.thread_id || metadata.session_id || "unknown";
  let title = currentUiTitle(threadId) || "unknown";
  try {
    if (title === "unknown") title = findThread?.get(threadId)?.title || title;
  } catch {
    // A concurrent Codex database write must not block proxying.
  }
  title = String(title).replace(/\s+/g, " ").trim();
  if (title.length > 80) title = `${title.slice(0, 79)}...`;
  title = title.replaceAll('"', "'");
  return `[${id}] session="${title}" thread=${threadId.slice(0, 8)}`;
}

function cleanRequestHeaders(headers, url, bodyLength) {
  const result = { ...headers };
  delete result.connection;
  delete result["proxy-connection"];
  delete result["transfer-encoding"];
  result.host = url.host;
  result["accept-encoding"] = "identity";
  result["content-length"] = String(bodyLength);
  if (UPSTREAM_API_KEY) {
    const hasXApiKey = Object.hasOwn(result, "x-api-key");
    if (Object.hasOwn(result, "authorization") || !hasXApiKey) {
      result.authorization = `Bearer ${UPSTREAM_API_KEY}`;
    }
    if (hasXApiKey) result["x-api-key"] = UPSTREAM_API_KEY;
  }
  return result;
}

function cleanResponseHeaders(headers) {
  const result = { ...headers };
  delete result.connection;
  delete result["transfer-encoding"];
  return result;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(Object.assign(new Error("Request body too large"), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function parseSseEvents() {
  const decoder = new StringDecoder("utf8");
  let pending = "";
  return (chunk) => {
    pending += decoder.write(chunk);
    const events = [];
    while (true) {
      const match = /\r?\n\r?\n/.exec(pending);
      if (!match) break;
      const block = pending.slice(0, match.index);
      pending = pending.slice(match.index + match[0].length);
      const data = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data || data === "[DONE]") continue;
      try {
        events.push(JSON.parse(data));
      } catch {
        // Ignore non-JSON SSE data; it cannot prove model output started.
      }
    }
    return events;
  };
}

function isSubstantive(event) {
  const type = event?.type || "";
  if ([
    "response.output_text.delta",
    "response.reasoning_summary_text.delta",
    "response.function_call_arguments.delta",
    "response.custom_tool_call_input.delta",
    "response.completed",
    "response.failed",
    "response.incomplete",
  ].includes(type)) return true;
  if (type.endsWith("_call_arguments.delta") || type.includes("tool_call") && type.endsWith(".delta")) return true;
  if (type === "response.output_item.added") {
    return ![undefined, "message", "reasoning"].includes(event.item?.type);
  }
  return false;
}

function requestUpstream(req, body, onResponse, onError) {
  const url = new URL(req.url, UPSTREAM);
  const client = url.protocol === "https:" ? https : http;
  const upstreamReq = client.request(url, {
    method: req.method,
    headers: cleanRequestHeaders(req.headers, url, body.length),
    agent: agents[url.protocol],
  }, onResponse);
  upstreamReq.on("error", onError);
  upstreamReq.end(body);
  return upstreamReq;
}

function forwardNormally(req, res, body) {
  requestUpstream(req, body, (upstreamRes) => {
    res.writeHead(upstreamRes.statusCode || 502, cleanResponseHeaders(upstreamRes.headers));
    upstreamRes.pipe(res);
  }, (error) => {
    if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    res.end(`Upstream error: ${error.message}`);
  });
}

function forwardWithTtft(req, res, body) {
  const id = ++requestSequence;
  const label = requestLabel(req, id);
  let closed = false;
  let activeRequest = null;
  let activeResponse = null;
  let heartbeat = null;
  let attempt = 0;

  const ensureSseResponse = () => {
    if (res.headersSent) return;
    res.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache",
      connection: "keep-alive",
      "x-accel-buffering": "no",
      "x-ttft-proxy": "active",
    });
    res.write(": ttft-proxy connected\n\n");
    heartbeat = setInterval(() => {
      if (!closed) res.write(": ttft-proxy waiting\n\n");
    }, HEARTBEAT_MS);
  };

  const finish = () => {
    if (closed) return;
    closed = true;
    if (heartbeat) clearInterval(heartbeat);
    activeRequest?.destroy();
    activeResponse?.destroy();
  };

  res.on("close", finish);

  const startAttempt = () => {
    if (closed) return;
    attempt += 1;
    const startedAt = Date.now();
    const enforceTtft = attempt <= TTFT_RETRIES;
    const parseEvents = parseSseEvents();
    const buffered = [];
    let bufferedBytes = 0;
    let forwarding = false;
    let settled = false;
    let timer = null;

    const retryOrClose = (reason) => {
      if (closed || settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      activeRequest?.destroy();
      activeResponse?.destroy();
      if (attempt <= TTFT_RETRIES) {
        ensureSseResponse();
        res.write(`: ttft-proxy retry ${attempt + 1}\n\n`);
        log(`${label} ${reason}; retrying attempt ${attempt + 1}/${TTFT_RETRIES + 1}`);
        setTimeout(startAttempt, Math.min(1_000, attempt * 250));
      } else {
        log(`${label} ${reason}; final attempt failed`);
        if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
        res.end();
      }
    };

    if (enforceTtft) {
      timer = setTimeout(() => retryOrClose(`TTFT exceeded ${TTFT_TIMEOUT_MS}ms on attempt ${attempt}`), TTFT_TIMEOUT_MS);
    }

    log(`${label} attempt ${attempt}/${TTFT_RETRIES + 1} started${enforceTtft ? "" : " without another TTFT retry"}`);
    activeRequest = requestUpstream(req, body, (upstreamRes) => {
      if (closed || settled) return upstreamRes.destroy();
      activeResponse = upstreamRes;
      const contentType = String(upstreamRes.headers["content-type"] || "");
      if (upstreamRes.statusCode !== 200 || !contentType.includes("text/event-stream")) {
        settled = true;
        if (timer) clearTimeout(timer);
        if (res.headersSent) {
          upstreamRes.resume();
          res.end();
          return;
        }
        res.writeHead(upstreamRes.statusCode || 502, cleanResponseHeaders(upstreamRes.headers));
        upstreamRes.pipe(res);
        return;
      }

      ensureSseResponse();
      upstreamRes.on("data", (chunk) => {
        if (closed || settled) return;
        if (forwarding) {
          res.write(chunk);
          return;
        }
        buffered.push(chunk);
        bufferedBytes += chunk.length;
        const started = parseEvents(chunk).some(isSubstantive) || bufferedBytes >= MAX_BUFFER_BYTES;
        if (!started) return;
        forwarding = true;
        if (timer) clearTimeout(timer);
        if (heartbeat) {
          clearInterval(heartbeat);
          heartbeat = null;
        }
        log(`${label} substantive output after ${Date.now() - startedAt}ms on attempt ${attempt}`);
        for (const bufferedChunk of buffered) res.write(bufferedChunk);
        buffered.length = 0;
      });
      upstreamRes.on("end", () => {
        if (closed || settled) return;
        if (!forwarding && attempt <= TTFT_RETRIES) return retryOrClose(`upstream ended before output on attempt ${attempt}`);
        settled = true;
        if (timer) clearTimeout(timer);
        if (!forwarding) for (const bufferedChunk of buffered) res.write(bufferedChunk);
        res.end();
      });
      upstreamRes.on("error", (error) => retryOrClose(`upstream stream error: ${error.message}`));
    }, (error) => retryOrClose(`upstream request error: ${error.message}`));
  };

  startAttempt();
}

const server = http.createServer(async (req, res) => {
  if (req.url === "/__ttft_proxy/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ ok: true, upstream: UPSTREAM.origin, configReloadS: Math.round(configReloadMs / 1000), ttftTimeoutMs: TTFT_TIMEOUT_MS, ttftRetries: TTFT_RETRIES }));
    return;
  }
  try {
    const body = await readBody(req);
    if (req.method === "POST" && /\/responses\/?(?:\?.*)?$/.test(req.url || "")) {
      forwardWithTtft(req, res, body);
    } else {
      forwardNormally(req, res, body);
    }
  } catch (error) {
    if (!res.headersSent) res.writeHead(error.statusCode || 500, { "content-type": "text/plain; charset=utf-8" });
    res.end(error.message);
  }
});

server.on("clientError", (_error, socket) => socket.end("HTTP/1.1 400 Bad Request\r\n\r\n"));
server.listen(PORT, HOST, () => log(`listening on http://${HOST}:${PORT}, upstream=${UPSTREAM.origin}, ttft=${TTFT_TIMEOUT_MS}ms, retries=${TTFT_RETRIES}`));
