// ---------- Adaptation : project by project ----------

let adCurrent = null, adPoll = null, adProject = null;
const AD_BUSY = ['analysing', 'searching', 'fetching', 'scripting', 'voicing', 'rendering'];
const AD_STEPS = [['Modèle', ['analysing']], ['Sources', ['sources_search', 'searching', 'sources_review']], ['Script', ['scripting', 'script_review']],
                  ['Aperçu', ['voicing', 'preview_review']], ['Rendu', ['rendering', 'done']]];
const AD_STEPS_SCRIPT = [['Modèle', ['analysing']], ['Script', ['plan_review']], ['Images', ['searching', 'images_review', 'fetching']],
                         ['Aperçu', ['script_review', 'scripting', 'voicing', 'preview_review']], ['Rendu', ['rendering', 'done']]];
const AD_STATUS = { analysing: 'analyse…', plan_review: 'storyboard à relire', searching: 'recherche des images…', images_review: 'images à vérifier', fetching: 'téléchargement des moments…', sources_search: 'sources à choisir', sources_review: 'sources à vérifier', scripting: 'écriture…',
  script_review: 'scripts à relire', voicing: 'voix et aperçus…', preview_review: 'aperçus à valider',
  rendering: 'rendu…', done: 'terminé', error: 'erreur' };

async function openAdaptation(){
  screens.forEach(el => el.classList.remove('active'));
  document.getElementById('adaptationScreen').classList.add('active');
  if (!Object.keys(voiceLanguages).length){
    try { voiceLanguages = (await api('/api/voices')).languages || {}; } catch (e){ /* labels fall back to codes */ }
  }
  loadAdaptationList();
}

function renderAdChips(list){
  const bar = document.getElementById('adProjects');
  bar.innerHTML = list.length ? '<span class="tiny">Projets :</span>' + list.slice(0, 12).map(p =>
    `<button class="chipbtn ${p.project_id === adCurrent ? 'active' : ''}" data-id="${p.project_id}" style="${p.project_id === adCurrent ? 'border-color:var(--accent);color:var(--text)' : ''}">
      ${esc((p.subject || p.reference_url || '').slice(0, 34))}${p.group ? ' · ' + esc((p.targets || []).map(t => (channels.find(c => c.name === t.channel) || {}).display_name || t.channel).join(', ')) : ''} · ${esc(AD_STATUS[p.status] || p.status)}</button>`).join('')
    : '<span class="tiny">Aucun projet pour l\'instant.</span>';
  bar.querySelectorAll('.chipbtn').forEach(b => b.onclick = () => { adCurrent = b.dataset.id; loadAdaptationList(); });
}

async function loadAdaptationList(){
  const list = await api('/api/adaptations');
  if (adCurrent === null && list.length) adCurrent = list[0].project_id;
  renderAdChips(list);
  if (adCurrent && list.some(p => p.project_id === adCurrent)) loadAdProject();
  else { adCurrent = ''; renderNewAdaptation(); }
}
document.getElementById('adNewBtn').addEventListener('click', () => { adCurrent = ''; clearTimeout(adPoll); loadAdaptationList(); });

function adStepsHtml(status, mode){
  const steps = mode === 'script' ? AD_STEPS_SCRIPT : AD_STEPS;
  const at = steps.findIndex(([, sts]) => sts.includes(status));
  return `<div class="ad-steps">${steps.map(([l], i) =>
    `<div class="ad-step ${i < at || status === 'done' ? 'done' : i === at ? 'active' : ''}"><div class="bar"></div><div class="lbl">${i + 1} · ${l}</div></div>`).join('')}</div>`;
}

async function renderNewAdaptation(){
  const stage = document.getElementById('adStage');
  stage.innerHTML = spinnerHtml('Chargement...');
  const settingsByChannel = {};
  await Promise.all(channels.map(async ch => {
    try { settingsByChannel[ch.name] = await api(`/api/channels/${ch.name}/adaptation`); } catch (e){ /* shown as no voice */ }
  }));
  stage.innerHTML = `${adStepsHtml('new')}
    <article class="chcard">
      <div class="chcard-body">
        <label class="f">1. Le Short viral modèle (YouTube, TikTok…)</label>
        <input class="f" id="adRef" placeholder="https://www.youtube.com/shorts/…">
        <label class="f" style="margin-top:6px">2. Comment construire la vidéo ?</label>
        <div class="ad-row">
          <label class="switch" style="color:var(--text)"><input type="radio" name="adMode" value="script" checked> <b>Script d'abord</b> <span class="pill ok">conseillé</span>
            <span class="tiny">écrire le meilleur script (rétention) avec l'image voulue de chaque phrase, puis l'app cherche ces images plan par plan</span></label>
          <label class="switch" style="color:var(--text)"><input type="radio" name="adMode" value="sources"> <b>Sources d'abord</b>
            <span class="tiny">tu as déjà les vidéos, ou tu préfères les choisir d'abord : le script est écrit avec les clips trouvés</span></label>
        </div>
        <label class="switch" id="adVersionsBox" style="color:var(--text);margin-top:4px"><input type="checkbox" id="adVersions" checked>
          <b>Une version différente par chaîne</b> <span class="tiny">chaque chaîne a son angle, son accroche et sa fin (sinon : la même vidéo traduite) ; en « Sources d'abord », avec les mêmes clips</span></label>
        <div id="adSrcBox" style="display:none"><label class="f" style="margin-top:6px">Facultatif : les vidéos d'origine des clips, une par ligne. Laisse vide si tu ne les as pas : l'app te dira quoi chercher et te proposera des vidéos.</label>
        <textarea class="f" id="adSrc" rows="4" placeholder="https://www.tiktok.com/@…/video/…"></textarea></div>
        <label class="f" style="margin-top:6px">3. Les chaînes qui recevront une version (chacune dans sa langue, avec sa voix)</label>
        <div class="stack" style="gap:6px">${channels.map(ch => {
          const d = settingsByChannel[ch.name], s = d && d.settings, v = d && d.voices.find(x => x.voice_id === s.voice_id);
          return `<label class="switch" style="color:var(--text)"><input type="checkbox" class="ad-target" value="${ch.name}" ${v ? '' : 'disabled'}>
            <span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}
            <span class="tiny">${s ? esc(voiceLanguages[s.language] || s.language) : ''} · ${v ? esc(v.display_name) : 'pas de voix (Réglages → Voix)'}</span></label>`;
        }).join('')}</div>
      </div>
      <div class="chcard-foot"><button class="btn ghost small" id="adToVoices" data-icon="mic">Réglages → Voix</button>
        <button class="btn primary push" id="adCreate" data-icon="globe">Analyser →</button></div>
    </article>`;
  hydrateIcons(stage);
  document.getElementById('adToVoices').onclick = () => goTo(13);
  const syncVersions = () => {
    document.getElementById('adVersionsBox').style.display = stage.querySelectorAll('.ad-target:checked').length > 1 ? '' : 'none';
  };
  stage.querySelectorAll('.ad-target').forEach(x => x.addEventListener('change', syncVersions));
  syncVersions();
  stage.querySelectorAll('input[name="adMode"]').forEach(r => r.onchange = () => {
    document.getElementById('adSrcBox').style.display = r.value === 'script' && r.checked ? 'none' : '';
    syncVersions();
  });
  document.getElementById('adCreate').onclick = async ev => {
    const btn = ev.currentTarget;
    const mode = (stage.querySelector('input[name="adMode"]:checked') || {}).value || 'sources';
    const body = { reference_url: document.getElementById('adRef').value.trim(), mode,
                   versions: document.getElementById('adVersions').checked,
                   source_urls: mode === 'script' ? [] : document.getElementById('adSrc').value.split('\n').map(x => x.trim()).filter(Boolean),
                   channels: [...stage.querySelectorAll('.ad-target:checked')].map(x => x.value) };
    btn.disabled = true;
    try { const p = await api('/api/adaptations', { method:'POST', body: JSON.stringify(body) }); adCurrent = p.project_id; loadAdaptationList(); }
    catch (e){ log(e.message, 'error'); btn.disabled = false; }
  };
}

