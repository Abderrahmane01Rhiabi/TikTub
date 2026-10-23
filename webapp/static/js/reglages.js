// ---------- Réglages → Montage : each channel's default style ----------

async function loadMontageSettings(){
  const grid = document.getElementById('montageSettingsGrid');
  if (!channels.length){ grid.innerHTML = emptyState('Aucune chaîne', 'Ajoute une chaîne dans config.yaml.', 'settings'); return; }
  grid.innerHTML = channels.map(ch => `<article class="chcard" data-channel="${ch.name}">${spinnerHtml('Chargement...')}</article>`).join('');
  await Promise.all(channels.map(async ch => {
    const card = grid.querySelector(`[data-channel="${ch.name}"]`);
    try { renderMontageSettingsCard(card, ch, await api(`/api/channels/${ch.name}/montage`)); }
    catch (e){ showLoadError(card, e, () => loadMontageSettings()); }
  }));
}

function renderMontageSettingsCard(card, ch, data){
  const s = data.settings;
  const musicUrl = f => `/api/channels/${ch.name}/assets/music/${encodeURIComponent(f)}`;
  card.innerHTML = `
    <div class="chcard-head">
      <div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div></div>
      <label class="switch" title="Les vidéos téléchargées pour cette chaîne arrivent au Cadrage déjà en Montage auto"><input type="checkbox" class="ms-default" ${s.default_mode === 'montage' ? 'checked' : ''}> Montage auto par défaut</label>
    </div>
    <div class="chcard-body">
      <label class="f">Sous-titres</label>
      <div class="capstyle-pick">${Object.entries(MONTAGE_CAPTION_LABELS).map(([k, l]) =>
        `<button class="${k === s.caption_style ? 'active' : ''}" data-v="${k}">${capSampleHtml(k)}<span>${l}${k === 'accent' ? ' — mots-clés en jaune' : ' — tout en blanc'}</span></button>`).join('')}</div>
    </div>
    <div class="chcard-body">
      <label class="f">Musique de fond</label>
      <div style="display:flex;gap:8px">
        <select class="f ms-music">
          <option value="">— aucune —</option>
          ${data.music_files.map(f => `<option ${f === s.music_file ? 'selected' : ''}>${esc(f)}</option>`).join('')}
        </select>
        <button class="btn secondary small ms-upload" data-icon="upload" title="Ajouter un morceau (mp3, wav, m4a...)">Ajouter</button>
        <input type="file" class="ms-file" accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*" hidden>
      </div>
      ${s.music_file ? `
      <label class="f" style="margin-top:4px">Moment du morceau qui démarre quand l'image revient après l'écran noir</label>
      <audio class="ms-audio" controls preload="metadata" src="${musicUrl(s.music_file)}"></audio>
      <div class="entry-row">
        <input class="f ms-entry" type="number" min="0" step="0.5" value="${s.music_entry}" title="secondes">
        <span class="tiny">s (${fmtSec(s.music_entry)})</span>
        <button class="btn secondary small ms-take" title="Met l'instant où en est le lecteur">Prendre l'instant du lecteur</button>
        <button class="btn ghost small ms-listen">▶ Écouter ce moment</button>
      </div>` : '<div class="tiny">Choisis un morceau, ou ajoute-le avec « Ajouter ».</div>'}
      <div class="mstyle-row" style="margin-top:6px"><span>Volume</span>${segHtml('ms-vol', MONTAGE_VOLUME_LABELS, s.volume)}
        <span class="tiny">${s.volume === 'marque' ? 'bien présente, ~5 dB sous la voix' : 'discrète, ~9 dB sous la voix'}</span></div>
    </div>
    <div class="chcard-foot">
      <label class="switch"><input type="checkbox" class="ms-hook" ${s.hook ? 'checked' : ''}> Accroche en haut de l'écran</label>
      <span class="note push ms-saved"></span>
    </div>`;
  hydrateIcons(card);

  const save = async patch => {
    try {
      const d = await api(`/api/channels/${ch.name}/montage`, { method:'PUT', body: JSON.stringify({ settings: { ...data.settings, ...patch } }) });
      renderMontageSettingsCard(card, ch, d);
      card.querySelector('.ms-saved').textContent = 'Enregistré ✓';
    } catch (e){ log(e.message, 'error'); }
  };
  card.querySelector('.ms-default').onchange = e => save({ default_mode: e.target.checked ? 'montage' : 'simple' });
  card.querySelector('.ms-hook').onchange = e => save({ hook: e.target.checked });
  card.querySelectorAll('.capstyle-pick button').forEach(b => b.onclick = () => save({ caption_style: b.dataset.v }));
  wireSeg(card, 'ms-vol', v => save({ volume: v }));
  card.querySelector('.ms-music').onchange = e => save({ music_file: e.target.value || null });
  const fileInput = card.querySelector('.ms-file');
  card.querySelector('.ms-upload').onclick = () => fileInput.click();
  fileInput.onchange = async () => {
    const file = fileInput.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`/api/channels/${ch.name}/assets/music`, { method:'POST', body: form });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Envoi impossible');
      data.music_files = d.music_files;
      await save({ music_file: file.name });
      toast(`« ${file.name} » ajouté`, 'success');
    } catch (e){ log(e.message, 'error'); }
  };
  const audio = card.querySelector('.ms-audio');
  const entry = card.querySelector('.ms-entry');
  if (audio && entry){
    entry.onchange = () => save({ music_entry: Math.max(0, parseFloat(entry.value) || 0) });
    card.querySelector('.ms-take').onclick = () => save({ music_entry: Math.round(audio.currentTime * 2) / 2 });
    card.querySelector('.ms-listen').onclick = () => { audio.currentTime = parseFloat(entry.value) || 0; audio.play(); };
  }
}

