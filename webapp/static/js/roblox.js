// ---------- Montage Roblox : one long Roblox video → several Shorts ----------

let rbCurrent = null, rbPoll = null;
const RB_BUSY = ['analysing', 'rendering'];
const RB_STATUS = { analysing: 'analyse…', plan_review: 'textes à relire', rendering: 'montage…', review: 'vidéos à regarder',
  done: 'terminé', error: 'erreur' };
const RB_STEPS = [['Analyse', ['analysing']], ['Textes', ['plan_review']], ['Montage', ['rendering']], ['Vidéos', ['review', 'done']]];
const RB_STYLES = [['clip', 'Clip sous-titré', 'le meilleur moment, ses répliques sous-titrées, zoom et « boom » sur la chute'],
  ['pov', 'POV', 'un titre « POV : … » et la réaction'],
  ['histoire', 'Histoire racontée', 'une voix raconte, plusieurs extraits, sous-titres mot à mot'],
  ['top3', 'Top 3', '#3, #2, #1 en gros, une étiquette par moment'],
  ['devine', 'Devine la suite', 'arrêt sur image, question, 3-2-1, puis la réponse']];
const RB_LANGS = [['fr', 'Français'], ['en', 'Anglais']];

function openRoblox(){
  screens.forEach(el => el.classList.remove('active'));
  document.getElementById('robloxScreen').classList.add('active');
  loadRobloxList();
}

async function loadRobloxList(){
  const list = await api('/api/roblox');
  if (rbCurrent === null && list.length) rbCurrent = list[0].project_id;
  const bar = document.getElementById('rbProjects');
  bar.innerHTML = list.length ? '<span class="tiny">Projets :</span>' + list.slice(0, 12).map(p =>
    `<button class="chipbtn" data-id="${esc(p.project_id)}" style="${p.project_id === rbCurrent ? 'border-color:var(--accent);color:var(--text)' : ''}">
      ${esc((p.titre || p.url).slice(0, 34))} · ${esc(RB_STATUS[p.status] || p.status)}</button>`).join('')
    : '<span class="tiny">Aucun projet pour l\'instant.</span>';
  bar.querySelectorAll('.chipbtn').forEach(b => b.onclick = () => { rbCurrent = b.dataset.id; clearTimeout(rbPoll); loadRobloxList(); });
  if (rbCurrent && list.some(p => p.project_id === rbCurrent)) loadRbProject();
  else { rbCurrent = ''; renderNewRoblox(); }
}
document.getElementById('rbNewBtn').addEventListener('click', () => { rbCurrent = ''; clearTimeout(rbPoll); loadRobloxList(); });

function rbStepsHtml(status){
  const at = RB_STEPS.findIndex(([, sts]) => sts.includes(status));
  return `<div class="ad-steps">${RB_STEPS.map(([l], i) =>
    `<div class="ad-step ${i < at || status === 'done' ? 'done' : i === at ? 'active' : ''}"><div class="bar"></div><div class="lbl">${i + 1} · ${l}</div></div>`).join('')}</div>`;
}

function chOptions(){
  return channels.map(c => `<option value="${esc(c.name)}">${esc(c.display_name || c.name)}</option>`).join('');
}

function renderNewRoblox(){
  const stage = document.getElementById('rbStage');
  stage.innerHTML = `${rbStepsHtml('new')}
    <article class="chcard"><div class="chcard-body">
      <label class="f">1. La vidéo Roblox longue (YouTube : une compilation, un live, un let's play…)</label>
      <input class="f" id="rbUrl" placeholder="https://www.youtube.com/watch?v=…">
      <label class="f" style="margin-top:12px">2. Les styles de montage (un Short par style et par langue)</label>
      <div style="display:flex;flex-direction:column;gap:6px">${RB_STYLES.map(([k, n, d]) =>
        `<label class="tiny" style="display:flex;gap:8px;align-items:center;cursor:pointer"><input type="checkbox" class="rb-style" value="${k}" checked>
          <b>${esc(n)}</b> — ${esc(d)}</label>`).join('')}</div>
      <label class="f" style="margin-top:12px">3. Les langues, et la chaîne de chacune</label>
      <div style="display:flex;flex-direction:column;gap:6px">${RB_LANGS.map(([k, n]) =>
        `<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><label class="tiny" style="display:flex;gap:8px;align-items:center;cursor:pointer;width:110px">
          <input type="checkbox" class="rb-lang" value="${k}" checked> ${esc(n)}</label>
          <select class="f rb-ch" data-lang="${k}" style="max-width:280px">${chOptions()}</select></div>`).join('')}</div>
      <label class="f" style="margin-top:12px">4. Le son</label>
      <label class="tiny" style="display:flex;gap:8px;cursor:pointer"><input type="radio" name="rbMusic" value="original" checked> Garder le son d'origine (voix, bruitages et musique de la vidéo)</label>
      <label class="tiny" style="display:flex;gap:8px;cursor:pointer"><input type="radio" name="rbMusic" value="chaine"> Remplacer par la musique de la chaîne (Réglages → Voix) : le son d'origine est coupé</label>
    </div>
    <div class="chcard-foot"><span class="note">L'analyse prend quelques minutes : seuls les passages les plus revus sont téléchargés, jamais toute la vidéo.</span>
      <button class="btn primary" id="rbGo" data-icon="sparkle">Analyser</button></div></article>`;
  hydrateIcons(stage);
  document.getElementById('rbGo').onclick = async ev => {
    const btn = ev.currentTarget;
    const styles = [...stage.querySelectorAll('.rb-style:checked')].map(x => x.value);
    const cibles = [...stage.querySelectorAll('.rb-lang:checked')].map(x => ({ langue: x.value,
      channel: stage.querySelector(`.rb-ch[data-lang="${x.value}"]`).value }));
    const musique = stage.querySelector('input[name="rbMusic"]:checked').value;
    btn.disabled = true; btn.innerHTML = spin('Création…');
    try {
      const p = await api('/api/roblox', { method: 'POST', body: JSON.stringify({ url: document.getElementById('rbUrl').value, styles, cibles, musique }) });
      rbCurrent = p.project_id; loadRobloxList();
    } catch (e){ log(e.message, 'error'); btn.disabled = false; btn.innerHTML = 'Analyser'; }
  };
}

