// ---------- Step 3 : AI results ----------

// Import processing runs in the background (POST /api/process_selected
// returns at once); Résultats IA shows its real progress while it runs —
// also after a page reload, since the state comes from the server.
let processPollTimer = null;
let processSeenRunning = false;

document.getElementById('toResultsBtn').addEventListener('click', async () => {
  const btn = document.getElementById('toResultsBtn');
  btn.disabled = true;
  try {
    const selected = await api('/api/videos?status=selected');
    const toReview = selected.some(v => v.edit_mode === 'montage' && !(v.montage && v.montage.validated));
    const r = await api('/api/process_selected', { method:'POST' });
    if (!r.started && !r.running){ log('Aucune vidéo sélectionnée à traiter.', 'error'); return; }
    goTo(toReview ? 10 : 5);
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; }
});

const PROCESS_PHASES = {
  ia: 'Analyse IA (titre, description, tags)', encodage: 'Encodage (fond + cadrage)',
  transcription: 'Montage auto : transcription', 'plan IA': "Montage auto : plan de l'IA", montage: 'Montage auto : rendu',
};

function formatEta(seconds){
  if (seconds == null) return '';
  if (seconds < 60) return `≈ ${Math.max(1, seconds)} s restantes`;
  return `≈ ${Math.round(seconds / 60)} min restantes`;
}

function progressBarHtml(job, label){
  const pct = Math.round((job.fraction || 0) * 100);
  const eta = formatEta(job.eta_seconds);
  return `
    <div class="pjob">
      <div class="pjob-line"><span>${esc(label)}</span><b>${pct} %</b></div>
      <div class="pbar"><div style="width:${pct}%"></div></div>
      <div class="pjob-line tiny"><span>${pct === 0 ? 'Préparation…' : esc(eta)}</span><span>${job.elapsed_seconds != null ? `${job.elapsed_seconds} s écoulées` : ''}</span></div>
    </div>`;
}

async function loadResultsScreen(){
  clearTimeout(processPollTimer);
  const list = document.getElementById('resultsList');
  const status = await api('/api/process_status');
  if (status.key && !status.done){
    processSeenRunning = true;
    const phase = PROCESS_PHASES[status.phase] || 'Encodage (fond + cadrage)';
    list.innerHTML = `
      <article class="chcard">
        <div class="chcard-head">
          <div class="who"><div class="name">${spin('')} Traitement en cours</div>
            <div class="meta" style="margin-left:0">Tu peux changer d'écran ou recharger la page : ça continue.</div></div>
          <span class="pill wait">vidéo ${Math.min(status.index + 1, status.total)} sur ${status.total}</span>
        </div>
        <div class="chcard-body">
          <div class="muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(status.title || '')}</div>
          ${progressBarHtml(status, phase)}
        </div>
      </article>`;
    // keep polling only while this screen is the one shown
    processPollTimer = setTimeout(() => { if (currentSpace === 'publication' && current === 5) safeLoad(loadResultsScreen, 'resultsList'); }, 1500);
    return;
  }
  if (processSeenRunning && status.key){
    processSeenRunning = false;
    if (status.error) log(`Traitement interrompu : ${status.error}`, 'error');
    else log(`${status.processed} vidéo(s) traitée(s)`, 'success');
  }
  list.innerHTML = spinnerHtml('Chargement...');
  const [videos, waiting] = await Promise.all([api('/api/videos?status=ready_for_upload'), api('/api/videos?status=montage_review')]);
  renderResults(videos);
  if (waiting.length){
    list.insertAdjacentHTML('afterbegin', `<div class="toolbar"><span class="fact warn">${icon('alert', 14)} ${waiting.length} montage${waiting.length > 1 ? 's attendent' : ' attend'} ta validation.</span><span class="spacer"></span><button class="btn secondary small" id="toMontageBtn">Aller à Import → 4 · Montage</button></div>`);
    document.getElementById('toMontageBtn').onclick = () => goTo(10);
  }
}