// ---------- Réglages → Drones : the shared drone-shot library ----------

async function loadBrollLibrary(){
  const grid = document.getElementById('brollGrid');
  const data = await api('/api/broll');
  document.getElementById('brollCount').textContent = `${data.clips.length} plan${data.clips.length > 1 ? 's' : ''}`;
  const missing = data.healthy_size - data.clips.length;
  document.getElementById('brollHealth').innerHTML = missing > 0
    ? `<div class="warnbox">${icon('alert', 14)} Bibliothèque un peu petite : avec ${data.clips.length} plans, une chaîne peut revoir un plan avant ${data.videos_without_repeat} vidéos.
       Ajoute encore environ <b>${missing} plans</b> (${data.healthy_size} au total) pour que chaque chaîne attende au moins ${data.videos_without_repeat} vidéos avant de réutiliser un plan.</div>` : '';
  const themes = document.getElementById('brollThemes');
  themes.innerHTML = (data.has_key ? '<span class="tiny">Idées :</span>' + data.themes.map(t => `<button class="chipbtn" data-t="${esc(t)}">${esc(t)}</button>`).join('')
    : `<span class="fact warn">${icon('alert', 14)} Clé PIXABAY_API_KEY absente du fichier .env : impossible d'ajouter des plans.</span>`);
  themes.querySelectorAll('.chipbtn').forEach(b => b.onclick = () => { document.getElementById('brollTheme').value = b.dataset.t; fetchBroll(); });
  document.getElementById('brollFetchBtn').disabled = !data.has_key;
  grid.innerHTML = data.clips.length ? data.clips.map(c => `
    <div class="bcard" data-id="${c.id}" style="background-image:url('${c.thumb_url}')" title="${esc(c.tags || c.query || '')}">
      <span class="buse ${c.uses ? '' : 'zero'}" title="${c.uses ? 'Utilisé dans : ' + Object.entries(c.uses_by_channel).map(([ch, n]) => `${(channels.find(x => x.name === ch) || {}).display_name || ch} ×${n}`).join(', ') : 'Jamais utilisé'}">${c.uses ? `×${c.uses}` : 'neuf'}</span>
      <button class="bdel" title="Supprimer ce plan">✕</button>
      <div class="bq">${esc(c.query || '')}</div>
    </div>`).join('') : emptyState('Bibliothèque vide', "Ajoute des plans avec un thème ci-dessus : le Montage auto en a besoin d'au moins 2.", 'film');
  grid.querySelectorAll('.bcard').forEach(card => {
    const clip = data.clips.find(c => String(c.id) === card.dataset.id);
    card.onclick = () => {   // play / stop the shot in place
      const playing = card.querySelector('video');
      if (playing){ playing.remove(); return; }
      card.insertAdjacentHTML('afterbegin', `<video src="${clip.video_url}" autoplay muted loop playsinline></video>`);
    };
    card.querySelector('.bdel').onclick = async ev => {
      ev.stopPropagation();
      if (!confirm('Supprimer ce plan de la bibliothèque ?')) return;
      try { await api(`/api/broll/${card.dataset.id}`, { method:'DELETE' }); loadBrollLibrary(); }
      catch (e){ log(e.message, 'error'); }
    };
  });
}

