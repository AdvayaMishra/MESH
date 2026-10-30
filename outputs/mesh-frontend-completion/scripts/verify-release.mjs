import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fingerprint } from './source-fingerprint.mjs';
mkdirSync('verification', { recursive: true });
const report = { startedAt: new Date().toISOString(), sourceFingerprint: fingerprint(), runtime: process.version, gates: [], completedAt: null, passed: false };
const gates = [
 ['unit',['--test','tests/*.test.mjs']],
 ['logic',['scripts/run-logic.mjs']],
 ['source',['scripts/audit-source.mjs']],
 ['types',['node_modules/typescript/bin/tsc','--noEmit']],
 ['lint',['node_modules/eslint/bin/eslint.js','.']],
 ['build',['node_modules/next/dist/bin/next','build']],
 ['browser',['node_modules/@playwright/test/cli.js','test']],
];
for(const [name,args] of gates) {
 console.log(`Running ${name}`);
 const started=Date.now();
 const result=spawnSync(process.execPath,args,{encoding:'utf8',maxBuffer:20*1024*1024,env:{...process.env,E2E_PORT:process.env.E2E_PORT||'3124'}});
 writeFileSync(`verification/${name}.log`,(result.stdout||'')+(result.stderr||'')+(result.error?String(result.error):''));
 report.gates.push({name,exitCode:result.status,seconds:Math.round((Date.now()-started)/1000),passed:result.status===0});
 writeFileSync('verification/results.json',JSON.stringify(report,null,2));
 console.log(`${name}: ${result.status===0?'PASS':'FAIL'}`);
 if(result.status!==0) { console.log((result.stdout||'').slice(-3000)+(result.stderr||'').slice(-3000)); break; }
}
report.completedAt=new Date().toISOString();report.sourceFingerprintAtEnd=fingerprint();report.passed=report.sourceFingerprint===report.sourceFingerprintAtEnd&&report.gates.length===gates.length&&report.gates.every(g=>g.passed);
writeFileSync('verification/results.json',JSON.stringify(report,null,2));
process.exitCode=report.passed?0:1;
