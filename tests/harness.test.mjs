import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { auditRecord, collectRecords, git, scanRecords, validateDocs } from '../tools/harness/lib.mjs';
import { exportSnapshot } from '../tools/harness/export.mjs';

function fixture(t, withGit = false) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'astra-harness-test-'));
  t.after(() => {
    const relative = path.relative(path.resolve(os.tmpdir()), path.resolve(root));
    if (!/^astra-harness-test-[^/\\]+$/.test(relative)) throw new Error('Unsafe temporary cleanup target');
    fs.rmSync(root, { recursive: true, force: true });
  });
  if (withGit) {
    git(root, ['init', '-b', 'test']);
    git(root, ['config', 'user.name', 'Harness Test']);
    git(root, ['config', 'user.email', 'test@example.test']);
    git(root, ['config', 'commit.gpgsign', 'false']);
    git(root, ['config', 'core.autocrlf', 'false']);
  }
  return root;
}
function write(root, file, text) {
  fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
  fs.writeFileSync(path.join(root, file), text);
}
function docsFixture(root) {
  write(root, 'AGENTS.md', '# Entry\n[Profile](PROJECT.md)\n');
  write(root, 'PROJECT.md', '# Profile\n');
  write(root, 'docs/harness/NEXT_TASKS.md', '# Tasks\n');
}

test('broken document links and active task omissions fail, corrected registry passes', t => {
  const root = fixture(t);
  docsFixture(root);
  write(root, 'docs/harness/tasks/one.md', '# One\n[Missing](absent.md)\n');
  let result = validateDocs(root);
  assert.equal(result.issues.length, 2);
  write(root, 'docs/harness/tasks/one.md', '# One\n');
  write(root, 'docs/harness/NEXT_TASKS.md', '[One](tasks/one.md)\n');
  assert.deepEqual(validateDocs(root).issues, []);
  write(root, 'docs/harness/NEXT_TASKS.md', '[One](tasks/one.md)\n[Again](tasks/one.md)\n');
  assert.match(validateDocs(root).issues.join('\n'), /exactly one/);
});

test('skill frontmatter and required local references must remain usable', t => {
  const root = fixture(t);
  docsFixture(root);
  write(root, '.agents/skills/astra-check/SKILL.md', '---\nname: incorrect\ndescription: Check a specific task.\n---\n[Root](../../../AGENTS.md)\n');
  assert.match(validateDocs(root).issues.join('\n'), /folder and skill name/);
  write(root, '.agents/skills/astra-check/SKILL.md', '---\nname: astra-check\ndescription: Check a specific task.\n---\n[Root](../../../AGENTS.md)\n');
  assert.deepEqual(validateDocs(root).issues, []);
  write(root, '.agents/skills/existing/SKILL.md', '---\nname: "existing"\ndescription: Another format.\n---\n[External](missing.md)\n');
  write(root, 'docs/product.md', '[Unrelated reference](missing.md)\n');
  write(root, 'README.md', '[Product only](unrelated.md)\n');
  write(root, 'package.json', '{"name":"product"}');
  const unrelated = path.join(root, '.venv');
  fs.mkdirSync(unrelated);
  fs.symlinkSync(unrelated, path.join(root, 'environment-link'), process.platform === 'win32' ? 'junction' : 'dir');
  assert.deepEqual(validateDocs(root).issues, []);
  write(root, 'package.json', '{"name":"kawaken-style-astra-dev-workflow-kit"}');
  assert.match(validateDocs(root).issues.join('\n'), /README\.md: missing link unrelated\.md/);
  write(root, 'README.md', '[Setup](PROJECT.md)\n');
  assert.deepEqual(validateDocs(root).issues, []);
});

test('distribution scanner flags secrets, personal paths, binary data and source-specific prose', () => {
  const examples = [
    ['note.md', 'gh' + 'p_' + 'x'.repeat(30), 'access token'],
    ['note.md', 'AI' + 'za' + 'x'.repeat(35), 'Google API key'],
    ['note.md', 'API' + '_KEY = "' + 'X'.repeat(30) + '"', 'literal credential'],
    ['note.md', ['C:', 'Users', 'someone', 'work'].join(String.fromCharCode(92)), 'absolute Windows path'],
    ['note.md', 'person' + '@' + 'private-mail.test', 'personal email address'],
    ['note.md', Buffer.from([0, 255]), 'not UTF-8 text'],
    ['image.png', 'text', 'file type outside the text-only distribution'],
    ['note.md', 'PROJECT_ONLY_FACT', 'source-specific content'],
  ];
  for (const [file, content, expected] of examples) {
    assert.ok(auditRecord(file, Buffer.from(content), ['PROJECT_ONLY_FACT']).includes(expected), expected);
  }
  assert.deepEqual(auditRecord('README.md', Buffer.from('# Portable workflow\n')), []);
  const network = [192, 168, 0, 0].join('.');
  assert.deepEqual(auditRecord('tools/harness/feedback/review_server.py', Buffer.from(network + '/16')), []);
  assert.ok(auditRecord('README.md', Buffer.from(network + '/24')).includes('private network address'));
  assert.ok(auditRecord('README.md', Buffer.from([192, 168, 1, 5].join('.'))).includes('private network address'));
  assert.deepEqual(auditRecord('(commit metadata)', Buffer.from('noreply@github.com')), []);
  assert.ok(auditRecord('(commit metadata)', Buffer.from('someone' + '@' + 'github.com')).includes('personal email address'));
});