async function fetchBroll(){
  const theme = document.getElementById('brollTheme').value.trim();
  if (!theme){ document.getElementById('brollTheme').focus(); return; }
  const btn = document.getElementById('brollFetchBtn');
  btn.disabled = true; btn.innerHTML = spin('Téléchargement…');
  try {
    const r = await api('/api/broll/fetch', { method:'POST', body: JSON.stringify({ theme, count: 3 }) });
    toast(r.added.length ? `${r.added.length} plan(s) ajouté(s)` : 'Aucun nouveau plan Full HD pour ce thème', r.added.length ? 'success' : undefined);
    await loadBrollLibrary();
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; btn.innerHTML = 'Ajouter 3 plans'; }
}
document.getElementById('brollFetchBtn').addEventListener('click', fetchBroll);
document.getElementById('brollTheme').addEventListener('keydown', e => { if (e.key === 'Enter') fetchBroll(); });

// A video saved by hand from a site the app can't read (Douyin's app, Xiaohongshu, a private post), dropped
// on a plan or as a source: sent with whom to credit; the answer is the project.
async function adDropFile(input, btn, path, credit, done){
  const file = input.files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  form.append('credit', credit || '');
  btn.disabled = true; btn.innerHTML = spin(path.startsWith('plans') ? "l'IA regarde ta vidéo…" : 'envoi…');
  try {
    const res = await fetch(`/api/adaptations/${adCurrent}/${path}`, { method: 'POST', body: form });
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || 'Envoi impossible');
    toast(`« ${file.name} » déposé`, 'success');
    done(d);
  } catch (e){ log(e.message, 'error'); btn.disabled = false; btn.textContent = btn.dataset.label; }
  finally { input.value = ''; }
}