function renderResults(videos){
  const list = document.getElementById('resultsList');
  document.getElementById('resultsCountText').textContent = `Publication · étape 1 sur 3 · ${videos.length} vidéo(s) prêtes`;
  if (!videos.length){
    list.innerHTML = emptyState('Aucune vidéo prête', 'Les vidéos arrivent ici après le cadrage (Import) ou la génération.', 'film');
    return;
  }

  list.innerHTML = videos.map(v => {
    const ai = v.ai_data || {};
    const desc = (ai.description_suggestions || [''])[0] || '';
    const tags = (ai.tags || []).join(', ');
    const ch = channels.find(c => c.name === v.channel) || { display_name: v.channel };
    return `
    <article class="chcard rcard" data-video="${v.video_id}">
      <div class="chcard-head">
        <div class="who"><div class="name"><span class="dot" style="background:${channelColor(v.channel)}"></span>${esc(ch.display_name)}</div></div>
        <span class="pill ok">${icon('check', 11)} Prête</span>
      </div>
      <div class="rlayout">
        <div class="rthumb" style="background:linear-gradient(160deg,${channelColor(v.channel)},#171a21 120%)">
          ${v.media_url ? `<video src="${v.media_url}" muted controls></video>` : ''}
        </div>
        <div class="rfields">
          <div><label class="f">Titre</label><input class="f r-title" dir="auto" value="${esc(ai.optimized_title)}"></div>
          <div><label class="f">Description</label><textarea class="f r-desc" dir="auto">${esc(desc)}</textarea></div>
          <div><label class="f">Tags, séparés par des virgules</label><textarea class="tags-input r-tags" dir="auto" rows="2" style="resize:vertical">${esc(tags)}</textarea></div>
        </div>
      </div>
      <div class="chcard-foot">
        <div class="askrow" style="flex:1;min-width:240px">
          ${icon('sparkle', 16)}
          <input class="r-ask" placeholder="Demande à l'IA, ex : rends le titre plus drôle…">
          <button class="btn secondary small r-redo">Envoyer à l'IA</button>
        </div>
        <button class="btn primary small r-save push">Enregistrer</button>
      </div>
    </article>`;
  }).join('');

  list.querySelectorAll('.rcard').forEach(card => {
    const videoId = card.dataset.video;
    card.querySelector('.r-save').addEventListener('click', async () => {
      const title = card.querySelector('.r-title').value;
      const desc = card.querySelector('.r-desc').value;
      const tags = card.querySelector('.r-tags').value.split(',').map(t=>t.trim()).filter(Boolean);
      try {
        await api(`/api/videos/${videoId}/ai_data`, { method:'PATCH', body: JSON.stringify({optimized_title:title, description_suggestions:[desc], tags}) });
        log('Métadonnées enregistrées', 'success');
      } catch (e){ log(e.message, 'error'); }
    });
    card.querySelector('.r-redo').addEventListener('click', async () => {
      const instruction = card.querySelector('.r-ask').value.trim();
      if (!instruction){ return; }
      const btn = card.querySelector('.r-redo');
      btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> En cours...';
      try {
        const updated = await api(`/api/videos/${videoId}/ai_redo`, { method:'POST', body: JSON.stringify({instruction}) });
        const ai = updated.ai_data || {};
        card.querySelector('.r-title').value = ai.optimized_title || '';
        card.querySelector('.r-desc').value = (ai.description_suggestions||[''])[0] || '';
        card.querySelector('.r-tags').value = (ai.tags||[]).join(', ');
        log('Vidéo régénérée par l\'IA', 'success');
      } catch (e){ log(e.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = "Envoyer à l'IA"; }
    });
  });
}

// ---------- Step 4 : Backgrounds ----------

async function loadBackgrounds(){
  const grid = document.getElementById('backgroundsGrid');
  grid.innerHTML = channels.map(ch => `
    <article class="chcard" data-channel="${ch.name}">
      <div class="chcard-head">
        <div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div></div>
        ${ch.has_background ? `<span class="pill ok">${icon('check', 11)} Image définie</span>` : '<span class="pill wait">Fond noir</span>'}
      </div>
      <div class="chcard-body">
        <div class="preview ${ch.has_background ? '' : 'empty'}" style="${ch.has_background ? `background-image:url('/api/channels/${ch.name}/background?t=${Date.now()}')` : ''}">
          ${ch.has_background ? '' : icon('image', 24)}
        </div>
      </div>
      <input type="file" accept="image/*" class="bg-file" style="display:none">
      <div class="chcard-foot">
        <button class="btn secondary small bg-pick" data-icon="upload">${ch.has_background ? "Changer l'image" : 'Ajouter une image'}</button>
        ${ch.has_background ? '<button class="btn ghost small danger bg-remove push">Retirer</button>' : ''}
      </div>
    </article>
  `).join('');
  hydrateIcons(grid);

  grid.querySelectorAll('.chcard').forEach(card => {
    const channelName = card.dataset.channel;
    const fileInput = card.querySelector('.bg-file');
    card.querySelector('.bg-pick').addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const form = new FormData();
      form.append('file', file);
      try {
        await fetch(`/api/channels/${channelName}/background`, { method:'POST', body: form });
        log(`Fond mis à jour pour ${channelName}`, 'success');
        const chObj = channels.find(c => c.name === channelName);
        if (chObj) chObj.has_background = true;
        loadBackgrounds();
      } catch (e){ log(e.message, 'error'); }
    });
    const removeBtn = card.querySelector('.bg-remove');
    if (removeBtn) removeBtn.addEventListener('click', async () => {
      try {
        await api(`/api/channels/${channelName}/background`, { method: 'DELETE' });
        log(`Fond retiré pour ${channelName}`, 'success');
        const chObj = channels.find(c => c.name === channelName);
        if (chObj) chObj.has_background = false;
        loadBackgrounds();
      } catch (e){ log(e.message, 'error'); }
    });
  });
}

// ---------- Step 5 : Schedule ----------

let scheduleMethod = 'static';
document.querySelectorAll('#scheduleMethodSeg .seg-opt').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('#scheduleMethodSeg .seg-opt').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  scheduleMethod = btn.dataset.m;
}));

