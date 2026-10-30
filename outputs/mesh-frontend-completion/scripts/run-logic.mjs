import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
let failed = false;
for (const file of readdirSync('scripts').filter((f) => /^verify-.*\.ts$/.test(f)).sort()) {
  const result = spawnSync(process.execPath, ['--no-warnings', '--experimental-loader', './scripts/real-test-loader.mjs', `scripts/${file}`], { stdio: 'inherit' });
  if (result.status !== 0) failed = true;
}
process.exitCode = failed ? 1 : 0;
