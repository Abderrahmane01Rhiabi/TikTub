const CHANNEL_COLORS = {
  // Kept distinct from the status colors (accent blue, ok green, warn amber,
  // danger red) so a channel dot is never mistaken for a state.
  meme_culture: '#38bdf8', animeshorts: '#b18cfd', prince_moulay_hassan: '#fb923c',
  lungte888: '#e2e8f0', zit_bliss: '#fd8cc4', lungtemotivates: '#2dd4bf'
};
// Génération's script formats (generative/script_plan.py FORMATS) and plan parts
const SCRIPT_FORMATS = { A: 'Affirmations', B: 'Histoire', D: 'Liste éducative', M: 'Mythe ou réalité',
  C: 'Citation expliquée', E: 'Exercice guidé', L: 'Lettre à toi', P: 'Le saviez-vous (psycho)' };
const SCRIPT_HOOKS = { question: 'question', fait: 'fait surprenant', choc: 'phrase contre-intuitive', scene: 'scène',
  adresse: 'adresse directe', promesse: 'promesse' };
const SCRIPT_ENDINGS = { question: 'question en commentaire', phrase: 'phrase à garder', defi: 'petit défi',
  partage: 'à envoyer à quelqu\'un', repeter: 'affirmation à répéter', chute: 'chute' };
function channelColor(name){ return CHANNEL_COLORS[name] || '#9aa1ac'; }
function esc(s){ return (s ?? '').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function spinnerHtml(text){ return `<span class="spinner-row"><span class="spinner"></span>${esc(text)}</span>`; }

// Every message lands in the "Historique" box; successes and errors also pop
// up as a toast in the corner, where they're actually seen.
function log(msg, cls){
  const el = document.getElementById('log');
  const line = document.createElement('div');
  if (cls) line.className = cls;
  line.textContent = new Date().toLocaleTimeString() + ' — ' + msg;
  el.prepend(line);
  if (cls === 'error' || cls === 'success') toast(msg, cls);
}
function toast(msg, cls){
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${cls || ''}`;
  el.textContent = msg;
  const dismiss = () => { el.classList.add('leaving'); setTimeout(() => el.remove(), 200); };
  el.addEventListener('click', dismiss);
  box.prepend(el);
  while (box.children.length > 4) box.lastChild.remove();
  setTimeout(dismiss, cls === 'error' ? 9000 : 4500);
}

// GETs are plain reads and answer in well under a second: one still pending
// after 20s means the server is down or restarting (uvicorn --reload), and
// the screen should say so instead of spinning forever. Actions
// (POST/PATCH/...) get no timeout — downloads, processing and publishing
// legitimately run for minutes.
const GET_TIMEOUT_MS = 20000;
let staleNoticeShown = false;
function checkBuild(res){
  const serverBuild = res.headers.get('X-TikTub-Build');
  if (staleNoticeShown || !serverBuild || PAGE_BUILD.startsWith('__') || serverBuild === PAGE_BUILD) return;
  staleNoticeShown = true;
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast';
  el.style.cursor = 'default';
  el.innerHTML = `<b>Nouvelle version de TikTub</b><br>Cette page est plus ancienne que le serveur — recharge-la pour éviter des erreurs.
    <div style="margin-top:8px"><button class="btn primary small">Recharger maintenant</button></div>`;
  el.querySelector('button').addEventListener('click', () => location.reload());
  box.prepend(el);
}
async function api(path, options = {}){
  const method = (options.method || 'GET').toUpperCase();
  const controller = new AbortController();
  const timer = method === 'GET' ? setTimeout(() => controller.abort(), GET_TIMEOUT_MS) : null;
  let res;
  try {
    res = await fetch(path, Object.assign({headers:{'Content-Type':'application/json'}, signal: controller.signal}, options));
  } catch (e){
    throw new Error(e.name === 'AbortError'
      ? 'Le serveur ne répond pas (délai dépassé) — il redémarre peut-être. Réessaie dans quelques secondes.'
      : 'Serveur injoignable — vérifie que uvicorn tourne toujours dans le terminal.');
  } finally {
    clearTimeout(timer);
  }
  checkBuild(res);
  if (!res.ok){
    const text = await res.text();
    let detail = text;
    try { const parsed = JSON.parse(text); if (parsed && parsed.detail) detail = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail); } catch (_) {}
    throw new Error(`${res.status} — ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

// A failed screen load shows what went wrong + a retry button, in place of
// its content — never a spinner left running or a misleading empty state.
function showLoadError(el, error, retry){
  if (!el) return;
  el.innerHTML = `<div class="load-error">${icon('alert', 16)}<span style="flex:1;min-width:200px">${esc(error.message)}</span><button class="btn secondary small">${icon('refresh', 13)} Réessayer</button></div>`;
  el.querySelector('button').addEventListener('click', retry);
}
async function safeLoad(fn, containerId){
  try { await fn(); }
  catch (e){
    showLoadError(document.getElementById(containerId), e, () => safeLoad(fn, containerId));
    log(e.message, 'error');
  }
}

let channels = [];
let current = 2;
let currentSpace = 'home';
const screens = document.querySelectorAll('.screen');
const stepBtns = document.querySelectorAll('#stepnav .step');

// Spaces: two sources of videos (Import, Génération) feeding ONE publishing
// pipeline (Publication), plus Accueil / Dashboard / one-time Réglages.
// Numbered screens (data-idx) belong to the space whose range contains them.
const STEP_SPACES = { settings: [0, 1, 11, 12, 13, 14, 8, 9], import: [2, 3, 4, 10], publication: [5, 6, 7] };
const lastStep = { settings: 0, import: 2, publication: 5 };
function spaceOfStep(i){
  return Object.keys(STEP_SPACES).find(k => STEP_SPACES[k].includes(i));
}

function render(){
  const stepSpace = STEP_SPACES[currentSpace] ? currentSpace : null;
  screens.forEach(el => {
    if (el.dataset.idx !== undefined) el.classList.toggle('active', stepSpace !== null && +el.dataset.idx === current);
  });
  document.getElementById('homeScreen').classList.toggle('active', currentSpace === 'home');
  if (currentSpace !== 'dashboard') dashboardScreen.classList.remove('active');
  if (currentSpace !== 'generation') generationScreen.classList.remove('active');
  if (currentSpace !== 'adaptation') document.getElementById('adaptationScreen').classList.remove('active');
  stepBtns.forEach(btn => {
    const i = +btn.dataset.i;
    btn.style.display = btn.dataset.space === stepSpace ? '' : 'none';
    btn.classList.remove('current','done','todo');
    const order = stepSpace ? STEP_SPACES[stepSpace] : [];
    const a = order.indexOf(i), b = order.indexOf(current);
    btn.classList.add(i === current ? 'current' : (a < b ? 'done' : 'todo'));
  });
  document.querySelectorAll('#spacenav .space').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.space === currentSpace));
}

