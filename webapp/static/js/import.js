// ---------- Step 0 : Connect channels ----------

function connectionCardHtml(ch){
  return `
    <article class="chcard" data-channel="${ch.name}">
      <div class="chcard-head">
        <div class="who">
          <div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div>
          ${ch.google_account_email ? `<div class="meta">${esc(ch.google_account_email)}</div>` : ''}
        </div>
        ${ch.has_credentials
          ? '<span class="pill wait" data-role="pill">Vérification…</span>'
          : '<span class="pill bad" data-role="pill">Pas de credentials</span>'}
      </div>
      <div class="chcard-body conn-body">
        ${ch.has_credentials
          ? `<div class="muted">${spinnerHtml('Vérification de la connexion…')}</div>`
          : `<div class="muted">Ajoute le fichier <code>channels/${esc(ch.name)}/credentials.json</code> (Google Cloud Console → Identifiants OAuth).</div>`}
      </div>
      <div class="chcard-foot" data-role="foot"></div>
    </article>`;
}

async function loadConnectionScreen(){
  const grid = document.getElementById('connectGrid');
  grid.innerHTML = channels.map(connectionCardHtml).join('');

  await Promise.all(channels.filter(ch => ch.has_credentials).map(async ch => {
    const body = grid.querySelector(`[data-channel="${ch.name}"] .conn-body`);
    try {
      const status = await api(`/api/channels/${ch.name}/connection_status`);
      connectionCache[ch.name] = { at: Date.now(), status };
      renderConnectionBody(body, ch, status);
    } catch (e){
      renderConnectionBody(body, ch, { state: 'error', reason: e.message });
    }
  }));
}

// `body` is the card's .conn-body; the pill and the footer of the same card
// are filled in too.
function renderConnectionBody(body, ch, status){
  const card = body.closest('.chcard');
  const pill = card.querySelector('[data-role="pill"]');
  const foot = card.querySelector('[data-role="foot"]');
  const ytLine = status.youtube_channel_title
    ? `<div class="fact">${icon('link')}<span>Chaîne YouTube liée : <b style="color:var(--text)">${esc(status.youtube_channel_title)}</b></span></div>` : '';
  let pillCls, pillHtml, bodyHtml, btnCls = 'secondary', btnLabel = 'Reconnecter';

  if (status.connected && status.can_edit){
    pillCls = 'ok'; pillHtml = `${icon('check', 11)} Connectée`;
    bodyHtml = `<div class="facts">${ytLine}</div>`;
  } else if (status.connected){
    pillCls = 'warn'; pillHtml = 'Permissions limitées';
    bodyHtml = `<div class="facts">${ytLine}</div><div class="muted">Upload OK, mais l'édition depuis le Dashboard est indisponible.</div>`;
    btnCls = 'primary'; btnLabel = "Reconnecter (activer l'édition)";
  } else if (status.state === 'expired'){
    pillCls = 'warn'; pillHtml = 'Connexion expirée';
    bodyHtml = `<div class="muted">${esc(status.reason || '')}</div>
      <div class="tiny">Si ça revient chaque semaine : ton projet Google Cloud est en mode « Test » — publie-le dans Google Auth Platform → Audience.</div>`;
    btnCls = 'primary'; btnLabel = 'Se reconnecter';
  } else if (status.state === 'error'){
    pillCls = 'bad'; pillHtml = 'Vérification impossible';
    bodyHtml = `<div class="muted">${esc(status.reason || '')}</div>`;
  } else {
    pillCls = 'bad'; pillHtml = 'Jamais connectée';
    bodyHtml = `<div class="muted">Connecte le compte Google qui gère cette chaîne.</div>`;
    btnCls = 'primary'; btnLabel = 'Se connecter';
  }

  pill.className = `pill ${pillCls}`;
  pill.innerHTML = pillHtml;
  body.innerHTML = bodyHtml;
  foot.innerHTML = `<button class="btn ${btnCls} small connect-btn">${esc(btnLabel)}</button>`;
  foot.querySelector('.connect-btn').addEventListener('click', () => startConnect(ch, body));
}

async function startConnect(ch, card){
  try {
    const { auth_url } = await api(`/api/channels/${ch.name}/connect/start`, { method:'POST' });
    const popup = window.open(auth_url, 'oauth_' + ch.name, 'width=520,height=650');
    if (!popup){ log('Le navigateur a bloqué la popup — autorise les popups pour ce site.', 'error'); return; }

    const poll = setInterval(async () => {
      if (popup.closed){
        clearInterval(poll);
        try {
          const status = await api(`/api/channels/${ch.name}/connection_status`);
          connectionCache[ch.name] = { at: Date.now(), status };
          renderConnectionBody(card, ch, status);
          if (status.connected) log(`${ch.display_name} connectée : ${status.youtube_channel_title}`, 'success');
        } catch (e){ log(e.message, 'error'); }
      }
    }, 1000);
  } catch (e){ log(e.message, 'error'); }
}

