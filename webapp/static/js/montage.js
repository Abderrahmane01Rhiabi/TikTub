// ---------- Montage pro : the timeline of a version (its montage document, adaptation/montage_doc.py) ----------
// Six tracks under the preview — images, voice, banners, captions, music, sound effects — a red head following
// the video. Click an element: the video goes there and the panel under the tracks changes it; drag a sound, a
// cut or a music zone; drop a shot of the stock on a plan. Nothing is sent until « Refaire l'aperçu »: the server
// checks the montage, keeps the one before (« Annuler ») and renders only what changed (the sound alone: seconds).

const MT_PX_S = 42;                        // pixels per second
const mtState = {};                        // channel -> {data, doc, orig, sel, pid, target}

const MT_ROWS = [['images', 'Images'], ['voix', 'Voix'], ['bandeau', 'Bandeau'], ['sous', 'Sous-titres'],
                 ['musique', 'Musique'], ['effets', 'Effets']];
const MT_CADRES = { noir: ['#111111', '#FFFFFF', 'Noir'], rouge: ['#D62828', '#FFFFFF', 'Rouge actu'],
                    blanc: ['#FFFFFF', '#111111', 'Blanc'], bleu: ['#6D8DFD', '#FFFFFF', 'Bleu'] };
const MT_SOUND_KEYS = ['musique', 'effets'];

async function mtLoad(p, box){
  const ch = box.dataset.channel;
  try {
    const data = await api(`/api/adaptations/${p.project_id}/targets/${ch}/montage`);
    if (!data || !data.doc){ box.innerHTML = ''; return; }
    mtState[ch] = { data, doc: mtCopy(data.doc), orig: mtCopy(data.doc), sel: null, pid: p.project_id,
                    target: p.targets.find(t => t.channel === ch) || {}, avant: false, voix: {} };
    mtDraw(box);
  } catch (e){
    box.innerHTML = `<div class="errbox">Timeline : ${esc(e.message)}</div>`;
  }
}

function mtCopy(x){ return JSON.parse(JSON.stringify(x)); }
function mtX(t){ return Math.round(t * MT_PX_S); }
function mtR(t){ return Math.round(t * 100) / 100; }

function mtStarts(data){ return data.mots.map(w => w[1]); }
function mtSnap(data, t){ return mtStarts(data).reduce((b, s) => Math.abs(s - t) < Math.abs(b - t) ? s : b, t); }

// ---------------- what changed (the counter, and whether the picture must be made again)

function mtChanges(ch){
  const { doc, orig, voix } = mtState[ch], out = [];
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  if (Object.keys(voix).length) out.push('voix');
  if (!same(doc.plans, orig.plans)) out.push('images');
  if (!same(doc.bandeaux, orig.bandeaux) || doc.bandeau_cadre !== orig.bandeau_cadre) out.push('bandeaux');
  if (!same(doc.sous_titres, orig.sous_titres)) out.push('sous-titres');
  if (!same(doc.musique, orig.musique)) out.push('musique');
  if (!same(doc.effets, orig.effets)) out.push('effets');
  return out;
}

function mtSoundOnly(changes){ return changes.length && changes.every(c => MT_SOUND_KEYS.includes(c)); }

// ---------------- the tracks

function mtBlock(kind, i, a, b, inner, extra = '', title = '', handle = false){
  return `<div role="button" tabindex="0" class="mt-blk mt-${kind}" data-kind="${kind}" data-i="${i}" data-t="${a}"
    style="left:${mtX(a)}px;width:${Math.max(6, mtX(b - a) - 2)}px;${extra}" title="${esc(title)}">${inner}${
    handle ? `<span class="mt-cut" data-cut="${i}" title="Glisse pour déplacer la coupe (elle se cale sur un mot)"></span>` : ''}</div>`;
}

function mtCaptionGroups(data, doc){
  const fixes = (doc.sous_titres || {}).mots || {}, out = [];
  data.phrases.forEach(ph => {
    for (let k = 0; k < ph.mots.length; k += 3){
      const idx = ph.mots.slice(k, k + 3);
      const nextIdx = ph.mots[k + 3];
      const a = data.mots[idx[0]][1];
      const b = nextIdx != null ? data.mots[nextIdx][1] : data.mots[idx[idx.length - 1]][2] + 0.12;
      out.push({ idx, a, b, text: idx.map(w => fixes[String(w)] || data.mots[w][0]).join(' ') });
    }
  });
  return out;
}