// What the useful re-edits credit (their description, the names on their pictures): the way to the
// original footage. A TikTok / Instagram account can't be listed from here: its profile is to open by hand.
function adOriginalsHtml(sug, cand, box = 'ad-clips'){
  const o = sug.originaux || {};
  if (!(o.comptes || []).length && !(o.videos || []).length) return '';
  const linksOf = ls => (ls || []).map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} ↗</a>`).join(' ');
  const loose = (o.videos || []).filter(v => !(o.comptes || []).some(a => (a.videos || []).some(x => x.url === v.url)));
  return `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${icon('link', 14)} Originaux cités par des remontages</div>
      <div class="meta" style="margin-left:0">Des vidéos d'autres créateurs montrent les bonnes scènes : voici qui elles créditent. Les vidéos trouvées ont été vérifiées par l'IA ; un compte TikTok ou Instagram s'ouvre à la main, copie ensuite le lien de la bonne vidéo.</div></div></div>
    <div class="chcard-body">
      ${(o.comptes || []).map(a => `<div class="ad-row"><b>${esc(a.name)}</b> <span class="tiny">cité par « ${esc((a.via_titre || '').slice(0, 60))} »</span> ${linksOf(a.links)}</div>
        ${(a.videos || []).length ? `<div class="${box}">${a.videos.map(cand).join('')}</div>` : ''}`).join('')}
      ${loose.length ? `<div class="tiny">Liens de vidéos donnés comme source dans leur description :</div><div class="${box}">${loose.map(cand).join('')}</div>` : ''}
    </div></article>`;
}

// ---------- Réglages → Effets sonores : the sounds the montage plays, by rule ----------

const SFX_NAMES = { whoosh: 'Whoosh', shutter: 'Déclic (shutter)', riser: 'Montée (riser)', impact: 'Impact', pop: 'Pop' };
let sfxAudio = null, sfxData = null;

async function loadSfxSettings(){
  sfxData = await api('/api/sfx');
  const d = sfxData, box = document.getElementById('sfxList');
  const sel = document.getElementById('sfxKind'), kept = sel.value;
  sel.innerHTML = Object.keys(d.regles).map(k => `<option value="${k}">${esc(SFX_NAMES[k] || k)}</option>`).join('');
  if (kept) sel.value = kept;
  sfxRuleNote();
  const kinds = [...Object.keys(d.regles), ...[...new Set(d.sons.map(x => x.type))].filter(k => !d.regles[k])];
  box.innerHTML = `<div class="tiny">Au plus ${d.max} sons par vidéo, à ${d.ecart_s} s d'écart au moins ; le moment le plus fort de chaque son tombe sur l'évènement.</div>` +
    kinds.map(k => {
      const list = d.sons.filter(x => x.type === k), on = list.filter(x => x.actif).length;
      return `
      <article class="chcard">
        <div class="chcard-head"><div class="who"><div class="name">${esc(SFX_NAMES[k] || k)} <span class="tiny">(${on} actif${on > 1 ? 's' : ''} sur ${list.length})</span></div>
          <div class="meta" style="margin-left:0">${d.regles[k] ? `Joué quand : ${esc(d.regles[k])}` : 'Pas utilisé par le montage : aucune règle ne joue ce type.'}</div></div>
          ${d.regles[k] && list.length && !on ? '<span class="pill warn">Aucun son actif : ce moment restera muet</span>' : ''}</div>
        <div class="chcard-body">${list.map(x => `
          <div class="sfxrow" data-name="${esc(x.name)}" style="display:flex;align-items:center;gap:12px;padding:8px 0;border-top:1px solid var(--border-soft);flex-wrap:wrap;${x.actif ? '' : 'opacity:.55'}">
            <button class="btn ghost small" data-act="play" title="Écouter" style="flex:none">▶</button>
            <span class="vname" style="flex:1 1 200px;white-space:normal"><b>${esc(x.name.replace(/^[^_]+_/, '').replace(/\.(mp3|wav)$/, ''))}</b>
              <span class="tiny"> · ${x.duree != null ? `${x.duree} s` : ''}${x.perso ? ' · ajouté par toi' : ''}${x.licence ? ` · ${esc(x.licence)}` : ''}</span>
              ${x.source ? ` <a class="tiny" href="${esc(x.source)}" target="_blank" rel="noopener">source ↗</a>` : ''}</span>
            ${d.regles[k] ? `<label class="tiny" style="display:flex;gap:6px;align-items:center;cursor:pointer;flex:none"><input type="checkbox" data-act="on" ${x.actif ? 'checked' : ''}> Utilisé</label>` : ''}
            ${x.perso ? `<button class="btn ghost small" data-act="del" title="Supprimer" style="flex:none">✕</button>` : ''}
          </div>`).join('') || '<span class="tiny">Aucun son de ce type pour l\'instant.</span>'}</div>
      </article>`;
    }).join('');
  box.querySelectorAll('.sfxrow').forEach(row => {
    const name = row.dataset.name;
    row.querySelector('[data-act="play"]').onclick = () => {
      if (sfxAudio) sfxAudio.pause();
      sfxAudio = new Audio(`/api/sfx/${encodeURIComponent(name)}/audio`);
      sfxAudio.play().catch(e => log(e.message, 'error'));
    };
    const on = row.querySelector('[data-act="on"]');
    if (on) on.onchange = async () => {
      try { await api(`/api/sfx/${encodeURIComponent(name)}`, { method:'PATCH', body: JSON.stringify({ actif: on.checked }) }); loadSfxSettings(); }
      catch (e){ on.checked = !on.checked; log(e.message, 'error'); }
    };
    const del = row.querySelector('[data-act="del"]');
    if (del) del.onclick = async () => {
      if (!confirm('Supprimer ce son ?')) return;
      try { await api(`/api/sfx/${encodeURIComponent(name)}`, { method:'DELETE' }); loadSfxSettings(); }
      catch (e){ log(e.message, 'error'); }
    };
  });
}

function sfxRuleNote(){
  const k = document.getElementById('sfxKind').value;
  document.getElementById('sfxRuleNote').textContent = sfxData && k ? `Un son « ${SFX_NAMES[k] || k} » sera joué quand : ${sfxData.regles[k]}.` : '';
}
document.getElementById('sfxKind').addEventListener('change', sfxRuleNote);
document.getElementById('sfxAddBtn').addEventListener('click', () => document.getElementById('sfxFile').click());
document.getElementById('sfxFile').addEventListener('change', async ev => {
  const file = ev.target.files[0];
  if (!file) return;
  const btn = document.getElementById('sfxAddBtn');
  const form = new FormData();
  form.append('file', file);
  form.append('kind', document.getElementById('sfxKind').value);
  form.append('source', document.getElementById('sfxSource').value);
  form.append('licence', document.getElementById('sfxLicence').value);
  btn.disabled = true; btn.innerHTML = spin('Préparation…');
  try {
    const res = await fetch('/api/sfx', { method:'POST', body: form });
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || 'Envoi impossible');
    toast(`« ${d.name} » ajouté`, 'success');
    document.getElementById('sfxSource').value = '';
    await loadSfxSettings();
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Choisir le fichier…'; ev.target.value = ''; }
});

// ---------- Réglages → Voix : the voice library + each channel's language / voice / music ----------

let voiceLanguages = {};
const STANDARD_ACCENTS = ['standard', 'modern standard', 'parisian'];
function accentBadge(a){
  if (!a) return '';
  return `<span class="accent ${STANDARD_ACCENTS.includes(String(a).toLowerCase()) ? 'std' : ''}">${esc(a)}</span>`;
}
function voiceLabel(v){ return `${v.display_name}${v.accent ? ` (${v.accent})` : ''}`; }

async function loadVoiceSettings(){
  const box = document.getElementById('voiceLibrary');
  const data = await api('/api/voices');
  voiceLanguages = data.languages || {};
  const byLang = {};
  data.voices.forEach(v => (byLang[v.language || '?'] ||= []).push(v));
  box.innerHTML = Object.keys(byLang).length ? Object.entries(byLang).map(([lg, vs]) => `
    <article class="chcard">
      <div class="chcard-head"><div class="who"><div class="name">${icon('mic', 14)} ${esc(voiceLanguages[lg] || lg)} · ${vs.length} voix</div></div></div>
      <div class="chcard-body" style="gap:0">${vs.map(v => `
        <div class="vrow" data-voice="${v.voice_id}">
          <input class="f v-name" value="${esc(v.display_name)}" title="${esc(v.name || '')} — ${esc(v.voice_id)}">
          <div>${accentBadge(v.accent)}</div>
          <div class="tiny">${esc([v.gender === 'male' ? 'homme' : v.gender === 'female' ? 'femme' : v.gender, v.age && v.age.replace('_', ' ')].filter(Boolean).join(', '))}</div>
          ${v.has_preview ? `<audio controls preload="none" src="${v.preview_url}"></audio>` : '<span class="tiny">pas d\'extrait</span>'}
          <button class="btn ghost small v-del" title="Retirer cette voix">✕</button>
        </div>`).join('')}
      </div>
    </article>`).join('') : emptyState('Aucune voix', 'Ajoute des identifiants ElevenLabs ci-dessus.', 'mic');
  box.querySelectorAll('.vrow').forEach(row => {
    const id = row.dataset.voice;
    row.querySelector('.v-name').onchange = async e => {
      try { await api(`/api/voices/${id}`, { method:'PATCH', body: JSON.stringify({ name: e.target.value }) }); toast('Nom enregistré', 'success'); }
      catch (err){ log(err.message, 'error'); }
    };
    row.querySelector('.v-del').onclick = async () => {
      if (!confirm('Retirer cette voix de la bibliothèque ?')) return;
      try { await api(`/api/voices/${id}`, { method:'DELETE' }); loadVoiceSettings(); } catch (err){ log(err.message, 'error'); }
    };
  });
  await loadAdaptationChannels();
}

document.getElementById('voiceAddBtn').addEventListener('click', async () => {
  const ids = document.getElementById('voiceIds').value.split(/[\s,;]+/).map(x => x.trim()).filter(Boolean);
  if (!ids.length) return;
  const btn = document.getElementById('voiceAddBtn'), note = document.getElementById('voiceAddNote');
  btn.disabled = true; btn.innerHTML = spin('Recherche chez ElevenLabs…');
  try {
    const r = await api('/api/voices', { method:'POST', body: JSON.stringify({ voice_ids: ids }) });
    note.textContent = `${r.added.length} ajoutée(s)` + (r.failed.length ? ` · ${r.failed.length} introuvable(s) : ${r.failed.map(f => f.voice_id).join(', ')}` : '');
    document.getElementById('voiceIds').value = r.failed.map(f => f.voice_id).join('\n');
    await loadVoiceSettings();
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; btn.innerHTML = 'Ajouter'; hydrateIcons(btn); }
});

async function loadAdaptationChannels(){
  const grid = document.getElementById('adChannelGrid');
  grid.innerHTML = channels.map(ch => `<article class="chcard" data-channel="${ch.name}">${spinnerHtml('Chargement...')}</article>`).join('');
  await Promise.all(channels.map(async ch => {
    const card = grid.querySelector(`[data-channel="${ch.name}"]`);
    try { renderAdaptationChannel(card, ch, await api(`/api/channels/${ch.name}/adaptation`)); }
    catch (e){ showLoadError(card, e, () => loadAdaptationChannels()); }
  }));
}

function renderAdaptationChannel(card, ch, data){
  const s = data.settings;
  const voice = data.voices.find(v => v.voice_id === s.voice_id);
  const musicUrl = f => `/api/channels/${ch.name}/assets/music/${encodeURIComponent(f)}`;
  card.innerHTML = `
    <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div></div>
      <select class="f ad-lang" style="width:auto">${Object.entries(voiceLanguages).map(([k, l]) => `<option value="${k}" ${k === s.language ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></div>
    <div class="chcard-body">
      <label class="f">Voix</label>
      <select class="f ad-voice"><option value="">— aucune —</option>${data.voices.map(v =>
        `<option value="${v.voice_id}" ${v.voice_id === s.voice_id ? 'selected' : ''}>${esc(voiceLabel(v))}</option>`).join('')}</select>
      ${voice && voice.has_preview ? `<audio controls preload="none" src="${voice.preview_url}" style="width:100%;height:32px"></audio>` :
        (data.voices.length ? '' : `<div class="tiny">Aucune voix dans cette langue : ajoute-en ci-dessus.</div>`)}
    </div>
    <div class="chcard-body">
      <label class="f">Musique de fond</label>
      <select class="f ad-music"><option value="">— aucune —</option>${data.music_files.map(f => `<option ${f === s.music_file ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>
      ${s.music_file ? `<audio class="ad-audio" controls preload="none" src="${musicUrl(s.music_file)}" style="width:100%;height:32px"></audio>
        <div class="entry-row"><input class="f ad-start" type="number" min="0" step="0.5" value="${s.music_start}"><span class="tiny">s : départ de la musique (${fmtSec(s.music_start)})</span>
        <button class="btn secondary small ad-take">Prendre l'instant du lecteur</button></div>` :
        '<div class="tiny">Les morceaux viennent du dossier musique de la chaîne (Réglages → Montage → Ajouter).</div>'}
    </div>
    <div class="chcard-body">
      <label class="f">Style visuel (bandeaux et sous-titres de toutes ses vidéos Adaptation)</label>
      <select class="f ad-style" style="width:auto">${(data.styles || []).map(st => `<option value="${st.name}" ${st.name === s.style ? 'selected' : ''}>${esc(st.label)}</option>`).join('')}</select>
      <img class="ad-style-prev" src="/api/adaptation/styles/${s.style}/preview?lang=${s.language}" alt="" style="width:100%;max-width:540px;border-radius:8px;display:block">
    </div>`;
  const save = async body => {
    try { renderAdaptationChannel(card, ch, await api(`/api/channels/${ch.name}/adaptation`, { method:'PUT', body: JSON.stringify(body) })); }
    catch (e){ log(e.message, 'error'); }
  };
  card.querySelector('.ad-lang').onchange = e => save({ language: e.target.value, settings: { voice_id: null } });
  card.querySelector('.ad-voice').onchange = e => save({ settings: { voice_id: e.target.value || null } });
  card.querySelector('.ad-music').onchange = e => save({ settings: { music_file: e.target.value || null } });
  const styleSel = card.querySelector('.ad-style');
  if (styleSel) styleSel.onchange = e => save({ settings: { style: e.target.value } });
  const start = card.querySelector('.ad-start'), audio = card.querySelector('.ad-audio');
  if (start) start.onchange = () => save({ settings: { music_start: parseFloat(start.value) || 0 } });
  if (start && audio) card.querySelector('.ad-take').onclick = () => save({ settings: { music_start: Math.round(audio.currentTime * 2) / 2 } });
}