// ---------- Step 1 : URLs & download ----------

function countLinks(text){
  return text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#')).length;
}

function renderUrlsGrid(){
  const grid = document.getElementById('urlsGrid');
  grid.innerHTML = channels.map(ch => `
    <article class="chcard">
      <div class="chcard-head">
        <div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div></div>
        <span class="pill wait" id="links-${ch.name}">0 lien</span>
      </div>
      <div class="chcard-body">
        <textarea class="urls" data-channel="${ch.name}" placeholder="https://www.tiktok.com/@.../video/...&#10;https://www.instagram.com/reel/..."></textarea>
        <div class="dl-progress" id="dlprog-${ch.name}"></div>
      </div>
      <div class="chcard-foot"><span class="note" id="status-${ch.name}">${ch.ready ? 'Rien à télécharger.' : '⚠ Pas de credentials OAuth pour cette chaîne'}</span></div>
    </article>
  `).join('');
  grid.querySelectorAll('textarea.urls').forEach(area => area.addEventListener('input', () => {
    const n = countLinks(area.value);
    const pill = document.getElementById(`links-${area.dataset.channel}`);
    pill.textContent = `${n} lien${n > 1 ? 's' : ''}`;
    pill.className = `pill ${n ? 'ok' : 'wait'}`;
  }));
}

// Downloads run in the background (POST /api/downloads); each channel card
// follows its own links live from GET /api/download_status — also after a
// page reload, since the job lives on the server.
let downloadPollTimer = null;
let downloadSeenRunning = false;

document.getElementById('downloadAllBtn').addEventListener('click', async () => {
  const areas = Array.from(document.querySelectorAll('#urlsGrid textarea.urls')).filter(t => t.value.trim());
  if (!areas.length){ log('Colle au moins un lien dans une chaîne.', 'error'); return; }
  const dlBtn = document.getElementById('downloadAllBtn');
  dlBtn.disabled = true;
  dlBtn.innerHTML = '<span class="spinner"></span> Téléchargement…';

  const batchIds = [];
  for (const area of areas){
    const channelName = area.dataset.channel;
    const statusEl = document.getElementById(`status-${channelName}`);
    try {
      const { batch_id } = await api(`/api/channels/${channelName}/urls`, { method:'POST', body: JSON.stringify({ text: area.value }) });
      batchIds.push(batch_id);
      area.value = '';
      area.dispatchEvent(new Event('input')); // reset the "N liens" pill
    } catch (e){
      statusEl.textContent = 'Liens refusés';
      log(`${channelName}: ${e.message}`, 'error');
    }
  }
  if (!batchIds.length){ resetDownloadButton(); return; }
  try {
    const r = await api('/api/downloads', { method:'POST', body: JSON.stringify({ batch_ids: batchIds }) });
    if (!r.started && !r.running){ log('Aucun lien à télécharger.', 'error'); resetDownloadButton(); return; }
    downloadSeenRunning = true;
    pollDownloads();
  } catch (e){ log(e.message, 'error'); resetDownloadButton(); }
});

function resetDownloadButton(){
  const dlBtn = document.getElementById('downloadAllBtn');
  dlBtn.disabled = false;
  dlBtn.innerHTML = `${icon('download', 15)} Télécharger`;
}

const DL_ICONS = { waiting: '·', running: null, done: '✓', failed: '✗', duplicate: '↺' };

function renderDownloadJob(job){
  const items = job.items || [];
  channels.forEach(ch => {
    const mine = items.filter(i => i.channel === ch.name);
    const box = document.getElementById(`dlprog-${ch.name}`);
    const statusEl = document.getElementById(`status-${ch.name}`);
    if (!box || !statusEl) return;
    if (!mine.length){ box.innerHTML = ''; return; }
    const finished = mine.filter(i => ['done', 'failed', 'duplicate'].includes(i.state)).length;
    const ok = mine.filter(i => i.state === 'done').length;
    const failed = mine.filter(i => i.state === 'failed').length;
    const dup = mine.filter(i => i.state === 'duplicate').length;
    const pct = Math.round(finished / mine.length * 100);
    box.innerHTML = `
      <div class="pjob">
        <div class="pjob-line"><span>${finished < mine.length ? 'Téléchargement…' : 'Terminé'}</span><b>${finished}/${mine.length}</b></div>
        <div class="pbar"><div style="width:${pct}%"></div></div>
      </div>
      <div class="dl-items">${mine.map(i => `
        <div class="dl-item ${i.state}">
          <span class="ic">${i.state === 'running' ? '<span class="spinner"></span>' : DL_ICONS[i.state]}</span>
          <span class="u" title="${esc(i.url)}">${esc(sourceLabel(i.url))}</span>
          ${i.message && i.state === 'running' ? `<span class="m">${esc(i.message)}</span>` : ''}
          ${i.message && (i.state === 'failed' || i.state === 'duplicate')
            ? `<span class="why" title="${esc(i.detail || i.message)}">${esc(i.message)}</span>` : ''}
          ${i.state === 'failed'
            ? `<span class="fix"><button class="btn secondary small" data-upload-source="${esc(i.id)}" title="Tu as la vidéo sur ton ordinateur ? Dépose-la ici, elle continuera comme si le téléchargement avait marché.">${icon('upload', 12)} Déposer le fichier</button></span>` : ''}
        </div>`).join('')}</div>`;
    statusEl.textContent = finished < mine.length
      ? `${finished}/${mine.length} terminée(s)…`
      : [ok && `✓ ${ok} téléchargée(s)`, failed && `✗ ${failed} échec(s)`, dup && `↺ ${dup} doublon(s)`].filter(Boolean).join(' · ');
  });
}

