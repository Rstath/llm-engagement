const API = window.API_BASE_URL;
const app = document.getElementById('app');
const participantLabel = document.getElementById('participantLabel');
let state = { meta: null, participant: null, progress: null };

const preQuestions = [
  ['age_group', 'What is your age group?', ['18-24', '25-34', '35-44', '35 +']],
  ['gender', 'What is your gender?', ['Female', 'Male', 'Non-binary / Other', 'Prefer not to say']],
  ['education', 'What is your highest level of education?', ['High school', 'Undergraduate degree', 'Postgraduate degree', 'Other']],
  ['messaging_app_use', 'How often do you use messaging applications?', ['Less than once per day', '1–3 times per day', '4–10 times per day', 'More than 10 times per day']],
  ['texting_ease', 'How easy do you find it to communicate through text messages?', ['1', '2', '3', '4', '5']],
  ['message_style', 'How often do you split one thought into multiple short messages?', ['Very rarely', 'Rarely', 'Sometimes', 'Often', 'Very often']],
  ['ai_used', 'Have you used AI-based conversational systems before?', ['Yes', 'No']],
  ['ai_frequency', 'How often do you use AI-based conversational systems?', ['Never used', 'Very rarely', 'Rarely', 'Sometimes', 'Often', 'Very often']]
];

