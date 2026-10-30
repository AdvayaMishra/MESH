import { existsSync, statSync } from 'node:fs';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { resolve as pathResolve } from 'node:path';
const root = process.cwd();
export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith('@/') || specifier.startsWith('.') || specifier.startsWith('/')) {
    const base = specifier.startsWith('@/') ? pathResolve(root, specifier.slice(2)) : specifier.startsWith('/') ? specifier : pathResolve(context.parentURL ? fileURLToPath(new URL('.', context.parentURL)) : root, specifier);
    for (const candidate of [base, base + '.ts', base + '.tsx', base + '.js', base + '/index.ts']) {
      if (existsSync(candidate) && statSync(candidate).isFile()) return { url: pathToFileURL(candidate).href, shortCircuit: true };
    }
  }
  return nextResolve(specifier, context);
}