async function pollDownloads(){
  clearTimeout(downloadPollTimer);
  let job;
  try { job = await api('/api/download_status'); }
  catch (e){ downloadPollTimer = setTimeout(pollDownloads, 3000); return; }
  if (!job.key) return;
  renderDownloadJob(job);
  if (!job.done){
    const dlBtn = document.getElementById('downloadAllBtn');
    dlBtn.disabled = true;
    dlBtn.innerHTML = '<span class="spinner"></span> Téléchargement…';
    downloadSeenRunning = true;
    downloadPollTimer = setTimeout(pollDownloads, 1000);
    return;
  }
  resetDownloadButton();
  if (downloadSeenRunning){
    downloadSeenRunning = false;
    const items = job.items || [];
    const ok = items.filter(i => i.state === 'done').length;
    const failed = items.filter(i => i.state === 'failed').length;
    if (job.error) log(`Téléchargement interrompu : ${job.error}`, 'error');
    else log(`${ok} vidéo(s) téléchargée(s)${failed ? ` · ${failed} échec(s), voir les cartes` : ''}`, failed ? 'error' : 'success');
    safeLoad(refreshDownloadedRow, 'downloadedRow');
  }
}

async function refreshDownloadedRow(){
  const videos = await api('/api/videos?status=selected');
  const byChannel = {};
  videos.forEach(v => { (byChannel[v.channel] ||= []).push(v); });

  const row = document.getElementById('downloadedRow');
  const count = document.getElementById('downloadedCount');
  count.textContent = `${videos.length} vidéo${videos.length > 1 ? 's' : ''}`;
  count.className = `pill ${videos.length ? 'ok' : 'wait'}`;
  const withVideos = channels.filter(ch => byChannel[ch.name]?.length);
  if (!withVideos.length){ row.innerHTML = '<span class="tiny">Rien téléchargé pour l\'instant — colle des liens ci-dessus puis clique « Télécharger ».</span>'; return; }

  row.innerHTML = withVideos.map(ch => `
    <div class="dl-group">
      <div class="lbl"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)} · ${byChannel[ch.name].length}</div>
      <div class="thumbs">${byChannel[ch.name].map(v => `
        <div class="thumb" title="${esc(v.title || '')}" style="background:linear-gradient(160deg,${channelColor(ch.name)},#171a21 120%)">
          ${v.media_url ? `<video src="${v.media_url}" muted></video>` : ''}
          <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7-11-7z" fill="white" opacity=".9"/></svg>
        </div>`).join('')}
      </div>
    </div>
  `).join('');
}

// ---------- Step 2 : Selection ----------

