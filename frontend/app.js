const API = window.API_BASE_URL;
const app = document.getElementById('app');
const participantLabel = document.getElementById('participantLabel');
let state = { meta: null, participant: null, progress: null, device: 'desktop', hadExistingParticipant: false };

const LIKERT_FREQUENCY = ['Very rarely', 'Rarely', 'Sometimes', 'Often', 'Very often'];
const AI_FREQUENCY = ['Never used', 'Very rarely', 'Rarely', 'Sometimes', 'Often', 'Very often'];
const EMOTIONS = [
  'Insecure', 'Helpless', 'Excluded', 'Threatened', 'Critical', 'Frustrated',
  'Humiliated', 'Bitter', 'Hurt', 'Guilty', 'Powerless', 'Lonely',
  'Powerful', 'Excited', 'Proud', 'Hopeful', 'Startled', 'Disapproving',
  'Awful', 'Repelled'
];
const BFI_SCALE_LABELS = {
  1: 'Disagree strongly',
  2: 'Disagree a little',
  3: 'Neither agree nor disagree',
  4: 'Agree a little',
  5: 'Agree strongly'
};

function htmlEscape(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}
async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });

  if (!res.ok) {
    let message = await res.text();

    try {
      const parsed = JSON.parse(message);
      message = parsed.detail || message;
    } catch {}

    if (message === 'Wrong password') {
      message = 'Wrong password. Please try again';
    }

    throw new Error(message);
  }

  return res.json();
}
function renderProgressFromServer(progress) {
  setProgress(progress);
  if (progress.current_step === 'done' || progress.completed) {
    renderDone();
  } else {
    route();
  }
}
function saveParticipant(id) { localStorage.setItem('participant_id', id); }
function saveAccessCode(code) { if (code) localStorage.setItem('participant_access_code', code); }
function clearParticipantSession() {
  localStorage.removeItem('participant_id');
  localStorage.removeItem('participant_access_code');
  state.participant = null;
  state.progress = null;
  state.hadExistingParticipant = false;
  document.querySelectorAll('.resume-modal-backdrop').forEach(el => el.remove());
  renderParticipantLogin();
}
function setProgress(progress) {
  state.progress = progress;
  state.participant = progress.participant_id;
  saveParticipant(progress.participant_id);
  if (participantLabel) participantLabel.textContent = `Participant: ${progress.participant_id}`;
  renderParticipantLogoutButton();
}
function renderParticipantLogoutButton() {
  let btn = document.getElementById('participantLogoutButton');
  if (!state.participant || location.hash.replace('#', '') === 'researcher') {
    if (btn) btn.remove();
    return;
  }
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'participantLogoutButton';
    btn.className = 'participant-logout-button';
    btn.type = 'button';
    btn.textContent = 'Log out';
    document.body.appendChild(btn);
  }
  btn.onclick = clearParticipantSession;
}
function errorBox(err) { return `<p class="error">${htmlEscape(err.message || err)}</p>`; }
function actions(...buttons) { return `<div class="actions">${buttons.join('')}</div>`; }
function radioGroup(name, options, selected = '', horizontal = false) {
  return `<div class="radio-group ${horizontal ? 'horizontal' : ''}">${options.map(o => `<label><input type="radio" name="${htmlEscape(name)}" value="${htmlEscape(o)}" ${selected === o ? 'checked' : ''}> ${htmlEscape(o)}</label>`).join('')}</div>`;
}
function getRadio(name) { return document.querySelector(`input[name="${CSS.escape(name)}"]:checked`)?.value || null; }
function requiredError(fields) {
  const errors = {};
  for (const [key, value] of Object.entries(fields)) if (value === null || value === undefined || value === '') errors[key] = 'This question is required.';
  return errors;
}
function fieldError(errors, key) { return errors?.[key] ? `<div class="field-error">${htmlEscape(errors[key])}</div>` : ''; }
function saveDraft(key, value) { localStorage.setItem(`${state.participant}_${key}`, JSON.stringify(value)); }
function loadDraft(key, fallback) {
  try { return JSON.parse(localStorage.getItem(`${state.participant}_${key}`) || JSON.stringify(fallback)); }
  catch { return fallback; }
}
function clearDraft(key) { localStorage.removeItem(`${state.participant}_${key}`); }

function detectDevice() {
  const ua = navigator.userAgent || '';
  const isTablet = /iPad|Tablet|Nexus 7|Nexus 10|SM-T|Lenovo Tab/i.test(ua) || (navigator.maxTouchPoints > 1 && /Macintosh/i.test(ua));
  const isMobile = /Mobi|Android|iPhone|iPod|Windows Phone/i.test(ua) && !isTablet;
  if (isTablet) return 'tablet';
  if (isMobile) return 'mobile';
  return 'desktop';
}
function isDesktopDevice() { return state.device === 'desktop' && window.matchMedia('(min-width: 1025px)').matches; }
function stepLabel(step) {
  return ({ consent: 'the consent form', pre: 'the pre-experiment questionnaire', big5: 'the Big Five Inventory', topics: 'topic selection', topic_preferences: 'topic selection', chat: 'the conversation', done: 'the thank-you page' })[step] || 'where you left off';
}
function hasSavedProgress(progress) {
  const step = progress?.current_step || 'consent';
  return Boolean(progress?.participant_id && step !== 'consent' && step !== 'done' && !progress?.completed);
}
function showResumeModalOnce() {
  if (!state.hadExistingParticipant || !hasSavedProgress(state.progress)) return;
  document.querySelectorAll('.resume-modal-backdrop').forEach(el => el.remove());
  const modal = document.createElement('div');
  modal.className = 'modal fade show resume-modal-backdrop';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.innerHTML = `<div class="modal-dialog modal-dialog-centered"><div class="modal-content resume-modal-content">
    <div class="modal-header"><h3 class="modal-title">Saved progress found</h3><button type="button" class="btn-close" aria-label="Close">×</button></div>
    <div class="modal-body"><p>You have already started this study.</p><p>You will continue from <strong>${htmlEscape(stepLabel(state.progress.current_step))}</strong>.</p></div>
    <div class="modal-footer"><button type="button" class="resume-continue">Continue</button></div>
  </div></div>`;
  document.body.appendChild(modal);
  const close = () => modal.remove();
  modal.querySelector('.btn-close').addEventListener('click', close);
  modal.querySelector('.resume-continue').addEventListener('click', close);
}
function parseTimestamp(value) {
  if (!value) return new Date();
  const raw = String(value);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw);
  const d = new Date(hasTimezone ? raw : `${raw}Z`);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}