async function loadAdProject(){
  clearTimeout(adPoll);
  const stage = document.getElementById('adStage');
  const p = await api(`/api/adaptations/${adCurrent}`);
  const changed = !adProject || adProject.project_id !== p.project_id || adProject.status !== p.status || AD_BUSY.includes(p.status);
  const statusMoved = !adProject || adProject.status !== p.status;
  adProject = p;
  if (statusMoved) api('/api/adaptations').then(renderAdChips).catch(() => {});   // keep the project chips' status current
  if (changed){
    const toneSel = p.ton_chaine
      ? `<span class="tiny" title="Réglé pour la chaîne dans Réglages → Voix : même musique et même style à chaque vidéo">Ton : ${esc((p.tons.find(o => o.ton === p.ton_chaine) || {}).label || p.ton_chaine)} (celui de la chaîne)</span>`
      : p.reference && !AD_BUSY.includes(p.status)
      ? `<label class="tiny" title="Le ton règle la musique, la quantité d'effets et les sons (au prochain aperçu)" style="display:flex;gap:6px;align-items:center">Ton
          <select class="f" id="adTone" style="width:auto;padding:4px 8px;font-size:12px">${p.ton ? '' : '<option value="">à deviner</option>'}
          ${(p.tons || []).map(o => `<option value="${o.ton}" ${o.ton === p.ton ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select></label>` : '';
    const head = `<div class="toolbar"><span class="fact">${icon('globe', 14)} ${esc(p.subject || p.reference_url)}</span>${toneSel}<span class="spacer"></span>
      <a class="tiny" href="${esc(p.reference_url)}" target="_blank" rel="noopener">Short modèle ↗</a>
      ${!AD_BUSY.includes(p.status) && p.reference ? '<button class="btn ghost small" id="adNewVersion" data-icon="globe" title="La même vidéo pour une autre chaîne, avec un nouvel angle">Nouvelle version pour une autre chaîne</button>' : ''}
      ${AD_BUSY.includes(p.status) ? '' : '<button class="btn ghost small" id="adDelete" data-icon="trash">Supprimer</button>'}</div>
      <div id="adNewVersionBox"></div>
      ${(p.group_members || []).length > 1 ? `<div class="ad-versions"><span class="tiny">Versions de ce Short :</span>${p.group_members.map(m =>
        `<button class="ad-vtab ${m.project_id === p.project_id ? 'on' : ''}" data-id="${m.project_id}">
          <b>${esc(m.channels.map(ch => (channels.find(c => c.name === ch) || {}).display_name || ch).join(', '))}</b>
          <span>${esc(m.angle || '')}</span><i>${esc(AD_STATUS[m.status] || m.status)}</i></button>`).join('')}</div>` : ''}`;
    stage.innerHTML = adStepsHtml(p.status, p.mode) + head + '<div id="adBody" class="stack"></div>';
    hydrateIcons(stage);
    stage.querySelectorAll('.ad-vtab').forEach(b => b.onclick = () => {
      if (b.dataset.id === p.project_id) return;
      adCurrent = b.dataset.id; adProject = null; loadAdaptationList();
    });
    const toneBox = document.getElementById('adTone');
    if (toneBox) toneBox.onchange = async () => {
      if (!toneBox.value) return;
      try { await api(`/api/adaptations/${p.project_id}/ton`, { method: 'PATCH', body: JSON.stringify({ ton: toneBox.value }) });
            toast('Ton changé : musique, effets et sons suivront au prochain aperçu', 'success'); adProject = null; loadAdProject(); }
      catch (e){ log(e.message, 'error'); }
    };
    const nv = document.getElementById('adNewVersion');
    if (nv) nv.onclick = async () => {
      const box = document.getElementById('adNewVersionBox');
      const taken = new Set(p.group_channels || p.targets.map(t => t.channel));
      const free = [];
      await Promise.all(channels.filter(c => !taken.has(c.name)).map(async c => {
        try { const d = await api(`/api/channels/${c.name}/adaptation`); if (d.settings && d.settings.voice_id) free.push(c); } catch (e){ /* skip */ }
      }));
      box.innerHTML = free.length ? `<div class="ad-row" style="margin:8px 0">Pour quelle chaîne ?
          <select class="f" id="adNvChannel" style="width:auto">${free.map(c => `<option value="${c.name}">${esc(c.display_name)}</option>`).join('')}</select>
          <button class="btn primary small" id="adNvGo">Créer la version (nouvel angle)</button></div>`
        : '<div class="tiny" style="margin:8px 0">Toutes tes chaînes avec une voix ont déjà leur version (Réglages → Voix pour en régler une autre).</div>';
      const go = document.getElementById('adNvGo');
      if (go) go.onclick = async () => {
        go.disabled = true;
        try { const np = await api(`/api/adaptations/${p.project_id}/new-version`, { method:'POST',
                body: JSON.stringify({ channel: document.getElementById('adNvChannel').value }) });
              adCurrent = np.project_id; adProject = null; loadAdaptationList(); }
        catch (e){ log(e.message, 'error'); go.disabled = false; }
      };
    };
    const del = document.getElementById('adDelete');
    if (del) del.onclick = async () => {
      if (!confirm('Supprimer ce projet et ses fichiers de travail ? Les vidéos déjà envoyées à Publication restent.')) return;
      try { await api(`/api/adaptations/${p.project_id}`, { method:'DELETE' }); adCurrent = null; adProject = null; loadAdaptationList(); }
      catch (e){ log(e.message, 'error'); }
    };
    const body = document.getElementById('adBody');
    if (AD_BUSY.includes(p.status)) body.innerHTML = adBusyHtml(p);
    else if (p.status === 'error') renderAdError(body, p);
    else if (p.status === 'sources_search') renderAdSearch(body, p);
    else if (p.status === 'plan_review') renderAdPlan(body, p);
    else if (p.status === 'images_review') renderAdImages(body, p);
    else if (p.status === 'sources_review') renderAdSources(body, p);
    else if (p.status === 'script_review') renderAdScripts(body, p);
    else if (p.status === 'preview_review') renderAdPreviews(body, p);
    else if (p.status === 'done') renderAdDone(body, p);
  }
  if (AD_BUSY.includes(p.status)) adPoll = setTimeout(() => { if (currentSpace === 'adaptation') safeLoad(loadAdProject, 'adStage'); }, 2000);
}

function adBusyHtml(p){
  const pct = Math.round(((p.progress && p.progress.fraction) || 0) * 100);
  return `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${spin('')} ${esc(AD_STATUS[p.status])}</div>
      <div class="meta" style="margin-left:0">${esc((p.progress && p.progress.phase) || 'préparation…')} — tu peux changer d'écran, ça continue.</div></div>
      <span class="pill wait">${pct} %</span></div>
    <div class="chcard-body"><div class="pbar"><div style="width:${pct}%"></div></div></div></article>`;
}

function renderAdError(body, p){
  body.innerHTML = `<div class="errbox">${esc(p.error || 'Erreur')}</div>
    <div class="ad-row"><button class="btn primary small" id="adRetry" data-icon="refresh">Réessayer cette étape</button>
      ${['voicing', 'rendering'].includes(p.failed_step) ? '<button class="btn ghost small" id="adErrBack" data-icon="eye">← Revenir au script</button>' : ''}</div>`;
  hydrateIcons(body);
  const errBack = document.getElementById('adErrBack');
  if (errBack) errBack.onclick = async () => {
    try { await api(`/api/adaptations/${p.project_id}/back-to-script`, { method:'POST' }); adProject = null; loadAdProject(); } catch (e){ log(e.message, 'error'); }
  };
  document.getElementById('adRetry').onclick = async () => {
    try { await api(`/api/adaptations/${p.project_id}/retry`, { method:'POST' }); loadAdProject(); } catch (e){ log(e.message, 'error'); }
  };
}

function renderAdSources(body, p){
  const ref = p.reference || {};
  const usable = p.clips.filter(c => c.usable).length;
  body.innerHTML = `
    <article class="chcard"><div class="chcard-body">
      <div><b>Question du modèle :</b> ${esc(ref.question || '—')}</div>
      ${(p.sources || []).filter(m => m.failed).map(m => `<div class="warnbox">Ignorée : ${esc(m.failed)}</div>`).join('')}
      ${(ref.faits_douteux || []).length ? `<div class="warnbox">À ne pas reprendre tel quel : ${esc(ref.faits_douteux.join(' · '))}</div>` : ''}
      <label class="f" style="margin-top:4px">Crédits affichés en haut de la vidéo et dans la description</label>
      <input class="f" id="adCredits" value="${esc(p.credits || '')}">
    </div></article>
    <article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${p.clips.length} clips trouvés · ${usable} gardés</div>
      <div class="meta" style="margin-left:0">Décoche ceux qui ne doivent pas servir. L'image montre le moment fort, déjà recadrée et nettoyée.</div></div></div>
      <div class="chcard-body"><div class="ad-clips">${p.clips.map(c => `
        <div class="ad-clip ${c.usable ? '' : 'off'}" data-id="${c.id}">
          <div class="ad-play" data-video="${c.thumb_url.replace('/thumb', '/video')}" title="Cliquer pour voir le clip">
            <img src="${c.thumb_url}" loading="lazy" alt=""><span class="ad-play-btn">▶</span></div>
          <div class="meta"><label><input type="checkbox" class="ad-use" ${c.usable ? 'checked' : ''}> <b>${esc(c.id)}</b> · ${(c.end - c.start).toFixed(1)} s</label>
            <span>${esc((c.desc || '').slice(0, 110))}</span>
            ${c.why_not && !c.usable ? `<span style="color:#f5c56d">${esc(c.why_not)}</span>` : ''}
            ${c.low_res ? '<span style="color:#f5c56d">basse résolution</span>' : ''}</div>
        </div>`).join('')}</div></div>
      <div class="chcard-foot"><button class="btn primary push" id="adScripts" data-icon="edit">Écrire les scripts →</button></div>
    </article>
    ${p.suggestions ? `<details class="chcard" style="padding:12px 14px"><summary style="cursor:pointer;font-weight:600">Il manque des images ? Ajouter d'autres sources (vidéos proposées)</summary>
      <div id="adFinder" class="stack" style="margin-top:10px"></div></details>` : ''}`;
  hydrateIcons(body);
  if (p.suggestions) renderAdFinder(document.getElementById('adFinder'), p);
  const patch = b => api(`/api/adaptations/${p.project_id}/sources`, { method:'PATCH', body: JSON.stringify(b) }).catch(e => log(e.message, 'error'));
  document.getElementById('adCredits').onchange = e => patch({ credits: e.target.value });
  adBindPlay(body);
  body.querySelectorAll('.ad-clip:not(.ad-cand)').forEach(card => card.querySelector('.ad-use').onchange = e => {
    card.classList.toggle('off', !e.target.checked);
    patch({ usable: { [card.dataset.id]: e.target.checked } });
  });
  document.getElementById('adScripts').onclick = async () => {
    try { await patch({ credits: document.getElementById('adCredits').value });
          await api(`/api/adaptations/${p.project_id}/scripts`, { method:'POST' }); loadAdProject(); }
    catch (e){ log(e.message, 'error'); }
  };
}

// ---------- "what to download": the scenes to find, the credited accounts, the YouTube candidates ----------

const adPicked = new Set();
const adUnpicked = new Set();                 // what the person unticked: never ticked again automatically
let adPickedFor = null;

function adLoadPicks(pid){                    // your ticks survive a reload (this browser, this project)
  if (adPickedFor === pid) return;
  adPickedFor = pid; adPicked.clear(); adUnpicked.clear();
  try {
    const d = JSON.parse(localStorage.getItem('adPicks:' + pid) || '{}');
    (d.picked || []).forEach(u => adPicked.add(u)); (d.unpicked || []).forEach(u => adUnpicked.add(u));
  } catch (e){ /* private window: ticks just aren't remembered */ }
}

function adSavePicks(){
  if (!adPickedFor) return;
  try { localStorage.setItem('adPicks:' + adPickedFor, JSON.stringify({ picked: [...adPicked], unpicked: [...adUnpicked] })); }
  catch (e){ /* ignore */ }
}

function renderAdSearch(body, p){
  body.innerHTML = `<article class="chcard"><div class="chcard-body">
      <div><b>Ce qu'il faut télécharger</b></div>
      <div class="tiny">Voici ce qu'il faut télécharger pour le refaire. Coche les vidéos qui conviennent (ou colle tes liens en bas), puis lance l'analyse.
        Pas besoin des vidéos exactes : des images équivalentes suffisent, ton script est réécrit.</div>
    </div></article><div id="adFinder" class="stack"></div>`;
  renderAdFinder(document.getElementById('adFinder'), p);
}

function adDuration(s){
  if (!s) return '';
  s = Math.round(s);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function adViews(n){
  if (!n) return '';
  return n >= 1e6 ? (n / 1e6).toFixed(1) + ' M vues' : n >= 1e3 ? Math.round(n / 1e3) + ' k vues' : n + ' vues';
}

const AD_LEVEL = { exacte: ['ok', 'vidéo exacte'], equivalente: ['ok', 'images équivalentes'],
  partielle: ['warn', 'partielle : à regarder'], rien: ['bad', 'rien pour cette scène'] };
const AD_VERDICT = { oui: ['ok', 'vidéo exacte trouvée'], probable: ['ok', 'images équivalentes'],
  partielle: ['warn', 'partielle : à regarder'], non: ['bad', 'rien d\'utile'] };
const AD_RANK = { exacte: 0, equivalente: 1, partielle: 2, rien: 4 };
const AD_ORIGIN = { youtube: 'YouTube', langue: 'langue locale', image: 'par image', compte: 'compte crédité', perso: 'ton lien', action: 'par action', cite: 'cité par un remontage' };

function adVerifOf(sug, url){
  const v = (sug.verifs || {})[url];
  return v && v.par_scene ? v : null;              // an older check judged one scene only: redo it
}

function adVerifHtml(v, scene, long){
  if (v.copie) return `<span class="pill bad">copie du Short modèle</span><span>Un repost du Short que tu adaptes : ne pas l'utiliser (droits d'auteur).</span>`;
  const remix = (v.telechargeable === false ? `<span class="pill bad">bloquée d'ici : impossible à télécharger (pays, vidéo retirée)</span>` : '')
    + (v.film ? `<span class="pill bad">film / série / TV : droits d'auteur, jamais choisi automatiquement</span>` : '')
    + (v.remontage ? `<span class="pill warn" title="Seule son image est prise (ta voix, ton script, ton montage), créditée à l'original quand un filigrane le nomme">remontage d'un autre créateur : pris s'il n'y a pas d'original</span>` : '');
  const per = v.par_scene || {};
  const useful = Object.entries(per).filter(([, e]) => e.niveau !== 'rien').map(([i]) => +i);
  const here = scene >= 0 ? (per[scene] || { niveau: 'rien', moments: [], raison: '' }) : null;
  const [cls, label] = here ? AD_LEVEL[here.niveau] : AD_VERDICT[v.verdict];
  const ms = here ? here.moments : v.moments;
  const others = useful.filter(i => i !== scene).map(i => i + 1);
  const fault = here && here.defauts ? `<span class="pill bad" title="Ce qu'on voit à ce moment : ${esc(here.defauts)}">à l'image : ${esc(here.defauts)}</span>` : '';
  return `${remix}${fault}<span class="pill ${cls}">${esc(label)}</span>
    <span>${esc((here && here.raison) || v.raison)}${(ms || []).length ? ' · à ' + [...new Set(ms.map(m => adDuration(m.debut) || '0:00'))].join(', ') : ''}</span>
    ${others.length ? `<span style="color:var(--ok)">utile ${scene >= 0 ? 'aussi ' : ''}pour ${others.length > 1 ? 'les scènes' : 'la scène'} ${others.join(', ')}</span>` : ''}
    ${long && useful.length ? '<span style="color:var(--ok)">seuls les passages utiles seront téléchargés</span>' : ''}`;
}

function adCandHtml(c, scene, sug, have, pickMode){
  const v = adVerifOf(sug, c.url), err = (sug.verif_errors || {})[c.url];
  const already = have.has(adKey(c.url)), picked = already || adPicked.has(c.url);
  const long = (c.duration || 0) >= 150;
  const tags = (c.origines || []).map(o => o === 'image' && c.hits > 1 ? `par image ×${c.hits}`
    : o === 'langue' && scene >= 0 && ((sug.scenes[scene] || {}).langue || {}).langue ? sug.scenes[scene].langue.langue.toLowerCase()
    : AD_ORIGIN[o] || o);
  const platformName = c.platform && c.platform !== 'YouTube' ? c.platform : '';
  return `<div class="ad-clip ad-cand ${picked ? 'picked' : ''}" data-url="${esc(c.url)}">
    <a href="${esc(adAt(c.url, 0))}" target="_blank" rel="noopener">${c.thumb ? `<img src="${esc(c.thumb)}" loading="lazy" alt="" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('div'), {className: 'ad-noimg', textContent: '${esc(platformName || 'vidéo')}'}))">`
      : `<div class="ad-noimg">${esc(platformName || 'vidéo')}</div>`}</a>
    <div class="meta">${pickMode ? (pickMode.chosen ? `<span class="pill ok">${icon('check', 11)} choisie</span>` : adMomentButtons(v, scene))
      : `<label><input type="checkbox" class="ad-pick" ${picked ? 'checked' : ''} ${already ? 'disabled' : ''}> ${already ? 'déjà ajoutée' : 'prendre'}</label>`}
      <span class="title">${esc(c.title)}</span>
      <span>${esc(platformName ? platformName + (c.channel && c.channel !== platformName ? ' · ' + c.channel : '') : c.channel)}${c.duration ? ' · ' + adDuration(c.duration) : ''}${c.views ? ' · ' + adViews(c.views) : ''}</span>
      ${tags.length ? `<span class="ad-tags">${tags.map(t => `<i>${esc(t)}</i>`).join('')}</span>` : ''}
      ${v ? adVerifHtml(v, scene, long)
        : `${err ? `<span style="color:var(--danger)">${esc(err)}</span>` : ''}
           ${long ? '<span style="color:#f5c56d">vidéo longue : vérifie-la, seuls les passages utiles seront pris</span>' : ''}
           <button class="btn ghost small ad-check" title="L'IA regarde la vidéo et la compare à chaque plan du modèle (15 s sur YouTube, 1 à 2 min ailleurs)">Vérifier avec l'IA</button>`}
    </div></div>`;
}

function adKey(url){                               // the same video, however it is spelled (as finder.same_video)
  const yt = /(?:v=|youtu\.be\/|shorts\/)([\w-]{11})/.exec(url || '');
  if (yt) return 'youtube:' + yt[1];
  return (url || '').trim().toLowerCase().replace(/^https?:\/\/(www\.|m\.)?/, '').split(/[?#]/)[0].replace(/\/+$/, '');
}

function adMomentButtons(v, scene){
  const e = v && (v.par_scene || {})[scene];
  if (!e || e.niveau === 'rien') return '';
  const ms = (e.moments || []).length ? e.moments : [{ debut: 0 }];
  return `<span class="ad-links">${ms.slice(0, 3).map(m => `<button class="chipbtn ad-choose" data-debut="${+m.debut || 0}" data-fin="${m.fin != null ? +m.fin : (+m.debut || 0) + 4}">Choisir · ${adDuration(m.debut) || '0:00'}</button>`).join('')}</span>`;
}

function adSceneCands(sug, si){
  // the scene's own results, plus videos found for another scene that the AI judged useful for this one
  const own = (sug.scenes[si] || {}).candidats || [], seen = new Set(own.map(c => c.url));
  const elsewhere = [...(sug.scenes || []).flatMap(s => s.candidats || []), ...(sug.image_videos || []), ...(sug.perso || []),
                     ...(sug.comptes || []).flatMap(a => a.videos || [])].filter(c => {
    const e = (((sug.verifs || {})[c.url] || {}).par_scene || {})[si];
    if (seen.has(c.url) || !e || !['exacte', 'equivalente', 'partielle'].includes(e.niveau)) return false;
    seen.add(c.url); return true;
  });
  return [...own, ...elsewhere];
}

function adSortCands(cands, scene, sug){
  const rank = c => { const v = adVerifOf(sug, c.url); if (!v) return 3;
    const e = scene >= 0 ? (v.par_scene || {})[scene] : null; return e ? AD_RANK[e.niveau] : (v.verdict === 'non' ? 4 : 1); };
  return [...cands].sort((a, b) => rank(a) - rank(b) || (b.score || 0) - (a.score || 0));
}

const AD_ENGINES = [['Google Lens', 'https://images.google.com/'], ['Yandex', 'https://yandex.com/images/'],
                    ['Bing', 'https://www.bing.com/visualsearch']];

function adFramesHtml(p, frames){
  if (!frames.length) return '';
  return `<div class="ad-frames">${frames.map(f => `<figure><img src="/api/adaptations/${p.project_id}/frames/${esc(f.file)}" alt="" loading="lazy">
      <figcaption><button class="chipbtn ad-copyimg" data-src="/api/adaptations/${p.project_id}/frames/${esc(f.file)}">Copier</button>
        <a class="chipbtn" href="/api/adaptations/${p.project_id}/frames/${esc(f.file)}" download="${esc(f.file)}">Enregistrer</a></figcaption></figure>`).join('')}</div>
    <div class="ad-links"><span class="tiny">Chercher par image :</span>${AD_ENGINES.map(([l, u]) => `<a href="${u}" target="_blank" rel="noopener">${l} ↗</a>`).join('')}
      <span class="tiny">Copier l'image, coller (Ctrl + V) dans le moteur, puis <b>agrandir le cadre à toute l'image</b> (Google zoome tout seul sur un détail).</span></div>`;
}

async function adCopyImage(src){
  const blob = await fetch(src).then(r => r.blob());
  const bmp = await createImageBitmap(blob);
  const canvas = Object.assign(document.createElement('canvas'), { width: bmp.width, height: bmp.height });
  canvas.getContext('2d').drawImage(bmp, 0, 0);
  const png = await new Promise(r => canvas.toBlob(r, 'image/png'));
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
}

function renderAdFinder(box, p){
  const sug = p.suggestions || { comptes: [], scenes: [] };
  adLoadPicks(p.project_id);
  const dead = new Set((p.sources || []).filter(m => m.failed).map(m => m.url));
  const have = new Set((p.source_urls || []).filter(u => !dead.has(u)).map(adKey));
  const pending = new Set(p.pending_excerpts || []);
  const made = new Set((p.clips || []).filter(c => c.extrait).map(c => c.scene));
  (sug.perso || []).forEach(c => {           // your verified links that serve stay ticked, even after a reload
    const v = (sug.verifs || {})[c.url];
    if (v && v.par_scene && v.verdict !== 'non' && !v.copie && v.telechargeable !== false && !adUnpicked.has(c.url) && !have.has(adKey(c.url))) adPicked.add(c.url);
  });
  const links = ls => `<div class="ad-links">${ls.map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} ↗</a>`).join('')}</div>`;
  const chips = qs => qs.map(q => `<span class="chipbtn" title="Copier" data-copy="${esc(q)}">${esc(q)}</span>`).join('');
  const im = sug.images || { frames: [] };
  const framesOf = si => (im.frames || []).filter(f => f.scene === si);
  const loose = (im.frames || []).filter(f => f.scene === null || f.scene === undefined);
  const verified = Object.values(sug.verifs || {}).filter(v => v.par_scene);
  const imageState = !im.frames || !im.frames.length
    ? `Pas d'image du Short${im.error ? ' : ' + esc(im.error) : ''}.`
    : `${im.frames.length} images ${im.source === 'short' ? 'prises dans le Short, une par plan' : 'publiques de YouTube (le Short n\'a pas pu être téléchargé)'}.
       ${im.search_error ? `<span style="color:#f5c56d">Recherche automatique impossible : ${esc(im.search_error)} — utilise les boutons ci-dessous.</span>`
         : 'Cherchées automatiquement sur Yandex.'}`;
  box.innerHTML = `
    <article class="chcard"><div class="chcard-body">
      <div class="tiny">${icon('image', 12)} ${imageState}
        ${verified.length ? `${icon('sparkle', 12)} ${verified.length} vidéo(s) déjà vérifiée(s) par l'IA, les meilleures en premier.` : ''}
        Pour aller plus loin à la main : l'extension <a href="https://www.invid-project.eu/tools-and-services/invid-verification-plugin/" target="_blank" rel="noopener">InVID-WeVerify ↗</a>
        découpe une vidéo en images et lance toutes les recherches par image.</div>
    </div></article>
    ${sug.comptes.length ? `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${icon('link', 14)} Comptes crédités dans le modèle</div>
        <div class="meta" style="margin-left:0">Souvent l'auteur des vidéos d'origine : ouvre son profil et copie le lien de la bonne vidéo en bas.</div></div></div>
      <div class="chcard-body">${sug.comptes.map(c => `<div class="ad-row"><b>${esc(c.name)}</b>${links(c.links)}</div>
        ${(c.videos || []).length ? `<div class="tiny">Ses vidéos YouTube sur le sujet :</div>
          <div class="ad-clips">${adSortCands(c.videos, -1, sug).map(v => adCandHtml(v, -1, sug, have)).join('')}</div>` : ''}`).join('')}</div></article>` : ''}
    ${adOriginalsHtml(sug, c => adCandHtml(c, -1, sug, have))}
    <article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${icon('eye', 14)} Vidéos à chercher · ${sug.scenes.length}</div>
        <div class="meta" style="margin-left:0">Pour chaque scène : les images du Short, quoi chercher, et les vidéos trouvées (YouTube, langue locale, par image), les vérifiées en premier.</div></div></div>
      <div class="chcard-body">${sug.scenes.map((sc, si) => `
        <div class="ad-scene" data-scene="${si}">
          <div class="what">${si + 1}. Cherche : ${esc(sc.scene)}</div>
          ${sc.pub ? `<div class="warnbox">Publicité dans le modèle : pas besoin de la chercher, ton script ne reprendra pas la marque.</div>` : ''}
          ${sc.indices ? `<div class="tiny">Indices : ${esc(sc.indices)}</div>` : ''}
          ${adFramesHtml(p, framesOf(si))}
          <div class="ad-links"><span class="tiny">Recherches :</span>${chips(sc.recherches)}</div>
          ${links(sc.liens || [])}
          ${sc.langue ? `<div class="ad-links"><span class="tiny">En ${esc(sc.langue.langue.toLowerCase())} (filmé ${esc(sc.langue.pays ? 'en/au ' + sc.langue.pays : 'ailleurs')}) :</span>${chips(sc.langue.recherches)}</div>
            ${links(sc.liens_langue || [])}` : ''}
          ${(() => { const list = adSceneCands(sug, si); return list.length
              ? `<div class="ad-clips">${adSortCands(list, si, sug).map(c => adCandHtml(c, si, sug, have)).join('')}</div>`
              : sc.pub ? '' : '<div class="tiny">Aucune vidéo trouvée automatiquement : utilise les images et les liens de recherche ci-dessus.</div>'; })()}
          ${!sc.pub && si > 0 && (sc.plans || []).length
            ? (made.has(si) ? `<div class="ad-row"><span class="pill warn">${icon('check', 11)} extrait du Short modèle ajouté à tes clips</span></div>`
              : `<div class="ad-row"><label class="switch" style="color:var(--text)"><input type="checkbox" class="ad-scene-excerpt" data-scene="${si}" ${pending.has(si) ? 'checked' : ''}>
                 Extrait du Short modèle (dernier recours)</label>
               <span class="tiny">3 s de cette scène prises dans le modèle, nettoyées et créditées${p.status === 'sources_search' ? ', ajoutées avec tes vidéos au téléchargement' : ''}</span></div>`) : ''}
        </div>`).join('') || '<div class="tiny">Le modèle n\'a pas pu être découpé en scènes.</div>'}</div></article>
    ${loose.length || (sug.image_videos || []).length ? `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${icon('image', 14)} Trouvées par image (toutes scènes)</div></div></div>
      <div class="chcard-body">${adFramesHtml(p, loose)}
        ${(sug.image_videos || []).length ? `<div class="ad-clips">${adSortCands(sug.image_videos, -1, sug).map(c => adCandHtml(c, -1, sug, have)).join('')}</div>` : ''}</div></article>` : ''}
    ${(sug.perso || []).length ? `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${icon('link', 14)} Tes liens vérifiés</div>
        <div class="meta" style="margin-left:0">Jugés comme les vidéos proposées. Ceux qui servent sont cochés ; seuls leurs passages utiles seront téléchargés.</div></div></div>
      <div class="chcard-body"><div class="ad-clips">${adSortCands(sug.perso, -1, sug).map(c => adCandHtml(c, -1, sug, have)).join('')}</div></div></article>` : ''}
    <article class="chcard"><div class="chcard-body">
      <label class="f">Tes propres liens (TikTok, YouTube, Instagram, VK…), un par ligne</label>
      <textarea class="f ad-own" rows="3" placeholder="https://www.tiktok.com/@…/video/…"></textarea>
      <div class="ad-row" style="margin-top:8px"><input class="f ad-file-credit" placeholder="Crédit de ta vidéo, ex. 微蓝 (Douyin 69627156)" style="flex:1;min-width:220px">
        <input type="file" class="ad-file-input" accept=".mp4,.mov,.m4v,.webm,.mkv,video/*" hidden>
        <button class="btn secondary small ad-file" title="Une vidéo enregistrée à la main (appli Douyin, Xiaohongshu, Instagram…) : ajoutée aux sources, analysée avec les autres">📁 Déposer un fichier comme source</button></div></div>
      <div class="chcard-foot"><span class="tiny ad-count"></span>
        <button class="btn secondary ad-own-check" data-icon="sparkle" title="L'IA regarde chaque lien et le compare aux plans du modèle (1 à 2 min)">Vérifier mes liens avec l'IA</button>
        ${p.status === 'sources_search' && (p.wanting || []).length ? `<button class="btn secondary ad-more" title="Cherche l'ACTION des scènes sans bonne vidéo dans des compilations, vidéos GoPro, vlogs… même si la vidéo parle d'autre chose ; l'IA regarde les nouvelles vidéos (2 à 5 min)">🔎 Chercher plus pour ${p.wanting.length} scène(s)</button>` : ''}
        <button class="btn primary push ad-add" data-icon="download">Télécharger et analyser →</button></div></article>`;
  if (p.fetch_note) box.insertAdjacentHTML('afterbegin', `<div class="warnbox">${esc(p.fetch_note)}</div>`);
  hydrateIcons(box);
  const more = box.querySelector('.ad-more');
  if (more) more.onclick = async () => {
    more.disabled = true;
    try { await api(`/api/adaptations/${p.project_id}/images/more`, { method:'POST' }); adProject = null; loadAdProject(); }
    catch (e){ log(e.message, 'error'); more.disabled = false; }
  };
  const own = box.querySelector('.ad-own'), count = box.querySelector('.ad-count');
  const urls = () => [...adPicked, ...own.value.split('\n').map(x => x.trim()).filter(Boolean)].filter(u => !have.has(adKey(u)));
  const recount = () => {
    adSavePicks();
    const n = urls().length, x = pending.size;
    count.textContent = n || x ? [n ? `${n} vidéo(s) à télécharger` : '', x ? `${x} extrait(s) du Short` : ''].filter(Boolean).join(' + ')
      : 'Coche au moins une vidéo ou colle un lien.';
  };
  recount();
  own.oninput = recount;
  box.querySelectorAll('[data-copy]').forEach(b => b.onclick = () => {
    navigator.clipboard.writeText(b.dataset.copy).then(() => toast('Recherche copiée', 'success')).catch(() => {});
  });
  box.querySelectorAll('.ad-copyimg').forEach(b => b.onclick = () =>
    adCopyImage(b.dataset.src).then(() => toast('Image copiée : colle-la (Ctrl + V) dans le moteur', 'success'))
      .catch(() => toast('Copie impossible ici : utilise « Enregistrer » puis glisse le fichier', 'error')));
  box.querySelectorAll('.ad-cand').forEach(card => {
    const url = card.dataset.url;
    const cb = card.querySelector('.ad-pick');
    cb.onchange = () => {
      box.querySelectorAll(`.ad-cand[data-url="${CSS.escape(url)}"] .ad-pick`).forEach(x => { x.checked = cb.checked; x.closest('.ad-cand').classList.toggle('picked', cb.checked); });
      if (cb.checked){ adPicked.add(url); adUnpicked.delete(url); } else { adPicked.delete(url); adUnpicked.add(url); }
      recount();
    };
    const chk = card.querySelector('.ad-check');
    if (chk) chk.onclick = async () => {
      chk.disabled = true; chk.innerHTML = spin('l\'IA regarde…');
      try {
        const np = await api(`/api/adaptations/${p.project_id}/suggestions/check`, { method:'POST',
          body: JSON.stringify({ url }) });
        adProject = np; renderAdFinder(box, np);
      } catch (e){ log(e.message, 'error'); chk.disabled = false; chk.textContent = 'Vérifier avec l\'IA'; }
    };
  });
  box.querySelectorAll('.ad-scene-excerpt').forEach(b => b.onchange = async () => {
    b.disabled = true;
    if (p.status === 'sources_review') b.parentElement.insertAdjacentHTML('beforeend', ' ' + spin('repérage dans le Short…'));
    try {
      const np = await api(`/api/adaptations/${p.project_id}/scenes/${b.dataset.scene}/excerpt`, { method:'POST' });
      if (np.status === 'sources_review' && p.status === 'sources_review'){ toast('Extrait ajouté à tes clips', 'success'); adProject = null; loadAdProject(); return; }
      adProject = np; renderAdFinder(box, np);
    } catch (e){ log(e.message, 'error'); b.checked = !b.checked; b.disabled = false; }
  });
  const fileBtn = box.querySelector('.ad-file'), fileIn = box.querySelector('.ad-file-input');
  fileBtn.dataset.label = fileBtn.textContent.trim();
  fileBtn.onclick = () => fileIn.click();
  fileIn.onchange = () => adDropFile(fileIn, fileBtn, 'sources/file', box.querySelector('.ad-file-credit').value,
                                     () => { adProject = null; loadAdProject(); });
  box.querySelector('.ad-own-check').onclick = async ev => {
    const list = own.value.split('\n').map(x => x.trim()).filter(Boolean);
    if (!list.length){ toast('Colle d\'abord un ou plusieurs liens', 'error'); return; }
    const btn = ev.currentTarget; btn.disabled = true; btn.innerHTML = spin('l\'IA regarde tes liens…');
    try {
      const np = await api(`/api/adaptations/${p.project_id}/suggestions/own`, { method:'POST', body: JSON.stringify({ urls: list }) });
      const vs = (np.suggestions || {}).verifs || {};
      list.forEach(u => { const v = vs[u]; if (v && v.par_scene && v.verdict !== 'non' && v.telechargeable !== false) adPicked.add(u); });   // the useful ones, ticked
      adProject = np; renderAdFinder(box, np);
      const kept = list.filter(u => adPicked.has(u)).length;
      toast(`${list.length} lien(s) vérifié(s), ${kept} utile(s) coché(s)`, 'success');
    } catch (e){ log(e.message, 'error'); btn.disabled = false; btn.textContent = 'Vérifier mes liens avec l\'IA'; }
  };
  box.querySelector('.ad-add').onclick = async ev => {
    const list = urls();
    if (!list.length && !pending.size){ recount(); return; }
    const btn = ev.currentTarget; btn.disabled = true;
    try { await api(`/api/adaptations/${p.project_id}/sources/add`, { method:'POST', body: JSON.stringify({ urls: list }) });
          list.forEach(u => adPicked.delete(u)); adSavePicks(); loadAdProject(); }
    catch (e){ log(e.message, 'error'); btn.disabled = false; }
  };
}

function adBindPlay(root){
  // a thumbnail with ▶: click to watch the clip, cleaned like the render
  root.querySelectorAll('.ad-play').forEach(box => box.onclick = () => {
    if (box.querySelector('video')) return;
    if (box.clientWidth < 150){         // a small thumbnail (script screen): watch it large, over the page
      const over = Object.assign(document.createElement('div'), { className: 'ad-lightbox' });
      over.innerHTML = `<div class="ad-lightbox-in"><video src="${box.dataset.video}" controls autoplay playsinline></video>
        <button class="btn secondary small">Fermer</button></div>`;
      const close = () => over.remove();
      over.onclick = e => { if (e.target === over) close(); };
      over.querySelector('button').onclick = close;
      document.addEventListener('keydown', function esc(e){ if (e.key === 'Escape'){ close(); document.removeEventListener('keydown', esc); } });
      document.body.appendChild(over);
      return;
    }
    const img = box.querySelector('img'), w = img.clientWidth, h = img.clientHeight || 120;
    box.dataset.thumb = img.src;
    box.innerHTML = `<div class="ad-play-wait" style="height:${h}px;width:${w || ''}px">${spin('…')}</div>`;
    const v = Object.assign(document.createElement('video'), { src: box.dataset.video, controls: true, autoplay: true, playsInline: true });
    v.style.cssText = `width:${w ? w + 'px' : '100%'};height:${h}px;background:#000;display:block;object-fit:contain;border-radius:6px`;
    v.onloadeddata = () => { box.innerHTML = ''; box.appendChild(v); };
    v.onerror = () => { box.innerHTML = '<div class="ad-play-wait">aperçu indisponible</div>'; };
    v.load();
  });
}