async function loadSelection(){
  const videos = await api('/api/videos');
  const relevant = videos.filter(v => ['selected','rejected'].includes(v.status));
  const byChannel = {};
  relevant.forEach(v => { (byChannel[v.channel] ||= []).push(v); });

  const wrap = document.getElementById('selectionSections');
  const withVideos = channels.filter(ch => byChannel[ch.name]?.length);
  if (!withVideos.length){
    wrap.innerHTML = emptyState('Aucune vidéo à trier', 'Télécharge des vidéos à l\'étape 1 · URLs.', 'inbox');
  } else {
    wrap.innerHTML = withVideos.map(ch => {
      const vids = byChannel[ch.name];
      const allSelected = vids.every(v => v.status === 'selected');
      return `
      <article class="chcard" data-channel="${ch.name}">
        <div class="chcard-head">
          <div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div></div>
          <div style="display:flex;align-items:center;gap:12px">
            <span class="pill ok" data-role="selcount"></span>
            <label class="switch"><input type="checkbox" class="selall-cb" data-channel="${ch.name}" ${allSelected?'checked':''}> Tout</label>
          </div>
        </div>
        <div class="vgrid">${vids.map(v => `
          <div class="vcard" data-video="${v.video_id}">
            <div class="vthumb" style="background:linear-gradient(160deg,${channelColor(ch.name)},#171a21 120%)">
              ${v.media_url ? `<video src="${v.media_url}" muted></video>` : ''}
              <div class="check sel-check ${v.status==='selected'?'':'off'}" data-video="${v.video_id}">
                <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round"><path d="M5 13l4 4L19 7"/></svg>
              </div>
            </div>
            <div class="vtitle">${esc(v.title)}</div>
          </div>`).join('')}
        </div>
      </article>`;
    }).join('');
  }

  document.querySelectorAll('.sel-check').forEach(el => el.addEventListener('click', async () => {
    const nowSelected = el.classList.contains('off');
    el.classList.toggle('off', !nowSelected);
    try { await api(`/api/videos/${el.dataset.video}/select`, { method:'POST', body: JSON.stringify({selected: nowSelected}) }); }
    catch (e){ log(e.message, 'error'); }
    updateSelCount();
  }));
  document.querySelectorAll('.selall-cb').forEach(cb => cb.addEventListener('change', async () => {
    const targets = byChannel[cb.dataset.channel].map(v => v.video_id);
    for (const vid of targets){
      const check = document.querySelector(`.sel-check[data-video="${vid}"]`);
      check.classList.toggle('off', !cb.checked);
      await api(`/api/videos/${vid}/select`, { method:'POST', body: JSON.stringify({selected: cb.checked}) });
    }
    updateSelCount();
  }));
  updateSelCount();
}
function updateSelCount(){
  const total = document.querySelectorAll('.sel-check').length;
  const selected = document.querySelectorAll('.sel-check:not(.off)').length;
  document.getElementById('selCountText').textContent = `Import · étape 2 sur 4 · ${selected}/${total} sélectionnées`;
  document.querySelectorAll('#selectionSections .chcard').forEach(card => {
    const t = card.querySelectorAll('.sel-check').length;
    const n = card.querySelectorAll('.sel-check:not(.off)').length;
    const pill = card.querySelector('[data-role="selcount"]');
    pill.textContent = `${n}/${t} gardée${n > 1 ? 's' : ''}`;
    pill.className = `pill ${n ? 'ok' : 'wait'}`;
  });
}

// ---------- Step 4 : Frame positioning (cadrage) ----------

const FRAME_MODES = [
  { key: 'letterbox', label: 'Haut/bas', title: 'Bordure en haut et en bas seulement — la vidéo garde toute sa largeur' },
  { key: 'full_border', label: '4 côtés', title: 'Bordure sur les 4 côtés — la vidéo est centrée, légèrement réduite' },
  { key: 'fill', label: 'Plein cadre', title: "La vidéo remplit tout le cadre — aucune bordure visible, quitte à rogner un peu les bords" }
];

async function loadFrameStep(){
  const grid = document.getElementById('frameGrid');
  grid.innerHTML = spinnerHtml('Chargement...');
  const videos = await api('/api/videos?status=selected');
  if (!videos.length){ grid.innerHTML = emptyState('Aucune vidéo à cadrer', 'Garde au moins une vidéo à l\'étape 2 · Sélection.', 'film'); return; }

  grid.innerHTML = videos.map(v => {
    const ch = channels.find(c => c.name === v.channel) || { display_name: v.channel };
    return `
    <article class="chcard" data-video="${v.video_id}">
      <div class="chcard-head">
        <div class="who">
          <div class="name" style="font-size:13px"><span class="dot" style="background:${channelColor(v.channel)}"></span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.title || 'Vidéo')}</span></div>
          <div class="meta">${esc(ch.display_name)}</div>
        </div>
      </div>
      <div class="chcard-body">
        ${segHtml('mode-seg', { simple: 'Habillage simple', montage: 'Montage auto' }, v.edit_mode)}
      </div>
      <div class="chcard-body frame-body simple-only">
        <div class="fpreview-box">
          <div class="fpreview-spinner"><span class="spinner"></span></div>
          <img class="fpreview-img" alt="Aperçu du cadrage">
        </div>
        <div class="seg fmode-seg">
          ${FRAME_MODES.map(m => `<button class="seg-opt" data-mode="${m.key}" title="${esc(m.title)}">${m.label}</button>`).join('')}
        </div>
      </div>
      <div class="chcard-foot simple-only"><label class="switch"><input type="checkbox" class="rounded-check"> Coins arrondis</label></div>
      <div class="chcard-body montage-only"></div>
    </article>`;
  }).join('');

  for (const v of videos){
    const card = grid.querySelector(`[data-video="${v.video_id}"]`);
    let cur = v;
    const showMode = (mode) => {
      card.querySelectorAll('.simple-only').forEach(el => el.style.display = mode === 'simple' ? '' : 'none');
      card.querySelectorAll('.montage-only').forEach(el => el.style.display = mode === 'montage' ? '' : 'none');
      if (mode === 'montage') fillMontageCadrage(card, cur, u => { cur = u; });
    };
    showMode(v.edit_mode);
    wireSeg(card, 'mode-seg', async mode => {
      showMode(mode);
      try { cur = await api(`/api/videos/${v.video_id}/montage`, { method:'PATCH', body: JSON.stringify({edit_mode: mode}) }); }
      catch (e){ log(e.message, 'error'); }
      if (mode === 'montage') fillMontageCadrage(card, cur, u => { cur = u; });
    });
    let mode = v.frame_mode;
    try {
      const s = await api(`/api/videos/${v.video_id}/frame_suggestion`);
      if (!mode) mode = s.suggested_frame_mode;
    } catch (e){ /* not downloaded / unreadable — fall back below */ }

    renderFrameCard(card, v.video_id, mode || 'full_border', !!v.rounded_corners);

    if (!v.frame_mode && mode){
      // Persist the auto-suggestion right away so process_selected always has
      // an explicit choice, even for videos the user never touches here.
      api(`/api/videos/${v.video_id}/frame_mode`, { method:'PATCH', body: JSON.stringify({frame_mode: mode}) }).catch(()=>{});
    }
  }
}