// Planning has two views of the same schedule: a week calendar (default —
// shows gaps/overloaded days, drag a video to another day) and the list
// (exact edits). The choice is remembered per browser.
let planningView = 'calendar';
try { planningView = localStorage.getItem('tiktub.planningView') || 'calendar'; } catch (_) {}

function syncPlanningViewSeg(){
  document.querySelectorAll('#planningViewSeg .seg-opt').forEach(b => b.classList.toggle('active', b.dataset.v === planningView));
}
document.querySelectorAll('#planningViewSeg .seg-opt').forEach(btn => btn.addEventListener('click', () => {
  planningView = btn.dataset.v;
  try { localStorage.setItem('tiktub.planningView', planningView); } catch (_) {}
  loadPlanningScreen();
}));

async function loadPlanningScreen(){
  // Re-fetch the real, currently-pending schedule every time this screen is
  // entered — otherwise it keeps showing whatever was rendered by the last
  // "Générer le planning" click, even for videos already published since.
  syncPlanningViewSeg();
  const list = document.getElementById('scheduleSections');
  const cal = document.getElementById('scheduleCalendar');
  list.style.display = planningView === 'list' ? '' : 'none';
  cal.style.display = planningView === 'calendar' ? '' : 'none';
  const target = planningView === 'calendar' ? cal : list;
  target.innerHTML = spinnerHtml('Chargement...');
  try {
    if (planningView === 'calendar'){
      calData = await api('/api/calendar');
      jumpToNextPublicationWeek();
      renderCalendar();
    } else {
      const data = await api('/api/schedule');
      renderSchedule(data.schedule || []);
    }
  } catch (e){
    showLoadError(target, e, loadPlanningScreen);
    log(e.message, 'error');
  }
}

