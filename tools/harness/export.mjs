import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { auditRecord, git } from './lib.mjs';

// Export Git blobs only: no copy of .git, ignored runtime files, or local edits.
export function exportSnapshot(root, destination, revision = 'HEAD', denylist = []) {
  root = fs.realpathSync(root);
  destination = path.resolve(destination);
  if (revision.startsWith('-')) throw new Error('Invalid revision');
  if (fs.existsSync(destination)) throw new Error('Choose a new destination directory');
  const parent = fs.realpathSync(path.dirname(destination));
  destination = path.join(parent, path.basename(destination));
  if (destination === root || destination.startsWith(root + path.sep)) throw new Error('Destination must be outside the source repository');
  const commit = git(root, ['rev-parse', '--verify', revision + '^{commit}']).trim();
  const files = [];
  for (const entry of git(root, ['ls-tree', '-r', '-z', commit]).split('\0').filter(Boolean)) {
    const [meta, name] = entry.split('\t');
    const [mode, type, oid] = meta.split(' ');
    if (type !== 'blob' || !['100644', '100755'].includes(mode) || !name || name.includes('\\') || name.includes(':') || name.split('/').some(x => !x || x === '..' || x === '.' || x.toLowerCase() === '.git')) {
      throw new Error('Unsupported export entry');
    }
    if (name === '.release-manifest.json') continue;
    const bytes = git(root, ['cat-file', 'blob', oid], null);
    const issues = auditRecord(name, bytes, denylist);
    if (issues.length) throw new Error(name + ': ' + issues.join(', '));
    files.push({ name, bytes, mode, sha256: crypto.createHash('sha256').update(bytes).digest('hex') });
  }
  if (!files.length) throw new Error('No committed files to export');
  // All files pass before the first write. Failures never remove existing directories.
  fs.mkdirSync(destination);
  for (const { name, bytes, mode } of files) {
    const target = path.join(destination, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, bytes, { flag: 'wx', mode: mode === '100755' ? 0o755 : 0o644 });
  }
  const inventory = { format: 1, files: files.map(({ name, sha256 }) => ({ name, sha256 })) };
  fs.writeFileSync(path.join(destination, '.release-manifest.json'), JSON.stringify(inventory, null, 2) + '\n', { flag: 'wx' });
  return { files: files.length, historyCopied: false };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const options = {};
    for (let i = 2; i < process.argv.length; i += 2) {
      const name = process.argv[i];
      if (!['--output', '--ref', '--denylist'].includes(name) || !process.argv[i + 1] || options[name]) throw new Error('Use --output DIRECTORY [--ref COMMIT] [--denylist EXTERNAL_JSON]');
      options[name] = process.argv[i + 1];
    }
    if (!options['--output']) throw new Error('A new --output directory is required');
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
    let denylist = [];
    if (options['--denylist']) {
      const file = fs.realpathSync(options['--denylist']);
      const relative = path.relative(root, file);
      if (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative)) throw new Error('Keep the denylist outside this repository');
      try { denylist = JSON.parse(fs.readFileSync(file, 'utf8')); }
      catch { throw new Error('External denylist could not be read'); }
      if (!Array.isArray(denylist) || !denylist.every(x => typeof x === 'string' && x.trim())) throw new Error('Invalid denylist');
    }
    console.log(JSON.stringify(exportSnapshot(root, options['--output'], options['--ref'], denylist)));
  } catch (error) {
    console.error(error.status !== undefined ? 'Git export could not complete' : error.message);
    process.exitCode = 1;
  }
}