function formatMessageTime(value) {
  const d = parseTimestamp(value);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function iPhoneStatusTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function syntheticOlderMessage(transcript) {
  const first = transcript?.[0]?.created_at ? parseTimestamp(transcript[0].created_at) : new Date();
  const older = new Date(first.getTime() - 1000 * 60 * 60 * 3);
  return { speaker: 'Agent', text: 'hah ok, we can continue later', created_at: older.toISOString(), synthetic: true };
}
function visibleTranscript(transcript) {
  return [syntheticOlderMessage(transcript), ...(transcript || [])];
}
function chatMessageHtml(t) {
  const isHuman = t.speaker === 'Human' || t.speaker === 'user';
  const cls = isHuman ? 'Human' : 'Agent';
  const label = isHuman ? 'You' : 'Alex';
  const time = formatMessageTime(t.created_at);
  const meta = `${time}${isHuman ? ' · Delivered' : ''}`;
  const avatar = isHuman ? '' : '<div class="agent-mini-avatar">A</div>';
  return `<div class="message-row ${cls}${t.synthetic ? ' synthetic' : ''}">
    <div class="message-sender">${label}</div>
    <div class="message-line">${avatar}<div class="bubble ${cls}">${htmlEscape(t.text)}</div></div>
    <div class="message-meta">${htmlEscape(meta)}</div>
  </div>`;
}
function scrollMessagesToBottom() {
  const messages = document.getElementById('messages');
  if (messages) messages.scrollTop = messages.scrollHeight;
}
function scrollPageToTop() {
  window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
  const appShell = document.querySelector('.app-shell');
  if (appShell) appShell.scrollTop = 0;
  const card = document.querySelector('.card');
  if (card) card.scrollTop = 0;
}

function scrollToTopAfterRender() {
    requestAnimationFrame(() => {
    setTimeout(scrollPageToTop, 0);
  });
}
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
const AGENT_TEXT_LIMIT = 95;

function randomBetween(min, max) {
  return Math.floor(min + Math.random() * (max - min + 1));
}

function splitAgentText(text, limit = AGENT_TEXT_LIMIT) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (!clean) return [];

  if (clean.length <= limit) return [clean];

  const parts = [];
  let remaining = clean;

  while (remaining.length > limit && parts.length < 2) {
    const slice = remaining.slice(0, limit + 1);

    let cut = Math.max(
      slice.lastIndexOf('. '),
      slice.lastIndexOf('? '),
      slice.lastIndexOf('! '),
      slice.lastIndexOf(', '),
      slice.lastIndexOf(' ')
    );

    if (cut < 35) cut = limit;

    parts.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }

  if (remaining) {
    if (parts.length >= 2) {
      parts[1] = `${parts[1]} ${remaining}`.trim();
    } else {
      parts.push(remaining);
    }
  }

  return parts.filter(Boolean).slice(0, 2);
}

function readingDelay(userText) {
  const chars = String(userText || '').length;
  const readingMs = chars * randomBetween(42, 72);
  const reactionMs = randomBetween(450, 1300);
  return Math.min(4200, Math.max(800, readingMs + reactionMs));
}

function writingDelay(agentText) {
  const chars = String(agentText || '').length;
  const typingMs = chars * randomBetween(190, 330);
  const thinkingMs = randomBetween(300, 1200);
  return Math.min(5200, Math.max(900, typingMs + thinkingMs));
}

function interBubbleDelay() {
  return randomBetween(450, 1300);
}

function agentTypingDelay(text) {
  return writingDelay(text);
}
function spinnerHtml(label = 'Loading') {
  return `<div class="page-loader" role="status" aria-live="polite"><span class="spinner"></span><span>${htmlEscape(label)}</span></div>`;
}
function updateComposerState(textEl, sendBtn) {
  if (!textEl) return;
  textEl.style.height = 'auto';
  const nextHeight = Math.min(textEl.scrollHeight, 120);
  textEl.style.height = `${Math.max(38, nextHeight)}px`;
  const hasText = textEl.value.trim().length >= 1;
  if (sendBtn) {
    sendBtn.disabled = !hasText;
    sendBtn.classList.toggle('is-visible', hasText);
  }
}
function openInfoModal() {
  const existing = document.querySelector('.contact-modal-backdrop');
  if (existing) existing.remove();
  const modal = document.createElement('div');
  modal.className = 'modal fade show contact-modal-backdrop';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.innerHTML = `<div class="modal-dialog modal-dialog-centered"><div class="modal-content contact-modal-content">
    <div class="modal-header"><h3 class="modal-title">Questions or concerns?</h3><button type="button" class="btn-close" aria-label="Close">×</button></div>
    <div class="modal-body">
      <p>If you experience discomfort, distress, or any problem during the study, you may stop participating at any time by closing the browser window.</p>
      <p>You may contact the researcher at any time if something bad occurs during or after participation.</p>
      <p><strong>Researcher</strong><br>Roubini Stathopoulou<br><a href="mailto:rstathopoulou76@gmail.com">rstathopoulou76@gmail.com</a></p>
    </div>
    <div class="modal-footer"><button type="button" class="resume-continue">Close</button></div>
  </div></div>`;
  document.body.appendChild(modal);
  const close = () => modal.remove();
  modal.addEventListener('click', ev => { if (ev.target === modal) close(); });
  modal.querySelector('.btn-close').addEventListener('click', close);
  modal.querySelector('.resume-continue').addEventListener('click', close);
}
function renderHelpButton() {
  let btn = document.getElementById('studyHelpButton');
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'studyHelpButton';
    btn.className = 'study-help-button';
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Study contact information');
    btn.textContent = '?';
    document.body.appendChild(btn);
  }
  btn.onclick = openInfoModal;
}

