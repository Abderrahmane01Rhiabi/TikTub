// ---------- Génération : décor -> script -> audio -> assemblage ----------
// Un seul brouillon actif à la fois. Une fois assemblée (ready_for_upload),
// la vidéo n'est plus renvoyée par /generated_videos — cette page repart à
// zéro, la vidéo se termine à l'étape 6 · Résultats IA.

const generationScreen = document.getElementById('generationScreen');
let genChannel = null;
let genAssets = { backgrounds: [], music: [] };
let genVoices = [];         // the library's French voices (Réglages → Voix)
const DRONES_CHOICE = '__drones__';   // generative.pipeline.DRONES_CHOICE
let genBatchId = null;      // the batch currently shown, or null = show the "how many videos" starter
let genBatchPollTimer = null;
let genCardStatus = {};     // video_id -> last-rendered status, so a card whose status hasn't
                             // changed (e.g. mid-edit, or a decor pick in progress) is never
                             // blindly re-rendered just because a sibling in the same batch changed
const MAX_BATCH_COUNT = 20;
// Mirrors generative.caption_styles.CUSTOMIZABLE_COLOR_STYLES — only these
// styles have an accent color worth exposing a picker for.
const CAPTION_COLOR_STYLES = new Set(['karaoke', 'bounce', 'typewriter']);
const CAPTION_STYLE_DEFAULT_COLOR = { karaoke: '#ffe000', bounce: '#6d8dfd', typewriter: '#ffe000' };
function spin(text){ return `<span class="spinner"></span> ${esc(text)}`; }

document.getElementById('genBackBtn').addEventListener('click', startNewBatch);

function generationChannels(){ return channels.filter(ch => ch.generation_mode); }

function openGeneration(){
  screens.forEach(el => el.classList.remove('active'));
  generationScreen.classList.add('active');
  const gchs = generationChannels();
  if (!genChannel && gchs.length) genChannel = gchs[0].name;
  renderGenChannelChips();
  if (genChannel) loadGeneration(genChannel);
}

function startNewBatch(){
  clearTimeout(genBatchPollTimer);
  genBatchId = null;
  genCardStatus = {};
  renderStarter();
}

function renderGenChannelChips(){
  const seg = document.getElementById('genChannelSeg');
  const gchs = generationChannels();
  if (!gchs.length){
    seg.innerHTML = '<span class="empty-note">Aucune chaîne en mode génération (generation_mode) pour l\'instant.</span>';
    return;
  }
  seg.innerHTML = gchs.map(ch => `
    <button class="seg-opt ${ch.name === genChannel ? 'active' : ''}" data-ch="${ch.name}">
      <span class="dot" style="background:${channelColor(ch.name)};display:inline-block;margin-right:5px"></span>${esc(ch.display_name)}
    </button>`).join('');
  seg.querySelectorAll('.seg-opt').forEach(btn => btn.addEventListener('click', () => {
    genChannel = btn.dataset.ch;
    clearTimeout(genBatchPollTimer);
    genBatchId = null;
    genCardStatus = {};
    renderGenChannelChips();
    loadGeneration(genChannel);
  }));
}

async function loadGeneration(channelName){
  const stage = document.getElementById('genStage');
  stage.innerHTML = spinnerHtml('Chargement...');
  try {
    const [videos, assets, voices] = await Promise.all([
      api(`/api/channels/${channelName}/generated_videos`),
      api(`/api/channels/${channelName}/assets`),
      api('/api/voices?language=fr').catch(() => ({ voices: [] }))
    ]);
    genAssets = assets;
    genVoices = voices.voices || [];
    if (videos.length){
      // Some draft(s) from before a page reload/channel switch are still
      // mid-flow — resume that batch's view (pollBatchProgress re-fetches
      // with batch_id, which also picks up any sibling already finished).
      genCardStatus = {};
      genBatchId = (genPreferredBatch && videos.some(v => v.batch_id === genPreferredBatch)) ? genPreferredBatch : videos[0].batch_id;
      genPreferredBatch = null;
      pollBatchProgress(genBatchId);
    } else {
      genBatchId = null;
      renderStarter();
    }
  } catch (e){
    showLoadError(stage, e, () => loadGeneration(channelName));
    log(e.message, 'error');
  }
}

// ---- Starter : combien de vidéos ----

