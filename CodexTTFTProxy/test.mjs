import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { DatabaseSync } from "node:sqlite";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const upstreamPort = 43281;
const proxyPort = 43282;
const stateDbPath = path.join(os.tmpdir(), `ttft-proxy-test-${process.pid}.sqlite`);
const sessionIndexPath = path.join(os.tmpdir(), `ttft-proxy-test-${process.pid}.jsonl`);
const proxyConfigPath = path.join(os.tmpdir(), `ttft-proxy-test-${process.pid}.json`);
let attempts = 0;
const receivedAuthorization = [];
const scenarioAttempts = new Map();

const stateDb = new DatabaseSync(stateDbPath);
stateDb.exec("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT NOT NULL)");
stateDb.prepare("INSERT INTO threads (id, title) VALUES (?, ?)").run("test-thread", "Test session");
stateDb.close();
fs.writeFileSync(sessionIndexPath, `${JSON.stringify({ id: "test-thread", thread_name: "Current UI title" })}\n`);
const config = { upstream: `http://127.0.0.1:${upstreamPort}/`, apiKey: "configured-key-1", ttftTimeoutSeconds: 1, ttftRetries: 1, heartbeatSeconds: 1, interval: 5 };
fs.writeFileSync(proxyConfigPath, JSON.stringify(config));

const upstream = http.createServer((req, res) => {
  receivedAuthorization.push(req.headers.authorization);
  if (req.url === "/auth-check") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ authorization: req.headers.authorization }));
    return;
  }
  const scenario = new URL(req.url, `http://127.0.0.1:${upstreamPort}`).searchParams.get("scenario");
  if (scenario) {
    const scenarioAttempt = (scenarioAttempts.get(scenario) || 0) + 1;
    scenarioAttempts.set(scenario, scenarioAttempt);
    if (scenario === "http-retry" && scenarioAttempt === 1) {
      res.writeHead(400, { "content-type": "text/html" });
      res.end("<h1>sensitive upstream 400</h1>");
      return;
    }
    if (scenario === "http-exhausted") {
      const statusCode = scenarioAttempt === 1 ? 400 : 503;
      res.writeHead(statusCode, { "content-type": "text/plain", "x-upstream-attempt": String(scenarioAttempt) });
      res.end(`sensitive upstream ${statusCode}`);
      return;
    }
    if (scenario === "non-sse") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end('{"ok":true}');
      return;
    }
    res.writeHead(200, { "content-type": "text/event-stream" });
    res.end('data: {"type":"response.output_text.delta","delta":"recovered"}\n\ndata: {"type":"response.completed"}\n\n');
    return;
  }
  attempts += 1;
  res.writeHead(200, { "content-type": "text/event-stream" });
  res.write('data: {"type":"response.created"}\n\n');
  if (attempts === 1) {
    const heartbeat = setInterval(() => res.write(": upstream heartbeat\n\n"), 40);
    res.on("close", () => clearInterval(heartbeat));
    return;
  }
  setTimeout(() => {
    res.write('data: {"type":"response.output_text.delta","delta":"ok"}\n\n');
    res.end('data: {"type":"response.completed"}\n\n');
  }, 50);
});

await new Promise((resolve) => upstream.listen(upstreamPort, "127.0.0.1", resolve));
const proxy = spawn(process.execPath, [path.join(root, "proxy.mjs")], {
  env: { ...process.env, PORT: String(proxyPort), TTFT_CONFIG_PATH: proxyConfigPath, UPSTREAM_BASE_URL: "", UPSTREAM_API_KEY: "", CODEX_STATE_DB: stateDbPath, CODEX_SESSION_INDEX: sessionIndexPath },
  stdio: ["ignore", "pipe", "ignore"],
});
let proxyLog = "";
proxy.stdout.on("data", (chunk) => proxyLog += chunk);

function requestProxy(urlPath) {
  return new Promise((resolve, reject) => {
    const req = http.request(`http://127.0.0.1:${proxyPort}${urlPath}`, { method: "POST", headers: { authorization: "Bearer client-key", "content-type": "application/json", "x-codex-turn-metadata": JSON.stringify({ thread_id: "test-thread" }) } }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => body += chunk);
      res.on("end", () => resolve({ statusCode: res.statusCode, headers: res.headers, body }));
    });
    req.on("error", reject);
    req.end("{}");
  });
}

