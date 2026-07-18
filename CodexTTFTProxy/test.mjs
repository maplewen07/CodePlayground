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
  const output = await new Promise((resolve, reject) => {
    const req = http.request(`http://127.0.0.1:${proxyPort}/responses`, { method: "POST", headers: { authorization: "Bearer client-key", "content-type": "application/json", "x-codex-turn-metadata": JSON.stringify({ thread_id: "test-thread" }) } }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => text += chunk);
      res.on("end", () => resolve(text));
    });
    req.on("error", reject);
    req.end("{}");
  });

  assert.equal(attempts, 2);
  assert.deepEqual(receivedAuthorization, ["Bearer configured-key-1", "Bearer configured-key-1"]);
  assert.match(output, /response\.output_text\.delta/);
  assert.match(proxyLog, /session="Current UI title" thread=test-thr/);
  assert.ok(Date.now() - startedAt >= 900);

  config.apiKey = "configured-key-2";
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
  assert.doesNotMatch(proxyLog, /configured-key-[12]/);
  console.log("TTFT retry and API key hot-reload integration tests passed");
} finally {
  const exited = new Promise((resolve) => proxy.once("exit", resolve));
  proxy.kill();
  await exited;
  await new Promise((resolve) => upstream.close(resolve));
  fs.rmSync(stateDbPath, { force: true });
  fs.rmSync(sessionIndexPath, { force: true });
  fs.rmSync(proxyConfigPath, { force: true });
}
