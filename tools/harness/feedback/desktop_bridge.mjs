import net from 'node:net';
import {randomUUID} from 'node:crypto';

const notify = (action) => action === 'notify';

// Desktop tool transport is a small, replaceable host adapter, not a public API.
export function decodeReply(reply, action, threadId) {
  if (reply?.error || reply?.result?.success === false) {
    return {ok: false, uncertain: false, error: 'desktop_rejected'};
  }
  if (reply?.result?.success !== true) {
    return {ok: false, uncertain: notify(action), error: 'unrecognized_desktop_reply'};
  }
  let data;
  try {
    data = JSON.parse(reply.result.contentItems.find(x => x.type === 'inputText').text);
  } catch {
    return {ok: false, uncertain: notify(action), error: 'unrecognized_desktop_reply'};
  }
  if (action === 'status') {
    const kind = data?.thread?.status?.type;
    if (data?.thread?.id !== threadId) return {ok: false, error: 'thread_mismatch'};
    if (!['active', 'idle', 'systemError', 'notLoaded'].includes(kind) || !Array.isArray(data.turns)) {
      return {ok: false, error: 'unrecognized_desktop_reply'};
    }
    // Unavailable/error threads must never be treated as ready.
    if (kind === 'systemError' || kind === 'notLoaded') return {ok: false, error: 'thread_unavailable'};
    return {ok: true, threadId, active: kind === 'active' || data.turns.some(t => t.status === 'inProgress')};
  }
  // The enclosing tool confirms acceptance. Receipt contents are not logged.
  return {ok: true};
}

export async function callDesktop(input, env = process.env) {
  const threadId = env.REVIEW_THREAD_ID;
  const tool = input.action === 'status' ? 'read_thread' : input.action === 'notify' ? 'send_message_to_thread' : null;
  if (!/^[a-f0-9-]{36}$/.test(threadId ?? '') || !env.CODEX_APP_TOOLS_PIPE_PATH || !tool) {
    return {ok: false, uncertain: false, error: 'desktop_not_configured'};
  }
  if (notify(input.action) && (typeof input.prompt !== 'string' || input.prompt.length > 6000)) {
    return {ok: false, uncertain: false, error: 'invalid_notification'};
  }
  const args = notify(input.action) ? {threadId, prompt: input.prompt} : {threadId, turnLimit: 1, maxOutputCharsPerItem: 1000};
  return new Promise(resolve => {
    const socket = net.createConnection(env.CODEX_APP_TOOLS_PIPE_PATH);
    let buffer = Buffer.alloc(0), written = false, finished = false;
    const fail = error => finish({ok: false, uncertain: written && notify(input.action), error});
    const timer = setTimeout(() => fail('desktop_timeout'), 20000);
    function finish(result) {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      socket.destroy();
      resolve(result);
    }
    socket.once('connect', () => {
      const payload = Buffer.from(JSON.stringify({
        jsonrpc: '2.0', id: 1, method: 'tools/call',
        params: {namespace: 'codex_app', tool, arguments: args, threadId,
          callId: 'html-review-' + randomUUID(), turnId: 'html-review-' + randomUUID()},
      }));
      const head = Buffer.alloc(4);
      head.writeUInt32LE(payload.length);
      written = true;
      socket.write(Buffer.concat([head, payload]));
    });
    socket.on('data', chunk => {
      buffer = Buffer.concat([buffer, chunk]);
      if (buffer.length < 4) return;
      const length = buffer.readUInt32LE();
      if (length > 8000000) return fail('oversized_response');
      if (buffer.length < length + 4) return;
      try { finish(decodeReply(JSON.parse(buffer.subarray(4, length + 4)), input.action, threadId)); }
      catch { fail('invalid_response'); }
    });
    socket.once('error', () => fail('desktop_unavailable'));
    socket.once('close', () => { if (!finished) fail('desktop_disconnected'); });
  });
}

if (process.argv[1] && new URL(import.meta.url).pathname.endsWith('/desktop_bridge.mjs') &&
    (await import('node:url')).pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    let body = '';
    for await (const chunk of process.stdin) {
      body += chunk;
      if (body.length > 16000) throw Error();
    }
    console.log(JSON.stringify(await callDesktop(JSON.parse(body))));
  } catch {
    console.log(JSON.stringify({ok: false, uncertain: false, error: 'invalid_request'}));
    process.exitCode = 1;
  }
}
