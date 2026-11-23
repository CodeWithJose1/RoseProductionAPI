import fs from 'node:fs';
import path from 'node:path';
import { connect, snapshot, SNAPSHOT_FILE } from './support.js';

export default async function globalSetup() {
  const conn = await connect();
  try {
    fs.mkdirSync(path.dirname(SNAPSHOT_FILE), { recursive: true });
    fs.writeFileSync(SNAPSHOT_FILE, JSON.stringify(await snapshot(conn)));
  } finally {
    await conn.end();
  }
}