function renderFrameCard(card, videoId, mode, rounded){
  const img = card.querySelector('.fpreview-img');
  const spinner = card.querySelector('.fpreview-spinner');
  spinner.style.display = 'flex';
  img.classList.remove('loaded');
  img.onload = () => { spinner.style.display = 'none'; img.classList.add('loaded'); };
  img.onerror = () => { spinner.style.display = 'none'; };
  img.src = `/api/videos/${videoId}/frame_preview?frame_mode=${mode}&rounded_corners=${rounded}&t=${Date.now()}`;

  card.querySelectorAll('.fmode-seg .seg-opt').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
    btn.onclick = async () => {
      renderFrameCard(card, videoId, btn.dataset.mode, rounded);
      try {
        await api(`/api/videos/${videoId}/frame_mode`, { method:'PATCH', body: JSON.stringify({frame_mode: btn.dataset.mode, rounded_corners: rounded}) });
      } catch (e){ log(e.message, 'error'); }
    };
  });

  const checkbox = card.querySelector('.rounded-check');
  checkbox.checked = rounded;
  checkbox.onchange = async () => {
    renderFrameCard(card, videoId, mode, checkbox.checked);
    try {
      await api(`/api/videos/${videoId}/frame_mode`, { method:'PATCH', body: JSON.stringify({frame_mode: mode, rounded_corners: checkbox.checked}) });
    } catch (e){ log(e.message, 'error'); }
  };
}

// ---------- Montage auto (shared pieces) ----------

const MONTAGE_CAPTION_LABELS = { cascade: 'Cascade', accent: 'Accent' };
const MONTAGE_VOLUME_LABELS = { doux: 'Doux', marque: 'Marqué' };

function segHtml(cls, options, active){
  return `<div class="seg ${cls}">${Object.entries(options).map(([k, l]) =>
    `<button class="seg-opt ${k === active ? 'active' : ''}" data-v="${k}">${esc(l)}</button>`).join('')}</div>`;
}
function wireSeg(root, cls, onPick){
  root.querySelectorAll(`.${cls} .seg-opt`).forEach(b => b.onclick = () => {
    root.querySelectorAll(`.${cls} .seg-opt`).forEach(x => x.classList.toggle('active', x === b));
    onPick(b.dataset.v);
  });
}
function fmtSec(x){
  const n = Math.max(0, Number(x) || 0), m = Math.floor(n / 60), s = Math.round((n - m * 60) * 10) / 10;
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}
function capSampleHtml(style){
  return style === 'accent'
    ? '<div class="capsample"><span class="l1">Why</span><span class="l2 k">hackers</span><span class="l3">never</span></div>'
    : '<div class="capsample"><span class="l1">never</span><span class="l2">do</span><span class="l3">anything</span></div>';
}

// Style of ONE video: caption style + music volume, starting from its
// channel's defaults (Réglages → Montage); a change becomes an override.
function montageStyleHtml(v){
  const s = v.montage_settings || {};
  const custom = Object.keys(v.montage_overrides || {}).length;
  return `<div class="mstyle">
    <div class="mstyle-row"><span>Sous-titres</span>${segHtml('ms-cap', MONTAGE_CAPTION_LABELS, s.caption_style)}</div>
    <div class="mstyle-row"><span>Musique</span>${segHtml('ms-vol', MONTAGE_VOLUME_LABELS, s.volume)}
      <span class="tiny">${s.music_file ? `${esc(s.music_file)} · à ${fmtSec(s.music_entry)}` : 'aucune (Réglages → Montage)'}</span></div>
    ${custom ? '<div class="mstyle-row"><span></span><button class="btn ghost small ms-reset">↺ Revenir au style de la chaîne</button></div>' : ''}
  </div>`;
}
function wireMontageStyle(root, v, onChange){
  const patch = async body => {
    try { onChange(await api(`/api/videos/${v.video_id}/montage`, { method:'PATCH', body: JSON.stringify(body) })); }
    catch (e){ log(e.message, 'error'); }
  };
  wireSeg(root, 'ms-cap', val => patch({ overrides: { ...(v.montage_overrides || {}), caption_style: val } }));
  wireSeg(root, 'ms-vol', val => patch({ overrides: { ...(v.montage_overrides || {}), volume: val } }));
  const reset = root.querySelector('.ms-reset');
  if (reset) reset.onclick = () => patch({ overrides: {} });
}

