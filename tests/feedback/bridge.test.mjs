import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeReply} from '../../tools/harness/feedback/desktop_bridge.mjs';

const target = '11111111-1111-1111-1111-111111111111';
const wrap = data => ({result: {success: true, contentItems: [{type: 'inputText', text: JSON.stringify(data)}]}});
test('desktop task readiness requires a recognized status and exact target', () => {
  assert.deepEqual(decodeReply(wrap({thread: {id: target, status: {type: 'idle'}}, turns: []}), 'status', target), {ok: true, threadId: target, active: false});
  assert.equal(decodeReply(wrap({thread: {id: target, status: {type: 'active'}}, turns: []}), 'status', target).active, true);
  assert.equal(decodeReply(wrap({thread: {id: 'other', status: {type: 'idle'}}, turns: []}), 'status', target).ok, false);
  assert.equal(decodeReply(wrap({thread: {id: target, status: {type: 'new-status'}}, turns: []}), 'status', target).ok, false);
});
test('unrecognized notification replies cannot invite automatic resend', () => {
  assert.equal(decodeReply({result: {}}, 'notify', target).uncertain, true);
  assert.equal(decodeReply({error: {message: 'private error'}}, 'notify', target).error, 'desktop_rejected');
  assert.equal(JSON.stringify(decodeReply({error: {message: 'private error'}}, 'notify', target)).includes('private error'), false);
});
