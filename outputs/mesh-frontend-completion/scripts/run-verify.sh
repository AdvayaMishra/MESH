#!/usr/bin/env bash
# Compile the pure-logic + store layer with tsc and run a verify script under plain node (no tsx/network needed).
# Usage: scripts/run-verify.sh verify-hr   |   scripts/run-verify.sh verify-tenants
set -e
cd "$(dirname "$0")/.."
# Node 24 can execute these TypeScript logic suites without installed dependencies.
# This route deliberately uses minimal test shims, not the production React/Zustand packages.
if ! command -v tsc >/dev/null 2>&1 && node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 24 ? 0 : 1)'; then
  exec node --no-warnings --experimental-loader ./scripts/node-test-loader.mjs "scripts/$1.ts"
fi
if ! command -v tsc >/dev/null 2>&1; then
  echo "TypeScript compiler not found. Install dependencies with npm ci first." >&2
  exit 1
fi
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
cat > "$OUT/tsconfig.json" <<JSON
{"compilerOptions":{"target":"ES2022","module":"commonjs","moduleResolution":"node","esModuleInterop":true,"skipLibCheck":true,"strict":true,"jsx":"preserve","rootDir":"$PWD","outDir":"$OUT/o","baseUrl":"$PWD","paths":{"@/*":["./*"]},"noEmitOnError":false,"ignoreDeprecations":"6.0","types":[]},"files":["$PWD/scripts/$1.ts"]}
JSON
tsc -p "$OUT/tsconfig.json" >/dev/null 2>&1 || true  # emit regardless; real type checking is `npm run typecheck`
cat > "$OUT/hook.js" <<JS
const M=require("module"),p=require("path");const o=M._resolveFilename;
M._resolveFilename=function(r,...a){if(r.startsWith("@/"))r=p.join("$OUT/o",r.slice(2));if(r==="zustand"||r==="zustand/middleware")try{o.call(this,r,...a)}catch(e){r="$PWD/scripts/shims/zustand.js"}else if(r==="react")try{o.call(this,r,...a)}catch(e){r="$PWD/scripts/shims/react.js"}return o.call(this,r,...a)};
JS
NODE_PATH="$PWD/node_modules" node -r "$OUT/hook.js" "$OUT/o/scripts/$1.js"
