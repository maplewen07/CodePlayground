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

const stateDb = new DatabaseSync(stateDbPath);
stateDb.exec("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT NOT NULL)");
stateDb.prepare("INSERT INTO threads (id, title) VALUES (?, ?)").run("test-thread", "Test session");
stateDb.close();
fs.writeFileSync(sessionIndexPath, `${JSON.stringify({ id: "test-thread", thread_name: "Current UI title" })}\n`);
fs.writeFileSync(proxyConfigPath, JSON.stringify({ upstream: `http://127.0.0.1:${upstreamPort}/`, ttftTimeoutSeconds: 1, ttftRetries: 1, heartbeatSeconds: 1, interval: 60 }));

const upstream = http.createServer((_req, res) => {
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
  env: { ...process.env, PORT: String(proxyPort), TTFT_CONFIG_PATH: proxyConfigPath, CODEX_STATE_DB: stateDbPath, CODEX_SESSION_INDEX: sessionIndexPath },
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
    const req = http.request(`http://127.0.0.1:${proxyPort}/responses`, { method: "POST", headers: { "content-type": "application/json", "x-codex-turn-metadata": JSON.stringify({ thread_id: "test-thread" }) } }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => text += chunk);
      res.on("end", () => resolve(text));
    });
    req.on("error", reject);
    req.end("{}");
  });

  assert.equal(attempts, 2);
  assert.match(output, /response\.output_text\.delta/);
  assert.match(proxyLog, /session="Current UI title" thread=test-thr/);
  assert.ok(Date.now() - startedAt >= 900);
  console.log("TTFT retry integration test passed");
} finally {
  const exited = new Promise((resolve) => proxy.once("exit", resolve));
  proxy.kill();
  await exited;
  await new Promise((resolve) => upstream.close(resolve));
  fs.rmSync(stateDbPath, { force: true });
  fs.rmSync(sessionIndexPath, { force: true });
  fs.rmSync(proxyConfigPath, { force: true });
}