function adPlayHtml(pid, cid){
  return `<div class="ad-play" data-video="/api/adaptations/${pid}/clips/${cid}/video" title="Cliquer pour voir le clip">
    <img src="/api/adaptations/${pid}/clips/${cid}/thumb" alt=""><span class="ad-play-btn">▶</span></div>`;
}

function adClipOptions(p, current){
  return p.clips.filter(c => c.usable || c.id === current).map(c =>
    `<option value="${c.id}" ${c.id === current ? 'selected' : ''}>${esc(c.id)} — ${esc((c.desc || '').slice(0, 50))}</option>`).join('');
}

const AD_ROLE = { accroche: 'Accroche', promesse: 'Promesse', montee: 'Montée', reponse: 'Réponse' };

function adAnnHtml(a){
  const t = (a && a.type) || '';
  return `<div class="ad-row ad-ann"><select class="f sc-ann-type" style="width:auto" title="Une flèche pour anticiper un mouvement, un cercle pour un détail">
      <option value="" ${t ? '' : 'selected'}>Pas de flèche</option><option value="fleche" ${t === 'fleche' ? 'selected' : ''}>➜ Flèche</option>
      <option value="cercle" ${t === 'cercle' ? 'selected' : ''}>◯ Cercle</option></select>
    <input class="f sc-ann-cible" value="${esc((a && a.cible) || '')}" placeholder="Quoi pointer (ex. la voiture noire à droite)" style="flex:1;min-width:180px;font-size:12px"></div>`;
}