document.getElementById('genScheduleBtn').addEventListener('click', async () => {
  const btn = document.getElementById('genScheduleBtn');
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Génération…';
  try {
    const schedule = await api('/api/schedule', { method:'POST', body: JSON.stringify({ method: scheduleMethod }) });
    log(`Planning généré : ${schedule.length} vidéo(s)`, 'success');
    await loadPlanningScreen();
  } catch (e){
    log(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = label;
  }
});

function dateBadgeHtml(raw, readable){
  return `<div class="datebadge" data-raw="${esc(raw)}">${icon('calendar', 13)}${esc(readable || raw)}</div>`;
}

function renderSchedule(schedule){
  const byChannel = {};
  schedule.forEach(e => {
    const ch = e.channel || (e.video_data && e.video_data.channel) || 'default';
    (byChannel[ch] ||= []).push(e);
  });
  const wrap = document.getElementById('scheduleSections');
  const names = Object.keys(byChannel);
  if (!names.length){
    wrap.innerHTML = emptyState('Aucun planning pour l\'instant', 'Choisis une méthode puis clique « Générer le planning ».', 'calendar');
    return;
  }

  wrap.innerHTML = names.map(name => {
    const chObj = channels.find(c => c.name === name);
    const entries = byChannel[name];
    return `
    <article class="chcard">
      <div class="chcard-head">
        <div class="who"><div class="name"><span class="dot" style="background:${channelColor(name)}"></span>${esc(chObj ? chObj.display_name : name)}</div></div>
        <span class="pill wait">${entries.length} vidéo${entries.length > 1 ? 's' : ''}</span>
      </div>
      <div>
      ${entries.map(e => `
        <div class="vrow" data-video="${e.video_id}" data-publish-now="${e.publish_now ? '1' : '0'}">
          <div class="mthumb" style="background:linear-gradient(160deg,${channelColor(name)},#171a21 120%)"></div>
          <div class="vname">${esc(e.title)}</div>
          ${e.publish_now
            ? `<span class="pill ok">${icon('globe', 11)} Publication immédiate</span>`
            : `${dateBadgeHtml(e.scheduled_time, e.when ? formatWhen(e.when) : e.scheduled_time)}
               <button class="editbtn edit-date" title="Modifier la date">${icon('edit')}</button>`}
          <button class="btn ghost small publish-now-toggle">${e.publish_now ? 'Programmer plutôt' : 'Publier maintenant'}</button>
        </div>`).join('')}
      </div>
    </article>`;
  }).join('');

  wrap.querySelectorAll('.publish-now-toggle').forEach(btn => btn.addEventListener('click', async () => {
    const row = btn.closest('.vrow');
    const current = row.dataset.publishNow === '1';
    btn.disabled = true;
    try {
      await api(`/api/schedule/${row.dataset.video}`, { method:'PATCH', body: JSON.stringify({ publish_now: !current }) });
      log(!current ? 'Vidéo marquée pour publication immédiate' : 'Vidéo remise en planning programmé', 'success');
      await loadPlanningScreen();
    } catch (e){ log(e.message, 'error'); btn.disabled = false; }
  }));

  wrap.querySelectorAll('.edit-date').forEach(btn => btn.addEventListener('click', () => {
    const row = btn.closest('.vrow');
    const badge = row.querySelector('.datebadge');
    const raw = badge.dataset.raw; // "YYYY-MM-DD HH:MM:SS"
    const localValue = raw.replace(' ', 'T').slice(0,16);
    badge.outerHTML = `<input type="datetime-local" class="dtinput" value="${localValue}">`;
    const input = row.querySelector('.dtinput');
    input.focus();
    input.addEventListener('blur', async () => {
      const scheduled_time = input.value.replace('T',' ') + ':00';
      try {
        const entry = await api(`/api/schedule/${row.dataset.video}`, { method:'PATCH', body: JSON.stringify({scheduled_time}) });
        input.outerHTML = dateBadgeHtml(entry.scheduled_time, formatWhen(input.value));
        log('Date mise à jour', 'success');
      } catch (e){ log(e.message, 'error'); }
    }, { once:true });
  }));
}


// ---------- Planning : week calendar ----------

let calData = null;
let calWeekStart = startOfWeek(new Date());
let calDrag = null;
let calUserNavigated = false;

// First view: if this week is empty but something is planned later, open the
// week of the next publication instead of an empty grid.
function jumpToNextPublicationWeek(){
  if (calUserNavigated) return;
  const now = new Date();
  const thisWeekEnd = addDays(calWeekStart, 7);
  const upcoming = (calData.items || []).map(i => new Date(i.when)).filter(d => d >= now).sort((a, b) => a - b);
  const anyThisWeek = (calData.items || []).some(i => { const d = new Date(i.when); return d >= calWeekStart && d < thisWeekEnd; });
  if (!anyThisWeek && upcoming.length) calWeekStart = startOfWeek(upcoming[0]);
}

function startOfWeek(d){
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); // Monday
  return x;
}
function addDays(d, n){ const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function pad2(n){ return String(n).padStart(2, '0'); }
function dayKey(d){ return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; }
function hhmm(d){ return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`; }
// The schedule API takes local "YYYY-MM-DD HH:MM:SS" (same as the pencil edit)
function toLocalApiTime(d){ return `${dayKey(d)} ${hhmm(d)}:00`; }

function renderCalendar(){
  const box = document.getElementById('scheduleCalendar');
  const now = new Date();
  const days = [...Array(7)].map((_, i) => addDays(calWeekStart, i));
  const weekEnd = addDays(calWeekStart, 7);
  const all = (calData.items || []).map(i => ({ ...i, date: new Date(i.when) }));
  const spacingMs = calData.spacing_hours * 3600 * 1000;

  // Lanes = channels that have anything to show at all (empty week included)
  const laneNames = channels.map(c => c.name).filter(n => all.some(i => i.channel === n));
  if (!laneNames.length){
    box.innerHTML = emptyState('Rien de programmé', 'Choisis une méthode puis clique « Générer le planning ».', 'calendar');
    return;
  }

  // Two videos of the same channel closer than spacing_hours = flagged (advice only).
  // close: video_id → the nearest too-close neighbour, so the tooltip can say which and by how much.
  const close = new Map();
  const flagPair = (a, b) => {
    const gap = Math.abs(a.date - b.date);
    [[a, b], [b, a]].forEach(([x, y]) => {
      const prev = close.get(x.video_id);
      if (!prev || gap < prev.gap) close.set(x.video_id, { other: y, gap });
    });
  };
  laneNames.forEach(n => {
    const mine = all.filter(i => i.channel === n && i.kind !== 'published').sort((a, b) => a.date - b.date);
    mine.forEach((it, k) => { if (k && it.date - mine[k - 1].date < spacingMs) flagPair(it, mine[k - 1]); });
  });

  const inWeek = all.filter(i => i.date >= calWeekStart && i.date < weekEnd);
  const pendingThisWeek = inWeek.filter(i => i.kind === 'pending').length;
  const fmtDay = d => d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
  const title = `Semaine du ${fmtDay(days[0])} au ${fmtDay(days[6])} ${days[6].getFullYear()}`;

  const header = `
    <div class="cal-head">
      <button class="btn secondary small" data-cal="prev" title="Semaine précédente">‹</button>
      <button class="btn secondary small" data-cal="next" title="Semaine suivante">›</button>
      <button class="btn ghost small" data-cal="today">Aujourd'hui</button>
      <span class="cal-title">${esc(title)}</span>
      <span class="summary">${pendingThisWeek} à publier cette semaine · ${inWeek.length - pendingThisWeek} déjà sur YouTube</span>
    </div>`;

  const head = `<div class="corner">Glisse une vidéo vers un autre jour</div>` + days.map(d => `
    <div class="hd ${dayKey(d) === dayKey(now) ? 'today' : ''}">${esc(d.toLocaleDateString('fr-FR', { weekday: 'short' }))}<b>${d.getDate()}</b></div>`).join('');

  const rows = laneNames.map(name => {
    const ch = channels.find(c => c.name === name) || { display_name: name };
    const cells = days.map(d => {
      const key = dayKey(d);
      const dayItems = inWeek.filter(i => i.channel === name && dayKey(i.date) === key).sort((a, b) => a.date - b.date);
      const isPast = addDays(d, 1) <= now;
      const count = dayItems.filter(i => i.kind !== 'published').length;
      const overLimit = count > calData.max_daily_uploads;
      return `<div class="cell ${key === dayKey(now) ? 'today' : ''} ${isPast ? 'past' : ''} ${overLimit ? 'over-limit' : ''}" data-channel="${name}" data-day="${key}">
        ${dayItems.map(i => slotHtml(i, close.get(i.video_id))).join('')}
        ${overLimit ? `<span class="limit">${count} > limite de ${calData.max_daily_uploads}/jour</span>` : ''}
      </div>`;
    }).join('');
    return `<div class="lane"><span class="dot" style="background:${channelColor(name)};margin-top:4px"></span><span>${esc(ch.display_name)}</span></div>${cells}`;
  }).join('');

  box.innerHTML = `${header}
    <div class="cal-wrap"><div class="cal">${head}${rows}</div></div>
    <div class="cal-legend">
      <span><span class="sw" style="background:var(--panel2)"></span>À publier (déplaçable)</span>
      <span style="opacity:.75">${icon('lock', 11)} Déjà programmée sur YouTube</span>
      <span style="opacity:.6">${icon('check', 11)} Publiée</span>
      <span style="color:#f5c56d">${icon('alert', 11)} Jaune = moins de ${calData.spacing_hours} h d'écart avec une autre vidéo de la même chaîne (conseil, non bloquant — survole pour le détail)</span>
      <span style="color:var(--danger)">Cadre rouge = plus de ${calData.max_daily_uploads} vidéos le même jour</span>
    </div>`;

  box.querySelector('[data-cal="prev"]').addEventListener('click', () => { calUserNavigated = true; calWeekStart = addDays(calWeekStart, -7); renderCalendar(); });
  box.querySelector('[data-cal="next"]').addEventListener('click', () => { calUserNavigated = true; calWeekStart = addDays(calWeekStart, 7); renderCalendar(); });
  box.querySelector('[data-cal="today"]').addEventListener('click', () => { calUserNavigated = true; calWeekStart = startOfWeek(new Date()); renderCalendar(); });
  wireCalendar(box, all);
}

function gapLabel(ms){
  const h = Math.round(ms / 3600000);
  return h >= 1 ? `${h} h` : `${Math.max(1, Math.round(ms / 60000))} min`;
}

function slotHtml(i, tooClose){
  const movable = i.kind === 'pending' && !i.publish_now;
  const lead = i.publish_now ? icon('globe', 10) : i.kind === 'scheduled' ? icon('lock', 10) : i.kind === 'published' ? icon('check', 10) : '';
  let tip = i.kind === 'pending'
    ? (i.publish_now ? 'Publication immédiate au prochain « Publier tout »' : 'Clique pour modifier, ou glisse vers un autre jour')
    : i.kind === 'scheduled' ? 'Déjà programmée sur YouTube (non modifiable ici)' : 'Déjà publiée';
  if (tooClose){
    tip = `⚠ À ${gapLabel(tooClose.gap)} de « ${tooClose.other.title || 'une autre vidéo'} » sur la même chaîne.\n`
      + `Écart conseillé : ${calData.spacing_hours} h minimum (réglage spacing_hours de config.yaml) — simple avertissement, rien n'est bloqué.\n\n${tip}`;
  }
  return `<button type="button" class="slot ${i.kind} ${tooClose ? 'close' : ''}" style="--ch:${channelColor(i.channel)}"
      data-video="${esc(i.video_id)}" data-channel="${esc(i.channel)}" ${movable ? 'draggable="true"' : ''} title="${esc(tip)}">
    <span class="t">${lead}${i.publish_now ? 'Immédiate' : hhmm(i.date)}${tooClose ? icon('alert', 11).replace('<svg', '<svg class="warn"') : ''}</span>
    <span class="n">${esc(i.title || 'Vidéo')}</span>
  </button>`;
}