function renderStarter(){
  const stage = document.getElementById('genStage');
  stage.innerHTML = `
    <article class="chcard" style="max-width:560px">
      <div class="chcard-head">
        <div class="who"><div class="name">${icon('sparkle', 15)} Nouveau lot</div></div>
        <span class="pill wait">Max ${MAX_BATCH_COUNT}</span>
      </div>
      <div class="chcard-body">
        <div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap">
          <div>
            <label class="f">Nombre de vidéos</label>
            <input class="f" type="number" id="draftCountInput" value="1" min="1" max="${MAX_BATCH_COUNT}" style="width:90px">
          </div>
          <button class="btn primary" id="startBatchBtn">Générer le script →</button>
          <span class="progress-text" id="genNote"></span>
        </div>
        <div class="facts">
          <div class="fact">${icon('edit')}<span>1. Scripts écrits par l'IA — gratuit, tu les relis et corriges</span></div>
          <div class="fact">${icon('mic')}<span>2. Voix ElevenLabs pour tout le lot — consomme des crédits</span></div>
          <div class="fact">${icon('film')}<span>3. Décor de chaque vidéo, puis création</span></div>
        </div>
      </div>
    </article>`;
  document.getElementById('draftCountInput').addEventListener('input', updateStartBatchLabel);
  document.getElementById('startBatchBtn').addEventListener('click', startBatch);
}

function readCountInput(){
  return Math.max(1, Math.min(MAX_BATCH_COUNT, parseInt(document.getElementById('draftCountInput').value, 10) || 1));
}

function updateStartBatchLabel(){
  const count = readCountInput();
  document.getElementById('startBatchBtn').textContent =
    count > 1 ? `Générer les ${count} scripts →` : 'Générer le script →';
}