function isAndroidDevice() {
  return /Android/i.test(navigator.userAgent || '');
}

function keepNativeInputVisible() {
  if (isDesktopDevice()) return;

  const root = document.documentElement;

  const setViewportHeight = () => {
    const vv = window.visualViewport;
    const height = vv ? vv.height : window.innerHeight;
    root.style.setProperty('--app-viewport-height', `${height}px`);

    const textEl = document.getElementById('chatText');
    const messages = document.getElementById('messages');

    if (textEl && document.activeElement === textEl) {
      requestAnimationFrame(() => {
        if (messages) messages.scrollTop = messages.scrollHeight;
        textEl.scrollIntoView({ block: 'nearest', behavior: 'auto' });
      });
    }
  };

  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', setViewportHeight);
    window.visualViewport.removeEventListener('scroll', setViewportHeight);
    window.visualViewport.addEventListener('resize', setViewportHeight);
    window.visualViewport.addEventListener('scroll', setViewportHeight);
  }

  window.removeEventListener('resize', setViewportHeight);
  window.addEventListener('resize', setViewportHeight);

  setViewportHeight();
}

async function loginWithAccessCode(code) {
  const clean = String(code || '').trim().toUpperCase();
  if (!clean) throw new Error('Please enter your participant code.');

  const progress = await api('/api/participant/login', {
    method: 'POST',
    body: JSON.stringify({ access_code: clean })
  });

  saveAccessCode(clean);
  state.hadExistingParticipant = hasSavedProgress(progress);
  setProgress(progress);
  route();
  setTimeout(showResumeModalOnce, 150);
}

function renderParticipantLogin(err = '') {
  document.body.dataset.step = 'login';
  renderParticipantLogoutButton();

  const savedCode = localStorage.getItem('participant_access_code') || '';

  app.innerHTML = `<div class="login-page">
    <h2>Login</h2>
    <p class="muted">Enter the anonymous participant code you received by email.</p>
    <div class="section">
      <label><strong>Participant code</strong>
        <input id="participantCode" class="access-code-input" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" value="${htmlEscape(savedCode)}" placeholder="e.g. P001-A7K2">
      </label>
      <p class="muted">Use the same code if you return later or use a different device.</p>
    </div>
    ${err ? errorBox(err) : ''}
  </div>` + actions('<button id="loginParticipant">Continue</button>');

  const input = document.getElementById('participantCode');
  const btn = document.getElementById('loginParticipant');

  input.addEventListener('input', () => {
    input.value = input.value.toUpperCase();
  });

  input.addEventListener('keydown', ev => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      btn.click();
    }
  });

  btn.onclick = async () => {
    try {
      await loginWithAccessCode(input.value);
    } catch (e) {
      renderParticipantLogin(e);
    }
  };

  setTimeout(() => input.focus(), 50);
}

async function init() {
  state.device = detectDevice();
  document.body.dataset.device = state.device;
  state.meta = await api('/api/meta');

  renderHelpButton();

  const hash = location.hash.replace('#', '');
  if (hash === 'researcher') {
    route();
    return;
  }

  const savedCode = localStorage.getItem('participant_access_code');
  const participant_id = localStorage.getItem('participant_id');

  if (savedCode) {
    try {
      await loginWithAccessCode(savedCode);
      return;
    } catch {
      localStorage.removeItem('participant_access_code');
      localStorage.removeItem('participant_id');
    }
  }

  if (participant_id) {
    try {
      state.hadExistingParticipant = true;
      setProgress(await api('/api/session', {
        method: 'POST',
        body: JSON.stringify({ participant_id })
      }));
      route();
      setTimeout(showResumeModalOnce, 150);
      return;
    } catch {
      localStorage.removeItem('participant_id');
    }
  }

  renderParticipantLogin();
}

function route() {
  const hash = location.hash.replace('#', '');

  if (hash === 'researcher') {
    const pageChanged = state.lastRenderedStep !== 'researcher';
    state.lastRenderedStep = 'researcher';
    if (pageChanged) scrollToTopAfterRender();
    return renderResearcherLogin();
  }

  if (!state.progress || !state.participant) {
    return renderParticipantLogin();
  }

  const nextStep = state.progress.current_step || 'consent';
  const pageChanged = state.lastRenderedStep !== nextStep;
  state.lastRenderedStep = nextStep;

  const finishRoute = (renderFn) => {
    const result = renderFn();
    renderParticipantLogoutButton();
    if (pageChanged) scrollToTopAfterRender();
    return result;
  };

  const step = state.progress.current_step || 'consent';
  document.body.dataset.step = step;
  if (step === 'consent') return finishRoute(renderConsent);
  if (step === 'pre') return finishRoute(renderPre);
  if (step === 'big5') return finishRoute(renderBig5);
  if (step === 'topics' || step === 'topic_preferences') return finishRoute(renderTopicsMost);
  if (step === 'chat') return finishRoute(renderChat);
  return finishRoute(renderDone);
}

