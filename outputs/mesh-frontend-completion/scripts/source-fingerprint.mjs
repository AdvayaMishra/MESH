import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
export function fingerprint() {
  const hash = createHash('sha256');
  function walk(dir, assets = false) {
    for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) { if (!entry.name.startsWith('.')) walk(file, assets); }
      else if (assets || /\.(ts|tsx|js|mjs|css)$/.test(entry.name)) { hash.update(file.split(path.sep).join('/')); hash.update(readFileSync(file)); }
    }
  }
  for (const dir of ['app', 'components', 'lib', 'stores', 'hooks', 'e2e', 'tests', 'scripts']) walk(dir);
  walk('public', true);
  for (const file of ['package.json', 'package-lock.json', 'next.config.ts', 'tsconfig.json', 'playwright.config.ts', 'eslint.config.mjs']) { hash.update(file); hash.update(readFileSync(file)); }
  return hash.digest('hex');
}
if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) console.log(fingerprint());
