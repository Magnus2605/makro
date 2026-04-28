/**
 * Eneste “entry”-script for Node: starter Python-backenden.
 * Selve API’et og statiske filer håndteres udelukkende i server.py.
 *
 * Kør: npm start  |  node server.js
 * Eller direkte:  python server.py
 */
const { spawn } = require("child_process");
const path = require("path");

const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const script = path.join(__dirname, "server.py");

const child = spawn(python, [script], {
  cwd: __dirname,
  stdio: "inherit",
  env: process.env
});

child.on("error", (err) => {
  console.error(`[makrotool] Kunne ikke starte ${python}:`, err.message);
  console.error("[makrotool] Sæt PYTHON til din Python-sti, eller kør: python server.py");
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code === null || code === undefined ? 1 : code);
});
