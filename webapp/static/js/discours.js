// ---------- Adaptation › Discours : a speech, the speaker's own voice (adaptation/discours_pipeline.py) ----------
// The passage (Gemini's 2-3, its first / last word moved by a click), the cut-aways one by one (keep, take out, a
// link or a file of one's own), then each channel's video with the settings panel (made again without AI).
// Réglages → Discours: each channel's « style Discours » and whether its cut-aways may be films.

const DS_SONS = [
  ['intelligente', 'Musique intelligente', 'l\'IA choisit dans la liste commune, sa montée tombe sur la chute'],
  ['choisie', 'Une musique de la liste', 'tu la choisis, sa montée tombe sur la chute'],
  ['notre_musique', 'Notre musique', 'la musique de la chaîne'],
  ['sans_musique', 'Sans musique', 'la voix de l\'orateur seule'],
];
const DS_LABELS = {
  cadre: { carre: 'Carré', '4:5': '4:5 (portrait)', '16:9': '16:9 (paysage)' },
  fond: { noir: 'Noir', flou: 'Son image floutée', degrade: 'Dégradé de la couleur de la chaîne' },
  etalonnage: { dark: 'Dark (contraste)', vivid: 'Vivid (couleurs)', aucun: 'Aucun' },
  densite: { faible: 'Peu de plans', normale: 'Normale', forte: 'Beaucoup de plans' },
  pauses: { resserrees: 'Resserrées (0,25 s)', gardees: 'Gardées' },
};
let dsSongs = null;

async function dsLoadSongs(){
  if (!dsSongs){ try { dsSongs = (await api('/api/musiques')).musiques || []; } catch (e){ dsSongs = []; } }
  return dsSongs;
}

function dsSoundPicker(son, chanson){
  const songs = dsSongs || [];
  return `<label class="f" style="margin-top:6px">La musique</label>
    <div class="ad-row" style="flex-direction:column;align-items:flex-start;gap:4px">${DS_SONS.map(([v, l, d]) =>
      `<label class="switch" style="color:var(--text)"><input type="radio" name="dsSon" value="${v}" ${v === son ? 'checked' : ''}>
        <b>${l}</b> <span class="tiny">${esc(d)}</span></label>`).join('')}</div>
    <div class="ds-song" style="display:${son === 'choisie' ? 'flex' : 'none'};gap:8px;align-items:center;margin-top:4px">
      <select class="f ds-chanson" style="width:auto;max-width:320px">${songs.map(s =>
        `<option value="${esc(s.fichier)}" data-url="${s.url}" ${s.fichier === chanson ? 'selected' : ''}>${esc((s.analyse || {}).titre || s.fichier)}${(s.analyse || {}).humeur ? ' — ' + esc(s.analyse.humeur) : ''}</option>`).join('')
        || '<option value="">aucune musique (Réglages → Voix → Musiques)</option>'}</select>
      <audio class="ds-song-play" controls preload="none" style="height:32px" src="${songs.length ? (songs.find(s => s.fichier === chanson) || songs[0]).url : ''}"></audio></div>`;
}

function dsBindSound(box){
  const song = box.querySelector('.ds-song'), sel = box.querySelector('.ds-chanson'), play = box.querySelector('.ds-song-play');
  box.querySelectorAll('input[name="dsSon"]').forEach(r => r.addEventListener('change', () => {
    song.style.display = (box.querySelector('input[name="dsSon"]:checked') || {}).value === 'choisie' ? 'flex' : 'none';
  }));
  if (sel) sel.onchange = () => { const o = sel.selectedOptions[0]; if (o && play) play.src = o.dataset.url; };
}

function dsSoundOf(box){
  const son = (box.querySelector('input[name="dsSon"]:checked') || {}).value || 'intelligente';
  return { son, chanson: son === 'choisie' ? (box.querySelector('.ds-chanson') || {}).value || null : null };
}

// the creation form's own part (drawn by adaptation.js when « Discours » is picked)
async function dsCreationHtml(){
  await dsLoadSongs();
  return `${dsSoundPicker('intelligente', null)}
    <label class="f" style="margin-top:6px">Durée visée</label>
    <div class="seg" id="dsDuree">${[30, 45, 60].map(d => `<button class="seg-opt ${d === 45 ? 'active' : ''}" data-d="${d}">${d} s</button>`).join('')}</div>
    <div class="tiny" style="margin-top:4px">La voix et l'image de l'orateur sont gardées ; les sous-titres sont traduits dans la langue de chaque chaîne.
      Cérémonies, émissions TV et archives sont toujours permises ; les extraits de films, séries ou clips seulement si <b>toutes</b> les chaînes choisies les autorisent (Réglages → Discours).</div>`;
}