function htmlEscape(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}
async function api(path, options = {}) {
  const res = await fetch(API + path, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
function saveParticipant(id) { localStorage.setItem('participant_id', id); }
function setProgress(progress) { state.progress = progress; state.participant = progress.participant_id; saveParticipant(progress.participant_id); participantLabel.textContent = `Participant: ${progress.participant_id}`; }
function errorBox(err) { return `<p class="error">${htmlEscape(err.message || err)}</p>`; }
function actions(...buttons) { return `<div class="actions">${buttons.join('')}</div>`; }

async function init() {
  state.meta = await api('/api/meta');
  const participant_id = localStorage.getItem('participant_id');
  setProgress(await api('/api/session', { method: 'POST', body: JSON.stringify({ participant_id }) }));
  route();
}
function route() {
  const hash = location.hash.replace('#', '');
  if (hash === 'researcher') return renderResearcherLogin();
  const step = state.progress.current_step || 'consent';
  if (step === 'consent') return renderConsent();
  if (step === 'pre') return renderPre();
  if (step === 'big5') return renderBig5();
  if (step === 'topics') return renderTopicsMost();
  if (step === 'chat') return renderChat();
  return renderDone();
}

function renderConsent(err = '') {
  app.innerHTML = `<h2>Informed consent form</h2>
    <p>This academic HCI thesis study collects questionnaire answers, Big Five scores, selected topic preferences, and a short mobile-style chat with an open-source AI model. Participation is voluntary and you may stop at any time.</p>
    <div class="section">
      <label><input id="c1" type="checkbox"> I confirm that I am at least 18 years old.</label>
      <label><input id="c2" type="checkbox"> I understand that participation is voluntary and that I may stop at any time.</label>
      <label><input id="c3" type="checkbox"> I agree that my questionnaire answers and chat messages may be saved for research analysis.</label>
    </div>${err ? errorBox(err) : ''}` + actions('<button id="continue">Save and continue</button>');
  document.getElementById('continue').onclick = async () => {
    try {
      setProgress(await api('/api/consent', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, age_confirmed: c1.checked, voluntary_participation: c2.checked, data_storage_agreed: c3.checked }) }));
      route();
    } catch (e) { renderConsent(e); }
  };
}
function renderPre(err = '') {
  app.innerHTML = `<h2>Pre-experiment questionnaire</h2><p class="muted">All fields are required.</p>
    ${preQuestions.map(([key, text, opts]) => `<div class="section"><strong>${htmlEscape(text)} *</strong>${opts.map(o => `<label><input type="radio" name="${key}" value="${htmlEscape(o)}"> ${htmlEscape(o)}</label>`).join('')}</div>`).join('')}
    <div class="section"><label><strong>Anything else about your mobile messaging habits?</strong><textarea id="free_text" rows="4"></textarea></label></div>
    ${err ? errorBox(err) : ''}` + actions('<button id="continue">Submit questionnaire</button>');
  document.getElementById('continue').onclick = async () => {
    const answers = {};
    for (const [key] of preQuestions) {
      const el = document.querySelector(`input[name="${key}"]:checked`);
      if (!el) return renderPre(new Error('Please complete all required questions.'));
      answers[key] = el.value;
    }
    answers.free_text = document.getElementById('free_text').value.trim();
    try { setProgress(await api('/api/pre', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, answers }) })); route(); } catch(e) { renderPre(e); }
  };
}
function renderBig5(err = '') {
  const items = state.meta.bfi_items;
  app.innerHTML = `<h2>Big Five Inventory (BFI-44)</h2><p class="muted">1 = Disagree strongly, 5 = Agree strongly.</p><div class="bfi-grid">
    ${Object.entries(items).map(([num, text]) => `<div class="bfi-item"><strong>${num}. ${htmlEscape(text)}</strong><div class="bfi-options">${[1,2,3,4,5].map(v => `<label><input type="radio" name="bfi_${num}" value="${v}" ${v===3?'checked':''}> ${v}</label>`).join('')}</div></div>`).join('')}
    </div>${err ? errorBox(err) : ''}` + actions('<button id="continue">Submit questionnaire</button>');
  document.getElementById('continue').onclick = async () => {
    const answers = {};
    for (const num of Object.keys(items)) answers[num] = Number(document.querySelector(`input[name="bfi_${num}"]:checked`).value);
    try { setProgress(await api('/api/big5', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, answers }) })); route(); } catch(e) { renderBig5(e); }
  };
}
function topicCards(selected, excluded = []) {
  const topics = state.meta.topics;
  return `<div class="topic-grid">${Object.entries(topics).filter(([id]) => !excluded.includes(id)).map(([id, t]) => `<label class="topic-option"><input type="checkbox" name="topic" value="${id}" ${selected.includes(id)?'checked':''}> <strong>${id} — ${htmlEscape(t.category)}</strong><br><span class="muted">${htmlEscape(t.example)}</span></label>`).join('')}</div>`;
}
function getCheckedTopics() { return [...document.querySelectorAll('input[name="topic"]:checked')].map(x => x.value); }
function renderTopicsMost(err = '') {
  app.innerHTML = `<h2>Select the 2 topics you find most interesting</h2>${topicCards([])}${err ? errorBox(err) : ''}` + actions('<button id="continue">Continue</button>');
  document.getElementById('continue').onclick = () => {
    const most = getCheckedTopics();
    if (most.length !== 2) return renderTopicsMost(new Error('Please select exactly 2 topics.'));
    renderTopicsLeast(most);
  };
}
function renderTopicsLeast(most, err = '') {
  app.innerHTML = `<h2>Select the 2 topics you find least interesting</h2><p class="muted">Your two most-interesting topics are removed from this list.</p>${topicCards([], most)}${err ? errorBox(err) : ''}` + actions('<button class="secondary" id="back">Back</button><button id="continue">Start conversation</button>');
  document.getElementById('back').onclick = () => renderTopicsMost();
  document.getElementById('continue').onclick = async () => {
    const least = getCheckedTopics();
    if (least.length !== 2) return renderTopicsLeast(most, new Error('Please select exactly 2 topics.'));
    try { setProgress(await api('/api/topics', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, most_topics: most, least_topics: least }) })); route(); } catch(e) { renderTopicsLeast(most, e); }
  };
}
async function renderChat(err = '') {
  app.innerHTML = `<h2>Conversation</h2><p class="muted">Loading chat...</p>`;
  let data;
  try { data = await api(`/api/chat/${state.participant}`); } catch(e) { app.innerHTML = errorBox(e); return; }
  const done = data.done || data.turns >= data.target_total_turns;
  app.innerHTML = `<h2>Conversation</h2><p class="muted">${htmlEscape(data.assignment.style_name)} · ${data.turns}/${data.target_total_turns} turns</p>
    <div class="chat"><div class="messages" id="messages">${data.transcript.map(t => `<div class="bubble ${t.speaker}">${htmlEscape(t.text)}</div>`).join('')}</div>
    ${done ? '<p class="muted">Conversation complete.</p>' : `<form class="chat-form" id="chatForm"><textarea id="chatText" rows="2" placeholder="Type your message..."></textarea><button>Send</button></form>`}</div>
    ${err ? errorBox(err) : ''}` + (done ? actions('<button id="finish">Finish experiment</button>') : '');
  document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
  const form = document.getElementById('chatForm');
  if (form) form.onsubmit = async (ev) => {
    ev.preventDefault();
    const text = document.getElementById('chatText').value.trim();
    if (!text) return;
    app.innerHTML = `<h2>Conversation</h2><p class="muted">Alex is replying...</p>`;
    try {
      const result = await api('/api/chat', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, text }) });
      if (result.done) { setProgress(await api(`/api/finish/${state.participant}`, { method: 'POST' })); renderDone(); } else renderChat();
    } catch(e) { renderChat(e); }
  };
  const finish = document.getElementById('finish');
  if (finish) finish.onclick = async () => { setProgress(await api(`/api/finish/${state.participant}`, { method: 'POST' })); renderDone(); };
}
function renderDone() {
  app.innerHTML = `<div class="thank-you"><h2>Thank you!</h2><p>Your responses have been submitted successfully.</p></div>`;
}
function renderResearcherLogin(err = '') {
  participantLabel.textContent = 'Researcher area';
  app.innerHTML = `<h2>Researcher login</h2><p class="muted">This page is protected by the backend. Changing the URL is not enough to access participant data.</p><label>Password<input type="password" id="password"></label>${err ? errorBox(err) : ''}` + actions('<button id="login">Log in</button>');
  document.getElementById('login').onclick = async () => {
    try { const res = await api('/api/researcher/login', { method:'POST', body: JSON.stringify({ password: document.getElementById('password').value }) }); localStorage.setItem('researcher_token', res.token); renderResearcherDashboard(); } catch(e) { renderResearcherLogin(e); }
  };
}
async function researcherApi(path) { return api(path, { headers: { Authorization: `Bearer ${localStorage.getItem('researcher_token') || ''}` } }); }
async function renderResearcherDashboard(err = '') {
  let data;
  try { data = await researcherApi('/api/researcher/overview'); } catch(e) { return renderResearcherLogin(e); }
  app.innerHTML = `<h2>Researcher dashboard</h2>${err ? errorBox(err) : ''}<p><a href="${API}/api/researcher/export.csv" id="exportLink">Download CSV export</a></p>
    <div class="table-wrap"><table><thead><tr><th>Participant</th><th>Created</th><th>Step</th><th>Completed</th></tr></thead><tbody>${data.participants.map(p => `<tr><td>${htmlEscape(p.participant_id)}</td><td>${htmlEscape(p.created_at)}</td><td>${htmlEscape(p.current_step)}</td><td>${p.completed ? 'Yes' : 'No'}</td></tr>`).join('')}</tbody></table></div>`;
  document.getElementById('exportLink').onclick = async (ev) => {
    ev.preventDefault();
    const res = await fetch(`${API}/api/researcher/export.csv`, { headers: { Authorization: `Bearer ${localStorage.getItem('researcher_token') || ''}` } });
    const blob = await res.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'llm_engagement_export.csv'; a.click(); URL.revokeObjectURL(url);
  };
}
window.addEventListener('hashchange', route);
init().catch(e => app.innerHTML = errorBox(e));