function renderConsent() {
  app.innerHTML = `<h2>Informed consent form</h2>
    <p>This consent form follows the structure recommended by the HCI informed-consent generator: study basics, procedure, data and privacy, voluntary participation, and research contacts.</p>
    <h3>Study basics</h3>
    <p><strong>Study title:</strong> Personality and demographic questionnaire for text-based interaction research<br>
    <strong>Research context:</strong> Academic HCI thesis research<br>
    <strong>Estimated duration:</strong> approximately 10–15 minutes per short conversation stage<br>
    <strong>Participants:</strong> adults aged 18 or older</p>
    <h3>Purpose and goal of the study</h3>
    <p>The purpose of this study is to collect demographic information, mobile text-communication habits, conversational-AI experience, Big Five personality scores, and multiple short text-based conversations with open-source AI models. The goal is to analyze text-based interaction and engagement in a thesis project.</p>
    <h3>What you will do</h3>
    <ol><li>complete this informed consent form,</li><li>complete a demographic and pre-experiment questionnaire,</li><li>complete the Big Five Inventory questionnaire,</li><li>select topic preferences,</li><li>complete multiple short mobile-style chats with open-source AI models at your own pace.</li></ol>
    <h3>Data and privacy</h3>
    <p>The study stores your questionnaire answers, computed Big Five scores, selected topic preferences, anonymous participant code, and chat messages in a research database. These results are visible only to the protected researcher dashboard and are not shown to participants. The data may be analyzed in aggregated or anonymized form for thesis purposes. Please do not enter identifying information unless explicitly requested.</p>
    <h3>Voluntary participation and withdrawal</h3>
    <p>Participation is voluntary. You may stop at any time. After each completed form or conversation, your progress is saved so that you can leave and resume later from the next step by using the same participant code.</p>
    <h3>Research contact</h3>
    <p>For questions about the study, contact the researcher responsible for this thesis project.</p>
    <div class="section consent-checks">
      <label><input id="c1" type="checkbox"> I confirm that I am at least 18 years old.</label>
      <label><input id="c2" type="checkbox"> I understand that participation is voluntary and that I may stop at any time.</label>
      <label><input id="c3" type="checkbox"> I agree that my questionnaire answers, Big Five scores, topic preferences, anonymous participant code, and chat messages may be saved for research analysis.</label>
    </div>` + actions('<button id="continue" disabled>Save and continue</button>');
  const btn = document.getElementById('continue');
  const update = () => { btn.disabled = !(c1.checked && c2.checked && c3.checked); };
  [c1,c2,c3].forEach(x => x.addEventListener('change', update));
  btn.onclick = async () => {
    const payload = {
      participant_id: state.participant,
      age_confirmed: c1.checked,
      voluntary_participation: c2.checked,
      data_storage_agreed: c3.checked,
      consent_version: 'HCI structured consent with participant-code resume'
    };
    try { setProgress(await api('/api/consent', { method: 'POST', body: JSON.stringify(payload) })); route(); }
    catch (e) { app.insertAdjacentHTML('beforeend', errorBox(e)); }
  };
}