function dsBindCreation(box){
  dsBindSound(box);
  box.querySelectorAll('#dsDuree .seg-opt').forEach(b => b.onclick = ev => {
    ev.preventDefault();
    box.querySelectorAll('#dsDuree .seg-opt').forEach(x => x.classList.toggle('active', x === b));
  });
}

function dsCreationOf(box){
  return { ...dsSoundOf(box), duree: Number((box.querySelector('#dsDuree .seg-opt.active') || {}).dataset?.d || 45) };
}

function renderDiscours(body, p){
  if (p.status === 'passage_review'){ dsPassage(body, p); return true; }
  if (p.status === 'plans_review'){ dsPlans(body, p); return true; }
  if (p.status === 'preview_review'){ dsPreviews(body, p); return true; }
  return false;                                       // done, error…: the usual screens
}

async function dsCall(url, method, data){
  try { await api(url, { method, body: data ? JSON.stringify(data) : undefined }); adProject = null; loadAdProject(); }
  catch (e){ log(e.message, 'error'); }
}

// ---------------------------------------------------------------- the passage

function dsPassage(body, p){
  const d = p.discours, c = d.choix || {};
  const around = c.autour || { debut: 0, mots: [] };
  let edge = 'debut', i0 = c.i0, i1 = c.i1;
  body.innerHTML = `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">Choisis le passage</div>
      <div class="meta" style="margin-left:0">${esc(d.titre_video || '')}${d.langue ? ` · parlé en ${esc(d.langue)}` : ''} · durée visée ${d.duree} s (les pauses seront resserrées)</div></div></div>
    <div class="chcard-body">
      <div class="stack" style="gap:8px">${d.passages.map((x, k) => `
        <label class="switch ds-pass" style="color:var(--text);align-items:flex-start">
          <input type="radio" name="dsPass" value="${k}" ${k === c.index || (c.index === undefined && k === 0) ? 'checked' : ''}>
          <span><b>${esc(x.titre || `Passage ${k + 1}`)}</b> <span class="pill ${x.note >= 8 ? 'ok' : 'wait'}">${x.note}/10</span>
            <span class="tiny">${fmtSec(x.debut)}–${fmtSec(x.fin)} (${Math.round(x.fin - x.debut)} s) · ${esc(x.pourquoi || '')}</span><br>
            <span class="tiny" style="color:var(--text)">« ${esc(x.texte)} »</span></span></label>`).join('')}</div>
      <div class="ad-row" style="margin-top:8px"><button class="btn ghost small" id="dsMore" data-icon="refresh">Chercher d'autres passages</button></div>
      <label class="f" style="margin-top:10px">Ajuste les bornes : clique un mot</label>
      <div class="seg" id="dsEdge"><button class="seg-opt active" data-e="debut">1er mot</button><button class="seg-opt" data-e="fin">Dernier mot</button></div>
      <div id="dsWords" style="line-height:2;margin-top:6px">${around.mots.map((w, k) => {
        const i = around.debut + k;
        return `<span class="ds-w" data-i="${i}" style="cursor:pointer;padding:2px 3px;border-radius:4px">${esc(w)}</span>`;
      }).join(' ')}</div>
      <div class="tiny" id="dsSpan"></div>
      <label class="f" style="margin-top:8px">L'orateur (crédité dans la description)</label>
      <input class="f" id="dsOrateur" value="${esc(d.orateur || '')}" placeholder="Nom de la personne qui parle">
      ${d.video_url ? `<video id="dsVideo" src="${d.video_url}" controls playsinline preload="metadata" style="width:100%;max-height:40vh;background:#000;margin-top:8px"></video>` : ''}
    </div>
    <div class="chcard-foot"><button class="btn secondary small" id="dsSave" data-icon="check">Enregistrer</button>
      <button class="btn primary push" id="dsOk" data-icon="check">Ce passage → chercher les plans</button></div></article>`;
  hydrateIcons(body);
  const paint = () => {
    body.querySelectorAll('.ds-w').forEach(s => {
      const i = Number(s.dataset.i), on = i >= i0 && i <= i1;
      s.style.background = on ? 'var(--accent-soft, rgba(255,122,0,.18))' : '';
      s.style.fontWeight = i === i0 || i === i1 ? '700' : '';
    });
    document.getElementById('dsSpan').textContent = `${i1 - i0 + 1} mots gardés`;
  };
  paint();
  body.querySelectorAll('#dsEdge .seg-opt').forEach(b => b.onclick = () => {
    edge = b.dataset.e; body.querySelectorAll('#dsEdge .seg-opt').forEach(x => x.classList.toggle('active', x === b));
  });
  body.querySelectorAll('.ds-w').forEach(s => s.onclick = () => {
    const i = Number(s.dataset.i);
    if (edge === 'debut') i0 = Math.min(i, i1 - 5); else i1 = Math.max(i, i0 + 5);
    paint();
  });
  const choice = () => Number((body.querySelector('input[name="dsPass"]:checked') || {}).value || 0);
  body.querySelectorAll('input[name="dsPass"]').forEach(r => r.onchange = () => dsCall(`/api/adaptations/${p.project_id}/discours/passage`, 'PUT',
    { index: choice(), orateur: document.getElementById('dsOrateur').value }));
  const v = document.getElementById('dsVideo');
  if (v && c.debut !== undefined) v.addEventListener('loadedmetadata', () => { v.currentTime = c.debut; }, { once: true });
  const save = () => api(`/api/adaptations/${p.project_id}/discours/passage`, { method: 'PUT',
    body: JSON.stringify({ index: choice(), i0, i1, orateur: document.getElementById('dsOrateur').value }) });
  document.getElementById('dsSave').onclick = async () => {
    try { await save(); adProject = null; loadAdProject(); toast('Passage enregistré', 'success'); } catch (e){ log(e.message, 'error'); }
  };
  document.getElementById('dsMore').onclick = async ev => {
    ev.currentTarget.disabled = true;
    await dsCall(`/api/adaptations/${p.project_id}/discours/passages/plus`, 'POST');
  };
  document.getElementById('dsOk').onclick = async () => {
    try { await save(); } catch (e){ log(e.message, 'error'); return; }
    dsCall(`/api/adaptations/${p.project_id}/discours/passage/approve`, 'POST');
  };
}

