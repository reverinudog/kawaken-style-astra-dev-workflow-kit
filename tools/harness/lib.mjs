import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

export function git(root, args, encoding = 'utf8') {
  return execFileSync('git', ['-C', root, ...args], {
    encoding, maxBuffer: 32 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'],
  });
}

export function walk(root, dir = root) {
  const ignored = new Set(['.git', 'node_modules', '.local', 'screenshots', 'coverage', 'dist', '__pycache__']);
  const result = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ignored.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isSymbolicLink()) throw new Error('Symbolic link is not supported: ' + path.relative(root, full));
    if (entry.isDirectory()) result.push(...walk(root, full));
    else result.push(path.relative(root, full).split(path.sep).join('/'));
  }
  return result.sort();
}

export function validateDocs(root) {
  const issues = [];
  const files = [];
  const entries = ['AGENTS.md', 'PROJECT.md', 'SETUP.md'];
  // The product README belongs to its maintainer after installation.
  const manifest = path.join(root, 'package.json');
  if (fs.existsSync(manifest) && JSON.parse(fs.readFileSync(manifest, 'utf8')).name === 'astra-dev-harness') entries.push('README.md', 'SECURITY.md', 'CONTRIBUTING.md');
  for (const name of entries) {
    const full = path.join(root, name);
    if (!fs.existsSync(full)) continue;
    if (!fs.lstatSync(full).isFile()) throw new Error('Non-regular harness entry: ' + name);
    files.push(name);
  }
  const docs = path.join(root, 'docs/harness');
  if (fs.existsSync(docs)) {
    if (fs.lstatSync(docs).isSymbolicLink()) throw new Error('Harness documents must be local files');
    files.push(...walk(root, docs));
  }
  const skills = path.join(root, '.agents/skills');
  if (fs.existsSync(skills)) {
    for (const entry of fs.readdirSync(skills, { withFileTypes: true })) {
      if (!entry.name.startsWith('astra-')) continue;
      if (entry.isSymbolicLink()) throw new Error('Harness skills must be local files');
      if (entry.isDirectory()) files.push(...walk(root, path.join(skills, entry.name)));
    }
  }
  for (const required of ['AGENTS.md', 'PROJECT.md', 'docs/harness/NEXT_TASKS.md']) {
    if (!files.includes(required)) issues.push(required + ': required file missing');
  }
  const names = new Set();
  for (const name of files.filter(x => x.endsWith('.md'))) {
    const text = fs.readFileSync(path.join(root, name), 'utf8');
    const withoutCode = text.replace(/^```[^\n]*\n[\s\S]*?^```\s*$/gm, '').replace(/`[^`\n]+`/g, '');
    for (const match of withoutCode.matchAll(/!?\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g)) {
      const ref = match[1];
      if (/^(?:https?:|mailto:|#)/i.test(ref)) continue;
      const location = decodeURIComponent(ref.split('#')[0]);
      const resolved = path.resolve(root, path.dirname(name), location);
      const rel = path.relative(root, resolved);
      if (rel.startsWith('..') || path.isAbsolute(rel)) issues.push(name + ': link escapes repository');
      else if (!fs.existsSync(resolved)) issues.push(name + ': missing link ' + location);
    }
    if (name.endsWith('/SKILL.md')) {
      const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
      const skillName = fm?.[1].match(/^name: (.+)$/m)?.[1]?.trim();
      const description = fm?.[1].match(/^description: (.+)$/m)?.[1]?.trim();
      if (!skillName || !/^[a-z0-9-]{1,64}$/.test(skillName)) issues.push(name + ': invalid skill name');
      if (!description || description.length > 1024) issues.push(name + ': missing or oversized description');
      if (skillName !== path.basename(path.dirname(name))) issues.push(name + ': folder and skill name differ');
      if (skillName && names.has(skillName)) issues.push(name + ': duplicate skill name');
      names.add(skillName);
    }
  }
  const indexFile = path.join(root, 'docs/harness/NEXT_TASKS.md');
  if (fs.existsSync(indexFile)) {
    const index = fs.readFileSync(indexFile, 'utf8');
    const refs = [...index.matchAll(/\[[^\]]*\]\((tasks\/[^\s)]+\.md)\)/g)].map(x => x[1]);
    const active = files.filter(x => /^docs\/harness\/tasks\/[^/]+\.md$/.test(x));
    for (const task of active) {
      const ref = task.replace('docs/harness/', '');
      if (refs.filter(x => x === ref).length !== 1) issues.push(task + ': needs exactly one NEXT_TASKS entry');
    }
    for (const ref of refs) {
      if (!active.includes('docs/harness/' + ref)) issues.push('NEXT_TASKS: entry is missing or not active: ' + ref);
    }
  }
  const lessonsIndex = path.join(root, 'docs/harness/LESSONS.md');
  if (fs.existsSync(lessonsIndex)) {
    const index = fs.readFileSync(lessonsIndex, 'utf8');
    for (const name of files.filter(x => /^docs\/harness\/lessons\/[^/]+\.md$/.test(x) && !x.endsWith('/README.md'))) {
      if (!index.includes('(lessons/' + path.basename(name) + ')')) issues.push(name + ': needs a LESSONS index entry');
    }
  }
  return { files: files.length, skills: names.size, issues };
}

const extensions = new Set(['.md', '.json', '.mjs', '.html', '.yml', '.yaml']);
const special = new Set(['.gitignore', '.gitattributes', '.gitkeep', 'LICENSE']);
const pathRules = [
  ['environment or credential file', /(?:^|\/)(?:\.env(?:\..*)?|credentials(?:\.[^/]*)?|id_rsa|id_ed25519)$/i],
  ['private key or archive', /\.(?:pem|key|p12|pfx|zip|7z|db|sqlite|exe|dll|mp4|png|jpg|wav)$/i],
  ['private working data', /(?:^|\/)(?:node_modules|\.local|screenshots|coverage|dist)(?:\/|$)/i],
];
const textRules = [
  ['private key', /-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----/],
  ['access token', /\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b/],
  ['cloud access key', /\bAKIA[A-Z0-9]{16}\b/],
  ['Google API key', /\bAIza[A-Za-z0-9_-]{30,}\b/],
  ['literal credential', /\b(?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|SECRET)\s*[=:]\s*["'][A-Za-z0-9_+\/-]{16,}["']/],
  ['absolute Windows path', /\b[A-Za-z]:[\\/](?![\\/])/],
  ['personal Unix path', /\/(?:Users|home)\/[A-Za-z0-9_.-]+(?:\/|\b)/],
  ['private network address', /\b(?:10\.[0-9]{1,3}|192\.168|172\.(?:1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}\b/],
];

export function auditRecord(name, bytes, denylist = []) {
  const issues = [];
  for (const [label, rule] of pathRules) if (rule.test(name)) issues.push(label);
  const harnessSource = /^(?:tools\/harness(?:\/(?:feedback|advice))?|tests\/(?:feedback|setup))\/[^/]+\.(?:py|js|css)$/.test(name);
  if (!harnessSource && !extensions.has(path.extname(name).toLowerCase()) && !special.has(path.basename(name)) && name !== '(commit metadata)') {
    issues.push('file type outside the text-only distribution');
  }
  if (bytes.length > 1024 * 1024) return [...issues, 'file exceeds distribution size limit'];
  let text;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch { return [...issues, 'not UTF-8 text']; }
  if (text.includes(String.fromCharCode(0))) issues.push('binary content');
  for (const [label, rule] of textRules) {
    // Standard network definitions are portable code constants, not host addresses.
    const candidate = label === 'private network address'
      ? text.replace(/\b(?:10\.0\.0\.0\/8|172\.16\.0\.0\/12|192\.168\.0\.0\/16)\b/g, '')
      : text;
    if (rule.test(candidate)) issues.push(label);
  }
  for (const match of text.matchAll(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi)) {
    const domain = match[0].split('@').pop().toLowerCase();
    if (!['users.noreply.github.com', 'example.com', 'example.test'].includes(domain) && match[0].toLowerCase() !== 'noreply@github.com') issues.push('personal email address');
  }
  const folded = (name + '\n' + text).toLowerCase();
  if (denylist.some(term => folded.includes(term.toLowerCase()))) issues.push('source-specific content');
  return [...new Set(issues)];
}

export function collectRecords(root, mode = 'worktree') {
  const records = [];
  if (mode === 'history') {
    const commits = git(root, ['rev-list', '--all']).trim().split('\n').filter(Boolean);
    const seen = new Set();
    const blobs = new Map();
    for (const commit of commits) {
      for (const entry of git(root, ['ls-tree', '-r', '-z', commit]).split('\0').filter(Boolean)) {
        const tab = entry.indexOf('\t');
        const [permissions, type, oid] = entry.slice(0, tab).split(' ');
        const name = entry.slice(tab + 1);
        const key = oid + '\0' + name;
        if (seen.has(key)) continue;
        seen.add(key);
        if (type !== 'blob' || !['100644', '100755'].includes(permissions)) {
          throw new Error('Non-regular historical file: ' + name);
        }
        if (!blobs.has(oid)) blobs.set(oid, git(root, ['cat-file', 'blob', oid], null));
        records.push({ name, bytes: blobs.get(oid) });
      }
    }
    const metadata = git(root, ['log', '--all', '--format=%an <%ae>%n%cn <%ce>%n%B']);
    records.push({ name: '(commit metadata)', bytes: Buffer.from(metadata) });
    return records;
  }
  if (mode === 'staged') {
    for (const entry of git(root, ['ls-files', '--stage', '-z']).split('\0').filter(Boolean)) {
      const tab = entry.indexOf('\t');
      const [permissions, oid, stage] = entry.slice(0, tab).split(' ');
      const name = entry.slice(tab + 1);
      if (permissions !== '100644' && permissions !== '100755') throw new Error('Non-regular indexed file: ' + name);
      if (stage !== '0') throw new Error('Unmerged index entry: ' + name);
      records.push({ name, bytes: git(root, ['cat-file', 'blob', oid], null) });
    }
    return records;
  }
  const names = new Set(git(root, ['ls-files', '--cached', '--others', '--exclude-standard', '-z']).split('\0').filter(Boolean));
  for (const name of names) {
    const full = path.join(root, name);
    if (!fs.existsSync(full)) continue; // A deleted tracked file is checked through index/history modes.
    if (!fs.lstatSync(full).isFile()) throw new Error('Non-regular file: ' + name);
    records.push({ name, bytes: fs.readFileSync(full) });
  }
  return records;
}

export function scanRecords(records, denylist = []) {
  return records.flatMap(({ name, bytes }) => auditRecord(name, bytes, denylist).map(reason => ({ file: name, reason })));
}
