import { strict as assert } from 'node:assert';
import { modelSpendQuestion } from '../lib/what-if.ts';
const data = [{ month: 'Oct', actual: 100, forecast: 100 }, { month: 'Nov', actual: null, forecast: 200 }];
assert.equal(modelSpendQuestion('reduce cloud cost by 15%', data).series[0].scenario, 170);
assert.equal(modelSpendQuestion('increase cloud spend 20 percent', data).series[0].scenario, 240);
for (const q of ['increase cost 0%', 'cut cost 101%', 'increase and reduce cloud cost 10%', 'add 10% employees', 'reduce cost']) assert.equal(modelSpendQuestion(q, data), null, q);
assert.equal(modelSpendQuestion('reduce cost 10%', []), null);
console.log('What-if model: 8 checks passed');

assert.equal(modelSpendQuestion('increase cloud cost by -10%', data), null);
assert.equal(modelSpendQuestion('reduce cloud cost by 10% then increase 20%', data), null);
console.log('Ambiguous and negative scenario inputs: 2 checks passed');
