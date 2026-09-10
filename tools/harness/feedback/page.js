import {DraftStore, FeedbackClient, newId, readStored, saveStored} from '/feedback-client.js';

const $ = id => document.getElementById(id);
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
function warn(message) { $('alert').textContent = message; $('alert').hidden = !message; }
let client, config, draft, draftStore, draftSaved = true, storeKey, receiptKey, receipt, at = 0, onSummary = false, watching, lastState;
const answering = () => config.mode !== 'explain';
const payload = () => ({version: config.version, answers: draft.answers.map(({id, decision, comment}) => ({id, decision, comment})), general: draft.general});

function persist() {
  const okay = draftSaved = draftStore.save(draft);
  $('draft-status').textContent = okay ? '途中保存済み · このブラウザで再開できます' : '途中保存できません。このタブを閉じずに保存領域を確認してください。';
  $('draft-status').dataset.saved = String(okay);
  if (receipt?.saved && lastState) delivery(lastState);
  return okay;
}

function record(index, patch) {
  draft.answers[index] = {...draft.answers[index], ...patch};
  draft.updated = new Date().toISOString();
  persist();
}

function showArchive(old) {
  $('archive-panel').hidden = false;
  const box = element('section');
  box.append(element('h3', old.title || '以前の資料'));
  for (const answer of old.answers || []) {
    box.append(element('p', (answer.title || answer.id) + '：' + (answer.decision || '未回答') + (answer.comment ? '\n' + answer.comment : '')));
  }
  if (old.general) box.append(element('p', '全体：' + old.general));
  $('archives').append(box);
}

function validate() {
  return config.proposals.findIndex((proposal, i) => {
    const answer = draft.answers[i];
    return !config.decisions.includes(answer.decision) ||
      ((config.commentRequired || []).includes(answer.decision) && !answer.comment.trim());
  });
}

function render() {
  $('slide').hidden = onSummary;
  $('summary').hidden = !onSummary;
  $('previous').disabled = !onSummary && at === 0;
  $('previous').hidden = onSummary;
  $('overview').hidden = onSummary || at === config.proposals.length - 1;
  $('progress').textContent = onSummary ? '提出前の確認' : (at + 1) + ' / ' + config.proposals.length;
  $('overview').textContent = onSummary ? '項目へ戻る' : answering() ? '一覧で確認' : '目次を見る';
  $('next').textContent = onSummary ? '項目へ戻る' : at === config.proposals.length - 1 ? answering() ? '一覧で確認' : '目次を見る' : '次へ';
  if (onSummary) return renderSummary();
  const proposal = config.proposals[at];
  const section = $('slide');
  section.replaceChildren(element('h2', proposal.title));
  section.firstChild.id = 'item-title';
  if (proposal.steps) {
    const steps = element('ol', undefined, 'steps');
    for (const step of proposal.steps) steps.append(element('li', step));
    section.append(steps);
  }
  const columns = element('div', undefined, proposal.before !== undefined ? 'columns' : '');
  for (const side of ['before', 'after']) {
    if (proposal[side] === undefined) continue;
    const panel = element('div', undefined, 'panel ' + side);
    if (proposal.before !== undefined) panel.append(element('h3', side === 'before' ? '現在' : '提案'));
    panel.append(element('p', proposal[side], 'content'));
    columns.append(panel);
  }
  section.append(columns);
  if (proposal.reason) section.append(element('p', proposal.reason, 'reason'));
  if (answering()) {
    const fieldset = element('fieldset');
    fieldset.append(element('legend', config.mode === 'choose' ? '選択' : 'この項目への回答'));
    const choices = element('div', undefined, 'choices');
    for (const decision of config.decisions) {
      const label = element('label', undefined, 'choice');
      const radio = element('input');
      radio.type = 'radio'; radio.name = 'decision'; radio.value = decision;
      radio.checked = draft.answers[at].decision === decision;
      radio.addEventListener('change', () => { record(at, {decision}); updateCommentLabel(); });
      label.append(radio, element('span', decision));
      choices.append(label);
    }
    fieldset.append(choices);
    const label = element('label', undefined, 'field');
    const text = element('span'); text.id = 'comment-label';
    const comment = element('textarea'); comment.rows = 3; comment.maxLength = 10000;
    comment.value = draft.answers[at].comment;
    comment.addEventListener('input', () => record(at, {comment: comment.value}));
    label.append(text, comment); section.append(fieldset, label);
    updateCommentLabel();
  }
}

