import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateDocs } from './lib.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
try {
  const result = validateDocs(root);
  if (result.issues.length) {
    for (const issue of result.issues) console.error(issue);
    process.exitCode = 1;
  } else console.log('PASS: document links, skill entries, task registry (' + result.files + ' files, ' + result.skills + ' skills)');
} catch (error) {
  console.error('Document check failed: ' + error.message);
  process.exitCode = 1;
}