function wireCalendar(box, all){
  const byId = Object.fromEntries(all.map(i => [i.video_id, i]));
  const now = new Date();

  box.querySelectorAll('.slot').forEach(el => {
    const item = byId[el.dataset.video];
    el.addEventListener('click', () => {
      if (item.kind === 'pending') openSlotDialog(item);
      else if (item.youtube_url) window.open(item.youtube_url, '_blank', 'noopener');
    });
    if (el.getAttribute('draggable') !== 'true') return;
    el.addEventListener('dragstart', ev => {
      calDrag = item;
      el.classList.add('dragging');
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('text/plain', item.video_id);
      box.querySelectorAll(`.cell[data-channel="${CSS.escape(item.channel)}"]`).forEach(c => {
        if (addDays(new Date(c.dataset.day + 'T00:00:00'), 1) > now) c.classList.add('droppable');
      });
    });
    el.addEventListener('dragend', () => {
      calDrag = null;
      el.classList.remove('dragging');
      box.querySelectorAll('.cell').forEach(c => c.classList.remove('droppable', 'over'));
    });
  });

  box.querySelectorAll('.cell').forEach(cell => {
    cell.addEventListener('dragover', ev => {
      if (!calDrag || !cell.classList.contains('droppable')) return;
      ev.preventDefault();
      cell.classList.add('over');
    });
    cell.addEventListener('dragleave', () => cell.classList.remove('over'));
    cell.addEventListener('drop', async ev => {
      ev.preventDefault();
      cell.classList.remove('over');
      const item = calDrag;
      if (!item || !cell.classList.contains('droppable')) return;
      const target = new Date(`${cell.dataset.day}T${hhmm(item.date)}:00`);
      if (dayKey(target) === dayKey(item.date)) return;
      if (target <= new Date()){
        log(`${target.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric' })} à ${hhmm(target)} est déjà passé — choisis un jour à venir, ou clique la vidéo pour changer aussi l'heure.`, 'error');
        return;
      }
      await saveSlot(item, target);
    });
  });
}

