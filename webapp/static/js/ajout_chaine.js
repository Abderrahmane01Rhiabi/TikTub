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

// ---- 2. the Gmail account (filled in by the next step of the feature)
function renderConnectStep(){
  addShell('Ajouter une chaîne — 2. Compte Google',
    `<div class="muted">Projet : <b>${esc(addDraft.project_id || '')}</b></div>`,
    `<button class="btn ghost small" data-act="cancel">Annuler</button>`);
}

document.getElementById('addChannelBtn').addEventListener('click', openAddChannel);