function adAnnMissing(card){
  // an arrow or circle chosen without saying what to point at: never dropped silently
  const rows = [...card.querySelectorAll('.ad-ann')];
  const k = rows.findIndex(r => r.querySelector('.sc-ann-type').value && !r.querySelector('.sc-ann-cible').value.trim());
  if (k < 0) return false;
  const input = rows[k].querySelector('.sc-ann-cible');
  input.style.borderColor = 'var(--danger)'; input.focus();
  toast(`Plan ${k + 1} : écris quoi pointer (ex. la semelle collée au sol), ou choisis « Pas de flèche »`, 'error');
  return true;
}

// Montage effects of a passage (chosen by the AI after the download, changeable here)
function adFxHtml(e){
  e = e || {};
  const box = (cls, on, label, tip) => `<label class="tiny" title="${tip}" style="display:inline-flex;gap:4px;align-items:center;cursor:pointer">
      <input type="checkbox" class="${cls}" ${on ? 'checked' : ''}>${label}</label>`;
  return `<div class="ad-row ad-fx" style="gap:12px;align-items:center">
      <span class="tiny" style="opacity:.7">Effets :</span>
      ${box('sc-fx-slow', e.ralenti, '🐢 Ralenti', 'Le moment fort passe au ralenti (2× plus lent, images recalculées)')}
      ${box('sc-fx-freeze', e.arret, '⏸ Arrêt sur image', 'L’image se fige un instant sur le moment fort (avec la flèche ou le cercle s’il y en a)')}
      ${box('sc-fx-trans', e.transition, '💨 Transition', 'Coup de zoom et « whoosh » : une nouvelle partie de l’histoire commence')}
      <input class="f sc-fx-zoom" value="${esc(e.zoom || '')}" placeholder="🔍 Zoom sur… (ex. les pieds de la femme)" style="flex:1;min-width:160px;font-size:12px">
      <input class="f sc-fx-num" value="${esc(e.chiffre || '')}" maxlength="16" placeholder="🔢 Chiffre (ex. 2 m)" title="Un chiffre fort qui apparaît en grand au moment fort du plan" style="width:150px;font-size:12px"></div>`;
}