function renderPre(errors = {}) {
  const saved = state.progress.pre || {};
  const usedAI = saved.used_ai_before || '';
  app.innerHTML = `<h2>Pre-experiment questionnaire</h2>
    <p class="muted">This questionnaire takes approximately 3–5 minutes to complete. Your responses will be used for research purposes only and will remain anonymous.</p>
    <h3>Demographics</h3>
    <div class="section"><strong>What is your age group? *</strong>${radioGroup('age_group', ['18-24', '25-34', '35-44', '35 +'], saved.age_group)}${fieldError(errors, 'age_group')}</div>
    <div class="section"><strong>What is your gender? *</strong>${radioGroup('gender', ['Female', 'Male', 'Non-binary / Other', 'Prefer not to say'], saved.gender)}${fieldError(errors, 'gender')}</div>
    <div class="section"><strong>What is your highest level of education? *</strong>${radioGroup('education', ['High school', 'Undergraduate degree', 'Postgraduate degree', 'Other'], saved.education)}${fieldError(errors, 'education')}</div>
    <div class="section"><strong>How often do you use messaging applications (e.g., WhatsApp, Messenger, Viber)? *</strong>${radioGroup('messaging_app_use', ['Less than once per day', '1–3 times per day', '4–10 times per day', 'More than 10 times per day'], saved.messaging_app_use)}${fieldError(errors, 'messaging_app_use')}</div>

    <h3>Mobile Communication Habits</h3>
    <div class="section"><label><strong>How easy do you find it to communicate through text messages? *</strong><input id="text_communication_ease" type="range" min="1" max="5" step="1" value="${htmlEscape(saved.text_communication_ease_1_5 || 3)}"><span class="range-label"><span>Not easy at all</span><strong id="rangeValue">${htmlEscape(saved.text_communication_ease_1_5 || 3)}</strong><span>Very easy</span></span></label></div>
    <p><strong>How frequently do you use the following text messaging styles when you communicate? *</strong></p>
    <p class="muted">Especially when you want to say a lot in your messages, consider whether you typically write everything in one long message or break your thoughts into multiple shorter consecutive messages.</p>
    <div class="section"><strong>One or two words per message *</strong>${radioGroup('style_one_two_words', LIKERT_FREQUENCY, saved.message_style_one_two_words, true)}${fieldError(errors, 'style_one_two_words')}</div>
    <div class="section"><strong>A single sentence per message *</strong>${radioGroup('style_single_sentence', LIKERT_FREQUENCY, saved.message_style_single_sentence, true)}${fieldError(errors, 'style_single_sentence')}</div>
    <div class="section"><strong>A short message (2-3 sentences) *</strong>${radioGroup('style_short_message', LIKERT_FREQUENCY, saved.message_style_short_2_3_sentences, true)}${fieldError(errors, 'style_short_message')}</div>
    <div class="section"><strong>A long detailed message of multiple sentences *</strong>${radioGroup('style_long_message', LIKERT_FREQUENCY, saved.message_style_long_detailed, true)}${fieldError(errors, 'style_long_message')}</div>

    <h3>Experience with Conversational AI</h3>
    <div class="section"><strong>Have you ever used conversational AI assistants to accomplish tasks in the past? *</strong>
      <p class="muted">For example, general-purpose open-source/local assistants such as Gemma-based assistants, or specific-purpose assistants like customer service chatbots.</p>
      ${radioGroup('used_ai_before', ['Yes', 'No'], usedAI)}${fieldError(errors, 'used_ai_before')}
    </div>
    <div id="aiFollowUps"></div>` + actions('<button id="continue" disabled>Continue to Big Five inventory</button>');

  const range = document.getElementById('text_communication_ease');
  range.addEventListener('input', () => document.getElementById('rangeValue').textContent = range.value);
  const aiBox = document.getElementById('aiFollowUps');
  const btn = document.getElementById('continue');

  function collectPre() {
    const aiExperience = {};
    for (const emotion of EMOTIONS) {
      const key = emotion.toLowerCase();
      aiExperience[key] = getRadio(`emotion_${key}`);
    }
    return {
      age_group: getRadio('age_group'),
      gender: getRadio('gender'),
      education: getRadio('education'),
      messaging_app_use: getRadio('messaging_app_use'),
      text_communication_ease_1_5: Number(document.getElementById('text_communication_ease').value),
      message_style_one_two_words: getRadio('style_one_two_words'),
      message_style_single_sentence: getRadio('style_single_sentence'),
      message_style_short_2_3_sentences: getRadio('style_short_message'),
      message_style_long_detailed: getRadio('style_long_message'),
      used_ai_before: getRadio('used_ai_before'),
      ai_use_general_purpose: getRadio('ai_general_purpose'),
      ai_use_specific_purpose: getRadio('ai_specific_purpose'),
      ai_experience_emotions: aiExperience
    };
  }
  function validatePre(answers) {
    let validation = requiredError({
      age_group: answers.age_group,
      gender: answers.gender,
      education: answers.education,
      messaging_app_use: answers.messaging_app_use,
      style_one_two_words: answers.message_style_one_two_words,
      style_single_sentence: answers.message_style_single_sentence,
      style_short_message: answers.message_style_short_2_3_sentences,
      style_long_message: answers.message_style_long_detailed,
      used_ai_before: answers.used_ai_before,
    });
    if (answers.used_ai_before === 'Yes') {
      validation = { ...validation, ...requiredError({ ai_general_purpose: answers.ai_use_general_purpose, ai_specific_purpose: answers.ai_use_specific_purpose }) };
      for (const emotion of EMOTIONS) {
        const key = emotion.toLowerCase();
        if (!answers.ai_experience_emotions[key]) validation[`emotion_${key}`] = 'This question is required.';
      }
    }
    return validation;
  }
  function renderAiFollowups() {
    const value = getRadio('used_ai_before');
    if (value !== 'Yes') { aiBox.innerHTML = ''; updateButton(); return; }
    const emotions = saved.ai_experience_emotions || {};
    aiBox.innerHTML = `<div class="section"><strong>General-purpose AI assistants (e.g. Gemma-based, Llama-based, Mistral-based local assistants) *</strong>${radioGroup('ai_general_purpose', AI_FREQUENCY, saved.ai_use_general_purpose, true)}${fieldError(errors, 'ai_general_purpose')}</div>
      <div class="section"><strong>Specific-purpose AI assistants (e.g. customer service chatbots) *</strong>${radioGroup('ai_specific_purpose', AI_FREQUENCY, saved.ai_use_specific_purpose, true)}${fieldError(errors, 'ai_specific_purpose')}</div>
      <p><strong>Reflecting on your experience in interacting with various AI assistants, how often do you feel... *</strong></p>
      ${EMOTIONS.map(emotion => { const key = emotion.toLowerCase(); return `<div class="section compact"><strong>${htmlEscape(emotion)}</strong>${radioGroup(`emotion_${key}`, LIKERT_FREQUENCY, emotions[key], true)}${fieldError(errors, `emotion_${key}`)}</div>`; }).join('')}`;
    aiBox.querySelectorAll('input[type="radio"]').forEach(el => el.addEventListener('change', updateButton));
    updateButton();
  }
  function updateButton() { btn.disabled = Object.keys(validatePre(collectPre())).length > 0; }
  document.querySelectorAll('input[type="radio"]').forEach(el => el.addEventListener('change', () => { if (el.name === 'used_ai_before') renderAiFollowups(); updateButton(); }));
  renderAiFollowups();
  updateButton();

  btn.onclick = async () => {
    const answers = collectPre();
    const validation = validatePre(answers);
    if (Object.keys(validation).length) return renderPre(validation);
    if (answers.used_ai_before !== 'Yes') {
      answers.ai_use_general_purpose = null;
      answers.ai_use_specific_purpose = null;
      answers.ai_experience_emotions = {};
    }
    try { setProgress(await api('/api/pre', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, answers }) })); route(); }
    catch(e) { renderPre({ form: e.message }); }
  };
}

