// Same-origin client shared by the slide UI. No automatic draft submission.
export const newId = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, '0')).join('');

export class FeedbackClient {
  constructor(key) { this.key = key; }
  async api(path, body) {
    let response;
    try {
      response = await fetch(path, {
        headers: {'X-Feedback-Key': this.key, ...(body ? {'Content-Type': 'application/json'} : {})},
        ...(body ? {method: 'POST', body: JSON.stringify(body)} : {}),
      });
    } catch {
      throw Error('受付に接続できません。入力を保持しています。同じURLで受付を復旧してください。');
    }
    const data = await response.json();
    if (!response.ok) throw Error(data.error || '処理を完了できません。入力は保持しています。');
    return data;
  }
  review() { return this.api('/api/review'); }
  submit(body) { return this.api('/api/submit', body); }
  status(id) { return this.api('/api/submission?id=' + encodeURIComponent(id)); }
  retry(id) { return this.api('/api/retry', {submissionId: id}); }
  async watch(id, onChange, signal) {
    const response = await fetch('/api/events?id=' + encodeURIComponent(id), {
      headers: {'X-Feedback-Key': this.key}, signal,
    });
    if (!response.ok) throw Error('通知状況に接続できません。「状況を確認」で再接続してください。');
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += value;
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, end).trim();
        buffer = buffer.slice(end + 1);
        if (line) onChange(JSON.parse(line).notification);
      }
    }
  }
}

export function readStored(key) {
  const value = localStorage.getItem(key);
  if (!value) return null;
  try { return JSON.parse(value); }
  catch { throw Error('保存済み入力を読み取れません。保存データを保持したまま受付担当へ連絡してください。'); }
}

export function saveStored(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch { return false; }
}

// Each document version owns its draft. Older tabs cannot overwrite a newer version.
// The original base key remains readable for existing pages and is never deleted.
export class DraftStore {
  constructor(key, version, storage = localStorage) {
    this.key = key; this.version = version; this.storage = storage;
    this.prefix = key + ':version:';
  }
  read(key) {
    const text = this.storage.getItem(key);
    if (!text) return null;
    try { return JSON.parse(text); }
    catch { throw Error('保存済み入力を読み取れません。入力を保持して受付担当へ連絡してください。'); }
  }
  load() {
    const specific = this.read(this.prefix + this.version);
    if (specific) return specific;
    const previous = this.read(this.key);
    return previous?.version === this.version ? previous : null;
  }
  save(draft) {
    if (draft.version !== this.version) throw Error('保存先の版が一致しません。');
    try { this.storage.setItem(this.prefix + this.version, JSON.stringify(draft)); return true; }
    catch { return false; }
  }
  previous() {
    const byVersion = new Map();
    const records = [...(this.read(this.key + ':archives') || []), this.read(this.key)];
    for (let i = 0; i < this.storage.length; i++) {
      const key = this.storage.key(i);
      if (key.startsWith(this.prefix)) records.push(this.read(key));
    }
    for (const draft of records) {
      if (draft?.version && draft.version !== this.version) byVersion.set(draft.version, draft);
    }
    return [...byVersion.values()];
  }
}