function adFxOf(row){
  const q = c => row.querySelector(c);
  if (!q('.sc-fx-slow')) return null;
  const e = { ralenti: q('.sc-fx-slow').checked, arret: q('.sc-fx-freeze').checked,
              transition: q('.sc-fx-trans').checked, zoom: q('.sc-fx-zoom').value.trim() || null,
              chiffre: (q('.sc-fx-num') ? q('.sc-fx-num').value.trim() : '') || null };
  return (e.ralenti || e.arret || e.transition || e.zoom || e.chiffre) ? e : null;
}

function adAnnOf(row){
  const type = row.querySelector('.sc-ann-type').value, cible = row.querySelector('.sc-ann-cible').value.trim();
  return type && cible ? { type, cible } : null;
}

function renderAdPlan(body, p){
  const sb = p.storyboard || { plans: [] };
  const allApproved = p.targets.every(t => t.approved);
  const angles = p.angles || [], cur = p.angle || {};
  body.innerHTML = (cur.titre ? `<article class="chcard"><div class="chcard-body">
      <div><b>Angle de cette version : « ${esc(cur.titre)} »</b> <span class="tiny">${esc(cur.idee || '')}</span></div>
      <div class="ad-row"><select class="f" id="adAngle" style="width:auto;max-width:100%">
          ${angles.map((a, i) => `<option value="${i}" ${a.titre === cur.titre ? 'selected' : ''}>${esc(a.titre)} — ${esc(a.idee.slice(0, 70))}</option>`).join('')}
          <option value="custom">Mon propre angle…</option></select>
        <input class="f" id="adAngleCustom" placeholder="Décris ton angle (ex. le test honnête, ça vaut le coup ?)" style="display:none;flex:1;min-width:220px">
        <button class="btn secondary small" id="adAngleGo" data-icon="refresh" title="Le storyboard est réécrit avec cet angle (environ 1 minute)">Réécrire avec cet angle</button></div>
    </div></article>` : '') + `<article class="chcard"><div class="chcard-body"><div class="tiny">
      ${icon('sparkle', 12)} Le script est écrit <b>avant</b> les images, pour garder les gens jusqu'à la fin :
      <b>accroche</b> (2-3 s) → <b>promesse</b> → <b>montée</b> → <b>réponse</b>. Pour chaque phrase, <b>🎬 l'image voulue</b> sera cherchée ensuite :
      elle est <b>commune à toutes les langues</b>, la modifier demande de revalider chaque langue.
      ${(sb.corrections || []).length ? `<details style="margin-top:6px"><summary style="cursor:pointer">Relecture automatique : ${sb.corrections.length} correction(s)</summary>
        <ul>${sb.corrections.map(c => `<li>${esc(c)}</li>`).join('')}</ul></details>` : ''}</div></div></article>` +
  p.targets.map(t => {
    const sc = t.script || { passages: [] };
    const dir = t.rtl ? 'dir="rtl"' : '';
    return `
    <article class="chcard ad-target-card" data-channel="${t.channel}">
      <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(t.channel)}"></span>
        ${esc((channels.find(c => c.name === t.channel) || {}).display_name || t.channel)} · ${esc(t.language_label)}</div></div>
        ${t.approved ? `<span class="pill ok">${icon('check', 11)} validé</span>` : '<span class="pill warn">à relire</span>'}</div>
      <div class="chcard-body">
        ${t.problems.length ? `<div class="errbox">${t.problems.map(esc).join('<br>')}</div>` : ''}
        <label class="f">Titre</label><input class="f sc-title" ${dir} value="${esc(sc.titre || '')}">
        <div>${sc.passages.map((ps, i) => { const pl = sb.plans[i] || {}; return `
          <div class="ad-passage ad-plan" data-i="${i}">
            <div class="ad-plan-side"><b>${i + 1}</b><span class="pill ${pl.role === 'accroche' || pl.role === 'reponse' ? 'ok' : 'wait'}">${esc(AD_ROLE[pl.role] || pl.role || '')}</span>
              <span class="tiny">≥ ${pl.duree || '?'} s</span>
              ${(pl.plans_modele || []).length ? `<span class="tiny">plan${pl.plans_modele.length > 1 ? 's' : ''} ${pl.plans_modele.join(', ')} du modèle</span>` : '<span class="tiny">image nouvelle</span>'}</div>
            <div class="fields">
              <label class="tiny">🎬 Image voulue (commune à toutes les langues)</label>
              <textarea class="f sc-image" rows="2" style="min-height:40px;font-size:12.5px">${esc(pl.image || '')}</textarea>
              <input class="f sc-banner" ${dir} value="${esc(ps.bandeau)}" placeholder="Bandeau">
              <textarea class="f sc-text" ${dir}>${esc(ps.texte)}</textarea>
              <input class="f sc-keys" ${dir} value="${esc((ps.mots_cles || []).join(', '))}" placeholder="Mots en couleur, séparés par des virgules" style="font-size:12px">
              ${adAnnHtml(pl.annotation)}
            </div>
          </div>`; }).join('')}</div>
        <label class="f">Description</label><textarea class="f sc-desc" ${dir}>${esc(sc.description || '')}</textarea>
        <label class="f">Tags</label><input class="f sc-tags" ${dir} value="${esc((sc.tags || []).join(', '))}">
      </div>
      <div class="chcard-foot">
        <div class="askrow" style="flex:1;min-width:240px">${icon('sparkle', 16)}<input class="sc-ask" placeholder="Demande à l'IA, ex : rends l'accroche plus intrigante…">
          <button class="btn secondary small sc-revise">Envoyer</button></div>
        <button class="btn secondary small sc-save">Enregistrer</button>
        <button class="btn primary small sc-approve" data-icon="check">Valider ce script</button>
      </div>
    </article>`;
  }).join('') + `<div class="navbar"><span class="progress-text">${p.targets.filter(t => t.approved).length}/${p.targets.length} script(s) validé(s)</span><span></span>
      <button class="btn primary" id="adImages" ${allApproved ? '' : 'disabled'} title="L'app cherche une vidéo pour chaque plan (3 à 6 min)" data-icon="eye">Chercher les images →</button></div>`;
  hydrateIcons(body);
  body.querySelectorAll('.ad-target-card').forEach(card => {
    const ch = card.dataset.channel;
    const collect = () => ({
      titre: card.querySelector('.sc-title').value, description: card.querySelector('.sc-desc').value,
      tags: card.querySelector('.sc-tags').value.split(',').map(x => x.trim()).filter(Boolean),
      passages: [...card.querySelectorAll('.ad-plan')].map(row => ({
        image: row.querySelector('.sc-image').value, bandeau: row.querySelector('.sc-banner').value,
        texte: row.querySelector('.sc-text').value, annotation: adAnnOf(row),
        mots_cles: row.querySelector('.sc-keys').value.split(',').map(x => x.trim()).filter(Boolean) })) });
    const refresh = np => { adProject = np; renderAdPlan(body, np); };
    const save = () => adAnnMissing(card) ? Promise.reject(new Error('Flèche ou cercle sans cible'))
      : api(`/api/adaptations/${p.project_id}/targets/${ch}/plan`, { method:'PUT', body: JSON.stringify({ plan: collect() }) });
    card.querySelector('.sc-save').onclick = async () => {
      try { refresh(await save()); toast('Script enregistré', 'success'); } catch (e){ log(e.message, 'error'); }
    };
    card.querySelector('.sc-revise').onclick = async ev => {
      const req = card.querySelector('.sc-ask').value.trim();
      if (!req) return;
      const btn = ev.currentTarget; btn.disabled = true; btn.innerHTML = spin('…');
      try { await save(); refresh(await api(`/api/adaptations/${p.project_id}/targets/${ch}/plan/revise`, { method:'POST', body: JSON.stringify({ request: req }) })); }
      catch (e){ log(e.message, 'error'); btn.disabled = false; btn.textContent = 'Envoyer'; }
    };
    card.querySelector('.sc-approve').onclick = async () => {
      try { await save(); refresh(await api(`/api/adaptations/${p.project_id}/targets/${ch}/plan/approve`, { method:'POST' })); toast('Script validé', 'success'); }
      catch (e){ log(e.message, 'error'); }
    };
  });
  const angleSel = document.getElementById('adAngle');
  if (angleSel){
    angleSel.onchange = () => document.getElementById('adAngleCustom').style.display = angleSel.value === 'custom' ? '' : 'none';
    document.getElementById('adAngleGo').onclick = async ev => {
      const custom = angleSel.value === 'custom' ? document.getElementById('adAngleCustom').value.trim() : null;
      if (angleSel.value === 'custom' && !custom){ toast('Décris ton angle', 'error'); return; }
      ev.currentTarget.disabled = true;
      try { await api(`/api/adaptations/${p.project_id}/angle`, { method:'POST',
              body: JSON.stringify(custom ? { custom } : { index: +angleSel.value }) }); adProject = null; loadAdProject(); }
      catch (e){ log(e.message, 'error'); ev.currentTarget.disabled = false; }
    };
  }
  const go = document.getElementById('adImages');
  if (go) go.onclick = async () => {
    go.disabled = true;
    try { await api(`/api/adaptations/${p.project_id}/images`, { method:'POST' }); adProject = null; loadAdProject(); }
    catch (e){ log(e.message, 'error'); go.disabled = false; }
  };
}