function renderBig5(err = '') {
  const items = state.meta.bfi_items;
  const saved = state.progress.big5_answers || {};
  app.innerHTML = `<h2>Big Five Inventory (BFI-44)</h2>
    <p class="muted">Please indicate how much you agree or disagree with each statement. Scores are saved for research analysis and are not shown to participants.</p>
    <div class="scale-help"><strong>Likert scale for every item:</strong><br>1 = Disagree strongly | 2 = Disagree a little | 3 = Neither agree nor disagree | 4 = Agree a little | 5 = Agree strongly</div>
    <p><strong>I see myself as someone who...</strong></p>
    <div class="bfi-grid">${Object.entries(items).map(([num, text]) => {
      const current = Number(saved[num] || 3);
      return `<div class="bfi-item"><label><strong>${num}. ${htmlEscape(text)}</strong><input class="bfi-slider" type="range" min="1" max="5" step="1" name="bfi_${num}" value="${current}"><span class="range-label"><span>1</span><strong id="bfi_value_${num}">${current} - ${htmlEscape(BFI_SCALE_LABELS[current])}</strong><span>5</span></span></label></div>`;
    }).join('')}</div>${err ? errorBox(err) : ''}` + actions('<button id="continue">Submit questionnaire</button>');
  document.querySelectorAll('.bfi-slider').forEach(slider => slider.addEventListener('input', () => {
    const num = slider.name.replace('bfi_', '');
    document.getElementById(`bfi_value_${num}`).textContent = `${slider.value} - ${BFI_SCALE_LABELS[slider.value]}`;
  }));
  document.getElementById('continue').onclick = async () => {
    const answers = {};
    for (const num of Object.keys(items)) answers[num] = Number(document.querySelector(`input[name="bfi_${num}"]`).value);
    try { setProgress(await api('/api/big5', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, answers }) })); route(); }
    catch(e) { renderBig5(e); }
  };
}