async function startBatch(){
  const count = readCountInput();
  const btn = document.getElementById('startBatchBtn');
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = spin('Lancement...');
  try {
    const result = await api(`/api/channels/${genChannel}/generation_draft`, {
      method: 'POST',
      body: JSON.stringify({ count }),
    });
    genCardStatus = {};
    genBatchId = result.batch_id;
    pollBatchProgress(genBatchId);
  } catch (e){
    log(e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

// ---- Batch view (scripts -> audio -> decor/assemble, all per-video cards) ----

async function pollBatchProgress(batchId){
  clearTimeout(genBatchPollTimer);
  let videos, activeResp;
  try {
    [videos, activeResp] = await Promise.all([
      api(`/api/channels/${genChannel}/generated_videos?batch_id=${encodeURIComponent(batchId)}`),
      api(`/api/batches/${encodeURIComponent(batchId)}/active`),
    ]);
  } catch (e){
    log(e.message, 'error');
    genBatchPollTimer = setTimeout(() => pollBatchProgress(batchId), 5000);
    return;
  }

  if (!videos.length){
    // Every draft in this batch was individually abandoned — nothing left
    // to show, back to the starter.
    genBatchId = null;
    renderStarter();
    return;
  }

  renderBatchGrid(batchId, videos, activeResp.active);
  const assembling = videos.some(v => v.status === 'assembling');
  if (activeResp.active || assembling){
    genBatchPollTimer = setTimeout(() => pollBatchProgress(batchId), assembling ? 1500 : 3000);
  }
}

function renderBatchGrid(batchId, videos, active){
  const stage = document.getElementById('genStage');
  let cards = document.getElementById('genBatchCards');
  if (!cards){
    stage.innerHTML = `
      <div id="genBatchSummary" class="card"></div>
      <div id="genBatchCards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,440px),1fr));gap:12px;margin-top:12px;align-items:start"></div>`;
    cards = document.getElementById('genBatchCards');
  }

  renderBatchSummary(batchId, videos, active);

  const seen = new Set();
  videos.forEach((v, i) => {
    seen.add(v.video_id);
    let card = cards.querySelector(`[data-video="${v.video_id}"]`);
    if (!card){
      card = document.createElement('div');
      card.className = 'card';
      card.dataset.video = v.video_id;
      cards.appendChild(card);
    }
    // A card whose status hasn't changed since the last poll is left alone —
    // it may hold an in-progress script edit or a decor pick that a blind
    // refresh would wipe out, since sibling videos can still be generating.
    if (genCardStatus[v.video_id] === v.status && v.status === 'assembling'){
      const slot = card.querySelector('[data-role="progress"]');
      if (slot) slot.innerHTML = progressBarHtml(v.progress || { fraction: 0 }, 'Encodage de la vidéo');
    }
    if (genCardStatus[v.video_id] !== v.status){
      // The décor card carries a full-size WYSIWYG preview (background +
      // caption style together) — give it more room than the other, purely
      // textual card states.
      card.innerHTML = cardBodyHtml(v, i);
      wireCardEvents(card, v, batchId);
      genCardStatus[v.video_id] = v.status;
    }
  });

  cards.querySelectorAll('[data-video]').forEach(card => {
    if (!seen.has(card.dataset.video)){
      card.remove();
      delete genCardStatus[card.dataset.video];
    }
  });
}

function renderBatchSummary(batchId, videos, active){
  const scripting = videos.filter(v => v.status === 'awaiting_script').length;
  const readyForAudio = videos.filter(v => v.status === 'script_generated').length;
  const readyForDecor = videos.filter(v => v.status === 'audio_generated').length;
  const done = videos.filter(v => v.status === 'ready_for_upload').length;
  const assemblingCount = videos.filter(v => v.status === 'assembling').length;
  const failed = videos.filter(v => v.status === 'rendering_failed').length;
  // active + no video left awaiting_script means phase 2 (audio) is the one
  // running — script_generated is ambiguous on its own (it's both "phase 1
  // done, waiting for you" and "phase 2 hasn't reached this one yet").
  const audioRunning = active && scripting === 0 && readyForAudio > 0;

  let phaseLine;
  if (scripting > 0){
    phaseLine = `Écriture des scripts en cours (${videos.length - scripting}/${videos.length})…`;
  } else if (audioRunning){
    phaseLine = `Génération audio en cours (${videos.length - scripting - readyForAudio}/${videos.length - scripting})…`;
  } else if (readyForAudio > 0){
    phaseLine = `${readyForAudio} script${readyForAudio > 1 ? 's' : ''} prêt${readyForAudio > 1 ? 's' : ''} à relire — corrige-les si besoin, puis lance ${readyForAudio > 1 ? 'les audios' : "l'audio"}.`;
  } else if (assemblingCount > 0){
    phaseLine = `Création en cours : ${assemblingCount} vidéo${assemblingCount > 1 ? 's' : ''}…`;
  } else if (readyForDecor > 0 && done + failed < videos.length){
    phaseLine = `${readyForDecor} vidéo${readyForDecor > 1 ? 's' : ''} prête${readyForDecor > 1 ? 's' : ''} pour le décor.`;
  } else {
    phaseLine = `${done} prête${done > 1 ? 's' : ''}, ${failed} échec${failed > 1 ? 's' : ''} sur ${videos.length}.`;
  }

  const summary = document.getElementById('genBatchSummary');
  summary.innerHTML = `
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <div style="font-size:13px;font-weight:600;flex:1">${(active && (scripting > 0 || audioRunning)) || assemblingCount ? spin(phaseLine) : esc(phaseLine)}</div>
      ${readyForAudio > 0 && scripting === 0 && !audioRunning
        ? `<button class="btn primary small" id="genAudioAllBtn">${icon('mic', 14)} Générer ${readyForAudio > 1 ? `les ${readyForAudio} audios` : "l'audio"}</button>`
        : ''}
    </div>
    ${done + failed === videos.length
      ? `<div class="progress-text" style="margin-top:6px">Terminé — les vidéos prêtes t'attendent dans Publication → Résultats IA. <a href="#" data-go-results>Y aller →</a></div>`
      : ''}`;

  const goResults = summary.querySelector('[data-go-results]');
  if (goResults) goResults.addEventListener('click', ev => { ev.preventDefault(); goTo(5); });

  const audioBtn = document.getElementById('genAudioAllBtn');
  if (audioBtn){
    audioBtn.addEventListener('click', async () => {
      if (!confirm(`Générer ${readyForAudio > 1 ? `les ${readyForAudio} audios` : "l'audio"} maintenant ? Ceci consomme des crédits ElevenLabs.`)) return;
      audioBtn.disabled = true;
      audioBtn.innerHTML = spin('Lancement...');
      try {
        await api(`/api/batches/${batchId}/generate_audio`, { method: 'POST' });
      } catch (e){ log(e.message, 'error'); }
      pollBatchProgress(batchId);
    });
  }
}

function genHead(v, i, pillCls, pillText){
  return `<div style="padding:0 0 10px;margin-bottom:10px;border-bottom:1px solid var(--border-soft);display:flex;flex-direction:column;gap:6px">
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
      <span class="gen-label"><span class="num" style="white-space:nowrap">VIDÉO ${i + 1}</span></span>
      <span style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap">
        ${v.inspired_by ? `<span class="pill ok" title="Écrite dans le style d'une vidéo qui a très bien marché">★ Style gagnant</span>` : ''}
        <span class="pill ${pillCls}">${pillText}</span>
      </span>
    </div>
    ${v.title ? `<div style="font-size:13px;font-weight:600;line-height:1.35">${esc(v.title)}</div>` : ''}
    ${planLine(v)}
  </div>`;
}

// The plan the script was written in (format, topic, hook, ending: each the
// one the channel used least lately), and what still bothered after the retries.
function planLine(v){
  const p = v.script_plan;
  if (!p) return '';
  const parts = [`<b>${esc(SCRIPT_FORMATS[p.format] || p.format)}</b>`, esc(p.sujet),
                 `accroche : ${esc(SCRIPT_HOOKS[p.accroche] || p.accroche)}`, `fin : ${esc(SCRIPT_ENDINGS[p.fin] || p.fin)}`];
  const warns = (v.script_warnings || []).map(w => `<div style="color:#f5c56d">⚠ ${esc(w)}</div>`).join('');
  return `<div class="tiny" style="color:var(--muted);line-height:1.45">${parts.join(' · ')}${warns}</div>`;
}

// The voice the draft is (or will be) read with: its own, else the channel's.
function voicePicker(v, label){
  if (!genVoices.length) return '';
  const current = v.voice_id || v.default_voice_id;
  const opts = genVoices.map(x => {
    const bits = [x.gender === 'female' ? 'femme' : x.gender === 'male' ? 'homme' : '', x.accent && x.accent !== 'standard' ? x.accent : '']
      .filter(Boolean).join(', ');
    const mark = x.voice_id === v.default_voice_id ? ' · voix de la chaîne' : '';
    return `<option value="${esc(x.voice_id)}" ${x.voice_id === current ? 'selected' : ''}>${esc(x.display_name)}${bits ? ` (${esc(bits)})` : ''}${mark}</option>`;
  }).join('');
  const cur = genVoices.find(x => x.voice_id === current);
  return `<div style="margin-top:8px"><label class="f">${esc(label)}</label>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <select class="f" data-role="voice" style="flex:1;min-width:200px">${opts}</select>
      <audio data-role="voice-preview" controls preload="none" style="height:32px;max-width:220px" ${cur ? `src="${esc(cur.preview_url)}"` : ''}></audio>
    </div></div>`;
}

function cardBodyHtml(v, i){

  if (v.status === 'awaiting_script'){
    return `${genHead(v, i, 'wait', 'Écriture…')}
      <div style="font-size:13px">${spin('Écriture du script...')}</div>`;
  }

  if (v.status === 'script_generated'){
    return `${genHead(v, i, 'warn', 'Script à relire')}
      <textarea class="f" data-role="script" style="min-height:120px">${esc(v.script_text || '')}</textarea>
      ${voicePicker(v, 'Voix')}
      <div class="actions" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center">
        <button class="btn secondary small" data-action="save-script">Sauver</button>
        <button class="btn ghost small" data-action="regen-script">${icon('refresh', 13)} Régénérer</button>
        <button class="btn ghost small danger" data-action="drop">${icon('trash', 13)} Abandonner</button>
        <span class="progress-text" data-role="note"></span>
      </div>`;
  }

  if (v.status === 'audio_generated'){
    // first and default: a different drone shot per sentence (never the same background twice)
    const bgOptions = `<option value="${DRONES_CHOICE}">✨ Drones — un plan différent par phrase (recommandé)</option>` +
      genAssets.backgrounds.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('');
    const muOptions = genAssets.music.length
      ? genAssets.music.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('')
      : `<option value="">Aucun fichier — ajoute-en dans channels/${esc(genChannel)}/assets/music/</option>`;
    return `${genHead(v, i, 'ok', 'Voix prête — choisis le décor')}
      ${v.decor_preset ? `<div class="tiny" style="margin:-4px 0 8px;color:var(--muted)">Décor pré-rempli avec ${v.decor_preset.from_recipe ? 'la recette gagnante de la chaîne' : 'celui de la vidéo modèle'} — modifiable.</div>` : ''}
      <audio src="/api/videos/${v.video_id}/narration" controls style="width:100%"></audio>
      ${voicePicker(v, "Voix (pour changer : choisis-en une puis « Régénérer l'audio »)")}
      <div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap-reverse;align-items:flex-end">
        <div style="flex:1;min-width:200px;display:flex;flex-direction:column;gap:6px">
          <div><label class="f">Fond vidéo</label><select class="f" data-role="bg">${bgOptions}</select></div>
          <div>
            <label class="f">Musique</label><select class="f" data-role="music">${muOptions}</select>
            <audio data-role="music-preview" controls style="width:100%;margin-top:6px;height:32px" ${genAssets.music.length ? `src="/api/channels/${genChannel}/assets/music/${encodeURIComponent(genAssets.music[0])}"` : ''}></audio>
          </div>
          <div><label class="f">Cadrage</label>
            <select class="f" data-role="frame">
              <option value="fill">Plein cadre</option>
              <option value="letterbox">Haut/bas</option>
              <option value="full_border">4 côtés</option>
            </select>
          </div>
          <div><label class="f">Style de sous-titres</label>
            <select class="f" data-role="caption-style">
              <option value="karaoke">★ Karaoke (actuel)</option>
              <option value="mrbeast">MrBeast</option>
              <option value="hormozi">Hormozi</option>
              <option value="bounce">★ Spring / Bounce</option>
              <option value="typewriter">★ Typewriter</option>
              <option value="minimal">★ Minimaliste / Cinéma</option>
            </select>
          </div>
          <div data-role="caption-color-row" style="display:none;align-items:center;gap:8px">
            <label class="f" style="margin:0">Couleur</label>
            <input type="color" data-role="caption-color" value="${CAPTION_STYLE_DEFAULT_COLOR.karaoke}" style="width:40px;height:28px;padding:2px;background:var(--panel2);border:1px solid var(--border);border-radius:6px;cursor:pointer">
          </div>
          <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted)">
            <input type="checkbox" data-role="rounded"> Coins arrondis
          </label>
        </div>
        <div class="fpreview-box" style="width:100%;max-width:260px;flex:none;margin:0 auto">
          <div class="fpreview-spinner"><span class="spinner"></span></div>
          <img class="fpreview-img" data-role="preview" alt="Aperçu du décor">
        </div>
      </div>
      <div class="actions" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
        <button class="btn primary small" data-action="finalize">${icon('film', 13)} Lancer la création</button>
        <button class="btn ghost small" data-action="regen-audio">${icon('refresh', 13)} Régénérer l'audio</button>
        <span class="progress-text" data-role="note"></span>
      </div>`;
  }

  if (v.status === 'assembling'){
    return `${genHead(v, i, 'wait', 'Création…')}
      <div data-role="progress">${progressBarHtml(v.progress || { fraction: 0 }, 'Encodage de la vidéo')}</div>
      <div class="tiny" style="margin-top:8px">Tu peux changer d'écran ou recharger la page : la création continue.</div>`;
  }

  if (v.status === 'ready_for_upload'){
    return `${genHead(v, i, 'ok', icon('check', 11) + ' Créée')}
      <video src="${v.media_url || ''}" controls style="max-width:170px;aspect-ratio:9/16;border-radius:10px;background:#000"></video>`;
  }

  if (v.status === 'rendering_failed'){
    return `${genHead(v, i, 'bad', 'Échec')}
      <div class="muted" style="color:#f3b4b4;font-size:12px;overflow-wrap:anywhere">${esc(v.render_error || 'Échec inconnu.')}</div>
      <div class="actions" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
        <button class="btn primary small" data-action="retry">${icon('refresh', 13)} Réessayer</button>
        <button class="btn ghost small danger" data-action="drop">${icon('trash', 13)} Abandonner</button>
      </div>`;
  }

  return `${genHead(v, i, 'wait', esc(v.status))}`;
}