const AD_PICK = { exacte: ['ok', 'vidéo exacte'], equivalente: ['ok', 'images équivalentes'], partielle: ['warn', 'partielle'],
  choisie: ['wait', 'choisie à la main'], 'adaptée': ['ok', 'phrase adaptée à l\'image'], extrait: ['warn', 'extrait du Short modèle'] };

function adAt(url, sec){
  const t = Math.max(0, Math.floor(sec || 0));
  if ((url || '').startsWith('fichier:'))         // a file dropped by hand: played by the app, at that second
    return `/api/adaptations/${adCurrent}/fichiers/${encodeURIComponent(url.split('/').pop())}#t=${t}`;
  return /youtube\.com|youtu\.be/.test(url) ? `${url}${url.includes('?') ? '&' : '?'}t=${t}s` : url;
}

function renderAdImages(body, p){
  const sug = p.suggestions || { scenes: [] }, sb = p.storyboard || { plans: [] }, picks = p.picks || [];
  const t0 = p.targets[0] || {}, texts = ((t0.script || {}).passages || []);
  const active = sb.plans.map((pl, k) => k).filter(k => !sb.plans[k].retire);
  const n = active.length, got = active.map(k => picks[k]).filter(Boolean);
  const green = got.filter(x => ['exacte', 'equivalente', 'adaptée'].includes(x.niveau)).length;
  const links = ls => `<div class="ad-links">${ls.map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} ↗</a>`).join('')}</div>`;
  const chips = qs => qs.map(q => `<span class="chipbtn" title="Copier" data-copy="${esc(q)}">${esc(q)}</span>`).join('');
  const im = sug.images || { frames: [] };
  body.innerHTML = (p.fetch_note ? `<div class="warnbox">${esc(p.fetch_note)}</div>` : '') + `<article class="chcard"><div class="chcard-body">
      <div><b>${got.length}/${n} plans ont une vidéo choisie</b> : ${green} verte(s), ${got.length - green} à regarder, ${n - got.length} sans vidéo.</div>
      <div class="tiny">Pour chaque plan, l'app a cherché l'image voulue (YouTube, langue du pays, recherche par image, compte crédité), fait vérifier les meilleures vidéos par l'IA
        et choisi <b>le meilleur moment</b>. Tu peux en choisir un autre avec <b>« Choisir »</b>, donner <b>ton lien</b> pour un plan,
        <b>adapter la phrase</b> d'un plan sans vidéo à une image trouvée, ou <b>retirer</b> un plan. Quand chaque plan a sa vidéo : <b>Télécharger les images choisies</b>.</div>
    </div></article>` + adOriginalsHtml(sug, c => {
      const v = (sug.verifs || {})[c.url];
      const useful = v && ['oui', 'probable', 'partielle'].includes(v.verdict);
      return `<div class="ad-row"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc((c.title || c.url).slice(0, 70))} ↗</a>
        <span class="tiny">${!v ? 'pas encore vérifiée' : useful ? `${v.verdict === 'oui' ? '✅ exacte' : v.verdict === 'probable' ? '🟢 équivalente' : '🟡 partielle'}${v.remontage ? ' (encore un remontage)' : ''} — proposée dans « Autres vidéos » des plans concernés` : "❌ rien d'utile pour ces plans"}</span></div>`;
    }, 'stack') +
  sb.plans.map((pl, k) => {
    const sc = (sug.scenes || [])[k] || { candidats: [], recherches: [] };
    const pick = picks[k];
    const frames = (im.frames || []).filter(f => f.scene === k);
    const [cls, label] = pl.retire ? ['wait', 'plan retiré'] : pick ? (AD_PICK[pick.niveau] || ['wait', pick.niveau]) : ['bad', 'aucune vidéo'];
    if (pl.retire) return `<article class="chcard ad-imgplan" data-plan="${k}" style="opacity:.6"><div class="chcard-head"><div class="who">
        <div class="name">${k + 1} · ${esc(AD_ROLE[pl.role] || pl.role)} · retiré</div>
        <div class="meta" style="margin-left:0">« ${esc((texts[k] || {}).texte || '')} »</div></div>
        <button class="btn ghost small ad-unskip">Remettre ce plan</button></div></article>`;
    return `<article class="chcard ad-imgplan" data-plan="${k}"><div class="chcard-head"><div class="who">
        <div class="name">${k + 1} · ${esc(AD_ROLE[pl.role] || pl.role)} · ≥ ${pl.duree} s</div>
        <div class="meta" style="margin-left:0">« ${esc((texts[k] || {}).texte || '')} »</div></div>
        <span class="pill ${cls}">${esc(label)}</span></div>
      <div class="chcard-body">
        <div class="tiny">🎬 ${esc(pl.image)}</div>
        ${pick ? `<div class="ad-chosen">${icon('check', 13)} <b>${esc(pick.titre)}</b> — de ${adDuration(pick.moment.debut) || '0:00'} à ${adDuration(pick.moment.fin) || '0:00'}
            <a href="${esc(adAt(pick.url, pick.moment.debut))}" target="_blank" rel="noopener">voir ce moment ↗</a>
            ${pick.film ? `<span class="pill bad">film / série / TV : droits d'auteur, à remplacer</span>` : ''}
            ${pick.remontage ? `<span class="pill warn" title="Seule son image est prise : ta voix, ton script, ton montage">image d'un remontage · crédit : ${esc(pick.credit || 'le compte du remontage')}</span>` : ''}
            ${pick.defauts ? `<span class="pill bad">à l'image : ${esc(pick.defauts)} — choisis un autre moment</span>` : ''}
            ${pick.raison ? `<span class="tiny">${esc(pick.raison)}</span>` : ''}
            ${pick.credit && !pick.remontage ? `<span class="tiny">· crédit : ${esc(pick.credit)}</span>` : ''}
            <button class="btn ghost small ad-unpick" title="Ce plan n'aura plus de vidéo choisie : tu pourras en prendre une autre">Enlever ce choix</button></div>`
          : `<div class="warnbox">Aucune vidéo vérifiée ne montre ce plan. Choisis-en une ci-dessous, donne ton lien, ou :</div>
             <div class="ad-row"><button class="btn secondary small ad-adapt" data-icon="sparkle" title="L'IA réécrit la phrase (toutes les langues) autour d'une image déjà trouvée">Adapter la phrase à une image trouvée</button>
               <button class="btn ghost small ad-skip">Retirer ce plan</button></div>`}
        <div class="ad-row"><input class="f ad-plan-link" placeholder="Ton lien pour ce plan (TikTok, YouTube, VK…)" style="flex:1;min-width:220px">
          <button class="btn secondary small ad-plan-check" title="L'IA vérifie ce lien pour ce plan (15 s à 2 min)">Vérifier pour ce plan</button>
          ${pick ? '<button class="btn ghost small ad-skip">Retirer ce plan</button>' : ''}
          ${k > 0 && pl.role !== 'accroche' && ((p.reference || {}).plans || []).length && !(pick && pick.extrait)
            ? `<select class="f ad-excerpt-ref" style="width:auto;max-width:260px;font-size:12px" title="Le moment du Short modèle à prendre">
                ${p.reference.plans.map((r, i) => `<option value="${i + 1}" ${(pl.plans_modele || [])[0] === i + 1 ? 'selected' : ''}>Modèle ${i + 1} (${adDuration(r.debut) || '0:00'}–${adDuration(r.fin) || '0:00'}) — ${esc((r.visuel || '').slice(0, 50))}</option>`).join('')}</select>
              <button class="btn ghost small ad-excerpt" title="3 secondes maximum du moment choisi, nettoyées, créditées ; 2 par vidéo au plus, jamais l'accroche">Extrait du Short modèle (dernier recours)</button>` : ''}</div>
        <div class="ad-row"><input class="f ad-file-credit" placeholder="Crédit de ta vidéo, ex. 微蓝 (Douyin 69627156)" style="flex:1;min-width:220px">
          <input type="file" class="ad-file-input" accept=".mp4,.mov,.m4v,.webm,.mkv,video/*" hidden>
          <button class="btn secondary small ad-file" title="Une vidéo enregistrée à la main (appli Douyin, Xiaohongshu, Instagram…) : l'IA la vérifie pour ce plan (15 s à 2 min)">📁 Déposer un fichier pour ce plan</button></div>
        ${frames.length ? adFramesHtml(p, frames) : ''}
        <div class="ad-links"><span class="tiny">Recherches :</span>${chips(sc.recherches || [])}</div>
        ${links(sc.liens || [])}
        ${sc.langue ? `<div class="ad-links"><span class="tiny">En ${esc((sc.langue.langue || '').toLowerCase())} :</span>${chips(sc.langue.recherches || [])}</div>${links(sc.liens_langue || [])}` : ''}
        ${(sc.candidats || []).length ? `<details ${pick ? '' : 'open'}><summary class="tiny" style="cursor:pointer">Autres vidéos trouvées pour ce plan (${sc.candidats.length})</summary>
          <div class="ad-clips" style="margin-top:8px">${adSortCands(sc.candidats, k, sug).map(c => adCandHtml(c, k, sug, new Set(), { plan: k, chosen: pick && pick.url === c.url })).join('')}</div></details>` : ''}
      </div></article>`;
  }).join('') + `<div class="navbar"><span class="progress-text">${got.length}/${n} plan(s) avec une vidéo</span>
      ${p.wanting && p.wanting.length ? `<button class="btn secondary" id="adMore" title="Cherche l'ACTION de chaque plan sans vidéo (ou seulement partielle) dans des compilations, vidéos GoPro, vlogs… même si la vidéo parle d'autre chose ; l'IA regarde les nouvelles vidéos (2 à 5 min). Les autres plans ne changent pas.">🔎 Chercher plus pour ${p.wanting.length} plan(s)</button>` : '<span></span>'}
      <button class="btn primary" id="adFetch" ${got.length === n ? '' : 'disabled'} title="Télécharge seulement les moments choisis et fabrique un clip par plan (1 à 4 min)" data-icon="download">Télécharger les images choisies →</button></div>`;
  hydrateIcons(body);
  body.querySelectorAll('[data-copy]').forEach(b => b.onclick = () =>
    navigator.clipboard.writeText(b.dataset.copy).then(() => toast('Recherche copiée', 'success')).catch(() => {}));
  body.querySelectorAll('.ad-copyimg').forEach(b => b.onclick = () =>
    adCopyImage(b.dataset.src).then(() => toast('Image copiée : colle-la (Ctrl + V) dans le moteur', 'success'))
      .catch(() => toast('Copie impossible ici : utilise « Enregistrer » puis glisse le fichier', 'error')));
  const choose = async (k, b) => {
    try { const np = await api(`/api/adaptations/${p.project_id}/picks/${k}`, { method:'PUT', body: JSON.stringify(b) });
          adProject = np; renderAdImages(body, np); } catch (e){ log(e.message, 'error'); }
  };
  const post = async (path, btn, label, payload) => {
    if (btn){ btn.disabled = true; btn.innerHTML = spin(label); }
    try { const np = await api(`/api/adaptations/${p.project_id}/${path}`, { method:'POST', body: JSON.stringify(payload || {}) });
          adProject = np; renderAdImages(body, np); return np; }
    catch (e){ log(e.message, 'error'); if (btn){ btn.disabled = false; btn.textContent = btn.dataset.label || 'Réessayer'; } }
  };
  const moreBtn = document.getElementById('adMore');
  if (moreBtn) moreBtn.onclick = async () => {
    moreBtn.disabled = true;
    try { await api(`/api/adaptations/${p.project_id}/images/more`, { method:'POST' }); adProject = null; loadAdProject(); }
    catch (e){ log(e.message, 'error'); moreBtn.disabled = false; }
  };
  const fetchBtn = document.getElementById('adFetch');
  if (fetchBtn) fetchBtn.onclick = async () => {
    fetchBtn.disabled = true;
    try { await api(`/api/adaptations/${p.project_id}/fetch`, { method:'POST' }); adProject = null; loadAdProject(); }
    catch (e){ log(e.message, 'error'); fetchBtn.disabled = false; }
  };
  body.querySelectorAll('.ad-imgplan').forEach(card => {
    const k = +card.dataset.plan;
    card.querySelectorAll('.ad-skip').forEach(b => b.onclick = () => post(`plans/${k}/skip`, null, '', { skip: true }));
    const unskip = card.querySelector('.ad-unskip');
    if (unskip) unskip.onclick = () => post(`plans/${k}/skip`, null, '', { skip: false });
    const excerpt = card.querySelector('.ad-excerpt');
    if (excerpt){ excerpt.dataset.label = excerpt.textContent.trim();
      excerpt.onclick = () => post(`plans/${k}/excerpt`, excerpt, 'repérage dans le Short…',
                                   { ref: +((card.querySelector('.ad-excerpt-ref') || {}).value || 0) || null }); }
    const adapt = card.querySelector('.ad-adapt');
    if (adapt){ adapt.dataset.label = adapt.textContent.trim(); adapt.onclick = () => post(`plans/${k}/adapt`, adapt, 'l\'IA réécrit…'); }
    const chkLink = card.querySelector('.ad-plan-check');
    if (chkLink){ chkLink.dataset.label = 'Vérifier pour ce plan'; chkLink.onclick = () => {
      const url = card.querySelector('.ad-plan-link').value.trim();
      if (!url){ toast('Colle d\'abord un lien', 'error'); return; }
      post(`plans/${k}/link`, chkLink, 'l\'IA regarde…', { url });
    }; }
    const fileBtn = card.querySelector('.ad-file'), fileIn = card.querySelector('.ad-file-input');
    if (fileBtn){ fileBtn.dataset.label = fileBtn.textContent.trim();
      fileBtn.onclick = () => fileIn.click();
      fileIn.onchange = () => adDropFile(fileIn, fileBtn, `plans/${k}/file`, card.querySelector('.ad-file-credit').value,
                                         np => { adProject = np; renderAdImages(body, np); }); }
    const un = card.querySelector('.ad-unpick');
    if (un) un.onclick = () => choose(k, { url: null });
    card.querySelectorAll('.ad-choose').forEach(b => b.onclick = () =>
      choose(k, { url: b.closest('.ad-cand').dataset.url, debut: +b.dataset.debut, fin: +b.dataset.fin }));
    card.querySelectorAll('.ad-check').forEach(chk => chk.onclick = async () => {
      chk.disabled = true; chk.innerHTML = spin('l\'IA regarde…');
      try { const np = await api(`/api/adaptations/${p.project_id}/suggestions/check`, { method:'POST',
              body: JSON.stringify({ url: chk.closest('.ad-cand').dataset.url }) });
            adProject = np; renderAdImages(body, np); }
      catch (e){ log(e.message, 'error'); chk.disabled = false; chk.textContent = 'Vérifier avec l\'IA'; }
    });
  });
}