function fillMontageCadrage(card, v, onUpdate){
  const box = card.querySelector('.montage-only');
  const validated = v.montage && v.montage.validated;
  box.innerHTML = `
    <div class="mlayout" style="grid-template-columns:120px minmax(0,1fr)">
      <div class="mvideo">${v.media_url ? `<video src="${v.media_url}" muted controls preload="metadata"></video>` : ''}</div>
      <div class="mfields" style="gap:10px">
        ${montageStyleHtml(v)}
        <div class="mstate ${validated ? 'ok' : ''}">${validated
          ? '✓ Montage validé : il sera monté au prochain « Traiter ».'
          : "L'IA préparera le montage quand tu cliqueras « Traiter ». Tu le vérifieras ensuite à l'étape 4 · Montage."}</div>
      </div>
    </div>`;
  wireMontageStyle(box, v, u => { onUpdate(u); fillMontageCadrage(card, u, onUpdate); });
}

// ---------- Step 4 · Montage : review each planned montage ----------
// Cards are re-rendered only when a video's state changes (planning →
// review, validated...), never on a poll tick, so a hook being typed or a
// preview playing isn't wiped every few seconds.
let montagePollTimer = null;
const montageCardState = {};
const montageCardKey = v => `${v.status}|${v.montage ? v.montage.error || '' : ''}|${v.montage && v.montage.hooks ? v.montage.hooks.join('/') : ''}`;

function enterMontageStep(){
  // entering the screen: rebuild every card from the server state
  document.getElementById('montageList').innerHTML =
    '<div id="montageProgress"></div><div class="stack" id="montageCards"></div><div id="montageValidated"></div>';
  for (const k in montageCardState) delete montageCardState[k];
  return loadMontageStep();
}

async function loadMontageStep(){
  clearTimeout(montagePollTimer);
  if (!document.getElementById('montageCards')) return enterMontageStep();
  const [status, all] = await Promise.all([api('/api/process_status'), api('/api/videos')]);
  const running = status.key && !status.done;
  document.getElementById('montageProgress').innerHTML = running ? `
    <article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${spin('')} Traitement en cours</div>
      <div class="meta" style="margin-left:0">${esc(status.title || '')}</div></div>
      <span class="pill wait">vidéo ${Math.min(status.index + 1, status.total)} sur ${status.total}</span></div>
      <div class="chcard-body">${progressBarHtml(status, PROCESS_PHASES[status.phase] || 'Traitement')}</div></article>` : '';

  const shown = all.filter(v => ['montage_planning', 'montage_review'].includes(v.status));
  const cards = document.getElementById('montageCards');
  for (const id of Object.keys(montageCardState)){
    if (!shown.some(v => v.video_id === id)){ cards.querySelector(`[data-video="${id}"]`)?.remove(); delete montageCardState[id]; }
  }
  for (const v of shown){
    const key = montageCardKey(v);
    if (montageCardState[v.video_id] === key) continue;
    montageCardState[v.video_id] = key;
    let card = cards.querySelector(`[data-video="${v.video_id}"]`);
    if (!card){ card = document.createElement('article'); card.className = 'chcard mcard'; card.dataset.video = v.video_id; cards.appendChild(card); }
    renderMontageCard(card, v);
  }
  if (!shown.length && !running){
    cards.innerHTML = emptyState('Aucun montage à vérifier', "Choisis « Montage auto » pour une vidéo à l'étape 3 · Cadrage, puis clique « Traiter ».", 'film');
  } else if (cards.querySelector('.empty-state') && shown.length){ cards.querySelector('.empty-state').remove(); }

  const validated = all.filter(v => v.status === 'selected' && v.edit_mode === 'montage' && v.montage && v.montage.validated);
  document.getElementById('montageValidated').innerHTML = validated.length ? `
    <article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${icon('check', 14)} ${validated.length} montage${validated.length > 1 ? 's validés' : ' validé'}, prêt${validated.length > 1 ? 's' : ''} à être monté${validated.length > 1 ? 's' : ''}</div>
      <div class="meta" style="margin-left:0">${validated.map(v => esc(v.title)).join(' · ')}</div></div></div></article>` : '';
  const btn = document.getElementById('renderMontagesBtn');
  btn.disabled = !validated.length || running;
  btn.textContent = validated.length ? `Monter ${validated.length} vidéo${validated.length > 1 ? 's' : ''} validée${validated.length > 1 ? 's' : ''} →` : 'Monter les vidéos validées →';
  document.getElementById('montageCountText').textContent =
    `Import · étape 4 sur 4 · ${shown.filter(v => v.status === 'montage_review').length} à vérifier`;

  if (running || shown.some(v => v.status === 'montage_planning')){
    montagePollTimer = setTimeout(() => { if (currentSpace === 'import' && current === 10) safeLoad(loadMontageStep, 'montageCards'); }, 2500);
  }
}