async function saveSlot(item, when){
  try {
    await api(`/api/schedule/${item.video_id}`, { method: 'PATCH', body: JSON.stringify({ scheduled_time: toLocalApiTime(when) }) });
    log(`Déplacée au ${when.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })} à ${hhmm(when)}`, 'success');
  } catch (e){ log(e.message, 'error'); }
  calData = await api('/api/calendar');
  renderCalendar();
}

function openSlotDialog(item){
  const dlg = document.getElementById('slotDialog');
  const ch = channels.find(c => c.name === item.channel) || { display_name: item.channel };
  const local = `${dayKey(item.date)}T${hhmm(item.date)}`;
  dlg.innerHTML = `
    <div class="chcard" style="border:none">
      <div class="chcard-head">
        <div class="who">
          <div class="name"><span class="dot" style="background:${channelColor(item.channel)}"></span>${esc(ch.display_name)}</div>
          <div class="meta">${esc(item.title || '')}</div>
        </div>
        <button class="btn ghost small" data-act="close" title="Fermer">${icon('x', 14)}</button>
      </div>
      <div class="chcard-body">
        <label class="switch"><input type="checkbox" data-role="now" ${item.publish_now ? 'checked' : ''}> Publier immédiatement (publique) au prochain « Publier tout »</label>
        <div data-role="when-row" ${item.publish_now ? 'style="opacity:.4;pointer-events:none"' : ''}>
          <label class="f">Date et heure de publication</label>
          <input class="f" type="datetime-local" data-role="when" value="${local}">
        </div>
        <span class="tiny" data-role="err" style="color:var(--danger)"></span>
      </div>
      <div class="chcard-foot">
        <button class="btn ghost small" data-act="close">Annuler</button>
        <button class="btn primary small push" data-act="save">Enregistrer</button>
      </div>
    </div>`;
  const nowBox = dlg.querySelector('[data-role="now"]');
  nowBox.addEventListener('change', () => {
    dlg.querySelector('[data-role="when-row"]').style.cssText = nowBox.checked ? 'opacity:.4;pointer-events:none' : '';
  });
  dlg.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => dlg.close()));
  dlg.querySelector('[data-act="save"]').addEventListener('click', async () => {
    const err = dlg.querySelector('[data-role="err"]');
    try {
      if (nowBox.checked !== !!item.publish_now){
        await api(`/api/schedule/${item.video_id}`, { method: 'PATCH', body: JSON.stringify({ publish_now: nowBox.checked }) });
      }
      const value = dlg.querySelector('[data-role="when"]').value;
      if (!nowBox.checked && value && value !== local){
        await api(`/api/schedule/${item.video_id}`, { method: 'PATCH', body: JSON.stringify({ scheduled_time: value.replace('T', ' ') + ':00' }) });
      }
      dlg.close();
      log('Planning mis à jour', 'success');
      calData = await api('/api/calendar');
      renderCalendar();
    } catch (e){ err.textContent = e.message; }
  });
  dlg.showModal();
}

// ---------- Step 6 : Summary & publish ----------

async function loadSummaryFromSchedule(){
  const data = await api('/api/schedule');
  const schedule = data.schedule || [];
  const byChannel = {};
  schedule.forEach(e => {
    const ch = e.channel || (e.video_data && e.video_data.channel) || 'default';
    (byChannel[ch] ||= []).push(e);
  });
  const wrap = document.getElementById('summarySections');
  const names = Object.keys(byChannel);
  document.getElementById('preflightBox').innerHTML = '';
  if (!names.length){
    wrap.innerHTML = emptyState('Rien à publier', 'Génère d\'abord un planning à l\'étape 2 · Planning.', 'rocket');
    document.getElementById('summaryTotal').textContent = '0 vidéo';
    document.getElementById('summaryLbl').textContent = 'rien à publier';
    document.getElementById('publishAllBtn').disabled = true;
    return;
  }
  // One card per channel: its videos AND its pre-publish checks together
  // (they used to be two separate lists repeating the same channels).
  wrap.innerHTML = names.map(name => {
    const chObj = channels.find(c => c.name === name);
    return `
    <article class="chcard" data-channel="${name}">
      <div class="chcard-head">
        <div class="who">
          <div class="name"><span class="dot" style="background:${channelColor(name)}"></span>${esc(chObj ? chObj.display_name : name)}</div>
          <div class="meta" data-role="yt">&nbsp;</div>
        </div>
        <span class="pill wait" data-role="pf-pill">Vérification…</span>
      </div>
      <div>
        ${byChannel[name].map(e => `
          <div class="publish-row" data-title="${esc(e.title)}" data-video="${esc(e.video_id)}">
            <span class="name" title="${esc(e.title)}">${esc(e.title)}</span>
            <div class="info">
              <span class="when">${e.publish_now ? 'Publication immédiate' : esc(e.when ? formatWhen(e.when) : e.scheduled_time)}</span>
              <span class="info" data-role="flag"></span>
            </div>
            <div class="row-actions" data-role="actions"></div>
          </div>`).join('')}
      </div>
      <div class="facts" data-role="checks">${spinnerHtml('Connexion, quota, fichiers…')}</div>
    </article>`;
  }).join('');
  document.getElementById('summaryTotal').textContent = `${schedule.length} vidéo${schedule.length>1?'s':''}`;
  document.getElementById('summaryLbl').textContent = `sur ${names.length} chaîne${names.length>1?'s':''}`;
  loadPreflight();
}