// Does the clip show what its sentence says? (checked after the download; stale once the sentence or the clip changes)
function adAccordHtml(t, ps, i, p){
  const a = (t.accords || [])[i];
  if (!a || a.texte !== ps.texte || a.clip !== ps.clip) return '';
  if (a.note === 'bon') return `<div class="tiny" style="color:#6fd08c">✅ La phrase va avec son image</div>`;
  const red = a.note === 'non' && !a.garde;
  return `<div class="tiny" style="color:${red ? '#ff7b7b' : '#f5c56d'}">${a.note === 'non' ? (a.garde ? '❌ gardé quand même' : '❌ Ne va pas avec l\'image') : '🟡 Lien faible avec l\'image'}${a.pourquoi ? ' : ' + esc(a.pourquoi) : ''}</div>
    ${a.autre_clip ? `<div class="ad-row"><span class="tiny">Le clip <b>${esc(a.autre_clip)}</b> montre ta phrase : ${esc(((p || {}).clips || []).find(c => c.id === a.autre_clip)?.desc || '').slice(0, 90)}</span>
      <button class="btn ghost small ad-acc" data-act="clip" title="Ta phrase reste ; le clip change">Prendre ce clip</button></div>` : ''}
    ${a.proposition ? `<div class="ad-row"><span class="tiny">Proposé : « ${esc(a.proposition)} »</span>
      <button class="btn ghost small ad-acc" data-act="proposal">Prendre cette phrase</button></div>` : ''}
    ${red ? `<button class="btn ghost small ad-acc" data-act="keep" title="Regarde le clip avec ▶ : tu as le dernier mot">Garder quand même</button>` : ''}`;
}