function updateCommentLabel() {
  const required = (config.commentRequired || []).includes(draft.answers[at].decision);
  $('comment-label').textContent = required ? '修正したい内容（必須）' : 'この項目へのコメント（任意）';
}

function renderSummary() {
  $('summary').querySelector('h2').textContent = answering() ? '回答の一覧' : '資料の目次';
  const list = $('summary-items'); list.replaceChildren();
  config.proposals.forEach((proposal, index) => {
    const row = element('article', undefined, 'summary-row');
    const header = element('header');
    const button = element('button', answering() ? '確認・修正' : '見る');
    button.type = 'button';
    button.addEventListener('click', () => { at = index; onSummary = false; render(); });
    header.append(element('h3', (index + 1) + '. ' + proposal.title), button);
    row.append(header);
    if (answering()) {
      row.append(element('p', draft.answers[index].decision || '未回答', 'badge'));
      if (draft.answers[index].comment) row.append(element('p', draft.answers[index].comment));
    }
    list.append(row);
  });
  $('general').parentElement.hidden = !answering();
  $('summary').querySelector('.muted').hidden = !answering();
  $('submit').hidden = !answering();
  $('general').value = draft.general || '';
}

function delivery(state) {
  lastState = state;
  $('delivery').hidden = false;
  $('retry-notification').hidden = state.state !== 'failed';
  $('saved-state').textContent = receipt?.saved ? 'PC保存：保存済み' : 'PC保存：確認中';
  const accepted = ['notified', 'received'].includes(state.state);
  $('notified-state').textContent = 'Codex通知：' + (accepted ? '受付済み' : state.state === 'pending' ? '現在の作業終了を待機中' : state.state === 'sending' ? '送信中' : '未確認');
  $('received-state').textContent = '回答の受領：' + (state.state === 'received' ? '同じタスクで確認済み' : '待機中');
  const message = state.error || ({
    pending: '回答は保存済みです。タスクが実行中なら、終了後に通知します。',
    sending: '保存済み回答の場所を同じタスクへ知らせています。',
    notified: 'Codexが通知を受け付けました。回答を読んだことの確認を待っています。',
    received: '回答を受領しました。このタスクで作業を続けます。',
    unknown: '受付で提出番号を確認できません。保存済みの入力と提出情報を保持しています。',
  }[state.state] || '回答を保持しています。接続状況を確認してください。');
  const changed = receipt?.signature !== JSON.stringify(payload());
  $('delivery-detail').textContent = (receipt?.body?.version !== config.version ? '以前の版の提出です。' : changed ? '現在の入力には提出後の変更があります。下記は前回の提出状況です。' : '') + message;
}

async function watch() {
  if (!receipt?.saved) return;
  watching?.abort(); watching = new AbortController();
  try {
    delivery((await client.status(receipt.body.submissionId)).notification);
    await client.watch(receipt.body.submissionId, delivery, watching.signal);
  } catch (error) {
    if (error.name !== 'AbortError') $('delivery-detail').textContent = '回答は保存済みです。通知状況の接続が切れました。「状況を確認」で再接続できます。';
  }
}