// Pre-publish check: connection, quota, missing files, past dates — per channel,
// shown BEFORE "Publier tout" so nothing fails or gets skipped by surprise.
let lastPreflight = null;

async function loadPreflight(){
  try {
    lastPreflight = await api('/api/publish/preflight');
  } catch (e){
    lastPreflight = null;
    showLoadError(document.getElementById('preflightBox'), e, loadPreflight);
    document.querySelectorAll('#summarySections [data-role="checks"]').forEach(el => { el.innerHTML = '<span class="tiny">Vérification impossible.</span>'; });
    return lastPreflight;
  }
  lastPreflight.channels.forEach(fillPreflightCard);
  const total = lastPreflight.total_videos, ok = lastPreflight.total_publishable;
  // Nothing publishable → the button can't do anything useful: say why instead
  const publishBtn = document.getElementById('publishAllBtn');
  publishBtn.disabled = ok === 0;
  publishBtn.title = ok === 0 ? 'Aucune vidéo publiable — règle les problèmes signalés sur les cartes' : '';
  document.getElementById('summaryLbl').textContent = ok === total
    ? `tout est publiable` : `${ok} publiable${ok > 1 ? 's' : ''} sur ${total} — voir les cartes`;
  return lastPreflight;
}

function fillPreflightCard(item){
  const card = document.querySelector(`#summarySections .chcard[data-channel="${item.channel}"]`);
  if (!card) return;
  const facts = [];
  let level = 'ok';
  const worse = l => { if (l === 'bad' || (l === 'warn' && level === 'ok')) level = l; };

  const conn = item.connection;
  card.querySelector('[data-role="yt"]').textContent = conn.youtube_channel_title ? `YouTube · ${conn.youtube_channel_title}` : '';
  if (conn.state === 'connected'){
    facts.push(`<div class="fact">${icon('check')}<span>Connectée</span></div>`);
  } else {
    worse('bad');
    const label = {expired:'Connexion expirée', not_connected:'Jamais connectée', missing_credentials:'Pas de credentials.json'}[conn.state] || 'Connexion impossible';
    facts.push(`<div class="fact bad">${icon('alert')}<span>${label} — ses vidéos seront ignorées. <a href="#" data-go-settings>Reconnecter</a></span></div>`);
  }

  const q = item.quota;
  const resetAt = new Date(q.resets_at).toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
  const shared = q.shared_with && q.shared_with.length
    ? ` · partagé avec ${q.shared_with.map(c => esc((channels.find(x => x.name === c) || {}).display_name || c)).join(', ')}` : '';
  if (q.exhausted){
    worse('bad');
    facts.push(`<div class="fact bad">${icon('gauge')}<span>Quota du jour atteint — reprise après ${resetAt}${shared}</span></div>`);
  } else {
    const tight = q.estimated_uploads_left < item.videos;
    if (tight) worse('warn');
    facts.push(`<div class="fact ${tight ? 'warn' : ''}">${icon('gauge')}<span>Quota : ≈ ${q.estimated_uploads_left} upload(s) restant(s)${shared}${tight ? ' — les vidéos en trop attendront demain' : ''}</span></div>`);
  }

  // Per-video flags on the matching rows
  // re-runs must not stack flags/buttons
  card.querySelectorAll('[data-role="flag"], [data-role="actions"]').forEach(f => { f.innerHTML = ''; });
  const flag = (match, html, actions = '') => card.querySelectorAll('.publish-row').forEach(row => {
    if (!match(row)) return;
    row.querySelector('[data-role="flag"]').insertAdjacentHTML('beforeend', html);
    if (actions) row.querySelector('[data-role="actions"]').insertAdjacentHTML('beforeend', actions);
  });
  if (item.missing_files.length){
    worse('warn');
    const ids = item.missing_ids || [];
    flag(row => ids.includes(row.dataset.video),
      `<span class="pill bad" title="Fichier vidéo introuvable : ne sera pas publiée">Fichier manquant</span>`,
      `<button class="btn secondary small" data-reprocess title="Refaire le cadrage et le traitement depuis le fichier téléchargé">${icon('refresh', 12)} Retraiter</button><button class="btn ghost small danger" data-abandon title="Retirer cette vidéo du planning">${icon('trash', 12)} Abandonner</button>`);
    facts.push(`<div class="fact warn">${icon('alert')}<span>${item.missing_files.length} fichier(s) introuvable(s) — non publiée(s)</span></div>`);
  }
  if (item.past_dates.length){
    worse('warn');
    flag(row => item.past_dates.includes(row.dataset.title), `<span class="pill warn" title="Date déjà passée : sera publiée immédiatement">Date passée</span>`);
    facts.push(`<div class="fact warn">${icon('clock')}<span>${item.past_dates.length} date(s) déjà passée(s) — publiée(s) immédiatement</span></div>`);
  }

  const pill = card.querySelector('[data-role="pf-pill"]');
  pill.className = `pill ${level}`;
  pill.innerHTML = level === 'bad' && !item.publishable
    ? 'Bloquée'
    : `${level === 'ok' ? icon('check', 11) + ' ' : ''}${item.publishable}/${item.videos} publiable${item.publishable > 1 ? 's' : ''}`;
  card.querySelector('[data-role="checks"]').innerHTML = facts.join('');
  const go = card.querySelector('[data-go-settings]');
  if (go) go.addEventListener('click', ev => { ev.preventDefault(); goTo(0); });

  card.querySelectorAll('[data-abandon]').forEach(btn => btn.addEventListener('click', async () => {
    const row = btn.closest('.publish-row');
    if (!confirm(`Retirer « ${row.dataset.title} » du planning ? Elle ne sera pas publiée (le lien pourra être réimporté plus tard).`)) return;
    btn.disabled = true;
    try {
      await api(`/api/videos/${row.dataset.video}/abandon`, { method: 'POST' });
      log('Vidéo retirée du planning', 'success');
      await loadSummaryFromSchedule();
    } catch (e){ btn.disabled = false; log(e.message, 'error'); }
  }));

  card.querySelectorAll('[data-reprocess]').forEach(btn => btn.addEventListener('click', async () => {
    const row = btn.closest('.publish-row');
    btn.disabled = true;
    try {
      await api(`/api/videos/${row.dataset.video}/reprocess`, { method: 'POST' });
      log('Vidéo renvoyée au cadrage — ses titre/description/tags sont conservés. Termine par « Suivant (lancer l\'IA) ».', 'success');
      goTo(4);
    } catch (e){ btn.disabled = false; log(e.message, 'error'); }
  }));
}