function renderAdScripts(body, p){
  const allApproved = p.targets.every(t => t.approved);
  body.innerHTML = `<article class="chcard"><div class="chcard-body">
      <label class="f">Crédits affichés en haut de la vidéo et dans la description <span class="tiny">(les comptes dont les images sont utilisées)</span></label>
      <input class="f" id="adScriptCredits" value="${esc(p.credits || '')}"></div></article>` + p.targets.map(t => {
    const sc = t.script || { passages: [] };
    const dir = t.rtl ? 'dir="rtl"' : '';
    return `
    <article class="chcard ad-target-card" data-channel="${t.channel}">
      <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(t.channel)}"></span>
        ${esc((channels.find(c => c.name === t.channel) || {}).display_name || t.channel)} · ${esc(t.language_label)}</div></div>
        ${t.approved ? `<span class="pill ok">${icon('check', 11)} validé</span>` : '<span class="pill warn">à relire</span>'}</div>
      <div class="chcard-body">
        ${t.angle && (p.angles || []).length ? `<div class="ad-row ad-tangle" style="gap:6px"><b>Angle : « ${esc(t.angle.titre)} »</b>
            <select class="f sc-angle" style="width:auto;max-width:100%">${p.angles.map((a, i) =>
              `<option value="${i}" ${a.titre === t.angle.titre ? 'selected' : ''}>${esc(a.titre)}</option>`).join('')}<option value="custom">Mon propre angle…</option></select>
            <input class="f sc-angle-custom" placeholder="Décris ton angle" style="display:none;flex:1;min-width:200px">
            <button class="btn ghost small sc-angle-go" title="Le script de cette chaîne est réécrit (environ 1 minute)">Réécrire avec cet angle</button></div>` : ''}
        ${p.annotations_reviewed || p.mode !== 'script' ? `<div class="tiny">${icon('eye', 12)} Flèches, cercles et effets (ralenti, zoom, arrêt sur image, transition) choisis par l'IA <b>en regardant les vrais clips</b> : clique ▶ pour voir un clip, change-les si besoin.</div>` : ''}
        ${(sc.corrections || []).length ? `<details><summary class="tiny" style="cursor:pointer">Relecture automatique : ${sc.corrections.length} correction(s)</summary>
          <ul class="tiny">${sc.corrections.map(c => `<li>${esc(c)}</li>`).join('')}</ul></details>` : ''}
        ${t.problems.length ? `<div class="errbox">${t.problems.map(esc).join('<br>')}</div>` : ''}
        ${(() => { const refused = [...new Set(sc.passages.map(ps => ps.clip))].map(cid => p.clips.find(c => c.id === cid))
              .filter(c => c && (!c.usable || (c.absent && !c.forced && !(t.accords || []).some((a, i) =>
                a && a.clip === c.id && a.note === 'bon' && (sc.passages[i] || {}).texte === a.texte))));
            return refused.length ? `<div class="ad-row">${refused.map(c => `<span class="tiny">${esc(c.id)} ${c.usable ? `: action introuvable (on y voit : ${esc(c.absent)})` : `refusé (${esc(c.why_not || 'contrôle')})`} :</span>
              <button class="btn ghost small ad-force" data-clip="${esc(c.id)}" title="Regarde-le avec ▶ d'abord : tu as le dernier mot">Utiliser quand même</button>`).join('')}</div>` : ''; })()}
        ${(() => { const noted = [...new Set(sc.passages.map(ps => ps.clip))].map(cid => p.clips.find(c => c.id === cid))
              .filter(c => c && c.usable && c.note);
            return noted.length ? `<div class="tiny" style="color:#f5c56d">${noted.map(c => `${esc(c.id)} : ${esc(c.note)} — vérifie-le avec ▶ (le logo est effacé)`).join(' · ')}</div>` : ''; })()}
        ${(() => { const left = [...new Set(sc.passages.map(ps => ps.clip))].map(cid => p.clips.find(c => c.id === cid))
              .filter(c => c && (c.texte_efface || []).length);
            return left.length ? `<div class="tiny" style="opacity:.8">${left.map(c => `${esc(c.id)} : texte resté après nettoyage, effacé aussi (« ${esc(c.texte_efface.join(' », « '))} ») — vérifie avec ▶`).join(' · ')}</div>` : ''; })()}
        ${(() => { const low = [...new Set(sc.passages.map(ps => ps.clip))].map(cid => p.clips.find(c => c.id === cid))
              .filter(c => c && c.low_res);
            return low.length ? `<div class="tiny" style="color:#f5c56d">Basse résolution (floue à l'écran) : ${low.map(c => `${esc(c.id)} (${c.w}×${c.h})${sc.passages[0] && sc.passages[0].clip === c.id ? ' <b>— c\'est l\'accroche : cherche mieux si tu peux</b>' : ''}`).join(', ')}</div>` : ''; })()}
        <label class="f">Titre</label><input class="f sc-title" ${dir} value="${esc(sc.titre || '')}">
        <div>${sc.passages.map((ps, i) => `
          <div class="ad-passage" data-i="${i}">
            ${adPlayHtml(p.project_id, ps.clip)}
            <div class="fields">
              <div class="ad-row"><select class="f sc-clip">${adClipOptions(p, ps.clip)}</select>
                <input class="f sc-banner" ${dir} value="${esc(ps.bandeau)}" placeholder="Bandeau" style="flex:1;min-width:180px"></div>
              <textarea class="f sc-text" ${dir}>${esc(ps.texte)}</textarea>
              <input class="f sc-keys" ${dir} value="${esc((ps.mots_cles || []).join(', '))}" placeholder="Mots en couleur, séparés par des virgules" style="font-size:12px">
              ${adAnnHtml(ps.annotation)}
              ${adFxHtml(ps.effets)}
              ${ps.effets && ps.effets.zoom && ps.annotation ? `<div class="tiny" style="color:#f5c56d">Zoom ignoré : ce plan a une flèche ou un cercle (elle serait mal placée sur l'image zoomée). Choisis l'un ou l'autre.</div>` : ''}
              ${adAccordHtml(t, ps, i, p)}
            </div>
          </div>`).join('')}</div>
        <label class="f">Description</label><textarea class="f sc-desc" ${dir}>${esc(sc.description || '')}</textarea>
        <label class="f">Tags</label><input class="f sc-tags" ${dir} value="${esc((sc.tags || []).join(', '))}">
      </div>
      <div class="chcard-foot">
        <div class="askrow" style="flex:1;min-width:240px">${icon('sparkle', 16)}<input class="sc-ask" placeholder="Demande à l'IA, ex : la phrase 3 est trop longue…">
          <button class="btn secondary small sc-revise">Envoyer</button></div>
        <button class="btn secondary small sc-save">Enregistrer</button>
        <button class="btn primary small sc-approve" data-icon="check">Valider ce script</button>
      </div>
    </article>`;
  }).join('') + `<div class="navbar"><span class="progress-text">${p.targets.filter(t => t.approved).length}/${p.targets.length} script(s) validé(s)</span>
      ${p.mode === 'script' ? '<button class="btn ghost small" id="adBackImages" data-icon="eye">← Revenir aux images</button>' : '<span></span>'}
      <button class="btn primary" id="adVoices" ${allApproved ? '' : 'disabled'} data-icon="mic">Générer les voix et les aperçus →</button></div>`;
  hydrateIcons(body);
  adBindPlay(body);
  document.getElementById('adScriptCredits').onchange = async e => {
    try { adProject = await api(`/api/adaptations/${p.project_id}/credits`, { method:'PATCH', body: JSON.stringify({ credits: e.target.value }) });
          toast('Crédits enregistrés', 'success'); } catch (err){ log(err.message, 'error'); }
  };
  body.querySelectorAll('.ad-target-card').forEach(card => {
    const ch = card.dataset.channel;
    const collect = () => ({
      titre: card.querySelector('.sc-title').value, description: card.querySelector('.sc-desc').value,
      tags: card.querySelector('.sc-tags').value.split(',').map(x => x.trim()).filter(Boolean),
      passages: [...card.querySelectorAll('.ad-passage')].map(row => ({
        clip: row.querySelector('.sc-clip').value, bandeau: row.querySelector('.sc-banner').value,
        texte: row.querySelector('.sc-text').value, annotation: adAnnOf(row), effets: adFxOf(row),
        mots_cles: row.querySelector('.sc-keys').value.split(',').map(x => x.trim()).filter(Boolean) })) });
    const refresh = np => { adProject = null; renderAdScripts(body, np); adProject = np; };
    // a save is judged again (20 s or more): no voices started before it is written
    const busy = () => { const go = document.getElementById('adVoices'); if (go) go.disabled = true; };
    card.querySelectorAll('.sc-clip').forEach(sel => sel.onchange = () =>
      { const holder = sel.closest('.ad-passage').querySelector('.ad-play');
        holder.outerHTML = adPlayHtml(p.project_id, sel.value); adBindPlay(sel.closest('.ad-passage')); });
    card.querySelector('.sc-save').onclick = async () => {
      busy();
      try { refresh(await (adAnnMissing(card) ? Promise.reject(new Error('Flèche ou cercle sans cible')) : api(`/api/adaptations/${p.project_id}/targets/${ch}/script`, { method:'PUT', body: JSON.stringify({ script: collect() }) })));
            toast('Script enregistré', 'success'); } catch (e){ log(e.message, 'error'); }
    };
    card.querySelector('.sc-revise').onclick = async ev => {
      const req = card.querySelector('.sc-ask').value.trim();
      if (!req) return;
      const btn = ev.currentTarget; btn.disabled = true; btn.innerHTML = spin('…'); busy();
      try {
        await (adAnnMissing(card) ? Promise.reject(new Error('Flèche ou cercle sans cible')) : api(`/api/adaptations/${p.project_id}/targets/${ch}/script`, { method:'PUT', body: JSON.stringify({ script: collect() }) }));
        refresh(await api(`/api/adaptations/${p.project_id}/targets/${ch}/revise`, { method:'POST', body: JSON.stringify({ request: req }) }));
      } catch (e){ log(e.message, 'error'); btn.disabled = false; btn.textContent = 'Envoyer'; }
    };
    card.querySelector('.sc-approve').onclick = async () => {
      busy();
      try {
        await (adAnnMissing(card) ? Promise.reject(new Error('Flèche ou cercle sans cible')) : api(`/api/adaptations/${p.project_id}/targets/${ch}/script`, { method:'PUT', body: JSON.stringify({ script: collect() }) }));
        refresh(await api(`/api/adaptations/${p.project_id}/targets/${ch}/approve`, { method:'POST' }));
        toast('Script validé ✓', 'success');
      } catch (e){ log(e.message, 'error'); refresh(await api(`/api/adaptations/${p.project_id}`)); }
    };
  });
  const go = document.getElementById('adVoices');
  if (go) go.onclick = async () => {
    try { await api(`/api/adaptations/${p.project_id}/voices`, { method:'POST' }); adProject = null; loadAdProject(); } catch (e){ log(e.message, 'error'); }
  };
  body.querySelectorAll('.ad-target-card').forEach(card => {
    const sel = card.querySelector('.sc-angle');
    if (!sel) return;
    const custom = card.querySelector('.sc-angle-custom');
    sel.onchange = () => custom.style.display = sel.value === 'custom' ? '' : 'none';
    card.querySelector('.sc-angle-go').onclick = async ev => {
      const own = sel.value === 'custom' ? custom.value.trim() : null;
      if (sel.value === 'custom' && !own){ toast('Décris ton angle', 'error'); return; }
      ev.currentTarget.disabled = true;
      try { await api(`/api/adaptations/${p.project_id}/targets/${card.dataset.channel}/angle`, { method:'POST',
              body: JSON.stringify(own ? { custom: own } : { index: +sel.value }) }); adProject = null; loadAdProject(); }
      catch (e){ log(e.message, 'error'); ev.currentTarget.disabled = false; }
    };
  });
  body.querySelectorAll('.ad-acc').forEach(b => b.onclick = async () => {
    const card = b.closest('[data-channel]'), k = b.closest('.ad-passage').dataset.i;
    b.disabled = true;
    try { const np = await api(`/api/adaptations/${p.project_id}/targets/${card.dataset.channel}/passages/${k}/${b.dataset.act}`, { method:'POST' });
          adProject = null; renderAdScripts(body, np); adProject = np; }
    catch (e){ log(e.message, 'error'); b.disabled = false; }
  });
  body.querySelectorAll('.ad-force').forEach(b => b.onclick = async () => {
    b.disabled = true;
    try { const np = await api(`/api/adaptations/${p.project_id}/clips/${b.dataset.clip}/force`, { method:'POST' });
          toast(`${b.dataset.clip} utilisé quand même`, 'success'); adProject = null; renderAdScripts(body, np); adProject = np; }
    catch (e){ log(e.message, 'error'); b.disabled = false; }
  });
  const back = document.getElementById('adBackImages');
  if (back) back.onclick = async () => {
    try { await api(`/api/adaptations/${p.project_id}/back-to-images`, { method:'POST' }); adProject = null; loadAdProject(); } catch (e){ log(e.message, 'error'); }
  };
}

async function renderAdPreviews(body, p){
  const voicesByLang = {};
  await Promise.all([...new Set(p.targets.map(t => t.language))].map(async lg => {
    voicesByLang[lg] = (await api(`/api/voices?language=${lg}`)).voices;
  }));
  const anyValidated = p.targets.some(t => t.validated && !t.video_id);
  body.innerHTML = p.targets.map(t => {
    const vs = voicesByLang[t.language] || [];
    const cur = vs.find(v => v.voice_id === t.voice_id);
    const ok = t.checks && t.checks.ok;
    return `
    <article class="chcard ad-prev-card" data-channel="${t.channel}">
      <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(t.channel)}"></span>
        ${esc((channels.find(c => c.name === t.channel) || {}).display_name || t.channel)} · ${esc(t.language_label)}${t.duration ? ` · ${fmtSec(t.duration)}` : ''}</div></div>
        ${t.video_id ? `<span class="pill ok">${icon('check', 11)} dans Publication</span>` : t.validated ? `<span class="pill ok">${icon('check', 11)} validé</span>` : '<span class="pill warn">à regarder</span>'}</div>
      <div class="chcard-body"><div class="ad-preview">
        <div>${t.preview_url ? `<video src="${t.preview_url}?v=${Date.now()}" controls playsinline></video>` : ''}</div>
        <div class="stack" style="gap:10px">
          ${ok ? `<div class="okbox">${icon('check', 12)} Contrôle automatique : son complet, chaque phrase à sa place, volume ${t.checks.measures.lufs} LUFS.</div>`
               : `<div class="errbox">${((t.checks || {}).problems || ['Pas encore contrôlé']).map(esc).join('<br>')}</div>`}
          <div><label class="f">Voix</label>
            <div class="ad-row"><select class="f pv-voice">${vs.map(v => `<option value="${v.voice_id}" ${v.voice_id === t.voice_id ? 'selected' : ''}>${esc(voiceLabel(v))}</option>`).join('')}</select>
              <button class="btn secondary small pv-revoice">Refaire avec cette voix</button></div>
            ${cur && cur.has_preview ? `<audio class="pv-sample" controls preload="none" src="${cur.preview_url}" style="width:100%;height:32px;margin-top:6px"></audio>` : ''}</div>
          ${t.music ? `<div class="tiny">Musique : ${esc(t.music)}</div>` : '<div class="tiny">Sans musique (Réglages → Voix pour en choisir une).</div>'}
        </div>
      </div></div>
      <div class="chcard-foot">${t.video_id ? '' : `<button class="btn primary small push pv-validate" data-icon="check" ${ok && !t.validated ? '' : 'disabled'}>Valider cet aperçu</button>`}</div>
    </article>`;
  }).join('') + `<div class="navbar"><span class="progress-text">${p.targets.filter(t => t.validated).length}/${p.targets.length} aperçu(s) validé(s)</span>
      ${p.targets.some(t => t.video_id) ? '<span></span>' : '<button class="btn ghost small" id="adBackScript" data-icon="eye" title="Changer un clip, une phrase, un effet : la voix est gardée si les phrases ne changent pas">← Revenir au script</button>'}
      <button class="btn primary" id="adRender" ${anyValidated ? '' : 'disabled'} data-icon="film">Rendu final des aperçus validés →</button></div>`;
  hydrateIcons(body);
  const backScript = document.getElementById('adBackScript');
  if (backScript) backScript.onclick = async () => {
    try { await api(`/api/adaptations/${p.project_id}/back-to-script`, { method:'POST' }); adProject = null; loadAdProject(); } catch (e){ log(e.message, 'error'); }
  };
  body.querySelectorAll('.ad-prev-card').forEach(card => {
    const ch = card.dataset.channel;
    const sel = card.querySelector('.pv-voice');
    sel.onchange = () => {
      const v = (voicesByLang[p.targets.find(t => t.channel === ch).language] || []).find(x => x.voice_id === sel.value);
      const sample = card.querySelector('.pv-sample');
      if (sample && v) sample.src = v.preview_url;
    };
    card.querySelector('.pv-revoice').onclick = async () => {
      try { await api(`/api/adaptations/${p.project_id}/targets/${ch}/voice`, { method:'PATCH', body: JSON.stringify({ voice_id: sel.value }) });
            adProject = null; loadAdProject(); } catch (e){ log(e.message, 'error'); }
    };
    const val = card.querySelector('.pv-validate');
    if (val) val.onclick = async () => {
      try { await api(`/api/adaptations/${p.project_id}/targets/${ch}/validate`, { method:'POST' }); adProject = null; loadAdProject(); }
      catch (e){ log(e.message, 'error'); }
    };
  });
  const r = document.getElementById('adRender');
  if (r) r.onclick = async () => {
    try { await api(`/api/adaptations/${p.project_id}/render`, { method:'POST' }); adProject = null; loadAdProject(); } catch (e){ log(e.message, 'error'); }
  };
}

function renderAdDone(body, p){
  body.innerHTML = `<article class="chcard"><div class="chcard-body">
      <div class="okbox">${icon('check', 12)} ${p.targets.length} vidéo(s) prête(s) : elles attendent dans Publication, avec leur titre, leur description (crédits inclus) et leurs tags.</div>
      ${p.targets.map(t => `<div>${icon('check', 12)} ${esc((channels.find(c => c.name === t.channel) || {}).display_name || t.channel)} · ${esc(t.language_label)}</div>`).join('')}
    </div><div class="chcard-foot"><button class="btn primary push" id="adToPub" data-icon="rocket">Aller à Publication →</button></div></article>`;
  hydrateIcons(body);
  document.getElementById('adToPub').onclick = () => openSpace('publication');
}