async function loadRbProject(){
  clearTimeout(rbPoll);
  const p = await api(`/api/roblox/${rbCurrent}`);
  const stage = document.getElementById('rbStage');
  const head = `${rbStepsHtml(p.status)}
    <div class="toolbar"><div class="fact">${esc(p.titre || p.url)}${p.chaine_source ? ` · <span class="tiny">${esc(p.chaine_source)}</span>` : ''}</div>
      <button class="btn ghost small" id="rbDel" title="Supprimer le projet">Supprimer</button></div>`;
  let body = '';
  if (RB_BUSY.includes(p.status)){
    const pct = Math.round(((p.progress && p.progress.fraction) || 0) * 100);
    body = `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${spin('')} ${esc(RB_STATUS[p.status])}</div>
      <div class="meta" style="margin-left:0">${esc((p.progress && p.progress.phase) || 'préparation…')} — tu peux changer d'écran, ça continue.</div></div>
      <span class="pill wait">${pct} %</span></div>
      <div class="chcard-body"><div class="pbar"><div style="width:${pct}%"></div></div></div></article>`;
    rbPoll = setTimeout(() => { if (currentSpace === 'roblox' && rbCurrent === p.project_id) safeLoad(loadRbProject, 'rbStage'); }, 2000);
  } else if (p.status === 'error'){
    body = `<article class="chcard"><div class="chcard-body"><span class="pill warn">Erreur</span> ${esc(p.error || '')}</div>
      <div class="chcard-foot"><span></span><button class="btn primary" id="rbRetry" data-icon="refresh">Réessayer</button></div></article>`;
  } else {
    body = (p.absents || []).map(a => `<div class="tiny" style="margin:4px 0">⚠️ ${esc(a)}</div>`).join('') + rbTextsHtml(p) + rbVideosHtml(p);
  }
  stage.innerHTML = head + body;
  hydrateIcons(stage);
  wireRbProject(p);
}

function rbField(label, name, value, wide){
  return `<div style="flex:1 1 ${wide ? '100%' : '260px'}"><label class="f">${esc(label)}</label><input class="f" data-k="${name}" value="${esc(value || '')}"></div>`;
}