try {
  await new Promise((resolve, reject) => {
    let tries = 0;
    const poll = () => http.get(`http://127.0.0.1:${proxyPort}/__ttft_proxy/health`, (res) => {
      res.resume();
      resolve();
    }).on("error", () => ++tries < 30 ? setTimeout(poll, 50) : reject(new Error("proxy did not start")));
    poll();
  });

  const startedAt = Date.now();
  const ttftResponse = await requestProxy("/responses");

  assert.equal(attempts, 2);
  assert.deepEqual(receivedAuthorization, ["Bearer configured-key-1", "Bearer configured-key-1"]);
  assert.match(ttftResponse.body, /response\.output_text\.delta/);
  assert.match(proxyLog, /session="Current UI title" thread=test-thr/);
  assert.ok(Date.now() - startedAt >= 900);

  const recoveredResponse = await requestProxy("/responses?scenario=http-retry");
  assert.equal(scenarioAttempts.get("http-retry"), 2);
  assert.equal(recoveredResponse.statusCode, 200);
  assert.match(recoveredResponse.body, /recovered/);
  assert.match(proxyLog, /upstream returned HTTP 400 on attempt 1; retrying attempt 2\/2/);

  const exhaustedResponse = await requestProxy("/responses?scenario=http-exhausted");
  assert.equal(scenarioAttempts.get("http-exhausted"), 2);
  assert.equal(exhaustedResponse.statusCode, 503);
  assert.equal(exhaustedResponse.headers["x-upstream-attempt"], "2");
  assert.equal(exhaustedResponse.body, "sensitive upstream 503");
  assert.match(proxyLog, /upstream returned HTTP 503 on attempt 2; final response forwarded/);

  const nonSseResponse = await requestProxy("/responses?scenario=non-sse");
  assert.equal(scenarioAttempts.get("non-sse"), 1);
  assert.equal(nonSseResponse.statusCode, 200);
  assert.equal(nonSseResponse.body, '{"ok":true}');
  assert.doesNotMatch(proxyLog, /sensitive upstream/);

  config.apiKey = "configured-key-2";
  config.ttftRetries = 100;
  fs.writeFileSync(proxyConfigPath, JSON.stringify(config));
  const reloadedAuthorization = await new Promise((resolve, reject) => {
    const deadline = Date.now() + 6_000;
    const poll = () => http.get(`http://127.0.0.1:${proxyPort}/auth-check`, { headers: { authorization: "Bearer client-key" } }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => text += chunk);
      res.on("end", () => {
        const authorization = JSON.parse(text).authorization;
        if (authorization === "Bearer configured-key-2") return resolve(authorization);
        if (Date.now() >= deadline) return reject(new Error("API key config did not reload"));
        setTimeout(poll, 100);
      });
    }).on("error", reject);
    poll();
  });
  assert.equal(reloadedAuthorization, "Bearer configured-key-2");
  const reloadedHealth = await new Promise((resolve, reject) => http.get(`http://127.0.0.1:${proxyPort}/__ttft_proxy/health`, (res) => {
    let text = "";
    res.setEncoding("utf8");
    res.on("data", (chunk) => text += chunk);
    res.on("end", () => resolve(JSON.parse(text)));
  }).on("error", reject));
  assert.equal(reloadedHealth.ttftRetries, 100);
  assert.doesNotMatch(proxyLog, /configured-key-[12]/);
  console.log("TTFT, HTTP status retry, and API key hot-reload integration tests passed");
} finally {
  const exited = new Promise((resolve) => proxy.once("exit", resolve));
  proxy.kill();
  await exited;
  await new Promise((resolve) => upstream.close(resolve));
  fs.rmSync(stateDbPath, { force: true });
  fs.rmSync(sessionIndexPath, { force: true });
  fs.rmSync(proxyConfigPath, { force: true });
}
