// ---------- « Ajouter une chaîne » (Réglages → Connexion) ----------
// 1. the Google project (an existing one, or a new OAuth JSON dropped here)
// 2. the Gmail account, in Google's own window
// 3. confirmation — only then is channels/<name>/ created (channel_setup.py)

let addDraft = null;          // { draft_id, project_id, ... } once a project is chosen

function addDialog(){ return document.getElementById('addChannelDialog'); }

function addShell(title, body, foot){
  addDialog().innerHTML = `
    <div class="chcard" style="border:none">
      <div class="chcard-head">
        <div class="who"><div class="name">${esc(title)}</div></div>
        <button class="btn ghost small" data-act="cancel" title="Annuler">${icon('x', 14)}</button>
      </div>
      <div class="chcard-body">${body}<span class="tiny" data-role="err" style="color:var(--danger)"></span></div>
      <div class="chcard-foot">${foot}</div>
    </div>`;
  addDialog().querySelectorAll('[data-act="cancel"]').forEach(b => b.addEventListener('click', cancelAddChannel));
}

function addError(message){
  const err = addDialog().querySelector('[data-role="err"]');
  if (err) err.textContent = message;
}

async function cancelAddChannel(){
  const draft = addDraft;
  addDraft = null;
  addDialog().close();
  if (draft){ try { await api(`/api/channel_drafts/${draft.draft_id}`, { method: 'DELETE' }); } catch (_) {} }
}

async function openAddChannel(){
  addDraft = null;
  addShell('Ajouter une chaîne', spinnerHtml('Chargement des projets Google…'), '');
  addDialog().showModal();
  let data;
  try { data = await api('/api/google_projects'); }
  catch (e){ addError(e.message); return; }
  renderProjectStep(data);
}