test('release export contains audited committed text and checksums, without history or private working data', t => {
  const root = fixture(t, true);
  const outside = fixture(t);
  write(root, '.gitignore', '.local/\n');
  write(root, 'README.md', 'Committed public text\n');
  git(root, ['add', '.']);
  git(root, ['commit', '-m', 'snapshot']);
  write(root, 'README.md', 'PRIVATE_WORKING_EDIT');
  write(root, '.local/answers.json', 'PRIVATE_LOCAL_DATA');
  write(root, 'untracked.md', 'PRIVATE_UNTRACKED_DATA');
  const target = path.join(outside, 'export');
  assert.equal(exportSnapshot(root, target).historyCopied, false);
  assert.equal(fs.existsSync(path.join(target, '.git')), false);
  assert.equal(fs.existsSync(path.join(target, '.local')), false);
  assert.equal(fs.existsSync(path.join(target, 'untracked.md')), false);
  assert.equal(fs.readFileSync(path.join(target, 'README.md'), 'utf8'), 'Committed public text\n');
  const inventory = JSON.parse(fs.readFileSync(path.join(target, '.release-manifest.json'), 'utf8'));
  assert.equal(inventory.files.length, 2);
  assert.match(inventory.files[1].sha256, /^[a-f0-9]{64}$/);
  assert.throws(() => exportSnapshot(root, target), /new destination/);
  const rejected = path.join(outside, 'rejected');
  assert.throws(() => exportSnapshot(root, rejected, 'HEAD', ['Committed public text']), /source-specific/);
  assert.equal(fs.existsSync(rejected), false);
});

test('index scan sees staged content even when worktree is sanitized', t => {
  const root = fixture(t, true);
  write(root, 'note.md', 'STAGED_ONLY_FACT');
  git(root, ['add', 'note.md']);
  write(root, 'note.md', 'Sanitized content');
  assert.equal(scanRecords(collectRecords(root), ['STAGED_ONLY_FACT']).length, 0);
  assert.equal(scanRecords(collectRecords(root, 'staged'), ['STAGED_ONLY_FACT']).length, 1);
});

test('history scan sees deleted material, ignored but committed files and commit metadata', t => {
  const root = fixture(t, true);
  write(root, '.gitignore', 'private.json\n');
  write(root, 'old.md', 'DELETED_ONLY_FACT');
  write(root, 'private.json', '{}');
  git(root, ['add', '.gitignore', 'old.md']);
  git(root, ['add', '-f', 'private.json']);
  git(root, ['commit', '-m', 'initial']);
  git(root, ['rm', 'old.md', 'private.json']);
  git(root, ['commit', '-m', 'cleanup']);
  git(root, ['commit', '--allow-empty', '-m', 'METADATA_ONLY_FACT']);
  const records = collectRecords(root, 'history');
  assert.ok(records.some(x => x.name === 'private.json'));
  const findings = scanRecords(records, ['DELETED_ONLY_FACT', 'METADATA_ONLY_FACT']);
  assert.equal(findings.filter(x => x.reason === 'source-specific content').length, 2);
  // One blob may have multiple historic paths; each path must still be audited.
  write(root, 'ordinary.md', 'identical bytes');
  write(root, '.env', 'identical bytes');
  git(root, ['add', 'ordinary.md', '.env']);
  git(root, ['commit', '-m', 'same blob different paths']);
  git(root, ['rm', '.env']);
  git(root, ['commit', '-m', 'remove private path']);
  assert.ok(scanRecords(collectRecords(root, 'history')).some(x => x.file === '.env'));
});

test('malformed external denylist never echoes its contents', t => {
  const external = fixture(t);
  const file = path.join(external, 'deny.json');
  const marker = 'SENSITIVE_SOURCE_MARKER';
  fs.writeFileSync(file, '["' + marker + '",]');
  const script = fileURLToPath(new URL('../tools/harness/scan.mjs', import.meta.url));
  let failure;
  try {
    execFileSync(process.execPath, [script, '--denylist', file], { stdio: 'pipe' });
  } catch (error) { failure = error; }
  assert.equal(failure?.status, 1);
  const output = String(failure.stdout) + String(failure.stderr);
  assert.ok(!output.includes(marker));
  assert.match(output, /external denylist could not be read as JSON/);
});