// ---------------------------------------------------------------- the cut-aways

const DS_PX_S = 90;                       // the timeline: pixels per second
const dsPage = {};                        // the page of Pixabay propositions shown per moment (« Autres »)

function dsPlanKind(m){
  const c = m.clip || {};
  return c.a_la_main ? 'main' : c.stock ? 'ambiance' : 'youtube';
}

function dsRemap(t, parts){               // the passage's time -> the cut Short's (adaptation/discours.remap)
  let out = 0;
  for (const [a, b] of parts){
    if (t < a) return out;
    if (t <= b) return out + t - a;
    out += b - a;
  }
  return out;
}

function dsFrise(d, pid){
  const f = d.frise;
  if (!f) return '';
  const w = Math.ceil(f.total * DS_PX_S) + 40, x = t => Math.round(t * DS_PX_S);
  const speaker = (f.orateur || []).map(o => `<div class="ds-spk" data-src="${o.source}" style="left:${x(o.debut)}px;width:${Math.max(4, x(o.fin - o.debut))}px;
      background-image:url('/api/adaptations/${pid}/discours/frame?t=${o.source}')" title="L'orateur ${fmtSec(o.debut)} → ${fmtSec(o.fin)}"></div>`).join('');
  const ticks = Array.from({ length: Math.floor(f.total) + 1 }, (_, s) =>
    `<span class="ds-tick" style="left:${x(s)}px">${s % 5 ? '' : fmtSec(s)}</span>`).join('');
  const blocks = f.plans.map(b => {
    const m = d.moments[b.index] || {};
    const pic = ((m.propositions || []).find(c => c.stock === (m.clip || {}).stock) || {}).image;
    return `<div class="ds-blk ds-${dsPlanKind(m)}" draggable="true" data-i="${b.index}" style="left:${x(b.debut)}px;width:${Math.max(18, x(b.fin - b.debut))}px${pic ? `;background-image:url('${esc(pic)}')` : ''}"
      title="${esc(m.scene || '')} — glisse-le sur un autre mot"><b>${b.index + 1}</b></div>`;
  }).join('');
  const off = f.retires.map(r => `<div class="ds-off" draggable="true" data-i="${r.index}" style="left:${x(r.temps)}px" title="retiré : ${esc((d.moments[r.index] || {}).scene || '')}">${r.index + 1}</div>`).join('');
  const words = f.mots.map(([t, s], k) => `<span class="ds-w" data-w="${k}" style="left:${x(s)}px">${esc(t)}</span>`).join('');
  return `<article class="chcard"><div class="chcard-head"><div class="who"><div class="name">Timeline</div>
      <div class="meta" style="margin-left:0">La vidéo de ${fmtSec(f.total)} telle qu'elle sera montée (pauses resserrées) : l'orateur en gris, les plans de coupe par-dessus.
        Glisse un plan sur un mot pour le déplacer ; clique un mot pour l'écouter.
        <span class="ds-key ds-spk-key">orateur</span> <span class="ds-key ds-youtube">vidéo YouTube</span> <span class="ds-key ds-ambiance">ambiance Pixabay</span> <span class="ds-key ds-main">à toi</span></div></div></div>
    <div class="chcard-body">
      ${d.passage_url ? `<div class="ds-player"><video id="dsPlayer" src="${d.passage_url}" controls playsinline preload="metadata"></video>
        <div class="tiny" id="dsNow">Le passage d'origine, tel qu'il a été dit (avant de resserrer les pauses). Le curseur rouge suit la lecture.</div></div>` : ''}
      <div class="ds-frise"><div class="ds-track" style="width:${w}px">
        <div class="ds-zone" style="left:0;width:${x(f.accroche)}px" title="L'orateur d'abord : aucun plan avant ${f.accroche} s"></div>
        <div class="ds-rise" style="left:${x(f.montee)}px" title="La musique monte ici"></div>
        <div class="ds-row ds-ticks">${ticks}</div>
        <div class="ds-row ds-speaker">${speaker}</div>
        <div class="ds-row ds-plans"><span class="ds-lbl">plans</span>${blocks}${off}</div>
        <div class="ds-row ds-words">${words}</div>
        <div class="ds-head" id="dsHead" style="left:0"></div>
      </div></div>
    </div></article>`;
}