function topicCards(selected, excluded = []) {
  const topics = state.meta.topics;
  const ids = Object.keys(topics).filter(id => !excluded.includes(id));
  const maxed = selected.length >= 2;
  return `<p class="muted">Selected ${selected.length} / 2</p><div class="topic-grid">${ids.map(id => {
    const t = topics[id];
    const checked = selected.includes(id);
    const disabled = maxed && !checked;
    return `<label class="topic-option ${checked ? 'selected' : ''} ${disabled ? 'disabled' : ''}"><input type="checkbox" name="topic" value="${id}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}> <strong>${id} — ${htmlEscape(t.category)}</strong><br><span class="muted">${htmlEscape(t.example)}</span></label>`;
  }).join('')}</div>`;
}
function getCheckedTopics() { return [...document.querySelectorAll('input[name="topic"]:checked')].map(x => x.value); }
function renderTopicsMost(err = '') {
  const selected = loadDraft('most_interesting_topics', state.progress.most_topics || []);
  app.innerHTML = `<h2>Select the 2 topics you find most interesting</h2><p>Choose exactly 2 topics:</p>${topicCards(selected)}${err ? errorBox(err) : ''}` + actions('<button id="continue" disabled>Continue</button>');
  const btn = document.getElementById('continue');
  function refresh() { const now = getCheckedTopics(); saveDraft('most_interesting_topics', now); renderTopicsMost(err); }
  document.querySelectorAll('input[name="topic"]').forEach(cb => cb.addEventListener('change', refresh));
  btn.disabled = selected.length !== 2;
  btn.onclick = () => renderTopicsLeast(selected, '', true);
}
function renderTopicsLeast(most, err = '', shouldScrollTop = false) {
  if (shouldScrollTop) scrollToTopAfterRender();
  const savedLeast = loadDraft('least_interesting_topics', state.progress.least_topics || []).filter(id => !most.includes(id));
  app.innerHTML = `<h2>Select the 2 topics you find least interesting</h2><p>Choose exactly 2 topics. Your two most-interesting topics are removed from this list.</p>${topicCards(savedLeast, most)}${err ? errorBox(err) : ''}` + actions('<button class="secondary" id="back">Back</button><button id="continue" disabled>Start conversations</button>');
  const btn = document.getElementById('continue');
  function refresh() { const now = getCheckedTopics(); saveDraft('least_interesting_topics', now); renderTopicsLeast(most, err); }
  document.querySelectorAll('input[name="topic"]').forEach(cb => cb.addEventListener('change', refresh));
  btn.disabled = savedLeast.length !== 2;
  document.getElementById('back').onclick = () => { renderTopicsMost(); scrollToTopAfterRender(); };
  btn.onclick = async () => {
    if (savedLeast.length !== 2) return renderTopicsLeast(most, new Error('Please select exactly 2 topics.'));
    try {
      setProgress(await api('/api/topics', { method: 'POST', body: JSON.stringify({ participant_id: state.participant, most_topics: most, least_topics: savedLeast }) }));
      clearDraft('most_interesting_topics'); clearDraft('least_interesting_topics');
      route();
    } catch(e) { renderTopicsLeast(most, e); }
  };
}

async function renderChat(err = '') {
  app.innerHTML = spinnerHtml('Loading chat');
  let data;
  try { data = await api(`/api/chat/${state.participant}`); } catch(e) { app.innerHTML = errorBox(e); return; }

  if (data.done) {
    setProgress(await api(`/api/session`, {
      method: 'POST',
      body: JSON.stringify({ participant_id: state.participant })
    }));
    renderDone();
    return;
  }

  const done = data.conversation_done || data.turns >= data.target_total_turns;
  const desktop = isDesktopDevice();
  const pageClass = desktop ? 'chat-page chat-page--desktop' : 'chat-page chat-page--native';
  const shellClass = desktop ? 'phone-shell' : 'native-chat-shell';
  const screenClass = desktop ? 'phone-screen' : 'native-chat-screen';
  const statusBar = desktop ? `<div class="phone-status-bar"><span class="phone-clock">${iPhoneStatusTime()}</span><span class="phone-status-icons"><span class="wifi-icon" aria-hidden="true">
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
    <path d="M12 18a2 2 0 1 0 0 4a2 2 0 0 0 0-4zm0-4c-2.2 0-4.2.8-5.8 2.1l1.4 1.4c1.2-.9 2.7-1.5 4.4-1.5s3.2.5 4.4 1.5l1.4-1.4C16.2 14.8 14.2 14 12 14zm0-4c-3.4 0-6.5 1.2-9 3.3l1.4 1.4C6.5 12.9 9.1 12 12 12s5.5.9 7.6 2.7l1.4-1.4C18.5 11.2 15.4 10 12 10zm0-4C7.5 6 3.4 7.7.1 10.8l1.4 1.4C4.3 9.6 8 8 12 8s7.7 1.6 10.5 4.2l1.4-1.4C20.6 7.7 16.5 6 12 6z"/>
    </svg></span><span class="battery"><span class="battery-level"></span></span></span></div>` : '';

  const assignment = data.assignment || {};
  const positionText = assignment.conversation_order && assignment.total_conversations
    ? `Conversation ${assignment.conversation_order} of ${assignment.total_conversations}`
    : 'Conversation';

  const inputHtml = done
    ? `<p class="muted chat-complete">${htmlEscape(positionText)} complete.</p>`
    : `<form class="chat-form" id="chatForm"><div class="message-composer"><textarea id="chatText" rows="1" inputmode="text" enterkeyhint="send" autocomplete="off" autocapitalize="sentences" placeholder="Message"></textarea><button aria-label="Send message" type="submit" class="send-btn" disabled><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5"></path><path d="M5.5 11.5L12 5l6.5 6.5"></path></svg></button></div></form>`;

  app.innerHTML = `<div class="${pageClass}">
    <div class="${shellClass}">
      <div class="${screenClass}">
        ${statusBar}
        <div class="phone-header">
          <div class="phone-avatar">A</div>
          <div class="phone-title">Alex</div>
          <div class="muted" style="font-size:12px;margin-top:3px;">${htmlEscape(positionText)}</div>
        </div>
        <div class="phone-messages" id="messages">${visibleTranscript(data.transcript).map(chatMessageHtml).join('')}</div>
        ${inputHtml}
      </div>
    </div>
  </div>${err ? errorBox(err) : ''}` + (done ? actions('<button id="finish">Next conversation</button>') : '');

  scrollMessagesToBottom();
  keepNativeInputVisible();

  clearInterval(window.__phoneClockInterval);
  window.__phoneClockInterval = setInterval(() => {
    const clock = document.querySelector('.phone-clock');
    if (clock) clock.textContent = iPhoneStatusTime();
  }, 30000);

  const form = document.getElementById('chatForm');
  const textEl = document.getElementById('chatText');
  const sendBtn = form ? form.querySelector('.send-btn') : null;

  const sendMessage = async () => {
    const text = textEl.value.trim();
    if (!text) return;

    textEl.value = '';
    updateComposerState(textEl, sendBtn);

    const messages = document.getElementById('messages');
        messages.insertAdjacentHTML(
      'beforeend',
      chatMessageHtml({
        speaker: 'Human',
        text,
        created_at: new Date().toISOString()
      })
    );

    scrollMessagesToBottom();

    try {
      await sleep(readingDelay(text));

      messages.insertAdjacentHTML(
        'beforeend',
        `<div class="message-row Agent typing-row">
          <div class="message-sender">Alex</div>
          <div class="message-line">
            <div class="agent-mini-avatar">A</div>
            <div class="bubble Agent typing" aria-label="Alex is typing">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>`
      );

      scrollMessagesToBottom();

      const result = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          participant_id: state.participant,
          text
        })
      });

      const latestTranscript = result.transcript || [];

      const latestAgent = [...latestTranscript]
        .reverse()
        .find(t => t.speaker === 'Agent' || t.speaker === 'agent');

      const agentParts = splitAgentText(latestAgent?.text || '');

      const typing = messages.querySelector('.typing-row');
      if (typing) typing.remove();

      for (let i = 0; i < agentParts.length; i++) {
        if (i > 0) {
          messages.insertAdjacentHTML(
            'beforeend',
            `<div class="message-row Agent typing-row">
              <div class="message-sender">Alex</div>
              <div class="message-line">
                <div class="agent-mini-avatar">A</div>
                <div class="bubble Agent typing" aria-label="Alex is typing">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>`
          );

          scrollMessagesToBottom();
          await sleep(interBubbleDelay());

          const nextTyping = messages.querySelector('.typing-row');
          if (nextTyping) nextTyping.remove();
        }

        await sleep(writingDelay(agentParts[i]));

        messages.insertAdjacentHTML(
          'beforeend',
          chatMessageHtml({
            speaker: 'Agent',
            text: agentParts[i],
            created_at: new Date().toISOString()
          })
        );

        scrollMessagesToBottom();
      }

      const latestTurns = latestTranscript.length;
      const latestDone = result.conversation_done || result.done || latestTurns >= data.target_total_turns;

      if (latestDone) {
        const formEl = document.getElementById('chatForm');

        if (formEl) {
          formEl.outerHTML = `<p class="muted chat-complete">${htmlEscape(positionText)} complete.</p>`;
        }

        app.insertAdjacentHTML('beforeend', actions('<button id="finish">Next conversation</button>'));
        const finishBtn = document.getElementById('finish');

        if (finishBtn) {
          finishBtn.onclick = async () => {
            const progress = await api(`/api/finish/${state.participant}`, { method: 'POST' });
            renderProgressFromServer(progress);
          };
        }
      } else {
        data.transcript = latestTranscript;
        data.turns = latestTurns;
        textEl.focus({ preventScroll: true });
      }

    } catch (e) {
      const typing = messages.querySelector('.typing-row');
      if (typing) typing.remove();

      messages.insertAdjacentHTML(
        'beforeend',
        chatMessageHtml({
          speaker: 'Agent',
          text: e.message || String(e),
          created_at: new Date().toISOString()
        })
      );

      scrollMessagesToBottom();
    }
  };

  if (form && textEl) {
    form.onsubmit = async (ev) => { ev.preventDefault(); await sendMessage(); };
    updateComposerState(textEl, sendBtn);

    textEl.addEventListener('input', () => {
      updateComposerState(textEl, sendBtn);
      setTimeout(scrollMessagesToBottom, 30);
    });

    textEl.addEventListener('keydown', async (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();

        if (!sendBtn.disabled) {
          form.requestSubmit();
        }
      }
    });

    textEl.addEventListener('focus', () => {
      document.body.classList.add('chat-input-focused');
      keepNativeInputVisible();
      setTimeout(scrollMessagesToBottom, 80);
    });

    textEl.addEventListener('blur', () => {
      document.body.classList.remove('chat-input-focused');
    });
  }

  const finish = document.getElementById('finish');
  if (finish) {
    finish.onclick = async () => {
      const progress = await api(`/api/finish/${state.participant}`, { method: 'POST' });
      renderProgressFromServer(progress);
    };
  }
}

