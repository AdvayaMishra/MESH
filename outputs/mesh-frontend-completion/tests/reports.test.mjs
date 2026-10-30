import { strict as assert } from 'node:assert';
import { buildDemoReport } from '../lib/export/reports.ts';
const d = {
  monthlyCost: [{month:'Oct',actual:10,forecast:12}],
  employees: [{id:'one',name:'Example',department:'Engineering',status:'Active',verification:'Verified',joinDate:'2026-10-01'}],
  tasks: [], incidents: [{title:'Synthetic incident',severity:'high',status:'Open',detectedAt:'2026-10-15T00:00:00Z',riskBefore:20,riskAfter:30}],
  findings: [{title:'Open finding',severity:'high',scanner:'Semgrep',repo:'repo',status:'Open',detectedAt:'2026-10-15T00:00:00Z'},{title:'Fixed finding',status:'Fixed'}],
  approvalHistory: {p:[{action:'Approved',by:'Independent reviewer',note:'Reviewed the justification',at:'2026-10-16T00:00:00Z'}]},
  employeeName:id=>id,projectById:id=>({name:id}),
};
assert.deepEqual(buildDemoReport('r1',d).rows,[['Oct',10,12]]);
assert.equal(buildDemoReport('r2',d).rows[0][4],'Verified');
assert.equal(buildDemoReport('r4',d,'2026-10-16').rows.length,0);
assert.equal(buildDemoReport('r4',d,'2026-10-01','2026-10-31').rows.length,1);
assert.equal(buildDemoReport('r5',d).rows.length,1);
assert.equal(buildDemoReport('r6',d).rows[0][2],'Independent reviewer');
assert.equal(buildDemoReport('r6',d).rows[0][3],'Reviewed the justification');
assert.throws(()=>buildDemoReport('r4',d,'2026-11-01','2026-10-01'),/range/);
assert.throws(()=>buildDemoReport('unknown',d),/Unknown/);
console.log('Report scope, lifecycle fields, decision notes, date filtering and backlog checks passed');