function timelineHtml(t){
  if (!t || !t.total) return '';
  const pct = x => `${Math.max(0, Math.min(100, x / t.total * 100)).toFixed(2)}%`;
  const segs = t.segments.map(sg => `<div class="seg-${sg.kind}" style="left:${pct(sg.start)};width:calc(${pct(sg.end)} - ${pct(sg.start)})" title="${sg.kind === 'noir' ? 'Écran noir' : 'Drone'} ${fmtSec(sg.start)} → ${fmtSec(sg.end)}"></div>`).join('');
  const cuts = (t.cuts || []).map(c => `<div class="cut" style="left:${pct(c)}" title="Coupe à ${fmtSec(c)}"></div>`).join('');
  const chute = t.chute != null ? `<div class="chute" style="left:${pct(t.chute)}" title="Chute à ${fmtSec(t.chute)}"></div>` : '';
  return `<div class="tl">${segs}${cuts}${chute}</div>
    <div class="tl-legend"><span><i style="background:#2a3b5c"></i>Vidéo</span><span><i style="background:#000;border:1px solid #555"></i>Écran noir</span>
      <span><i style="background:#3a7fb8"></i>Drones</span><span><i style="background:#f5c56d"></i>Chute</span>${cuts ? '<span>┊ coupe</span>' : ''}</div>`;
}

function renderMontageCard(card, v){
  const ch = channels.find(c => c.name === v.channel) || { display_name: v.channel };
  const m = v.montage || {};
  const head = `<div class="chcard-head"><div class="who">
      <div class="name" style="font-size:13px"><span class="dot" style="background:${channelColor(v.channel)}"></span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.title || 'Vidéo')}</span></div>
      <div class="meta">${esc(ch.display_name)}${m.timeline ? ` · ${fmtSec(m.timeline.total)}` : ''}</div></div>
      ${v.status === 'montage_planning' ? `<span class="pill wait">${spin('')} analyse…</span>` : m.error ? '<span class="pill bad">plan impossible</span>' : m.unsuitable ? '<span class="pill warn">à vérifier</span>' : '<span class="pill ok">à valider</span>'}</div>`;
  if (v.status === 'montage_planning'){
    card.innerHTML = `${head}<div class="chcard-body"><span class="muted">${spin('')} Transcription et plan de l'IA en cours (1 à 3 minutes)…</span></div>`;
    return;
  }
  if (m.error){
    card.innerHTML = `${head}<div class="chcard-body"><div class="errbox">${esc(m.error)}</div></div>
      <div class="chcard-foot"><button class="btn secondary small m-replan" data-icon="refresh">Réessayer</button><button class="btn ghost small m-simple">Passer en habillage simple</button></div>`;
    wireMontageCardActions(card, v);
    hydrateIcons(card);
    return;
  }
  const hooks = m.hooks || [];
  const custom = m.hook && !hooks.includes(m.hook);
  const accent = (v.montage_settings || {}).caption_style === 'accent';
  const kw = new Set(m.keywords || []);
  card.innerHTML = `${head}
    <div class="chcard-body"><div class="mlayout">
      <div>
        <div class="mvideo">${m.preview_url ? `<video src="${m.preview_url}" controls playsinline></video><span class="mvideo-tag">Aperçu</span>`
          : v.media_url ? `<video src="${v.media_url}" controls muted preload="metadata"></video><span class="mvideo-tag">Original</span>` : ''}</div>
        <button class="btn secondary small full m-preview" style="margin-top:8px" data-icon="film">${m.preview_url ? "Refaire l'aperçu" : 'Aperçu rapide'}</button>
      </div>
      <div class="mfields">
        ${m.summary ? `<div class="muted" style="font-size:12.5px">${esc(m.summary)}</div>` : ''}
        ${m.unsuitable ? `<div class="warnbox">${esc(m.unsuitable)}</div>` : ''}
        <div><label class="f">Montage prévu par l'IA</label>${timelineHtml(m.timeline)}
          ${(m.timeline && m.timeline.notes.length) ? `<div class="tiny" style="margin-top:4px">${m.timeline.notes.map(esc).join(' · ')}</div>` : ''}</div>
        <div><label class="f">Accroche en haut de l'écran</label><div class="hooks">
          ${hooks.map((h, i) => `<label class="hook-opt"><input type="radio" name="hook-${v.video_id}" value="${i}" ${h === m.hook ? 'checked' : ''}>${esc(h)}</label>`).join('')}
          <label class="hook-opt"><input type="radio" name="hook-${v.video_id}" value="custom" ${custom ? 'checked' : ''}>
            <input class="f m-hook-custom" placeholder="Écrire la mienne…" value="${custom ? esc(m.hook) : ''}" style="padding:5px 8px;font-size:12.5px"></label>
        </div></div>
        <div><label class="f">Style de cette vidéo</label>${montageStyleHtml(v)}</div>
        ${accent ? `<div><label class="f">Mots en jaune — clique un mot pour l'ajouter ou l'enlever</label>
          <div class="kw-words">${(m.words || []).map((w, i) => (!m.timeline || m.timeline.kept_words.includes(i))
            ? `<button class="kw ${kw.has(i) ? 'on' : ''}" data-i="${i}">${esc(w)}</button>` : '').join('')}</div></div>` : ''}
        <div><label class="f">Plans de drone</label><div class="drones">
          ${(m.brolls || []).map((b, i) => `<div class="drone" style="background-image:url('${b.thumb_url}')"><button class="btn secondary small m-swap" data-slot="${i}" title="Changer ce plan">⟳</button></div>`).join('') || '<span class="tiny">Aucun plan : ajoute-en dans Réglages → Drones.</span>'}
        </div></div>
      </div>
    </div></div>
    <div class="chcard-foot">
      <button class="btn ghost small m-replan" data-icon="refresh" title="Gemini propose rarement deux fois le même montage">Nouveau plan (IA)</button>
      <button class="btn ghost small m-simple">Passer en habillage simple</button>
      <button class="btn primary small push m-validate" data-icon="check">Valider ce montage</button>
    </div>`;
  hydrateIcons(card);
  wireMontageCardActions(card, v);
}