function dsBindFrise(body, d){
  const f = d.frise, v = document.getElementById('dsPlayer');
  if (!f || !v) return;
  const head = document.getElementById('dsHead'), now = document.getElementById('dsNow'), frise = body.querySelector('.ds-frise');
  v.ontimeupdate = () => {
    const t = dsRemap(v.currentTime, f.parts);
    head.style.left = Math.round(t * DS_PX_S) + 'px';
    const b = f.plans.find(p => p.debut <= t && t < p.fin), m = b ? d.moments[b.index] : null;
    now.textContent = `${fmtSec(t)} dans le Short · ${m ? `plan ${b.index + 1} : ${m.scene || ''}` : "l'orateur à l'écran"}`;
    const x = t * DS_PX_S;
    if (x < frise.scrollLeft || x > frise.scrollLeft + frise.clientWidth - 40) frise.scrollLeft = Math.max(0, x - 80);
  };
  const seek = s => { v.currentTime = Number(s); v.play().catch(() => {}); };
  body.querySelectorAll('.ds-w').forEach(el => el.onclick = () => seek(f.mots[el.dataset.w][2]));
  body.querySelectorAll('.ds-spk').forEach(el => el.onclick = () => seek(el.dataset.src));
}

function dsStockHtml(m){
  const all = m.propositions || [], page = dsPage[m.index] || 0, cur = (m.clip || {}).stock;
  const shown = all.slice(page * 4, page * 4 + 4);
  return `<div class="ds-stock">
    <div class="ad-row"><input class="f ds-q" value="${esc(m.ambiance || '')}" placeholder="ce qu'on doit voir (en anglais)" style="flex:1">
      <button class="btn secondary small ds-search">Chercher sur Pixabay</button></div>
    ${all.length ? `<div class="ds-props">${shown.map(c => `
      <figure class="ds-prop ${c.stock === cur ? 'on' : ''}" data-s="${esc(c.stock)}" title="${esc(c.tags)}">
        <video src="${esc(c.apercu)}" poster="${esc(c.image)}" muted loop playsinline preload="none"></video>
        <figcaption>${c.stock === cur ? '✓ choisi' : c.pris != null && c.pris !== m.index ? `déjà au plan ${c.pris + 1}` : 'prendre'}</figcaption></figure>`).join('')}</div>
      ${all.length > 4 ? `<button class="btn secondary small ds-more">Autres ↻ (${page + 1}/${Math.ceil(all.length / 4)})</button>` : ''}` : ''}
  </div>`;
}

