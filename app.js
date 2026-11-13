const $ = id => document.getElementById(id);
const draftKey = 'postroom-draft';
let account = {};
async function api(path, data) {
  const response = await fetch('/api/' + path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error);
  return result;
}
function preview() {
  $('preview').textContent = $('copy').value || 'Your post will appear here as you type.';
  $('count').textContent = $('copy').value.length + ' / 3,000';
  $('publish').disabled = !account.name || !$('copy').value.trim();
  $('schedule').disabled = $('publish').disabled || !$('when').value;
}
async function refresh() {
  try {
    account = await api('state');
  } catch {
    $('connection').textContent = 'Demo mode. Run the local server to connect LinkedIn.';
    return;
  }
  $('author').textContent = account.name || 'Your LinkedIn profile';
  $('connection').textContent = account.name ? 'Connected as ' + account.name :
    account.configured ? 'Connect your personal profile to publish.' : 'Add your LinkedIn app credentials in .env to connect.';
  $('connect').hidden = !account.configured || !!account.name;
  $('disconnect').hidden = !account.name;
  $('queue').replaceChildren();
  for (const post of account.posts) {
    const item = document.createElement('li');
    item.textContent = post.state + ' · ' + new Date(post.when * 1000).toLocaleString() + ' · ' + post.text.slice(0, 90);
    if (post.state === 'Scheduled') {
      const cancel = document.createElement('button');
      cancel.textContent = 'Cancel';
      cancel.onclick = () => act('cancel', {id: post.id});
      item.append(cancel);
    }
    $('queue').append(item);
  }
  if (!account.posts.length) $('queue').append(Object.assign(document.createElement('li'), {textContent:'No posts yet.'}));
  preview();
}
let busy = false;
async function act(action, data) {
  if (busy) return;
  busy = true;
  try {
    const result = await api(action, data);
    $('status').textContent = result.message;
    if (action === 'publish' || action === 'schedule') {
      $('copy').value = '';
      $('when').value = '';
      localStorage.removeItem(draftKey);
    }
    await refresh();
  } catch (error) { $('status').textContent = error.message; }
  finally { busy = false; }
}
$('copy').value = localStorage.getItem(draftKey) || '';
$('copy').oninput = preview;
$('when').oninput = preview;
$('save').onclick = () => {
  localStorage.setItem(draftKey, $('copy').value);
  $('status').textContent = 'Draft saved in this browser.';
};
$('disconnect').onclick = () => act('disconnect', {});
$('publish').onclick = () => {
  if (confirm('Publish this post publicly on LinkedIn now?')) act('publish', {text:$('copy').value});
};
$('schedule').onclick = () => act('schedule', {text:$('copy').value, when:new Date($('when').value).getTime()/1000});
const feedback = new URLSearchParams(location.search).get('status');
if (feedback) {
  $('status').textContent = feedback;
  history.replaceState(null, '', location.pathname);
}
preview();
refresh();
setInterval(() => { if (account.posts && !busy) refresh(); }, 15000);