function publishResultsHtml(results){
  if (!results.length) return emptyState('Rien n\'a été publié', 'Aucune vidéo en attente.', 'rocket');
  const ok = results.filter(r => r.success).length;
  return `
  <article class="chcard">
    <div class="chcard-head">
      <div class="who"><div class="name">Résultat de la publication</div></div>
      <span class="pill ${ok === results.length ? 'ok' : (ok ? 'warn' : 'bad')}">${ok}/${results.length} publiée${ok > 1 ? 's' : ''}</span>
    </div>
    <div>
      ${results.map(r => {
        const ch = channels.find(c => c.name === r.channel);
        return `
        <div class="result-line ${r.success ? 'ok' : (r.skipped ? 'skip' : 'fail')}">
          ${icon(r.success ? 'check' : (r.skipped ? 'skip' : 'x'))}
          <span><b style="color:var(--text);font-weight:600">${esc(r.title || '')}</b>
            <span class="tiny"> · ${esc(ch ? ch.display_name : (r.channel || ''))}</span><br>
            ${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${r.url}</a>` : esc(r.error || '')}
            ${r.note ? `<span class="tiny"> · ${esc(r.note)}</span>` : ''}
          </span>
        </div>`;
      }).join('')}
    </div>
  </article>`;
}

document.getElementById('publishAllBtn').addEventListener('click', async () => {
  const btn = document.getElementById('publishAllBtn');
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Vérification...';
  try {
    const pf = await loadPreflight();
    if (pf && pf.total_publishable < pf.total_videos){
      const proceed = pf.total_publishable === 0
        ? (alert(`Aucune vidéo publiable pour l'instant (${pf.total_videos} en attente). Regarde les cartes des chaînes.`), false)
        : confirm(`${pf.total_publishable} vidéo(s) sur ${pf.total_videos} peuvent être publiées maintenant. Les autres seront ignorées (voir les avertissements) et resteront prêtes. Continuer ?`);
      if (!proceed) return;
    }
    btn.innerHTML = '<span class="spinner"></span> Publication en cours...';
    const { results } = await api('/api/publish_all', { method:'POST' });
    document.getElementById('publishResults').innerHTML = publishResultsHtml(results);
    log('Publication terminée', 'success');
    await loadSummaryFromSchedule(); // videos just published must disappear from "Prêt à publier"
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; btn.innerHTML = originalHtml; }
});