function mtTracks(ch){
  const { data, doc } = mtState[ch];
  const total = data.total, w = mtX(total) + 30;
  const stockById = Object.fromEntries(data.stock.map(s => [s.id, s]));
  const ticks = Array.from({ length: Math.floor(total) + 1 }, (_, s) =>
    `<span class="mt-tick" style="left:${mtX(s)}px">${s % 5 ? '' : fmtSec(s)}</span>`).join('');
  const images = doc.plans.map((e, i) => {
    const s = stockById[e.plan] || {};
    const framed = (e.zoom || 1) !== 1 || e.centre != null;
    return mtBlock('images', i, e.debut, e.fin, `<b>${i + 1}</b>${framed ? ' ⌖' : ''}`,
      s.thumb_url ? `background-image:url('${s.thumb_url}')` : '', `Plan ${i + 1} : ${s.desc || e.plan}`, i > 0);
  }).join('');
  const edits = mtState[ch].voix;
  const voix = data.phrases.map((ph, i) => {
    const e = edits[i];
    const label = e ? (data.manieres_dispo[e.maniere] || 'Normale') : ph.maniere;
    return mtBlock('voix', i, ph.debut, ph.fin, `<b>${i + 1}</b> ${esc(label)}${e ? ' ✎' : ''}`, e ? 'border-color:#f5c56d' : '', e ? e.texte : ph.texte);
  }).join('');
  const bans = data.phrases.map((ph, i) => {
    const b = doc.bandeaux[i] || {}, end = i + 1 < data.phrases.length ? data.phrases[i + 1].debut : ph.fin + 0.25;
    const text = b.cache ? '— aucun —' : (b.texte != null ? b.texte : ph.bandeau);
    const c = b.cadre === 'style' ? null : MT_CADRES[b.cadre || doc.bandeau_cadre];
    return mtBlock('bandeau', i, ph.debut, end, esc(text), (b.cache ? 'opacity:.45;' : '') + (c ? `background:${c[0]};color:${c[1]}` : ''), text);
  }).join('');
  const caps = mtCaptionGroups(data, doc).map((g, i) => mtBlock('sous', i, g.a, g.b, esc(g.text), '', g.text)).join('');
  const env = data.enveloppe || [], step = env.length ? total / env.length : 1;
  const m = doc.musique || {};
  const level = t => {
    let v = (m.volume || 100) / 100;
    (m.zones || []).forEach(z => { if (t >= z.debut && t <= z.fin) v *= z.volume / 100; });
    return v;
  };
  const sameSong = m.fichier === (mtState[ch].orig.musique || {}).fichier && m.debut === (mtState[ch].orig.musique || {}).debut;
  const bars = m.fichier ? (sameSong ? env : env.map(() => 0.5)).map((v, k) => `<span class="mt-bar" style="left:${mtX(k * step)}px;width:${Math.max(1, mtX(step) - 1)}px;
      height:${Math.max(4, Math.min(100, v * 100 * level(k * step)))}%"></span>`).join('') : '<span class="tiny mt-none">sans musique</span>';
  const zones = (m.zones || []).map((z, i) => mtBlock('zone', i, z.debut, z.fin, `${z.volume} %`, '', `Volume ${z.volume} % — glisse pour la déplacer`)).join('');
  const fx = (doc.effets || []).map((e, i) => `<div role="button" tabindex="0" class="mt-fx" data-kind="effet" data-i="${i}" data-t="${e.start}"
      style="left:${mtX(e.start)}px" title="${esc(e.kind)} — glisse pour le déplacer"><span class="mt-dia"></span>${esc(e.kind)}</div>`).join('');
  return `<div class="mt-wrap"><div class="mt-lbls"><span></span>${MT_ROWS.map(([k, l]) => `<span class="mt-lbl-${k}">${l}</span>`).join('')}</div>
    <div class="mt-scroll"><div class="mt-track" style="width:${w}px">
      <div class="mt-row mt-ticks">${ticks}</div>
      <div class="mt-row mt-r-images">${images}</div>
      <div class="mt-row mt-r-voix">${voix}</div>
      <div class="mt-row mt-r-bandeau">${bans}</div>
      <div class="mt-row mt-r-sous">${caps}</div>
      <div class="mt-row mt-r-musique" data-kind="musique" data-i="0" data-t="0">${bars}${zones}</div>
      <div class="mt-row mt-r-effets">${fx}</div>
      <div class="mt-head" style="left:0"></div>
    </div></div></div>`;
}

// ---------------- the panel: what the selected element can become

function mtStockGrid(ch, current){
  const { data } = mtState[ch];
  return `<div class="mt-stock">${data.stock.map(s => `<button type="button" class="mt-shot ${s.id === current ? 'on' : ''}" draggable="true"
      data-shot="${s.id}" title="${esc(s.desc || '')}" style="background-image:url('${s.thumb_url}')"><span>${s.duree} s</span></button>`).join('')}</div>`;
}

