import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectRecords, scanRecords } from './lib.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
try {
  let mode = 'worktree';
  let modeSet = false;
  let denylist = [];
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (['--staged', '--history'].includes(args[i])) {
      if (modeSet) throw new Error('Choose only one scan mode');
      mode = args[i].slice(2);
      modeSet = true;
    } else if (args[i] === '--denylist' && args[i + 1]) {
      const denyPath = path.resolve(args[++i]);
      const relative = path.relative(root, fs.realpathSync(denyPath));
      if (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative)) {
        throw new Error('The source denylist must stay outside this repository');
      }
      try {
        denylist = JSON.parse(fs.readFileSync(denyPath, 'utf8'));
      } catch {
        throw new Error('The external denylist could not be read as JSON');
      }
      if (!Array.isArray(denylist) || !denylist.every(x => typeof x === 'string' && x.trim())) {
        throw new Error('The denylist must be a JSON array of nonempty strings');
      }
    } else throw new Error('Unknown or incomplete argument');
  }
  const records = collectRecords(root, mode);
  if (!records.length) throw new Error('No files selected; scan is inconclusive');
  const issues = scanRecords(records, denylist);
  for (const issue of issues) console.error(issue.file + ': ' + issue.reason);
  if (issues.length) process.exitCode = 1;
  else console.log('PASS: ' + mode + ' content scan (' + records.length + ' records). Manual content review is still required.');
} catch (error) {
  // Avoid dumping raw Git command errors that might include sensitive content.
  console.error('Content scan could not complete: ' + (error.status !== undefined ? 'Git operation failed' : error.message));
  process.exitCode = 1;
}
