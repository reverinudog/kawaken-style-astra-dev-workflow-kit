import test from 'node:test';
import assert from 'node:assert/strict';
import {DraftStore} from '../../tools/harness/feedback/client.js';

const memory = () => {
  const values = new Map();
  return {get length() {return values.size;}, key: i => [...values.keys()][i],
    getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value)};
};
test('old and new tabs retain their own draft without replacing each other', () => {
  const storage = memory();
  storage.setItem('stable-key', JSON.stringify({version: 'v1', answers: ['legacy input']}));
  const oldTab = new DraftStore('stable-key', 'v1', storage);
  const newTab = new DraftStore('stable-key', 'v2', storage);
  assert.deepEqual(oldTab.load().answers, ['legacy input']);
  assert.equal(newTab.load(), null);
  newTab.save({version: 'v2', answers: ['new input']});
  oldTab.save({version: 'v1', answers: ['later old input']});
  // A pre-upgrade tab still using the original key cannot damage v2 either.
  storage.setItem('stable-key', JSON.stringify({version: 'v1', answers: ['legacy tab closing']}));
  assert.deepEqual(newTab.load().answers, ['new input']);
  assert.deepEqual(newTab.previous()[0].answers, ['later old input']);
  assert.deepEqual(oldTab.load().answers, ['later old input']);
});
test('failed draft storage is reported without touching another version', () => {
  const storage = memory();
  const draft = new DraftStore('stable-key', 'v2', storage);
  storage.setItem('stable-key:version:v1', JSON.stringify({version: 'v1', answers: ['keep']}));
  storage.setItem = () => {throw Error('quota');};
  assert.equal(draft.save({version: 'v2', answers: ['new']}), false);
  assert.deepEqual(draft.previous()[0].answers, ['keep']);
});