function renderDone() {
  if (participantLabel) participantLabel.textContent = state.participant ? `Participant: ${state.participant}` : '';
  renderParticipantLogoutButton();
  app.innerHTML = `<div class="thank-you"><div class="thank-you-check">✓</div><h2>Thank you!</h2><p>Your responses have been submitted successfully.</p></div>`;
}
function renderResearcherLogin(err = '') {
  const logout = document.getElementById('participantLogoutButton');
  if (logout) logout.remove();

  app.innerHTML = `<h2>Researcher login</h2><label>Password<input type="password" id="password"></label>${err ? errorBox(err) : ''}` + actions('<button id="login">Log in</button>');
  document.getElementById('login').onclick = async () => {
    try { const res = await api('/api/researcher/login', { method:'POST', body: JSON.stringify({ password: document.getElementById('password').value }) }); localStorage.setItem('researcher_token', res.token); renderResearcherDashboard(); } catch(e) { renderResearcherLogin(e); }
  };
}
async function researcherApi(path) { return api(path, { headers: { Authorization: `Bearer ${localStorage.getItem('researcher_token') || ''}` } }); }
async function renderResearcherDashboard(err = '') {
  let data;
  try { data = await researcherApi('/api/researcher/overview'); } catch(e) { return renderResearcherLogin(e); }

  app.innerHTML = `<h2>Researcher dashboard</h2>${err ? errorBox(err) : ''}
    <div class="actions">
      <button id="createCodes">Create participant codes</button>
      <a href="${API}/api/researcher/export.csv" id="exportLink">Download CSV export</a>
    </div>
    <div id="createdCodes"></div>
    <div class="table-wrap"><table><thead><tr><th>Participant</th><th>Access code</th><th>Created</th><th>Step</th><th>Completed</th></tr></thead><tbody>${data.participants.map(p => `<tr><td>${htmlEscape(p.participant_id)}</td><td>${htmlEscape(p.access_code || '')}</td><td>${htmlEscape(p.created_at)}</td><td>${htmlEscape(p.current_step)}</td><td>${p.completed ? 'Yes' : 'No'}</td></tr>`).join('')}</tbody></table></div>`;

  document.getElementById('createCodes').onclick = async () => {
    const raw = prompt('How many participant codes should I create?', '10');
    const count = Number(raw);
    if (!Number.isFinite(count) || count < 1 || count > 200) {
      alert('Enter a number from 1 to 200.');
      return;
    }

    try {
      async function researcherApi(path, options = {}) {
        return api(path, {
          ...options,
          headers: {
            ...(options.headers || {}),
            Authorization: `Bearer ${localStorage.getItem('researcher_token') || ''}`
          }
        });
      }

      const box = document.getElementById('createdCodes');
      box.innerHTML = `<div class="section"><h3>New participant codes</h3><p class="muted">Copy these now and email one code to each participant.</p><textarea readonly rows="8">${htmlEscape((res.codes || []).map(c => c.access_code).join('\n'))}</textarea></div>`;
    } catch (e) {
      renderResearcherDashboard(e);
    }
  };

  document.getElementById('exportLink').onclick = async (ev) => {
    ev.preventDefault();
    const res = await fetch(`${API}/api/researcher/export.csv`, { headers: { Authorization: `Bearer ${localStorage.getItem('researcher_token') || ''}` } });
    const blob = await res.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'llm_engagement_export.csv'; a.click(); URL.revokeObjectURL(url);
  };
}
window.addEventListener('hashchange', route);
init().catch(e => app.innerHTML = errorBox(e));