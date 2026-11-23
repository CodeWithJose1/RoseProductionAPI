import fs from 'node:fs';
import { connect, snapshot, SNAPSHOT_FILE } from './support.js';

// Fails the run if any pre-existing row changed or a test row was left behind.
export default async function globalTeardown() {
  const before = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, 'utf8'));
  const conn = await connect();
  try {
    const after = await snapshot(conn);
    const problems = [];
    for (const table of Object.keys(before)) {
      for (const [id, row] of Object.entries(before[table])) {
        if (!(id in after[table])) problems.push(`${table} ${id} deleted`);
        else if (after[table][id] !== row) problems.push(`${table} ${id} modified`);
      }
      for (const id of Object.keys(after[table])) {
        if (!(id in before[table])) problems.push(`${table} ${id} left behind`);
      }
    }
    if (problems.length) throw new Error(`Production data guard failed: ${problems.join(', ')}`);
    console.log('Production data guard: all pre-existing rows unchanged, no test rows left.');
  } finally {
    await conn.end();
  }
}