function dsPlans(body, p){
  const d = p.discours;
  const kept = d.moments.filter(m => m.action === 'garder').length;
  const nw = d.frise ? d.frise.mots.length : 0;
  body.innerHTML = `<div class="tiny">${kept}/${d.moments.length} plan(s) gardé(s). Chaque plan passe par-dessus l'orateur pendant que sa voix continue.
      ${d.films ? '' : ' Pas d\'extraits de films, séries ou clips (une des chaînes ne les autorise pas) ; les cérémonies et émissions TV sont permises.'}</div>
    ${dsFrise(d, p.project_id)}
    <div class="grid-3">${d.moments.map(m => `
      <article class="chcard ds-m" data-i="${m.index}" id="dsM${m.index}">
        <div class="chcard-head"><div class="who"><div class="name">${m.index + 1}. ${fmtSec(m.temps)} · « ${esc(m.mot)} »</div>
          <div class="meta" style="margin-left:0">${esc(m.scene || '')}</div></div>
          ${m.action === 'garder' ? `<span class="pill ok">gardé</span>` : '<span class="pill warn">retiré</span>'}</div>
        <div class="chcard-body">
          ${m.clip_url ? `<video src="${m.clip_url}" controls playsinline muted loop preload="metadata" style="width:100%;background:#000"></video>
            <div class="tiny">${esc((m.clip || {}).titre || '')} · ${esc((m.clip || {}).niveau || '')}${(m.clip || {}).film ? ' · <span class="pill warn">film</span>' : ''}</div>`
            : `<div class="tiny">Aucune vidéo trouvée.${m.journal.length ? '<br>' + m.journal.map(esc).join('<br>') : ''}</div>`}
          <div class="ad-row" style="margin-top:6px">
            <select class="f ds-act" style="width:auto"><option value="garder" ${m.action === 'garder' ? 'selected' : ''} ${m.clip_url ? '' : 'disabled'}>garder</option>
              <option value="retirer" ${m.action === 'retirer' ? 'selected' : ''}>retirer</option></select>
            ${m.mot_i != null ? `<button class="btn secondary small ds-mv" data-d="-1" title="Un mot plus tôt" ${m.mot_i > 0 ? '' : 'disabled'}>◀</button>
              <button class="btn secondary small ds-mv" data-d="1" title="Un mot plus tard" ${m.mot_i < nw - 1 ? '' : 'disabled'}>▶</button>` : ''}</div>
          ${dsStockHtml(m)}
          <div class="ad-row"><input class="f ds-url" placeholder="Ton lien (YouTube…)" style="flex:1">
            <input class="f ds-t" type="number" min="0" step="0.5" value="0" title="La seconde où le plan commence" style="width:70px">
            <button class="btn secondary small ds-link">OK</button></div>
          <label class="tiny" style="cursor:pointer">ou dépose un fichier <input type="file" class="ds-file" accept="video/*" style="font-size:11px"></label>
        </div></article>`).join('')}</div>
    <div class="navbar"><span class="progress-text">${kept} plan(s) de coupe</span><span></span>
      <button class="btn primary" id="dsPlansOk" data-icon="film">Faire les vidéos →</button></div>`;
  hydrateIcons(body);
  dsBindFrise(body, d);
  const base = `/api/adaptations/${p.project_id}/discours/moments`;
  const move = (i, w) => dsCall(`${base}/${i}/move`, 'POST', { mot: Number(w) });
  body.querySelectorAll('.ds-blk, .ds-off').forEach(b => {
    b.ondragstart = ev => ev.dataTransfer.setData('text/plain', b.dataset.i);
    b.onclick = () => document.getElementById('dsM' + b.dataset.i)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  body.querySelectorAll('.ds-w').forEach(w => {
    w.ondragover = ev => { ev.preventDefault(); w.classList.add('drop'); };
    w.ondragleave = () => w.classList.remove('drop');
    w.ondrop = ev => { ev.preventDefault(); w.classList.remove('drop'); move(ev.dataTransfer.getData('text/plain'), w.dataset.w); };
  });
  body.querySelectorAll('.ds-m').forEach(card => {
    const i = Number(card.dataset.i), url = `${base}/${i}`, m = d.moments[i];
    card.querySelectorAll('.ds-mv').forEach(b => b.onclick = () => move(i, m.mot_i + Number(b.dataset.d)));
    card.querySelector('.ds-search').onclick = ev => {
      const q = card.querySelector('.ds-q').value.trim();
      if (!q) return;
      ev.currentTarget.disabled = true;
      dsPage[i] = 0;
      dsCall(`${url}/pixabay`, 'POST', { recherche: q });
    };
    const more = card.querySelector('.ds-more');
    if (more) more.onclick = () => {
      dsPage[i] = ((dsPage[i] || 0) + 1) % Math.ceil(m.propositions.length / 4);
      dsPlans(body, p);
      document.getElementById('dsM' + i)?.scrollIntoView({ block: 'nearest' });
    };
    card.querySelectorAll('.ds-prop').forEach(f => {
      const v = f.querySelector('video');
      f.onmouseenter = () => v.play().catch(() => {});
      f.onmouseleave = () => v.pause();
      f.onclick = () => {
        if (f.classList.contains('on')) return;
        f.querySelector('figcaption').textContent = '…';
        dsCall(`${url}/pixabay`, 'POST', { stock: f.dataset.s });
      };
    });
    card.querySelector('.ds-act').onchange = ev => dsCall(url, 'POST', { action: ev.target.value });
    card.querySelector('.ds-link').onclick = ev => {
      const link = card.querySelector('.ds-url').value.trim();
      if (!link) return;
      ev.currentTarget.disabled = true;
      dsCall(url, 'POST', { url: link, debut: Number(card.querySelector('.ds-t').value || 0) });
    };
    card.querySelector('.ds-file').onchange = async ev => {
      const f = ev.target.files[0];
      if (!f) return;
      const fd = new FormData();
      fd.append('file', f);
      try {
        const r = await fetch(`${url}/file`, { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || 'Envoi impossible');
        adProject = null; loadAdProject();
      } catch (e){ log(e.message, 'error'); }
    };
  });
  document.getElementById('dsPlansOk').onclick = () => dsCall(`/api/adaptations/${p.project_id}/discours/plans/approve`, 'POST');
}

// ---------------------------------------------------------------- the settings (preview panel, Réglages → Discours)

function dsSelect(name, value, choices){
  return `<select class="f ds-r" data-k="${name}" style="width:auto">${choices.map(v =>
    `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc((DS_LABELS[name] || {})[v] || v)}</option>`).join('')}</select>`;
}

function dsSettingsHtml(s, opts){
  const range = (k, lo, hi, unit) => `<span style="display:flex;gap:8px;align-items:center"><input type="range" class="ds-r" data-k="${k}" data-num="1"
      min="${lo}" max="${hi}" step="1" value="${s[k]}" style="flex:1"><span class="tiny ds-out">${s[k]}${unit}</span></span>`;
  const check = (k, label) => `<label class="switch" style="color:var(--text)"><input type="checkbox" class="ds-r" data-k="${k}" ${s[k] ? 'checked' : ''}> ${label}</label>`;
  return `<div class="grid-3" style="gap:10px">
    <div><label class="f">Cadre</label>${dsSelect('cadre', s.cadre, opts.cadres)}</div>
    <div><label class="f">Taille du cadre</label>${range('taille', 60, 100, ' %')}</div>
    <div><label class="f">Arrondi</label>${range('arrondi', 0, 120, ' px')}</div>
    <div><label class="f">Fond</label>${dsSelect('fond', s.fond, opts.fonds)}</div>
    <div><label class="f">Étalonnage</label>${dsSelect('etalonnage', s.etalonnage, opts.etalonnages)}</div>
    <div><label class="f">Sous-titres</label><select class="f ds-r" data-k="sous_titres" style="width:auto">${(opts.styles || []).map(st =>
      `<option value="${esc(st.id)}" ${st.id === s.sous_titres ? 'selected' : ''}>${st.number ? st.number + ' · ' : ''}${esc(st.label)}</option>`).join('')}</select></div>
    <div><label class="f">Pauses</label>${dsSelect('pauses', s.pauses, ['resserrees', 'gardees'])}</div>
    ${opts.densites ? `<div><label class="f">Plans de coupe</label>${dsSelect('densite', s.densite, opts.densites)}</div>` : ''}
    <div><label class="f">Musique sous la voix</label>${range('volume_db', 3, 30, ' dB')}</div>
    <div class="stack" style="gap:4px">${check('ombre', 'Ombre sous le cadre')}${check('grain', 'Grain')}
      ${check('drop_punchline', 'Montée de la musique sur la chute')}${check('identite', 'Nom de la chaîne dans le coin')}</div>
  </div>`;
}

function dsReadSettings(box){
  const out = {};
  box.querySelectorAll('.ds-r').forEach(el => {
    out[el.dataset.k] = el.type === 'checkbox' ? el.checked : el.dataset.num ? Number(el.value) : el.value;
  });
  return out;
}

function dsBindRanges(box){
  box.querySelectorAll('.ds-r[data-num]').forEach(el => el.addEventListener('input', () => {
    el.parentElement.querySelector('.ds-out').textContent = el.value + (el.dataset.k === 'taille' ? ' %' : el.dataset.k === 'volume_db' ? ' dB' : ' px');
  }));
}

async function dsStyles(lang){
  try { return (await api(`/api/captions/styles?space=discours&lang=${lang}`)).styles.filter(s => !s.native); }
  catch (e){ return []; }
}

// ---------------------------------------------------------------- each channel's video

async function dsPreviews(body, p){
  const d = p.discours;
  await dsLoadSongs();
  const langs = [...new Set(p.targets.map(t => t.language.split('-')[0]))];
  const styles = await dsStyles(langs.includes('ar') ? 'ar' : langs[0]);
  const base = (p.targets[0] || {}).reglages || d.defauts;
  const sonLabel = v => (DS_SONS.find(x => x[0] === v) || [v, v])[1];
  body.innerHTML = `<article class="chcard" id="dsSettings">
      <div class="chcard-head"><div class="who"><div class="name">Réglages de cette vidéo</div>
        <div class="meta" style="margin-left:0">Par-dessus le « style Discours » de chaque chaîne (Réglages → Discours). Refaire les vidéos ne rappelle pas l'IA.</div></div></div>
      <div class="chcard-body">${dsSettingsHtml(base, { cadres: d.cadres, fonds: d.fonds, etalonnages: d.etalonnages, styles })}
        ${dsSoundPicker(d.son, d.chanson)}
        ${d.musique ? `<div class="tiny" style="margin-top:6px">🎵 Musique intelligente : <b>${esc(d.musique.titre || d.musique.fichier)}</b> — ${esc(d.musique.pourquoi_chanson || '')}</div>` : ''}</div>
      <div class="chcard-foot"><button class="btn secondary small push" id="dsRedo" data-icon="refresh">Refaire les vidéos avec ces réglages</button></div></article>`
    + p.targets.map(t => {
      const ok = t.checks && t.checks.ok;
      return `<article class="chcard ad-prev-card" data-channel="${t.channel}">
        <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(t.channel)}"></span>
          ${esc(rpChannelName(t.channel))} · ${esc(t.language_label)}${t.duration ? ` · ${fmtSec(t.duration)}` : ''} · ${esc(sonLabel(t.son))}</div></div>
          ${t.video_id ? `<span class="pill ok">${icon('check', 11)} dans Publication</span>` : t.validated ? `<span class="pill ok">${icon('check', 11)} validé</span>` : '<span class="pill warn">à regarder</span>'}</div>
        <div class="chcard-body"><div class="ad-preview">
          <div>${t.preview_url ? `<video src="${t.preview_url}?v=${Date.now()}" controls playsinline></video>` : ''}</div>
          <div class="stack" style="gap:10px">
            ${ok ? `<div class="okbox">${icon('check', 12)} La vidéo a la durée de la parole.</div>`
                 : `<div class="errbox">${((t.checks || {}).problems || ['Pas encore contrôlée']).map(esc).join('<br>')}</div>`}
            <div class="tiny">Sous-titres : ${esc(((styles.find(s => s.id === t.reglages.sous_titres) || {}).label) || t.reglages.sous_titres)}
              · cadre ${esc(DS_LABELS.cadre[t.reglages.cadre] || t.reglages.cadre)} · fond ${esc(DS_LABELS.fond[t.reglages.fond] || t.reglages.fond)}</div>
            ${d.orateur ? `<div class="tiny">Crédit : ${esc(d.orateur)}</div>` : ''}
          </div>
        </div></div>
        <div class="chcard-foot">${t.video_id ? '' : `<button class="btn primary small push pv-validate" data-icon="check" ${ok && !t.validated ? '' : 'disabled'}>Valider cette vidéo</button>`}</div>
      </article>`;
    }).join('') + `<div class="navbar"><button class="btn secondary" id="dsBackPlans">← Revenir aux plans</button>
      <span class="progress-text">${p.targets.filter(t => t.validated).length}/${p.targets.length} vidéo(s) validée(s)</span>
      <button class="btn primary" id="dsRender" ${p.targets.some(t => t.validated && !t.video_id) ? '' : 'disabled'} data-icon="film">Envoyer les vidéos validées à Publication →</button></div>`;
  hydrateIcons(body);
  const box = document.getElementById('dsSettings');
  dsBindRanges(box);
  dsBindSound(box);
  document.getElementById('dsBackPlans').onclick = () => dsCall(`/api/adaptations/${p.project_id}/discours/plans/back`, 'POST');
  document.getElementById('dsRedo').onclick = () => {
    const mine = dsReadSettings(box), changed = {};
    Object.keys(mine).forEach(k => { if (mine[k] !== base[k] || k in (d.reglages || {})) changed[k] = mine[k]; });
    dsCall(`/api/adaptations/${p.project_id}/discours/reglages`, 'PATCH', { reglages: changed, ...dsSoundOf(box) });
  };
  body.querySelectorAll('.ad-prev-card').forEach(card => {
    const val = card.querySelector('.pv-validate');
    if (val) val.onclick = () => dsCall(`/api/adaptations/${p.project_id}/targets/${card.dataset.channel}/validate`, 'POST');
  });
  document.getElementById('dsRender').onclick = () => dsCall(`/api/adaptations/${p.project_id}/render`, 'POST');
}

// ---------------------------------------------------------------- Réglages → Discours

async function loadDiscoursSettings(){
  const grid = document.getElementById('dsChannels');
  grid.innerHTML = channels.map(ch => `<article class="chcard" data-channel="${ch.name}">${spinnerHtml('Chargement...')}</article>`).join('');
  await Promise.all(channels.map(async ch => {
    const card = grid.querySelector(`[data-channel="${ch.name}"]`);
    try { dsChannelCard(card, ch, await api(`/api/channels/${ch.name}/discours`)); }
    catch (e){ showLoadError(card, e, () => loadDiscoursSettings()); }
  }));
}

function dsChannelCard(card, ch, d){
  const s = d.reglages;
  card.innerHTML = `<div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div>
      <div class="meta" style="margin-left:0">${esc(d.language)}</div></div></div>
    <div class="chcard-body">
      <label class="switch" style="color:var(--text)"><input type="checkbox" class="ds-films" ${s.films ? 'checked' : ''}>
        <b>Extraits de films autorisés</b> <span class="tiny">plans de coupe tirés de films, séries ou clips (fiction) : risque de réclamation Content ID. Les cérémonies, émissions TV et archives sont toujours permises.</span></label>
      ${dsSettingsHtml(s, { cadres: d.cadres, fonds: d.fonds, etalonnages: d.etalonnages, densites: d.densites, styles: d.styles })}
    </div>
    <div class="chcard-foot"><span class="note push ds-saved"></span></div>`;
  dsBindRanges(card);
  let timer = null;
  const save = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const nd = await api(`/api/channels/${ch.name}/discours`, { method: 'PUT',
          body: JSON.stringify({ ...dsReadSettings(card), films: card.querySelector('.ds-films').checked }) });
        dsChannelCard(card, ch, nd);
        card.querySelector('.ds-saved').textContent = 'Enregistré ✓';
      } catch (e){ log(e.message, 'error'); }
    }, 500);
  };
  card.querySelectorAll('.ds-r, .ds-films').forEach(el => el.addEventListener('change', save));
}