async function submit() {
  warn('');
  const missing = validate();
  if (missing >= 0) {
    at = missing; onSummary = false; render();
    warn('未回答、または必要なコメントがない項目があります。内容を確認してください。');
    return;
  }
  if (!persist()) { warn('途中保存できないため送信を止めました。このタブを閉じずに保存領域を確認してください。'); return; }
  const body = payload();
  const signature = JSON.stringify(body);
  // Keep an identical submission ID through lost responses and explicit retries.
  if (receipt?.signature !== signature) {
    if (receipt) {
      const history = readStored(receiptKey + ':history') || [];
      if (!history.some(item => item.body.submissionId === receipt.body.submissionId)) history.push(receipt);
      if (!saveStored(receiptKey + ':history', history)) { warn('前回の提出情報を保管できません。このタブを保持してください。'); return; }
    }
    receipt = {signature, body: {...body, submissionId: newId()}, saved: false};
  }
  if (!saveStored(receiptKey, receipt)) { warn('提出情報を保存できません。このタブを閉じずに保存領域を確認してください。'); return; }
  $('submit').disabled = true;
  try {
    const result = await client.submit(receipt.body);
    receipt.saved = result.saved === true;
    receipt.savedAt = result.savedAt;
    if (!saveStored(receiptKey, receipt)) warn('PCには保存済みですが、ブラウザの提出記録を更新できません。このタブを保持してください。');
    delivery(result.notification);
    void watch();
  } catch (error) { warn(error.message); }
  finally { $('submit').disabled = false; }
}

async function boot() {
  const params = new URLSearchParams(location.hash.slice(1));
  let key = params.get('key');
  if (key) sessionStorage.setItem('harness-feedback-key', key);
  else key = sessionStorage.getItem('harness-feedback-key');
  if (!key) throw Error('接続用リンクからページを開いてください。');
  client = new FeedbackClient(key);
  config = await client.review();
  config.mode ||= 'review';
  document.title = config.title; $('title').textContent = config.title;
  $('intro').textContent = config.test ? '接続確認用のテスト資料です。実際の判断や承認には使いません。' :
    answering() ? '1件ずつ確認し、一覧を見てからまとめて提出できます。' : '短い資料を順に確認できます。';
  storeKey = config.storageKey;
  receiptKey = storeKey + ':submission';
  draftStore = new DraftStore(storeKey, config.version);
  draftStore.previous().forEach(showArchive);
  draft = draftStore.load() || {
    version: config.version, title: config.title, updated: new Date().toISOString(), general: '',
    answers: config.proposals.map(p => ({id: p.id, title: p.title, decision: '', comment: ''})),
  };
  receipt = readStored(receiptKey);
  $('draft-status').hidden = !answering();
  $('delivery').hidden = !answering();
  document.querySelector('footer').hidden = !answering();
  $('overview').addEventListener('click', () => { onSummary = !onSummary; render(); });
  $('previous').addEventListener('click', () => { if (onSummary) onSummary = false; else at = Math.max(0, at - 1); render(); });
  $('next').addEventListener('click', () => {
    if (onSummary) onSummary = false;
    else if (at < config.proposals.length - 1) at++;
    else onSummary = true;
    render();
  });
  $('general').addEventListener('input', () => { draft.general = $('general').value; persist(); });
  $('submit').addEventListener('click', submit);
  $('refresh-status').addEventListener('click', () => void watch());
  $('retry-notification').addEventListener('click', async () => {
    if (!receipt?.saved) return;
    $('retry-notification').disabled = true;
    try { delivery((await client.retry(receipt.body.submissionId)).notification); void watch(); }
    catch (error) { warn(error.message); }
    finally { $('retry-notification').disabled = false; }
  });
  if (answering()) persist();
  render();
  $('delivery').hidden = !receipt?.saved;
  if (receipt?.saved) void watch();
  window.addEventListener('beforeunload', event => {
    if (answering() && !draftSaved) { event.preventDefault(); event.returnValue = ''; }
  });
}
boot().catch(error => { warn(error.message); $('title').textContent = '資料を開けませんでした'; });
