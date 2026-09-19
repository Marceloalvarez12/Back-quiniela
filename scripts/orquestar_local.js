#!/usr/bin/env node
/**
 * Orquestador local: arranca BACKEND (uvicorn) + FRONTEND (pnpm dev) y termina
 * ambos al recibir Ctrl+C. Pensado para Marcelo: un solo comando y todo arriba.
 *
 *   node scripts/orquestar_local.js
 *
 * Variables de entorno reconocidas:
 *   BACKEND_DIR  (default = ../Back-quiniela relativo al frontend)
 *   FRONTEND_DIR (default = process.cwd() del repo frontend)
 *   API_PORT     (default 8000)
 *   WEB_PORT     (default 3000)
 */

const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const ROOT = path.resolve(__dirname, '..');
const BACKEND_DIR = process.env.BACKEND_DIR || (() => {
  const candidate = path.join(ROOT, '..', 'Back-quiniela');
  return fs.existsSync(path.join(candidate, 'app.py')) ? candidate : ROOT;
})();

const childs = [];
const colorLog = (tag, msg) => {
  const C = { back: '\x1b[36m', front: '\x1b[35m', kill: '\x1b[33m' };
  const prefix = C[tag] || '';
  const reset = '\x1b[0m';
  process.stdout.write(`${prefix}[${tag}]${reset} ${msg}\n`);
};

function spawnChild(tag, cmd, args, cwd) {
  const child = spawn(cmd, args, {
    cwd, shell: true, stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    env: { ...process.env, FORCE_COLOR: '1' },
  });
  child.stdout.on('data', (b) => colorLog(tag, b.toString().replace(/\n$/, '')));
  child.stderr.on('data', (b) => colorLog(tag, b.toString().replace(/\n$/, '')));
  child.on('exit', (code, sig) => {
    colorLog('kill', `${tag} salió code=${code} sig=${sig}. Bajando sibling.`);
    childs.forEach((c) => { if (c !== child) try { c.kill('SIGTERM'); } catch {} });
    process.exit(code ?? 0);
  });
  childs.push(child);
  return child;
}

// Backend
const venvPy = process.platform === 'win32'
  ? path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')
  : path.join(BACKEND_DIR, '.venv', 'bin', 'python');
if (!fs.existsSync(venvPy)) {
  console.error('No encontré el venv del backend en', venvPy);
  console.error('Activá el venv o corré uvicorn manualmente.');
  process.exit(1);
}
spawnChild('back', venvPy, ['-m', 'uvicorn', 'app:app', '--host', '0.0.0.0', '--port', process.env.API_PORT || '8000', '--reload'], BACKEND_DIR);

// Frontend
const frontDir = process.env.FRONTEND_DIR || ROOT;
const pkgPath = path.join(frontDir, 'package.json');
if (fs.existsSync(pkgPath)) {
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
  if (pkg.dependencies?.next || pkg.devDependencies?.next) {
    const pnpmCmd = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm';
    spawnChild('front', pnpmCmd, ['dev'], frontDir);
  } else {
    colorLog('front', 'No detecté Next.js en este dir. Solo levanto el backend.');
  }
} else {
  colorLog('front', 'package.json no encontrado. Solo levanto el backend.');
}

const stopAll = (sig) => {
  colorLog('kill', `Recibí ${sig}. Cerrando procesos…`);
  childs.forEach((c) => { try { c.kill(sig); } catch {} });
  setTimeout(() => process.exit(0), 500);
};
process.on('SIGINT', () => stopAll('SIGINT'));
process.on('SIGTERM', () => stopAll('SIGTERM'));