function wireCardEvents(card, v, batchId){
  const note = card.querySelector('[data-role="note"]');
  const refresh = () => { delete genCardStatus[v.video_id]; pollBatchProgress(batchId); };

  const saveBtn = card.querySelector('[data-action="save-script"]');
  if (saveBtn) saveBtn.addEventListener('click', async () => {
    try {
      await api(`/api/videos/${v.video_id}/script`, {
        method: 'PATCH',
        body: JSON.stringify({ script_text: card.querySelector('[data-role="script"]').value }),
      });
      if (note) note.textContent = 'Sauvé ✓';
    } catch (e){ log(e.message, 'error'); }
  });

  const regenScriptBtn = card.querySelector('[data-action="regen-script"]');
  if (regenScriptBtn) regenScriptBtn.addEventListener('click', async () => {
    const originalLabel = regenScriptBtn.innerHTML;
    regenScriptBtn.disabled = true;
    regenScriptBtn.innerHTML = spin('Écriture...');
    try {
      await api(`/api/videos/${v.video_id}/generate_script`, { method: 'POST' });
      refresh();
    } catch (e){
      log(e.message, 'error');
      regenScriptBtn.disabled = false;
      regenScriptBtn.innerHTML = originalLabel;
    }
  });

  const voiceSelect = card.querySelector('[data-role="voice"]');
  if (voiceSelect) voiceSelect.addEventListener('change', async () => {
    const pv = card.querySelector('[data-role="voice-preview"]');
    const chosen = genVoices.find(x => x.voice_id === voiceSelect.value);
    if (pv && chosen){ pv.src = chosen.preview_url; pv.play().catch(() => {}); }
    if (v.status === 'script_generated'){     // remembered for the batch's "Générer les audios"
      try { await api(`/api/videos/${v.video_id}/voice`, { method: 'POST', body: JSON.stringify({ voice_id: voiceSelect.value }) }); }
      catch (e){ log(e.message, 'error'); }
    }
  });

  const regenAudioBtn = card.querySelector('[data-action="regen-audio"]');
  if (regenAudioBtn) regenAudioBtn.addEventListener('click', async () => {
    if (!confirm('Regénérer la voix ? Ceci consomme à nouveau des crédits ElevenLabs.')) return;
    const originalLabel = regenAudioBtn.innerHTML;
    regenAudioBtn.disabled = true;
    regenAudioBtn.innerHTML = spin('Synthèse en cours (1-2 min)...');
    try {
      const voice = card.querySelector('[data-role="voice"]');
      await api(`/api/videos/${v.video_id}/generate_audio`, {
        method: 'POST', body: JSON.stringify({ voice_id: voice ? voice.value : null }) });
      refresh();
    } catch (e){
      log(e.message, 'error');
      regenAudioBtn.disabled = false;
      regenAudioBtn.innerHTML = originalLabel;
    }
  });

  const dropBtn = card.querySelector('[data-action="drop"]');
  if (dropBtn) dropBtn.addEventListener('click', async () => {
    if (!confirm('Abandonner cette vidéo ?')) return;
    try {
      await api(`/api/videos/${v.video_id}/generation_draft`, { method: 'DELETE' });
    } catch (e){ log(e.message, 'error'); return; }
    refresh();
  });

  const finalizeBtn = card.querySelector('[data-action="finalize"]');
  if (finalizeBtn) finalizeBtn.addEventListener('click', async () => {
    const bg = card.querySelector('[data-role="bg"]').value;
    const mu = card.querySelector('[data-role="music"]').value;
    const frameMode = card.querySelector('[data-role="frame"]').value;
    const rounded = card.querySelector('[data-role="rounded"]').checked;
    const captionStyle = card.querySelector('[data-role="caption-style"]').value;
    const captionColor = CAPTION_COLOR_STYLES.has(captionStyle)
      ? card.querySelector('[data-role="caption-color"]').value
      : null;
    if (!bg || !mu){ if (note) note.textContent = 'Choisis un fond vidéo ET une musique.'; return; }
    const originalLabel = finalizeBtn.innerHTML;
    finalizeBtn.disabled = true;
    finalizeBtn.innerHTML = spin('Lancement…');
    try {
      await api(`/api/videos/${v.video_id}/finalize`, {
        method: 'POST',
        body: JSON.stringify({
          bg_video_filename: bg, bg_music_filename: mu, frame_mode: frameMode, rounded_corners: rounded,
          caption_style: captionStyle, caption_color: captionColor,
        }),
      });
      refresh();
    } catch (e){
      log(e.message, 'error');
      if (note) note.textContent = 'Échec de la création.';
      finalizeBtn.disabled = false;
      finalizeBtn.innerHTML = originalLabel;
    }
  });

  const retryBtn = card.querySelector('[data-action="retry"]');
  if (retryBtn) retryBtn.addEventListener('click', async () => {
    retryBtn.disabled = true;
    retryBtn.innerHTML = spin('Nouvelle tentative...');
    try {
      await api(`/api/videos/${v.video_id}/advance`, { method: 'POST' });
    } catch (e){ log(e.message, 'error'); }
    refresh();
  });

  // Live decor preview, only relevant on the audio_generated (décor) card —
  // background AND caption style together, so picking a style shows right
  // away what it'll actually look like, not just its name in a dropdown.
  const bgSelect = card.querySelector('[data-role="bg"]');
  if (bgSelect){
    const frameSelect = card.querySelector('[data-role="frame"]');
    const roundedCheck = card.querySelector('[data-role="rounded"]');
    const captionSelect = card.querySelector('[data-role="caption-style"]');
    const colorRow = card.querySelector('[data-role="caption-color-row"]');
    const colorInput = card.querySelector('[data-role="caption-color"]');
    const updatePreview = () => {
      const bg = bgSelect.value;
      const img = card.querySelector('[data-role="preview"]');
      if (!bg || !img) return;
      const spinner = img.parentElement.querySelector('.fpreview-spinner');
      spinner.style.display = 'flex';
      img.classList.remove('loaded');
      img.onload = () => { spinner.style.display = 'none'; img.classList.add('loaded'); };
      img.onerror = () => { spinner.style.display = 'none'; };
      const colorParam = CAPTION_COLOR_STYLES.has(captionSelect.value) ? `&caption_color=${encodeURIComponent(colorInput.value)}` : '';
      img.src = `/api/channels/${genChannel}/asset_frame_preview?bg_video_filename=${encodeURIComponent(bg)}&frame_mode=${frameSelect.value}&rounded_corners=${roundedCheck.checked}&caption_style=${captionSelect.value}${colorParam}&t=${Date.now()}`;
    };
    const updateColorVisibility = () => {
      const customizable = CAPTION_COLOR_STYLES.has(captionSelect.value);
      // style.display, not the `hidden` attribute: the row's inline
      // display:flex overrode `hidden`, so the picker never disappeared
      colorRow.style.display = customizable ? 'flex' : 'none';
      if (customizable) colorInput.value = CAPTION_STYLE_DEFAULT_COLOR[captionSelect.value];
    };
    captionSelect.addEventListener('change', updateColorVisibility);
    [bgSelect, frameSelect, roundedCheck, captionSelect, colorInput].forEach(el => el.addEventListener('change', updatePreview));

    // "Refaire ce style": start from the top performer's décor (still editable)
    const preset = v.decor_preset;
    if (preset){
      if (preset.bg_video_filename && (preset.bg_video_filename === DRONES_CHOICE || genAssets.backgrounds.includes(preset.bg_video_filename))) bgSelect.value = preset.bg_video_filename;
      const mu = card.querySelector('[data-role="music"]');
      if (preset.bg_music_filename && genAssets.music.includes(preset.bg_music_filename)){
        mu.value = preset.bg_music_filename;
        const mp = card.querySelector('[data-role="music-preview"]');
        if (mp) mp.src = `/api/channels/${genChannel}/assets/music/${encodeURIComponent(preset.bg_music_filename)}`;
      }
      if (preset.frame_mode) frameSelect.value = preset.frame_mode;
      roundedCheck.checked = !!preset.rounded_corners;
      if (preset.caption_style) captionSelect.value = preset.caption_style;
    }
    updateColorVisibility();
    if (preset && preset.caption_color && CAPTION_COLOR_STYLES.has(captionSelect.value)) colorInput.value = preset.caption_color;
    updatePreview();
  }

  const musicSelect = card.querySelector('[data-role="music"]');
  const musicPreview = card.querySelector('[data-role="music-preview"]');
  if (musicSelect && musicPreview){
    musicSelect.addEventListener('change', () => {
      if (!musicSelect.value) return;
      musicPreview.pause();
      musicPreview.src = `/api/channels/${genChannel}/assets/music/${encodeURIComponent(musicSelect.value)}`;
      musicPreview.play().catch(() => {}); // autoplay can be blocked — controls are there regardless
    });
  }
}