function mtPanel(ch){
  const { data, doc, sel } = mtState[ch];
  if (!sel) return `<div class="tiny">Clique un élément de la timeline pour le modifier. Tu peux aussi <b>glisser</b> un losange d'effet,
    la coupe entre deux plans, ou une zone de musique, et <b>déposer</b> un plan du stock sur la piste Images.</div>
    <div class="mt-p-row"><button type="button" class="btn ghost small mt-add-fx">+ Ajouter un son au curseur</button>
      <button type="button" class="btn ghost small mt-add-zone">+ Baisser ou monter la musique au curseur</button>
      <button type="button" class="btn ghost small mt-pick-music">Musique de la vidéo…</button></div>`;
  const i = Number(sel.i);
  if (sel.kind === 'images'){
    const e = doc.plans[i], s = data.stock.find(x => x.id === e.plan) || {};
    const c = e.centre == null ? 'auto' : e.centre;
    return `<div class="mt-p-title"><b>Plan ${i + 1}</b> · ${fmtSec(e.debut)} → ${fmtSec(e.fin)} · ${esc(s.desc || e.plan)}</div>
      <label class="f">Remplacer par un plan de ton stock (clique, ou glisse-le sur la piste Images)</label>${mtStockGrid(ch, e.plan)}
      <div class="mt-p-grid">
        <div><label class="f">Cadrage : zoom ×<span class="mt-zoom-out">${(e.zoom || 1).toFixed(2)}</span></label>
          <input type="range" class="mt-zoom" min="1" max="1.6" step="0.05" value="${e.zoom || 1}"></div>
        <div><label class="f">Cadrage : centrer sur</label><div class="mt-p-row">${[['auto', 'Le sujet (IA)'], [0.2, 'Gauche'], [0.5, 'Centre'], [0.8, 'Droite']]
          .map(([v, l]) => `<button type="button" class="chipbtn mt-centre ${String(v) === String(c) ? 'on' : ''}" data-v="${v}">${l}</button>`).join('')}</div></div>
      </div>
      <div class="mt-p-row"><button type="button" class="btn ghost small mt-split">Couper ce plan en deux</button>
        <button type="button" class="btn ghost small mt-del-plan" ${doc.plans.length < 2 ? 'disabled' : ''}>Supprimer ce plan (le voisin s'allonge)</button></div>`;
  }
  if (sel.kind === 'voix'){
    const ph = data.phrases[i], e = mtState[ch].voix[i] || { texte: ph.texte, maniere: ph.maniere_id };
    return `<div class="mt-p-title"><b>Phrase ${i + 1}</b> · ${fmtSec(ph.debut)} → ${fmtSec(ph.fin)}</div>
      <label class="f">Texte dit par la voix</label>
      <textarea class="f mt-v-txt" rows="2" maxlength="400" ${data.rtl ? 'dir="rtl"' : ''}>${esc(e.texte)}</textarea>
      <label class="f">Manière de dire (celles permises pour la famille de la chaîne)</label>
      <div class="mt-p-row">${Object.entries(data.manieres_dispo).map(([k, l]) =>
        `<button type="button" class="chipbtn mt-v-man ${k === e.maniere ? 'on' : ''}" data-v="${k}">${esc(l)}</button>`).join('')}</div>
      <div class="warnbox">La voix est refaite en entier chez ElevenLabs (quelques centimes, ≈ 1 min) ; les coupes, les sons et les zones
        de musique se recalent tout seuls sur la nouvelle voix. Un nouveau texte n'est pas revérifié contre les faits : relis-le.</div>
      ${mtState[ch].voix[i] ? '<div class="mt-p-row"><button type="button" class="btn ghost small mt-v-undo">Garder la phrase d\'origine</button></div>' : ''}`;
  }
  if (sel.kind === 'bandeau'){
    const b = doc.bandeaux[i] || {}, ph = data.phrases[i];
    return `<div class="mt-p-title"><b>Bandeau de la phrase ${i + 1}</b></div>
      <label class="f">Texte</label><input class="f mt-ban-txt" value="${esc(b.texte != null ? b.texte : ph.bandeau)}" maxlength="60" ${b.cache ? 'disabled' : ''}>
      <label class="switch"><input type="checkbox" class="mt-ban-hide" ${b.cache ? 'checked' : ''}> Pas de bandeau sur cette phrase</label>
      <label class="f">Cadre de ce bandeau</label>
      <div class="mt-p-row"><button type="button" class="chipbtn mt-cadre ${(b.cadre || doc.bandeau_cadre || 'style') === 'style' ? 'on' : ''}" data-v="">Celui du style</button>
        ${Object.entries(MT_CADRES).map(([k, [bg, fg, l]]) => `<button type="button" class="chipbtn mt-cadre ${(b.cadre || doc.bandeau_cadre) === k ? 'on' : ''}" data-v="${k}">
          <span class="mt-sw" style="background:${bg};color:${fg}">${l}</span></button>`).join('')}</div>
      <div class="mt-p-row"><button type="button" class="btn ghost small mt-cadre-all">Appliquer ce cadre à tous les bandeaux</button></div>`;
  }
  if (sel.kind === 'sous'){
    const g = mtCaptionGroups(data, doc)[i], st = doc.sous_titres || {}, own = (st.groupes || {})[String(g.idx[0])] || {};
    const look = { style: 'style' in own ? own.style : st.style, position: own.position || st.position, taille: own.taille || st.taille || 100 };
    return `<div class="mt-p-title"><b>Sous-titres</b> · ${fmtSec(g.a)} → ${fmtSec(g.b)}</div>
      <label class="f">Corriger les mots (le moment de chacun reste celui de la voix)</label>
      <div class="mt-p-row">${g.idx.map(w => `<input class="f mt-word" data-w="${w}" value="${esc((st.mots || {})[String(w)] || data.mots[w][0])}" style="width:auto;flex:1;min-width:90px">`).join('')}</div>
      <div class="mt-p-grid">
        <div><label class="f">Style de ce groupe</label><select class="f mt-cap-style">
          <option value="">Nos sous-titres (mot dit en couleur)</option>
          ${data.styles_sous_titres.map(x => `<option value="${x.id}" ${look.style === x.id ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></div>
        <div><label class="f">Position</label><select class="f mt-cap-pos">${data.positions.map(x => `<option value="${x}" ${look.position === x ? 'selected' : ''}>${x}</option>`).join('')}</select></div>
        <div><label class="f">Taille : <span class="mt-cap-size-out">${look.taille}</span> %</label>
          <input type="range" class="mt-cap-size" min="60" max="160" step="5" value="${look.taille}"></div>
      </div>
      <div class="mt-p-row"><button type="button" class="btn ghost small mt-cap-all">Appliquer ce style, cette position et cette taille à tous les sous-titres</button>
        ${Object.keys(own).length ? '<button type="button" class="btn ghost small mt-cap-reset">Comme le reste de la vidéo</button>' : ''}</div>`;
  }
  if (sel.kind === 'musique' || sel.kind === 'zone'){
    const m = doc.musique || {}, z = sel.kind === 'zone' ? m.zones[i] : null;
    return `<div class="mt-p-title"><b>Musique</b>${z ? ` · zone ${i + 1}` : ''}</div>
      ${z ? `<div class="mt-p-grid">
        <div><label class="f">Volume de cette zone : <span class="mt-zvol-out">${z.volume}</span> %</label>
          <input type="range" class="mt-zvol" min="0" max="200" step="5" value="${z.volume}"></div>
        <div><label class="f">De (s)</label><input type="number" class="f mt-zfrom" step="0.1" min="0" value="${z.debut}"></div>
        <div><label class="f">À (s)</label><input type="number" class="f mt-zto" step="0.1" min="0" value="${z.fin}"></div></div>
        <div class="mt-p-row"><button type="button" class="btn ghost small mt-zdel">Supprimer cette zone</button></div>` : ''}
      <div class="mt-p-grid">
        <div><label class="f">Chanson</label><select class="f mt-song"><option value="">— sans musique —</option>
          ${data.musiques.map(s => `<option value="${esc(s.fichier)}" ${s.fichier === m.fichier ? 'selected' : ''}>${s.permise ? '' : '· '}${esc(s.titre)}</option>`).join('')}</select></div>
        <div><label class="f">Elle commence à (s, dans la chanson)</label><input type="number" class="f mt-song-start" step="0.5" min="0" value="${m.debut || 0}"></div>
        <div><label class="f">Volume général : <span class="mt-mvol-out">${m.volume || 100}</span> %</label>
          <input type="range" class="mt-mvol" min="0" max="200" step="5" value="${m.volume || 100}"></div>
        <div><label class="f">Fondu à la fin : <span class="mt-fade-out">${m.fondu}</span> s</label>
          <input type="range" class="mt-fade" min="0" max="5" step="0.2" value="${m.fondu}"></div></div>
      <div class="mt-p-row"><button type="button" class="btn ghost small mt-add-zone">+ Baisser / monter une partie au curseur</button></div>`;
  }
  if (sel.kind === 'effet'){
    const e = doc.effets[i];
    const files = Object.entries(data.sons).flatMap(([k, xs]) => xs.map(x => ({ ...x, kind: k })));
    return `<div class="mt-p-title"><b>Effet</b> · ${esc(e.kind)} · ${esc(e.pourquoi || '')}</div>
      <div class="mt-p-grid">
        <div><label class="f">Son</label><select class="f mt-fx-file">${files.map(f => `<option value="${esc(f.file)}" data-kind="${f.kind}" ${f.file === e.file ? 'selected' : ''}>${esc(f.kind)} — ${esc(f.nom)}</option>`).join('')}</select></div>
        <div><label class="f">Moment (s)</label><input type="number" class="f mt-fx-at" step="0.05" min="0" value="${e.start}"></div>
        <div><label class="f">Volume : <span class="mt-fx-gain-out">${Math.round(e.gain * 100)}</span> %</label>
          <input type="range" class="mt-fx-gain" min="0" max="1" step="0.02" value="${e.gain}"></div></div>
      <div class="mt-p-row"><button type="button" class="btn ghost small mt-fx-play">▶ Écouter le son</button>
        <button type="button" class="btn ghost small mt-fx-del">Supprimer ce son</button></div>`;
  }
  return '';
}

// ---------------- drawing

function mtDraw(box){
  const ch = box.dataset.channel, st = mtState[ch];
  const changes = mtChanges(ch), t = st.target, versions = st.data.versions;
  const scroll = box.querySelector('.mt-scroll'), keepX = scroll ? scroll.scrollLeft : null;
  box.innerHTML = `<div class="mt-head-row"><b>Timeline</b>
      ${changes.length ? `<span class="pill warn">${changes.length} changement(s) à appliquer : ${changes.join(', ')}</span>` : '<span class="tiny">Clique, glisse, dépose : rien n\'est envoyé avant « Refaire l\'aperçu ».</span>'}
      <span style="flex:1"></span>
      ${t.preview_before_url ? `<button type="button" class="btn ghost small mt-avant">${st.avant ? 'Voir l\'après' : 'Voir l\'avant'}</button>` : ''}
      ${versions ? '<button type="button" class="btn ghost small mt-undo" title="Revenir au montage d\'avant le dernier rendu">Annuler le dernier rendu</button>' : ''}
      ${changes.length ? '<button type="button" class="btn ghost small mt-reset">Oublier mes changements</button>' : ''}
      <button type="button" class="btn primary small mt-go" ${changes.length ? '' : 'disabled'}>Refaire l'aperçu${changes.length ? (changes.includes('voix') ? ' (≈ 1 min, voix ElevenLabs)' : mtSoundOnly(changes) ? ' (≈ 5 s)' : ' (≈ 30 s)') : ''}</button></div>
    ${mtTracks(ch)}
    <div class="mt-panel">${mtPanel(ch)}</div>`;
  if (st.sel) box.querySelectorAll(`.mt-track [data-kind="${st.sel.kind}"][data-i="${st.sel.i}"]`).forEach(el => el.classList.add('on'));
  if (keepX != null) box.querySelector('.mt-scroll').scrollLeft = keepX;
  mtBind(box);
}

function mtVideo(box){ const card = box.closest('.ad-prev-card'); return card && card.querySelector('video'); }

function mtChanged(box){ mtDraw(box); }

function mtBind(box){
  const ch = box.dataset.channel, st = mtState[ch], { data, doc } = st;
  const v = mtVideo(box);
  const head = box.querySelector('.mt-head'), scroll = box.querySelector('.mt-scroll');
  const now = () => (v ? v.currentTime : 0);
  if (v){
    const follow = () => {
      const xpx = v.currentTime * MT_PX_S;
      head.style.left = Math.round(xpx) + 'px';
      if (!v.paused && (xpx < scroll.scrollLeft || xpx > scroll.scrollLeft + scroll.clientWidth - 40)) scroll.scrollLeft = Math.max(0, xpx - 80);
    };
    v.ontimeupdate = v.onseeked = follow;
    follow();
  }
  const select = (kind, i, t) => {
    st.sel = { kind, i: String(i) };
    mtDraw(box);
    if (v && t != null){ v.currentTime = Number(t) + 0.02; }
  };
  // a click selects; a drag (more than 4 px) moves a sound, a cut or a zone
  box.querySelectorAll('.mt-track [data-kind]').forEach(el => {
    el.onpointerdown = ev => {
      if (ev.button !== 0) return;
      const cut = ev.target.closest('.mt-cut');
      const kind = el.dataset.kind, i = Number(el.dataset.i);
      const movable = cut || kind === 'effet' || kind === 'zone';
      const x0 = ev.clientX;
      let moved = false;
      if (movable) el.setPointerCapture(ev.pointerId);
      el.onpointermove = mv => {
        if (!movable) return;
        const dt = (mv.clientX - x0) / MT_PX_S;
        if (Math.abs(mv.clientX - x0) > 4) moved = true;
        if (!moved) return;
        if (cut) el.style.left = `${mtX(doc.plans[i].debut + dt)}px`;
        else el.style.transform = `translateX(${mv.clientX - x0 - (kind === 'effet' ? 6 : 0)}px)`;
      };
      el.onpointerup = up => {
        el.onpointermove = el.onpointerup = null;
        const dt = (up.clientX - x0) / MT_PX_S;
        if (!moved){
          if (kind === 'musique' && ev.target.closest('.mt-zone')) return;
          return select(kind, el.dataset.i, kind === 'musique' ? null : el.dataset.t);
        }
        if (cut){
          const prev = doc.plans[i - 1], cur = doc.plans[i];
          const t = mtSnap(data, Math.min(cur.fin - 1, Math.max(prev.debut + 1, cur.debut + dt)));
          prev.fin = cur.debut = mtR(t);
          st.sel = { kind: 'images', i: String(i) };
        } else if (kind === 'effet'){
          doc.effets[i].start = mtR(Math.min(data.total - 0.3, Math.max(0, doc.effets[i].start + dt)));
          st.sel = { kind: 'effet', i: String(i) };
        } else if (kind === 'zone'){
          const z = doc.musique.zones[i], len = z.fin - z.debut;
          z.debut = mtR(Math.min(data.total - len, Math.max(0, z.debut + dt)));
          z.fin = mtR(z.debut + len);
          st.sel = { kind: 'zone', i: String(i) };
        }
        mtChanged(box);
      };
    };
  });
  box.querySelector('.mt-ticks').onclick = ev => {
    if (!v) return;
    const r = ev.currentTarget.getBoundingClientRect();
    v.currentTime = Math.max(0, (ev.clientX - r.left) / MT_PX_S);
  };
  // a shot of the stock dropped on a plan replaces it
  box.querySelectorAll('.mt-shot').forEach(b => b.ondragstart = ev => ev.dataTransfer.setData('text/plain', b.dataset.shot));
  box.querySelectorAll('.mt-images').forEach(el => {
    el.ondragover = ev => { ev.preventDefault(); el.classList.add('drop'); };
    el.ondragleave = () => el.classList.remove('drop');
    el.ondrop = ev => {
      ev.preventDefault();
      const id = ev.dataTransfer.getData('text/plain');
      if (!id) return;
      doc.plans[Number(el.dataset.i)].plan = id;
      st.sel = { kind: 'images', i: el.dataset.i };
      mtChanged(box);
    };
  });
  mtBindPanel(box, now);
  mtBindHead(box);
  mtDemo(box);
}

function mtBindPanel(box, now){
  const ch = box.dataset.channel, st = mtState[ch], { data, doc } = st;
  const i = st.sel ? Number(st.sel.i) : null;
  const on = (sel, ev, fn) => box.querySelectorAll(sel).forEach(el => el[ev] = () => fn(el));
  // the voice of a sentence
  const vEdit = () => {
    const ph = data.phrases[i];
    return st.voix[i] = st.voix[i] || { texte: ph.texte, maniere: ph.maniere_id };
  };
  const vClean = () => {
    const ph = data.phrases[i], e = st.voix[i];
    if (e && e.texte.trim() === ph.texte && e.maniere === ph.maniere_id) delete st.voix[i];
  };
  on('.mt-v-txt', 'onchange', el => { vEdit().texte = el.value.replace(/\s+/g, ' ').trim(); vClean(); mtChanged(box); });
  on('.mt-v-man', 'onclick', b => { vEdit().maniere = b.dataset.v; vClean(); mtChanged(box); });
  on('.mt-v-undo', 'onclick', () => { delete st.voix[i]; mtChanged(box); });
  // the shot
  on('.mt-panel .mt-shot', 'onclick', b => { doc.plans[i].plan = b.dataset.shot; mtChanged(box); });
  on('.mt-zoom', 'oninput', el => { box.querySelector('.mt-zoom-out').textContent = Number(el.value).toFixed(2); });
  on('.mt-zoom', 'onchange', el => { doc.plans[i].zoom = Number(el.value); mtChanged(box); });
  on('.mt-centre', 'onclick', b => { doc.plans[i].centre = b.dataset.v === 'auto' ? null : Number(b.dataset.v); mtChanged(box); });
  on('.mt-split', 'onclick', () => {
    const e = doc.plans[i], mid = mtSnap(data, (e.debut + e.fin) / 2);
    if (mid - e.debut < 1 || e.fin - mid < 1) return toast('Ce plan est trop court pour être coupé (au moins 1 s de chaque côté).', 'error');
    const used = new Set(doc.plans.map(x => x.plan));
    const other = (data.stock.find(s => !used.has(s.id)) || data.stock.find(s => s.id !== e.plan) || {}).id || e.plan;
    doc.plans.splice(i + 1, 0, { phrase: e.phrase, plan: other, debut: mtR(mid), fin: e.fin, zoom: 1, centre: null });
    e.fin = mtR(mid);
    st.sel = { kind: 'images', i: String(i + 1) };
    mtChanged(box);
  });
  on('.mt-del-plan', 'onclick', () => {
    const gone = doc.plans.splice(i, 1)[0];
    if (i > 0) doc.plans[i - 1].fin = gone.fin; else { doc.plans[0].debut = 0; }
    st.sel = null;
    mtChanged(box);
  });
  // the banners
  on('.mt-ban-txt', 'onchange', el => { doc.bandeaux[i].texte = el.value.trim() || null; mtChanged(box); });
  on('.mt-ban-hide', 'onchange', el => { doc.bandeaux[i].cache = el.checked; mtChanged(box); });
  on('.mt-cadre', 'onclick', b => {
    const want = b.dataset.v || 'style', video = doc.bandeau_cadre || 'style';
    if (want === video) delete doc.bandeaux[i].cadre; else doc.bandeaux[i].cadre = want;   // only this banner
    mtChanged(box);
  });
  on('.mt-cadre-all', 'onclick', () => {
    const c = doc.bandeaux[i].cadre || doc.bandeau_cadre;
    doc.bandeau_cadre = c && c !== 'style' ? c : null;
    doc.bandeaux.forEach(x => delete x.cadre);
    mtChanged(box);
  });
  // the captions
  on('.mt-word', 'onchange', el => {
    const w = el.dataset.w, mots = doc.sous_titres.mots = doc.sous_titres.mots || {};
    if (!el.value.trim() || el.value.trim() === data.mots[w][0]) delete mots[w]; else mots[w] = el.value.trim();
    mtChanged(box);
  });
  // a group of captions: its own look (sous_titres.groupes, keyed by its first word), or the video's for all
  const capGroup = () => {
    const st = doc.sous_titres, key = String(mtCaptionGroups(data, doc)[i].idx[0]);
    st.groupes = st.groupes || {};
    return { st, key, own: st.groupes[key] = st.groupes[key] || {} };
  };
  const capTidy = ({ st, key, own }) => {
    if ('style' in own && (own.style || null) === (st.style || null)) delete own.style;
    if (own.position === st.position) delete own.position;
    if (own.taille === (st.taille || 100)) delete own.taille;
    if (!Object.keys(own).length) delete st.groupes[key];
    if (!Object.keys(st.groupes).length) delete st.groupes;
  };
  on('.mt-cap-style', 'onchange', el => { const g = capGroup(); g.own.style = el.value || null; capTidy(g); mtChanged(box); });
  on('.mt-cap-pos', 'onchange', el => { const g = capGroup(); g.own.position = el.value; capTidy(g); mtChanged(box); });
  on('.mt-cap-size', 'oninput', el => { box.querySelector('.mt-cap-size-out').textContent = el.value; });
  on('.mt-cap-size', 'onchange', el => { const g = capGroup(); g.own.taille = Number(el.value); capTidy(g); mtChanged(box); });
  on('.mt-cap-all', 'onclick', () => {
    const g = capGroup(), look = { style: 'style' in g.own ? g.own.style : g.st.style, position: g.own.position || g.st.position,
                                   taille: g.own.taille || g.st.taille || 100 };
    Object.assign(g.st, look);
    delete g.st.groupes;
    mtChanged(box);
  });
  on('.mt-cap-reset', 'onclick', () => { const g = capGroup(); delete g.st.groupes[g.key]; capTidy({ ...g, own: {} }); mtChanged(box); });
  // the music
  const m = doc.musique;
  on('.mt-song', 'onchange', el => { m.fichier = el.value || null; mtChanged(box); });
  on('.mt-song-start', 'onchange', el => { m.debut = Math.max(0, Number(el.value) || 0); mtChanged(box); });
  on('.mt-mvol', 'oninput', el => { box.querySelector('.mt-mvol-out').textContent = el.value; });
  on('.mt-mvol', 'onchange', el => { m.volume = Number(el.value); mtChanged(box); });
  on('.mt-fade', 'oninput', el => { box.querySelector('.mt-fade-out').textContent = el.value; });
  on('.mt-fade', 'onchange', el => { m.fondu = Number(el.value); mtChanged(box); });
  on('.mt-zvol', 'oninput', el => { box.querySelector('.mt-zvol-out').textContent = el.value; });
  on('.mt-zvol', 'onchange', el => { m.zones[i].volume = Number(el.value); mtChanged(box); });
  on('.mt-zfrom', 'onchange', el => { m.zones[i].debut = mtR(Math.max(0, Number(el.value))); mtChanged(box); });
  on('.mt-zto', 'onchange', el => { m.zones[i].fin = mtR(Math.min(data.total, Number(el.value))); mtChanged(box); });
  on('.mt-zdel', 'onclick', () => { m.zones.splice(i, 1); st.sel = { kind: 'musique', i: '0' }; mtChanged(box); });
  on('.mt-add-zone', 'onclick', () => {
    const a = mtR(Math.max(0, now() - 1)), b = mtR(Math.min(data.total, a + 3));
    m.zones = (m.zones || []).concat([{ debut: a, fin: b, volume: 50 }]);
    st.sel = { kind: 'zone', i: String(m.zones.length - 1) };
    mtChanged(box);
  });
  on('.mt-pick-music', 'onclick', () => { st.sel = { kind: 'musique', i: '0' }; mtChanged(box); });
  // the sound effects
  on('.mt-fx-file', 'onchange', el => {
    const o = el.selectedOptions[0];
    Object.assign(doc.effets[i], { file: el.value, kind: o.dataset.kind, gain: (data.gains || {})[o.dataset.kind] || doc.effets[i].gain });
    mtChanged(box);
  });
  on('.mt-fx-at', 'onchange', el => { doc.effets[i].start = mtR(Math.max(0, Math.min(data.total - 0.3, Number(el.value)))); mtChanged(box); });
  on('.mt-fx-gain', 'oninput', el => { box.querySelector('.mt-fx-gain-out').textContent = Math.round(el.value * 100); });
  on('.mt-fx-gain', 'onchange', el => { doc.effets[i].gain = Number(el.value); mtChanged(box); });
  on('.mt-fx-del', 'onclick', () => { doc.effets.splice(i, 1); st.sel = null; mtChanged(box); });
  on('.mt-fx-play', 'onclick', () => {
    const e = doc.effets[i];
    new Audio(`/api/sfx/${encodeURIComponent(e.file.split(/[\\/]/).pop())}/audio`).play().catch(() => {});
  });
  on('.mt-add-fx', 'onclick', () => {
    const kind = data.sons.whoosh ? 'whoosh' : Object.keys(data.sons)[0];
    if (!kind) return toast('Aucun son allumé dans Réglages → Bibliothèques → Effets sonores.', 'error');
    doc.effets.push({ kind, file: data.sons[kind][0].file, start: mtR(Math.min(data.total - 0.3, now())),
                      gain: (data.gains || {})[kind] || 0.3, pourquoi: 'ajouté par toi', par: 'toi' });
    doc.effets.sort((a, b) => a.start - b.start);
    st.sel = { kind: 'effet', i: String(doc.effets.findIndex(e => e.pourquoi === 'ajouté par toi' && e.start === mtR(Math.min(data.total - 0.3, now())))) };
    mtChanged(box);
  });
}

function mtBindHead(box){
  const ch = box.dataset.channel, st = mtState[ch];
  const go = box.querySelector('.mt-go'), v = mtVideo(box);
  if (go) go.onclick = async () => {
    go.disabled = true;
    try {
      const voix = Object.entries(st.voix).map(([i, e]) => ({ i: Number(i), texte: e.texte, maniere: e.maniere }));
      await api(`/api/adaptations/${st.pid}/targets/${ch}/montage`, { method:'POST', body: JSON.stringify({ doc: st.doc, voix }) });
      toast('Aperçu en cours de rendu…', 'success');
      adProject = null; loadAdProject();
    } catch (e){ toast(e.message, 'error'); go.disabled = false; }
  };
  const reset = box.querySelector('.mt-reset');
  if (reset) reset.onclick = () => { st.doc = mtCopy(st.orig); st.voix = {}; st.sel = null; mtDraw(box); };
  const undo = box.querySelector('.mt-undo');
  if (undo) undo.onclick = async () => {
    if (mtChanges(ch).length && !confirm('Tes changements pas encore appliqués seront oubliés. Annuler le dernier rendu ?')) return;
    try { await api(`/api/adaptations/${st.pid}/targets/${ch}/montage/undo`, { method:'POST' }); adProject = null; loadAdProject(); }
    catch (e){ toast(e.message, 'error'); }
  };
  const avant = box.querySelector('.mt-avant');
  if (avant && v) avant.onclick = () => {
    const t = v.currentTime, playing = !v.paused;
    st.avant = !st.avant;
    v.src = `${st.avant ? st.target.preview_before_url : st.target.preview_url}?v=${Date.now()}`;
    v.addEventListener('loadedmetadata', () => { v.currentTime = t; if (playing) v.play().catch(() => {}); }, { once: true });
    v.closest('.ad-preview').classList.toggle('mt-is-avant', st.avant);
    avant.textContent = st.avant ? "Voir l'après" : "Voir l'avant";
    mtDemo(box);
  };
}

// after a render: the player jumps where the change is
function mtJump(card, t){
  const v = card.querySelector('video');
  if (!v || t == null) return;
  const go = () => { v.currentTime = Math.max(0, t - 0.5); };
  if (v.readyState >= 1) go(); else v.addEventListener('loadedmetadata', go, { once: true });
}

// ---------------- the instant demo: the changes not yet rendered, drawn over the playing video
// Exact for the banners, close for the captions and the zoom; a replaced shot shows as its still picture; added or
// moved sounds are played at their moment. A music zone or a new voice is heard only after « Refaire l'aperçu ».

function mtGroupsLook(data, doc){
  const st = doc.sous_titres || {}, own = st.groupes || {};
  return mtCaptionGroups(data, doc).map(g => {
    const x = own[String(g.idx[0])] || {};
    return { ...g, style: 'style' in x ? x.style : st.style, position: x.position || st.position || 'bas',
             taille: x.taille || st.taille || 100 };
  });
}

function mtBannerLook(data, doc, k){
  const b = doc.bandeaux[k] || {}, ph = data.phrases[k];
  const cadre = b.cadre === 'style' ? null : (b.cadre || doc.bandeau_cadre);
  return { text: b.cache ? '' : (b.texte != null ? b.texte : ph.bandeau), cadre: cadre || null };
}

function mtDemo(box){
  const ch = box.dataset.channel, st = mtState[ch], v = mtVideo(box);
  if (!v) return;
  const holder = v.parentElement;
  holder.style.position = 'relative';
  holder.style.overflow = 'hidden';
  let layer = holder.querySelector('.mt-demo');
  if (!layer){ layer = document.createElement('div'); layer.className = 'mt-demo'; holder.appendChild(layer); }
  if (st.demoStop) st.demoStop();
  const { data } = st, look = data.look || {};
  const changes = mtChanges(ch).filter(c => c !== 'voix');
  if (!changes.length || st.avant || !look.w){ layer.innerHTML = ''; v.style.transform = ''; return; }
  const doc = st.doc, orig = st.orig;
  const groupsNew = mtGroupsLook(data, doc), groupsOld = mtGroupsLook(data, orig);
  const heard = new Set((orig.effets || []).map(e => `${e.file}@${e.start}`));
  const extra = (doc.effets || []).filter(e => !heard.has(`${e.file}@${e.start}`));
  const up = s => (look.majuscules ? String(s).toUpperCase() : String(s));
  const planAt = (plans, t) => plans.find(e => t >= e.debut && t < e.fin) || plans[plans.length - 1];
  let last = v.currentTime, raf = null;

  const draw = () => {
    const t = v.currentTime;
    const s = v.clientWidth / look.w, top = v.offsetTop, left = v.offsetLeft;
    const parts = [`<span class="mt-demo-tag" title="Un aperçu rapide de tes changements : clique « Refaire l'aperçu » pour la vraie vidéo">DÉMO</span>`];
    // the shot: replaced (its still picture) or zoomed
    const pn = planAt(doc.plans, t), po = planAt(orig.plans, t);
    const swapped = pn && po && pn.plan !== po.plan;
    const zoom = (pn && pn.zoom || 1) / (po && !swapped ? (po.zoom || 1) : 1);
    if (swapped){
      const shot = data.stock.find(x => x.id === pn.plan) || {};
      parts.push(`<img class="mt-demo-shot" src="${shot.thumb_url || ''}" style="transform:scale(${pn.zoom || 1});transform-origin:${(pn.centre == null ? 0.5 : pn.centre) * 100}% 50%">`);
      v.style.transform = '';
    } else {
      v.style.transformOrigin = `${(pn && pn.centre != null ? pn.centre : 0.5) * 100}% 50%`;
      v.style.transform = Math.abs(zoom - 1) > 0.001 ? `scale(${zoom})` : '';
    }
    // the banner of the sentence being said
    let k = 0;
    data.phrases.forEach((ph, i) => { if (ph.debut <= t + 0.02) k = i; });
    const bn = mtBannerLook(data, doc, k), bo = mtBannerLook(data, orig, k);
    if (swapped || bn.text !== bo.text || bn.cadre !== bo.cadre){
      if (!swapped) parts.push(`<div class="mt-demo-mask" style="top:${look.bandeau_y * s - 14 * s}px;height:${150 * s}px"></div>`);
      if (bn.text){
        const c = bn.cadre ? look.cadres[bn.cadre] : [look.box, look.text];
        parts.push(`<div class="mt-demo-ban" style="top:${look.bandeau_y * s}px;font-size:${78 * s}px;padding:${10 * s}px ${18 * s}px;
          background:${c[0]};color:${c[1]}">${esc(up(bn.text))}</div>`);
      }
    }
    // the captions being said
    const gi = groupsNew.findIndex(g => t >= g.a && t < g.b);
    if (gi >= 0){
      const gn = groupsNew[gi], go = groupsOld[gi];
      const differs = gn.text !== go.text || gn.position !== go.position || gn.taille !== go.taille || (gn.style || '') !== (go.style || '');
      if (swapped || differs){
        if (!swapped && !go.style) parts.push(`<div class="mt-demo-mask" style="top:${(look.places[go.position] - 96 * go.taille / 100 * 1.35) * s}px;height:${96 * go.taille / 100 * 1.5 * s}px"></div>`);
        const said = gn.idx.filter(w => data.mots[w][1] <= t + 0.02).pop();
        const fixes = (doc.sous_titres || {}).mots || {};
        const words = gn.idx.map(w => `<span style="color:${w === said ? look.key : look.text}">${esc(up(fixes[String(w)] || data.mots[w][0]))}</span>`).join(' ');
        parts.push(`<div class="mt-demo-cap" style="bottom:${(look.h - look.places[gn.position]) * s}px;font-size:${96 * gn.taille / 100 * s}px">${words}${
          gn.style ? `<small class="mt-demo-note">style ${esc(gn.style)} après Refaire</small>` : ''}</div>`);
      }
    }
    layer.style.cssText = `left:${left}px;top:${top}px;width:${v.clientWidth}px;height:${v.clientHeight}px`;
    layer.innerHTML = parts.join('');
    // the sounds added or moved, heard at their moment while it plays
    if (!v.paused && t > last && t - last < 1){
      extra.forEach(e => {
        if (e.start > last && e.start <= t){
          const a = new Audio(`/api/sfx/${encodeURIComponent(e.file.split(/[\\/]/).pop())}/audio`);
          a.volume = Math.min(1, (e.gain || 0.3) * 2.5);
          a.play().catch(() => {});
        }
      });
    }
    last = t;
  };
  const loop = () => { draw(); raf = v.paused ? null : requestAnimationFrame(loop); };
  const onPlay = () => { if (!raf) raf = requestAnimationFrame(loop); };
  v.addEventListener('play', onPlay);
  v.addEventListener('seeked', draw);
  v.addEventListener('pause', draw);
  st.demoStop = () => {
    v.removeEventListener('play', onPlay); v.removeEventListener('seeked', draw); v.removeEventListener('pause', draw);
    if (raf) cancelAnimationFrame(raf);
    st.demoStop = null;
  };
  draw();
  if (!v.paused) onPlay();
}
