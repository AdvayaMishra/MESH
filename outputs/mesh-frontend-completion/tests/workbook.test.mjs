import { strict as assert } from 'node:assert';
import { crc32 } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { workbookBytes, columnName } from '../lib/export/workbook.ts';
assert.equal(columnName(0), 'A'); assert.equal(columnName(25), 'Z'); assert.equal(columnName(26), 'AA');
const bytes = workbookBytes(['Name', 'Amount'], [['=HYPERLINK("bad") & <text>', 12.5], ['Unicode café', -4]]);
const view = new DataView(bytes.buffer);
let offset = 0;
const entries = new Map();
while (view.getUint32(offset, true) === 0x04034b50) {
  const size = view.getUint32(offset + 18, true), names = view.getUint16(offset + 26, true), extra = view.getUint16(offset + 28, true);
  const name = new TextDecoder().decode(bytes.slice(offset + 30, offset + 30 + names));
  const start = offset + 30 + names + extra, body = bytes.slice(start, start + size);
  assert.equal(crc32(body), view.getUint32(offset + 14, true));
  entries.set(name, new TextDecoder().decode(body)); offset = start + size;
}
assert.equal(entries.size, 5);
assert.equal(view.getUint32(offset, true), 0x02014b50);
assert.equal(view.getUint32(bytes.length - 22, true), 0x06054b50);
const sheet = entries.get('xl/worksheets/sheet1.xml');
assert.ok(sheet.includes('&amp; &lt;text&gt;'));
assert.ok(sheet.includes('t="inlineStr"'));
assert.equal(sheet.includes('<f>'), false);
assert.ok(sheet.includes('<v>12.5</v>')); assert.ok(sheet.includes('<v>-4</v>'));
assert.ok(sheet.includes('Unicode café'));
mkdirSync('verification', { recursive: true }); writeFileSync('verification/unit-report.xlsx', bytes);
console.log('OOXML workbook: ZIP checksums, relationships, numeric/text cells and formula safety passed');