function rbTextsHtml(p){
  if (!['plan_review', 'review', 'done'].includes(p.status)) return '';
  const sent = k => ((p.videos || {})[k] || {}).video_id;
  return `<div class="fact" style="margin:16px 0 8px"><b>Les textes, à relire</b></div>` + p.styles.filter(s => p.plan[s]).map(s => {
    const st = p.plan[s];
    return `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${esc(p.noms_styles[s])}</div>
      <div class="meta" style="margin-left:0">${esc(rbMomentsOf(p, st))}</div></div></div>
      <div class="chcard-body">${p.cibles.map(c => {
        const L = c.langue, pub = (st.publication || {})[L] || {};
        const main = s === 'pov' ? rbField('Titre POV', 'pov', st.pov[L], true)
          : s === 'devine' ? rbField('Question', 'question', st.question[L]) + rbField('Texte final', 'final', st.final[L])
          : rbField('Titre à l\'écran', 'titre', st.titre[L], true);
        const list = s === 'histoire' ? st.passages.map((x, i) => rbField(`Phrase ${i + 1}`, `passages.${i}`, x.textes[L], true)).join('')
          : s === 'top3' ? st.rangs.map((x, i) => rbField(`#${x.rang}`, `labels.${i}`, x.label[L])).join('') : '';
        return `<div class="rb-lang-box" data-style="${s}" data-lang="${L}" style="border-top:1px solid var(--border-soft);padding:10px 0">
          <div class="tiny"><b>${esc(L.toUpperCase())}</b> · ${esc((channels.find(x => x.name === c.channel) || {}).display_name || c.channel)}${sent(`${s}_${L}`) ? ' · envoyée ✓' : ''}</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">${main}${list}</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">${rbField('Titre YouTube', 'pub.titre', pub.titre)}${rbField('Tags (séparés par des virgules)', 'pub.tags', (pub.tags || []).join(', '))}
            ${rbField('Description', 'pub.description', pub.description, true)}</div>
          <button class="btn secondary small rb-save" ${sent(`${s}_${L}`) ? 'disabled' : ''}>Enregistrer</button></div>`;
      }).join('')}</div></article>`;
  }).join('') + (['plan_review', 'review'].includes(p.status) ? `<div class="navbar"><span class="progress-text">${p.status === 'plan_review'
    ? 'Les vidéos ne sont pas encore faites.' : 'Une correction refait seulement la vidéo concernée.'}</span><span></span>
    <button class="btn primary" id="rbRender" data-icon="sparkle">${p.status === 'plan_review' ? 'Faire les vidéos' : 'Refaire les vidéos corrigées'}</button></div>` : '');
}

function rbMomentsOf(p, st){
  const ids = st.moment ? [st.moment] : (st.passages || st.rangs || []).map(x => x.moment);
  return [...new Set(ids)].map(id => p.moments[id]).filter(Boolean).join(' · ');
}

function rbVideosHtml(p){
  const keys = Object.keys(p.videos || {});
  if (!keys.length || !['review', 'done'].includes(p.status)) return '';
  return `<div class="fact" style="margin:16px 0 8px"><b>Les vidéos</b></div><div class="grid-3">${keys.map(k => {
    const v = p.videos[k];
    return `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">${esc(p.noms_styles[v.style])} · ${esc(v.langue.toUpperCase())}</div>
      <div class="meta" style="margin-left:0">${esc((channels.find(x => x.name === v.channel) || {}).display_name || v.channel)} · ${v.duree} s</div></div></div>
      <div class="chcard-body"><video src="${esc(v.url)}" controls preload="metadata" style="width:100%;max-height:520px;border-radius:12px;background:#000"></video></div>
      <div class="chcard-foot">${v.video_id ? '<span class="pill">envoyée en Publication ✓</span>' : v.a_refaire ? '<span class="pill warn">texte corrigé : à refaire</span>'
        : `<label class="tiny" style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" class="rb-keep" value="${esc(k)}" checked> Garder</label>`}</div></article>`;
  }).join('')}</div>
  ${p.status === 'review' ? `<div class="navbar"><span class="progress-text">Les vidéos gardées vont en Publication, prêtes à planifier.</span><span></span>
    <button class="btn primary" id="rbSend" data-icon="upload">Envoyer en Publication</button></div>` : ''}`;
}

function wireRbProject(p){
  const stage = document.getElementById('rbStage');
  const del = document.getElementById('rbDel');
  if (del) del.onclick = async () => {
    if (!confirm('Supprimer ce projet ? Les vidéos déjà envoyées en Publication restent.')) return;
    try { await api(`/api/roblox/${p.project_id}`, { method: 'DELETE' }); rbCurrent = ''; loadRobloxList(); }
    catch (e){ log(e.message, 'error'); }
  };
  const retry = document.getElementById('rbRetry');
  if (retry) retry.onclick = async () => { try { await api(`/api/roblox/${p.project_id}/retry`, { method: 'POST' }); loadRbProject(); } catch (e){ log(e.message, 'error'); } };
  stage.querySelectorAll('.rb-save').forEach(btn => btn.onclick = async () => {
    const box = btn.closest('.rb-lang-box'), edit = { passages: [], labels: [], publication: {} };
    box.querySelectorAll('input[data-k]').forEach(inp => {
      const [a, b] = inp.dataset.k.split('.');
      if (a === 'pub') edit.publication[b] = b === 'tags' ? inp.value.split(',').map(t => t.trim()).filter(Boolean) : inp.value;
      else if (a === 'passages' || a === 'labels') edit[a][+b] = inp.value;
      else edit[a] = inp.value;
    });
    btn.disabled = true;
    try { await api(`/api/roblox/${p.project_id}/textes`, { method: 'PUT', body: JSON.stringify({ style: box.dataset.style, langue: box.dataset.lang, edit }) });
      log('Textes enregistrés', 'success'); loadRbProject(); }
    catch (e){ log(e.message, 'error'); btn.disabled = false; }
  });
  const go = document.getElementById('rbRender');
  if (go) go.onclick = async () => { go.disabled = true; try { await api(`/api/roblox/${p.project_id}/render`, { method: 'POST' }); loadRbProject(); }
    catch (e){ log(e.message, 'error'); go.disabled = false; } };
  const send = document.getElementById('rbSend');
  if (send) send.onclick = async () => {
    const videos = [...stage.querySelectorAll('.rb-keep:checked')].map(x => x.value);
    send.disabled = true;
    try { await api(`/api/roblox/${p.project_id}/send`, { method: 'POST', body: JSON.stringify({ videos }) });
      log(`${videos.length} vidéo(s) envoyée(s) en Publication`, 'success'); loadRbProject(); }
    catch (e){ log(e.message, 'error'); send.disabled = false; }
  };
}