function wireMontageCardActions(card, v){
  const id = v.video_id;
  const patch = body => api(`/api/videos/${id}/montage`, { method:'PATCH', body: JSON.stringify(body) });
  const rerender = u => { montageCardState[id] = montageCardKey(u); renderMontageCard(card, u); };
  card.querySelector('.m-replan')?.addEventListener('click', async () => {
    try { await api(`/api/videos/${id}/montage/replan`, { method:'POST' }); montageCardState[id] = null; safeLoad(loadMontageStep, 'montageCards'); }
    catch (e){ log(e.message, 'error'); }
  });
  card.querySelector('.m-simple')?.addEventListener('click', async () => {
    try { await patch({ edit_mode: 'simple' }); toast('Vidéo renvoyée au Cadrage, en habillage simple.'); safeLoad(loadMontageStep, 'montageCards'); }
    catch (e){ log(e.message, 'error'); }
  });
  card.querySelector('.m-validate')?.addEventListener('click', async () => {
    try { await api(`/api/videos/${id}/montage/validate`, { method:'POST' }); toast('Montage validé ✓', 'success'); safeLoad(loadMontageStep, 'montageCards'); }
    catch (e){ log(e.message, 'error'); }
  });
  card.querySelector('.m-preview')?.addEventListener('click', async ev => {
    const btn = ev.currentTarget;
    btn.disabled = true; btn.innerHTML = spin('Aperçu en cours…');
    try {
      const u = await api(`/api/videos/${id}/montage/preview`, { method:'POST' });
      rerender(u);
      card.querySelector('.mvideo video')?.play().catch(() => {});
    } catch (e){ log(e.message, 'error'); btn.disabled = false; btn.textContent = 'Aperçu rapide'; }
  });
  card.querySelectorAll('.m-swap').forEach(b => b.addEventListener('click', async () => {
    b.disabled = true;
    try { rerender(await api(`/api/videos/${id}/montage/swap_broll/${b.dataset.slot}`, { method:'POST' })); }
    catch (e){ log(e.message, 'error'); b.disabled = false; }
  }));
  // hook: a proposal, or my own text (saved as I type)
  const custom = card.querySelector('.m-hook-custom');
  let hookTimer = null;
  const saveHook = text => { clearTimeout(hookTimer); hookTimer = setTimeout(() => patch({ hook: text }).catch(e => log(e.message, 'error')), 500); };
  card.querySelectorAll(`input[name="hook-${id}"]`).forEach(r => r.addEventListener('change', () => {
    if (r.value === 'custom'){ custom.focus(); if (custom.value.trim()) saveHook(custom.value); }
    else saveHook(v.montage.hooks[+r.value]);
  }));
  custom?.addEventListener('input', () => {
    card.querySelector(`input[name="hook-${id}"][value="custom"]`).checked = true;
    saveHook(custom.value);
  });
  // keywords
  let kwTimer = null;
  card.querySelectorAll('.kw').forEach(b => b.addEventListener('click', () => {
    b.classList.toggle('on');
    clearTimeout(kwTimer);
    kwTimer = setTimeout(() => {
      const shown = new Set([...card.querySelectorAll('.kw')].map(x => +x.dataset.i));
      const keywords = [...(v.montage.keywords || []).filter(i => !shown.has(i)),
                        ...[...card.querySelectorAll('.kw.on')].map(x => +x.dataset.i)];
      patch({ keywords }).catch(e => log(e.message, 'error'));
    }, 600);
  }));
  wireMontageStyle(card, v, rerender);
}

document.getElementById('renderMontagesBtn').addEventListener('click', async () => {
  const btn = document.getElementById('renderMontagesBtn');
  btn.disabled = true;
  try {
    const r = await api('/api/process_selected', { method:'POST' });
    if (!r.started && !r.running){ log('Aucune vidéo à monter.', 'error'); return; }
    goTo(5);
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; }
});