function goTo(i){
  current = i;
  currentSpace = spaceOfStep(i);
  lastStep[currentSpace] = i;
  render();
  onEnterScreen(i);
}

function openSpace(space){
  if (space === 'generation'){ currentSpace = space; render(); openGeneration(); return; }
  if (space === 'adaptation'){ currentSpace = space; render(); openAdaptation(); return; }
  if (space === 'dashboard'){ currentSpace = space; render(); openDashboard(); return; }
  if (STEP_SPACES[space]){ goTo(lastStep[space]); return; }
  currentSpace = 'home';
  render();
  safeLoad(loadHome, 'homeKpis');
}

document.querySelectorAll('#spacenav .space').forEach(btn =>
  btn.addEventListener('click', () => openSpace(btn.dataset.space)));
stepBtns.forEach(btn => btn.addEventListener('click', () => goTo(+btn.dataset.i)));
// Next/prev stay inside the current space; "Suivant" on the last Réglages
// screen returns to Accueil. (Cadrage → Publication goes through its own
// "Traiter" button, which processes the videos first.)
document.querySelectorAll('.next').forEach(btn => btn.addEventListener('click', () => {
  const steps = STEP_SPACES[currentSpace];
  const pos = steps ? steps.indexOf(current) : -1;
  if (pos < 0 || pos >= steps.length - 1){ openSpace('home'); return; }
  goTo(steps[pos + 1]);
}));
document.querySelectorAll('.prev').forEach(btn => btn.addEventListener('click', () => {
  const steps = STEP_SPACES[currentSpace];
  const pos = steps ? steps.indexOf(current) : -1;
  if (pos > 0) goTo(steps[pos - 1]);
}));

const SCREEN_LOADERS = {
  0: [() => loadConnectionScreen(), 'connectGrid'],
  1: [() => loadBackgrounds(), 'backgroundsGrid'],
  2: [() => { pollDownloads(); return refreshDownloadedRow(); }, 'downloadedRow'],
  3: [() => loadSelection(), 'selectionSections'],
  4: [() => loadFrameStep(), 'frameGrid'],
  5: [() => loadResultsScreen(), 'resultsList'],
  6: [() => loadPlanningScreen(), 'scheduleSections'],
  7: [() => loadSummaryFromSchedule(), 'summarySections'],
  8: [() => loadBackups(), 'backupList'],
  9: [() => loadStorage(), 'storageView'],
  10: [() => enterMontageStep(), 'montageList'],
  11: [() => loadMontageSettings(), 'montageSettingsGrid'],
  12: [() => loadBrollLibrary(), 'brollGrid'],
  13: [() => loadVoiceSettings(), 'voiceLibrary'],
  14: [() => loadSfxSettings(), 'sfxList'],
};
function onEnterScreen(i){
  const loader = SCREEN_LOADERS[i];
  if (loader) safeLoad(loader[0], loader[1]);
}
