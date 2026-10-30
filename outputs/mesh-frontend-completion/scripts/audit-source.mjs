#!/usr/bin/env node
// Dependency-free integrity audit; complements (does not replace) tsc, build, or browser tests.
import fs from 'node:fs';
import path from 'node:path';
const root = process.cwd();
const extensions = ['', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.json', '/index.ts', '/index.tsx', '/index.js', '/index.jsx'];
const ignored = new Set(['node_modules', '.next', '.git', 'dist', 'coverage']);
const files = [];
function walk(dir) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ignored.has(ent.name)) continue;
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(full);
    else if (/\.(?:tsx?|jsx?|mjs)$/.test(ent.name)) files.push(full);
  }
}
for (const dir of ['app', 'components', 'lib', 'store', 'stores', 'hooks', 'scripts']) {
  if (fs.existsSync(dir)) walk(dir);
}
const failures = [];
let checked = 0;
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8');
  const re = /(?:\bfrom\s*|\bimport\s*\(|\bimport\s*|\brequire\s*\()\s*['"]([^'"]+)['"]/g;
  for (const match of source.matchAll(re)) {
    const spec = match[1];
    if (!spec.startsWith('@/') && !spec.startsWith('./') && !spec.startsWith('../')) continue;
    checked++;
    const target = spec.startsWith('@/') ? path.join(root, spec.slice(2)) : path.resolve(path.dirname(file), spec);
    if (!extensions.some(ext => fs.existsSync(target + ext) && fs.statSync(target + ext).isFile())) {
      failures.push(`${path.relative(root, file)}: unresolved ${spec}`);
    }
  }
}
const routes = files.filter(f => path.resolve(f).startsWith(path.join(root, "app") + path.sep) && /(?:page|layout|loading|error|not-found)\.tsx?$/.test(path.basename(f))).length;
console.log(`Source integrity: ${files.length} source files, ${routes} route files, ${checked} local imports checked.`);
if (failures.length) {
  console.error(`${failures.length} unresolved local import(s):\n${failures.join('\n')}`);
  process.exitCode = 1;
} else {
  console.log('PASS: all statically referenced local modules resolve.');
}