// ---- 1. the Google project
function renderProjectStep(data){
  const projects = data.projects || [];
  const list = projects.map((p, k) => {
    const q = p.quota || {};
    const names = p.channels.map(c => `<span style="white-space:nowrap"><span class="dot" style="display:inline-block;vertical-align:middle;background:${channelColor(c.name)}"></span> ${esc(c.display_name)}</span>`).join(', ');
    return `
      <label class="fact" style="align-items:flex-start;padding:8px 0;border-top:1px solid var(--border-soft);cursor:pointer">
        <input type="radio" name="addProject" value="${esc(p.project_key)}" ${k === 0 ? 'checked' : ''} style="margin-top:3px">
        <span style="flex:1;min-width:0"><b style="color:var(--text)">${esc(p.project_id || 'Projet sans nom')}</b><br>
          <span class="tiny">Déjà utilisé par : ${names}</span><br>
          <span class="tiny">Quota aujourd'hui : ${q.uploads_today || 0} upload(s), ≈ ${q.units_used_estimate || 0} / ${data.daily_units} unités${q.exhausted ? ' — épuisé' : ''}</span>
        </span>
      </label>`;
  }).join('');
  const mode = projects.length ? 'existing' : 'new';
  addShell('Ajouter une chaîne — 1. Projet Google', `
    <div class="seg" id="addProjectSeg">
      <button class="seg-opt ${mode === 'existing' ? 'active' : ''}" data-m="existing" ${projects.length ? '' : 'disabled'}>Utiliser un projet existant</button>
      <button class="seg-opt ${mode === 'new' ? 'active' : ''}" data-m="new">Ajouter un nouveau projet</button>
    </div>
    <div data-pane="existing" ${mode === 'existing' ? '' : 'hidden'}>
      <div class="tiny" style="margin:8px 0">Les chaînes d'un même projet Google partagent son quota YouTube du jour : plus il y a de chaînes sur un projet, moins chacune peut publier.</div>
      ${list}
    </div>
    <div data-pane="new" ${mode === 'new' ? '' : 'hidden'}>
      <label class="dropzone" data-role="drop">
        <input type="file" accept=".json,application/json" hidden data-role="file">
        ${icon('upload', 18)}<span>Dépose ici le fichier JSON de Google Cloud<br><span class="tiny">Identifiants → ID client OAuth (« Application de bureau ») → Télécharger le JSON</span></span>
      </label>
      <div class="tiny" data-role="picked"></div>
    </div>`,
    `<button class="btn ghost small" data-act="cancel">Annuler</button>
     <button class="btn primary small push" data-act="next">Continuer</button>`);

  const dlg = addDialog();
  let pickedFile = null;
  dlg.querySelectorAll('#addProjectSeg .seg-opt').forEach(btn => btn.addEventListener('click', () => {
    dlg.querySelectorAll('#addProjectSeg .seg-opt').forEach(b => b.classList.toggle('active', b === btn));
    dlg.querySelectorAll('[data-pane]').forEach(p => { p.hidden = p.dataset.pane !== btn.dataset.m; });
  }));
  const drop = dlg.querySelector('[data-role="drop"]');
  const pick = file => { pickedFile = file; dlg.querySelector('[data-role="picked"]').textContent = file ? `Fichier choisi : ${file.name}` : ''; addError(''); };
  dlg.querySelector('[data-role="file"]').addEventListener('change', ev => pick(ev.target.files[0]));
  drop.addEventListener('dragover', ev => { ev.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', ev => { ev.preventDefault(); drop.classList.remove('over'); pick(ev.dataTransfer.files[0]); });

  dlg.querySelector('[data-act="next"]').addEventListener('click', async ev => {
    const btn = ev.currentTarget;
    const useExisting = dlg.querySelector('#addProjectSeg .seg-opt.active').dataset.m === 'existing';
    addError('');
    btn.disabled = true;
    try {
      if (useExisting){
        const key = (dlg.querySelector('input[name="addProject"]:checked') || {}).value;
        if (!key) throw new Error('Choisis un projet.');
        addDraft = await api('/api/channel_drafts/from_project', { method: 'POST', body: JSON.stringify({ project_key: key }) });
      } else {
        if (!pickedFile) throw new Error('Dépose d\'abord le fichier JSON de Google Cloud.');
        const form = new FormData();
        form.append('file', pickedFile);
        const res = await fetch('/api/channel_drafts/upload', { method: 'POST', body: form });
        const d = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(d.detail || 'Fichier refusé');
        addDraft = d;
      }
      renderConnectStep();
    } catch (e){ addError(e.message); btn.disabled = false; }
  });
}

// ---- 2. the Gmail account, in Google's own window
function renderConnectStep(problem){
  addShell('Ajouter une chaîne — 2. Compte Google', `
    <div class="muted">Projet Google : <b style="color:var(--text)">${esc(addDraft.project_id || '')}</b></div>
    ${problem ? `<div class="fact bad" style="margin-top:10px">${icon('alert')}<span>${esc(problem)}</span></div>` : ''}
    <div class="facts" style="margin-top:10px">
      <div class="fact">${icon('check')}<span>Choisis ton compte Gmail, puis la chaîne si ce compte en gère plusieurs.</span></div>
      <div class="fact">${icon('alert')}<span>Accès refusé ? Ajoute ton Gmail comme <b>utilisateur de test</b> : Google Cloud → Google Auth Platform → Audience → Utilisateurs test.</span></div>
      <div class="fact">${icon('clock')}<span>Pour que la connexion n'expire pas tous les 7 jours, passe le projet en mode <b>« Production »</b> (Audience → Publier l'application).</span></div>
    </div>`,
    `<button class="btn ghost small" data-act="cancel">Annuler</button>
     <button class="btn primary small push" data-act="google">Ouvrir la fenêtre Google</button>`);
  addDialog().querySelector('[data-act="google"]').addEventListener('click', openGoogleWindow);
}

async function openGoogleWindow(ev){
  const btn = ev.currentTarget;
  btn.disabled = true;
  let auth_url;
  try { ({ auth_url } = await api(`/api/channel_drafts/${addDraft.draft_id}/connect`, { method: 'POST' })); }
  catch (e){ addError(e.message); btn.disabled = false; return; }
  const popup = window.open(auth_url, 'oauth_new_channel', 'width=520,height=650');
  if (!popup){ addError('Le navigateur a bloqué la fenêtre Google — autorise les popups pour ce site.'); btn.disabled = false; return; }
  btn.innerHTML = '<span class="spinner"></span> En attente de Google…';
  const poll = setInterval(async () => {
    if (!popup.closed || !addDraft) return;
    clearInterval(poll);
    try {
      addDraft = await api(`/api/channel_drafts/${addDraft.draft_id}`);
      if (addDraft.youtube) renderConfirmStep();
      else renderConnectStep(addDraft.error || 'Connexion non terminée : la fenêtre Google a été fermée avant la fin.');
    } catch (e){ addError(e.message); btn.disabled = false; }
  }, 1000);
}

// ---- 3. confirmation: nothing is written before this
function renderConfirmStep(){
  const yt = addDraft.youtube;
  addShell('Ajouter une chaîne — 3. Confirmer', `
    <div class="fact">${icon('link')}<span>Chaîne YouTube : <b style="color:var(--text)">${esc(yt.title || '')}</b>${yt.custom_url ? ` <span class="tiny">${esc(yt.custom_url)}</span>` : ''}</span></div>
    <label class="f">Nom technique (dossier channels/…, minuscules, chiffres et _)</label>
    <input class="f" data-role="name" value="${esc(yt.suggested_name)}" maxlength="40">
    <label class="f">Nom affiché dans l'app</label>
    <input class="f" data-role="display" dir="auto" value="${esc(yt.display_name)}" maxlength="100">
    <label class="f">Langue de la chaîne</label>
    <select class="f" data-role="lang">
      ${[['fr', 'Français'], ['ar', 'Arabe'], ['en', 'Anglais']].map(([v, l]) => `<option value="${v}" ${v === yt.language ? 'selected' : ''}>${l}</option>`).join('')}
    </select>`,
    `<button class="btn ghost small" data-act="cancel">Annuler</button>
     <button class="btn primary small push" data-act="confirm">Créer la chaîne</button>`);
  const dlg = addDialog();
  dlg.querySelector('[data-act="confirm"]').addEventListener('click', async ev => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    addError('');
    try {
      const created = await api(`/api/channel_drafts/${addDraft.draft_id}/confirm`, { method: 'POST', body: JSON.stringify({
        name: dlg.querySelector('[data-role="name"]').value.trim(),
        display_name: dlg.querySelector('[data-role="display"]').value.trim(),
        language: dlg.querySelector('[data-role="lang"]').value,
      }) });
      addDraft = null;
      dlg.close();
      log(`Chaîne « ${created.display_name} » ajoutée (YouTube : ${created.youtube_title})`, 'success');
      channels = await api('/api/channels');           // everywhere in the app, no restart
      renderUrlsGrid();
      openChannelSettings(created.name);
    } catch (e){ addError(e.message); btn.disabled = false; }
  });
}

document.getElementById('addChannelBtn').addEventListener('click', openAddChannel);
