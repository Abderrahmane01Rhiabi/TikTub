// ---------- Montage pro : « Le plan du réalisateur » and « Je choisis mes plans » (2026-11-14) ----------
// The user: « l'IA n'a pas la capacité de bien regarder les plans comme un humain ». Screen 1, before the search: each
// sentence's idea of the AI director — kept with Entrée, or rewritten in the person's words. Screen 2, after the stock:
// the main shot of each sentence — the AI's best pre-ticked, only what's wrong changed (keys 1-8, Entrée, 0 « aucun ne
// va »); the AI editor makes the small cuts around it. Goal: under 3 minutes a video.

const CP_TYPES = { reel: 'Vraies images', idee: "Image d'idée", comparaison: 'Comparaison', projet: 'Rendu 3D / projet',
                   chiffre: 'Chiffre animé', carte: 'Carte animée', schema: 'Schéma animé' };
const CP_CHIPS = [['reel', 'Vraies images'], ['carte', 'Carte'], ['chiffre', 'Chiffre'], ['schema', 'Schéma'], ['idee', "Image d'idée"]];
let cpKeys = null;          // the keyboard of the screen shown (null: none)
let cpT0 = null;

document.addEventListener('keydown', e => {
  if (!cpKeys) return;
  const screen = document.getElementById('adaptationScreen');
  if (!screen || !screen.classList.contains('active') || !document.getElementById('cpRoot')) { cpKeys = null; return; }
  cpKeys(e);
});

function cpTimerStart(){
  if (!cpT0) cpT0 = Date.now();
}
function cpTimer(){
  if (!cpT0) return '0:00';
  const s = Math.floor((Date.now() - cpT0) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
setInterval(() => { const el = document.getElementById('cpTimer'); if (el) el.textContent = cpTimer(); }, 500);

function cpRtl(p){ return ['ar'].includes(((p.targets || [])[0] || {}).language) ? 'rtl' : 'auto'; }

// ---------- Screen 1 : the director's plan ----------

function renderAdRealisation(body, p){
  const plan = p.realisation || [];
  const texts = p.phrases || [];
  const st = { q: 0, mine: plan.map(() => null), kind: plan.map(() => null), recap: false };
  const dir = cpRtl(p);

  const draw = () => {
    const e = plan[st.q];
    if (st.recap) return drawRecap();
    const g = e.graphique;
    const gtxt = !g ? '' : e.type === 'chiffre' ? `compteur « ${esc(g.valeur || '')} ${esc(g.unite || '')} »${g.titre ? ' — ' + esc(g.titre) : ''}`
      : e.type === 'carte' ? `carte : ${esc(g.contenu || '')}${(g.reperes || []).length ? ' (repères : ' + g.reperes.map(r => esc(r.nom)).join(', ') + ')' : ''}`
      : esc(g.contenu || '');
    body.innerHTML = `<div id="cpRoot">
      <div class="cp-head"><b>Le plan du réalisateur</b><span class="tiny">étape 1 sur 2, avant la recherche</span>
        <div class="cp-prog"><i style="width:${100 * st.q / plan.length}%"></i></div><span class="cp-timer" id="cpTimer">${cpTimer()}</span></div>
      <div class="cp-phrase"><div class="n">Phrase ${st.q + 1} sur ${plan.length}</div><div class="t" dir="${dir}">${esc(texts[st.q] || '')}</div></div>
      <div class="cp-idea"><div class="tiny">Le réalisateur IA propose :</div><span class="ty">${esc(CP_TYPES[e.type] || e.type)}${g ? ' + vraies images' : ''}</span>
        <ol>${g ? `<li><b>Graphique</b> : ${gtxt}</li>` : ''}${(e.visuels || []).map(v => `<li>${(e.visuels.length > 1 && v.mot) ? `à partir de « <span dir="auto">${esc(v.mot)}</span> » : ` : ''}${esc(v.image)}</li>`).join('')}</ol>
        ${e.pourquoi ? `<div class="why">Pourquoi : ${esc(e.pourquoi)}</div>` : ''}${e.ta_version ? `<div class="why">(ta version d'avant : ${esc(e.ta_version)})</div>` : ''}</div>
      ${st.mine[st.q] ? `<div class="cp-yours"><b>Ta version</b> — l'IA la traduira quand tu lanceras la recherche :<div style="margin-top:3px">${st.kind[st.q] ? '[' + esc(CP_TYPES[st.kind[st.q]]) + '] ' : ''}${esc(st.mine[st.q])}</div></div>` : ''}
      <div class="cp-chips" id="cpChips">${CP_CHIPS.map(([k, l]) => `<button class="btn ghost small ${st.kind[st.q] === k ? 'on' : ''}" data-k="${k}">${l}</button>`).join('')}</div>
      <textarea class="f" id="cpText" rows="2" placeholder="Pas d'accord ? Écris ce que tu veux (ex. « une carte avec la route Tanger → Marrakech et 2h40 qui s'affiche »). Entrée pour valider, Échap pour revenir.">${esc(st.mine[st.q] || '')}</textarea>
      <div class="cp-bar"><button class="btn ghost" id="cpPrev" ${st.q ? '' : 'disabled'}>← Précédente</button>
        <button class="btn ghost" id="cpEdit">Écrire ma version <kbd>E</kbd></button>
        <button class="btn primary" id="cpNext">C'est bien, suivante <kbd>Entrée</kbd></button>
        <span class="cp-hint"><kbd>Entrée</kbd> garder · <kbd>E</kbd> écrire · <kbd>←</kbd> précédente</span></div>
      <div class="cp-bar"><button class="btn ghost small" id="cpBack">← Revenir au script</button></div></div>`;
    document.getElementById('cpPrev').onclick = () => { save(); if (st.q) { st.q--; draw(); } };
    document.getElementById('cpNext').onclick = next;
    document.getElementById('cpEdit').onclick = () => { cpTimerStart(); document.getElementById('cpText').focus(); };
    document.getElementById('cpBack').onclick = async () => {
      try { await api(`/api/adaptations/${p.project_id}/realisation/retour`, { method:'POST' }); adProject = null; loadAdProject(); }
      catch (err){ log(err.message, 'error'); }
    };
    document.querySelectorAll('#cpChips button').forEach(b => b.onclick = () => {
      st.kind[st.q] = st.kind[st.q] === b.dataset.k ? null : b.dataset.k;
      document.querySelectorAll('#cpChips button').forEach(x => x.classList.toggle('on', x.dataset.k === st.kind[st.q]));
      document.getElementById('cpText').focus();
    });
  };
  const save = () => {
    const el = document.getElementById('cpText');
    if (!el) return;
    const v = el.value.trim();
    st.mine[st.q] = v || null;
    if (!v) st.kind[st.q] = null;
  };
  const next = () => {
    cpTimerStart(); save();
    if (st.q < plan.length - 1) { st.q++; draw(); } else { st.recap = true; draw(); }
  };
  const drawRecap = () => {
    const n = st.mine.filter(Boolean).length;
    body.innerHTML = `<div id="cpRoot"><div class="cp-head"><b>Le plan, avant la recherche</b><div class="cp-prog"><i style="width:100%"></i></div>
        <span class="cp-timer" id="cpTimer">${cpTimer()}</span></div>
      ${plan.map((e, j) => `<div class="cp-row"><div class="t"><div dir="${dir}" style="font-weight:600">${esc(texts[j] || '')}</div>
        <div class="m">${st.mine[j] ? '<b>Ta version</b> : ' + (st.kind[j] ? '[' + esc(CP_TYPES[st.kind[j]]) + '] ' : '') + esc(st.mine[j])
          : esc(CP_TYPES[e.type] || e.type) + ' · ' + esc((e.visuels || []).map(v => v.image).join(' / '))}</div>
        ${st.mine[j] ? '<span class="cp-chg">changé par toi</span>' : '<span class="cp-keep">idée du réalisateur gardée</span>'}</div></div>`).join('')}
      <div class="cp-bar"><button class="btn ghost" id="cpRevoir">← Revoir</button>
        <button class="btn primary" id="cpGo">Lancer la recherche <kbd>Entrée</kbd></button>
        <span class="cp-hint">${n} phrase(s) changée(s)${n ? " — l'IA traduit tes versions (quelques secondes)" : ''}</span></div></div>`;
    document.getElementById('cpRevoir').onclick = () => { st.recap = false; st.q = plan.length - 1; draw(); };
    document.getElementById('cpGo').onclick = go;
  };
  const go = async () => {
    const b = document.getElementById('cpGo');
    if (b) { b.disabled = true; b.textContent = 'Traduction de tes versions…'; }
    const versions = {};
    plan.forEach((e, j) => { if (st.mine[j]) versions[e.phrase] = { texte: st.mine[j], type: st.kind[j] }; });
    try { await api(`/api/adaptations/${p.project_id}/realisation`, { method:'POST', body: JSON.stringify({ versions }) });
          cpKeys = null; adProject = null; loadAdProject(); }
    catch (err){ log(err.message, 'error'); if (b) { b.disabled = false; b.textContent = 'Lancer la recherche'; } }
  };
  cpKeys = e => {
    if (e.target.id === 'cpText') {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); next(); }
      else if (e.key === 'Escape') { e.target.value = ''; e.target.blur(); }
      return;
    }
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
    if (st.recap) { if (e.key === 'Enter') { e.preventDefault(); go(); } return; }
    if (e.key === 'Enter') { e.preventDefault(); next(); }
    else if (e.key === 'e' || e.key === 'E') { e.preventDefault(); cpTimerStart(); document.getElementById('cpText').focus(); }
    else if (e.key === 'ArrowLeft') { save(); if (st.q) { st.q--; draw(); } }
  };
  if (!plan.length) { body.innerHTML = '<div class="warnbox">Pas de plan du réalisateur : lance la recherche.</div>'; return; }
  draw();
}

// ---------- Screen 2 : the main shot of each sentence ----------

let cpShowStock = false;
let cpPicks = null;         // {sentence: shot} chosen so far (kept when going to the stock and back)

async function renderAdChoix(body, p){
  if (cpShowStock) return renderAdStockWithBack(body, p);
  let data;
  try { data = await api(`/api/adaptations/${p.project_id}/choix-plans`); }
  catch (err){ body.innerHTML = `<div class="warnbox">${esc(err.message)}</div>`; return; }
  const phrases = data.phrases || [];
  const shots = Object.fromEntries((p.stock || []).map(s => [s.id, s]));
  const st = { i: 0, pick: phrases.map(x => x.choix), recap: false };
  cpPicks = Object.fromEntries(phrases.map((x, j) => [x.n, st.pick[j]]));
  const dir = cpRtl(p);
  const clip = sid => `/api/adaptations/${p.project_id}/stock/${encodeURIComponent(sid)}/apercu`;

  const draw = () => {
    if (st.recap) return drawRecap();
    const ph = phrases[st.i];
    const used = {};
    st.pick.forEach((sid, j) => { if (j !== st.i && sid) used[sid] = j + 1; });
    body.innerHTML = `<div id="cpRoot">
      <div class="cp-head"><b>Je choisis mes plans</b><span class="tiny">étape 2 sur 2</span>
        <div class="cp-prog"><i style="width:${100 * st.i / phrases.length}%"></i></div><span class="cp-timer" id="cpTimer">${cpTimer()}</span></div>
      ${p.ajout_note ? `<div class="okbox" style="margin-bottom:8px">${esc(p.ajout_note)}</div>` : ''}
      <div class="cp-phrase"><div class="n">Phrase ${st.i + 1} sur ${phrases.length} — choisis son <b>image principale</b> ; le monteur IA fait les petites coupes autour</div>
        <div class="t" dir="${dir}">${esc(ph.texte)}</div>${ph.voulu ? `<div class="v">Le plan voulait : <b>${esc(ph.voulu)}</b></div>` : ''}</div>
      <div class="cp-grid" id="cpGrid">${ph.candidats.map((sid, k) => {
        const s = shots[sid] || {};
        return `<button class="cp-c ${st.pick[st.i] === sid ? 'sel' : ''}" data-sid="${esc(sid)}">
          <video poster="${esc(s.thumb_url || '')}" muted loop playsinline preload="none" data-src="${clip(sid)}"></video>
          ${k < 9 ? `<span class="k">${k + 1}</span>` : ''}${sid === ph.ia ? '<span class="ia">choix IA</span>' : ''}
          ${s.ajout_pour ? '<span class="add">ajouté</span>' : ''}
          <div class="d">${s.graphique ? '<b>Graphique animé</b> · ' : ''}${used[sid] ? `<b>déjà phrase ${used[sid]}</b> · ` : ''}${esc(s.desc || s.contenu || '')}</div></button>`;
      }).join('')}</div>
      <div class="cp-none" id="cpNone"><b>Aucun ne va pour cette phrase</b>
        <input class="f" id="cpLink" placeholder="Colle un lien YouTube / TikTok (l'IA trouve le bon moment)">
        <input class="f" id="cpDesc" placeholder="… ou décris ce que tu veux (ex. « le Boraq en gare de Marrakech »)">
        <div class="cp-bar" style="margin-top:4px"><button class="btn primary small" id="cpAddGo">Chercher pour cette phrase</button>
          <label class="btn ghost small" style="cursor:pointer">Envoyer une vidéo de mon PC<input type="file" id="cpFile" accept="video/*" hidden></label>
          <button class="btn ghost small" id="cpNoneX">Annuler</button><span class="tiny">1 à 4 min ; tes autres choix sont gardés</span></div></div>
      <div class="cp-bar"><button class="btn ghost" id="cpPrev" ${st.i ? '' : 'disabled'}>← Précédente</button>
        <button class="btn ghost" id="cpNoneB" style="color:#f59e0b">Aucun ne va <kbd>0</kbd></button>
        <button class="btn primary" id="cpNext">Phrase suivante <kbd>Entrée</kbd></button>
        <span class="cp-hint"><kbd>1</kbd>–<kbd>8</kbd> choisir · <kbd>Entrée</kbd> suivante · <kbd>←</kbd> précédente · <kbd>0</kbd> aucun ne va</span></div>
      <div class="cp-bar"><button class="btn ghost small" id="cpStock">Voir tout le stock (retirer des plans)</button></div></div>`;
    hydrateIcons(body);
    document.querySelectorAll('#cpGrid .cp-c').forEach(el => {
      const v = el.querySelector('video');
      const play = () => { if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); };
      el.onclick = () => pick(el.dataset.sid);
      el.onmouseenter = play;
      el.onmouseleave = () => { if (!el.classList.contains('sel')) v.pause(); };
      if (el.classList.contains('sel')) play();
    });
    document.getElementById('cpPrev').onclick = () => { if (st.i) { st.i--; draw(); } };
    document.getElementById('cpNext').onclick = next;
    document.getElementById('cpNoneB').onclick = openNone;
    document.getElementById('cpNoneX').onclick = () => document.getElementById('cpNone').classList.remove('on');
    document.getElementById('cpAddGo').onclick = () => add();
    document.getElementById('cpFile').onchange = ev => { if (ev.target.files[0]) add(ev.target.files[0]); };
    document.getElementById('cpStock').onclick = async () => {
      try { const np = await api(`/api/adaptations/${p.project_id}/choix-plans/enregistrer`, { method:'POST', body: JSON.stringify({ choix: choix() }) });
            adProject = np; p = np; } catch (err){ /* the stock opens anyway */ }
      cpShowStock = true; renderAdChoix(body, p);
    };
  };
  const pick = sid => { cpTimerStart(); st.pick[st.i] = sid; cpPicks[phrases[st.i].n] = sid; draw(); };
  const next = () => { cpTimerStart(); if (st.i < phrases.length - 1) { st.i++; draw(); } else { st.recap = true; draw(); } };
  const openNone = () => { cpTimerStart(); document.getElementById('cpNone').classList.add('on'); document.getElementById('cpLink').focus(); };
  const choix = () => Object.fromEntries(phrases.map((x, j) => [x.n, st.pick[j]]).filter(([, v]) => v));
  const add = async file => {
    const n = phrases[st.i].n;
    try {
      if (file) {
        const fd = new FormData(); fd.append('file', file); fd.append('choix', JSON.stringify(choix()));
        const r = await fetch(`/api/adaptations/${p.project_id}/choix-plans/${n}/fichier`, { method:'POST', body: fd });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Envoi impossible');
      } else {
        const url = document.getElementById('cpLink').value.trim(), description = document.getElementById('cpDesc').value.trim();
        if (!url && !description) return toast('Colle un lien ou décris ce que tu veux.', 'error');
        await api(`/api/adaptations/${p.project_id}/choix-plans/${n}/ajout`, { method:'POST', body: JSON.stringify({ url, description, choix: choix() }) });
      }
      cpKeys = null; adProject = null; loadAdProject();
    } catch (err){ log(err.message, 'error'); }
  };
  const drawRecap = () => {
    const changed = phrases.filter((x, j) => st.pick[j] !== x.ia).length;
    body.innerHTML = `<div id="cpRoot"><div class="cp-head"><b>Récapitulatif</b><div class="cp-prog"><i style="width:100%"></i></div>
        <span class="cp-timer" id="cpTimer">${cpTimer()}</span></div>
      ${phrases.map((x, j) => { const s = shots[st.pick[j]] || {};
        return `<div class="cp-row"><img src="${esc(s.thumb_url || '')}" alt=""><div class="t"><div dir="${dir}" style="font-weight:600">${esc(x.texte)}</div>
          <div class="m">${esc(s.desc || s.contenu || '')}</div>${st.pick[j] !== x.ia ? '<span class="cp-chg">changé par toi</span>' : '<span class="cp-keep">choix de l\'IA gardé</span>'}</div></div>`; }).join('')}
      <div class="cp-bar"><button class="btn ghost" id="cpRevoir">← Revoir</button>
        <button class="btn primary" id="cpGo" data-icon="film">Monter la vidéo <kbd>Entrée</kbd></button>
        <span class="cp-hint">${changed} phrase(s) changée(s) · ${cpTimer()}</span></div></div>`;
    hydrateIcons(body);
    document.getElementById('cpRevoir').onclick = () => { st.recap = false; st.i = phrases.length - 1; draw(); };
    document.getElementById('cpGo').onclick = go;
  };
  const go = async () => {
    const b = document.getElementById('cpGo');
    if (b) b.disabled = true;
    try { await api(`/api/adaptations/${p.project_id}/choix-plans`, { method:'POST', body: JSON.stringify({ choix: choix() }) });
          cpKeys = null; cpT0 = null; adProject = null; loadAdProject(); }
    catch (err){ log(err.message, 'error'); if (b) b.disabled = false; }
  };
  cpKeys = e => {
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
      if (e.key === 'Enter' && e.target.id !== 'cpFile') { e.preventDefault(); add(); }
      if (e.key === 'Escape') document.getElementById('cpNone').classList.remove('on');
      return;
    }
    if (st.recap) { if (e.key === 'Enter') { e.preventDefault(); go(); } return; }
    const ph = phrases[st.i];
    if (e.key >= '1' && e.key <= '9' && ph.candidats[+e.key - 1]) { e.preventDefault(); pick(ph.candidats[+e.key - 1]); }
    else if (e.key === 'Enter') { e.preventDefault(); next(); }
    else if (e.key === 'ArrowLeft') { if (st.i) { st.i--; draw(); } }
    else if (e.key === '0') { e.preventDefault(); openNone(); }
  };
  if (!phrases.length) { body.innerHTML = '<div class="warnbox">Aucune phrase.</div>'; return; }
  draw();
}

function renderAdStockWithBack(body, p){
  cpKeys = null;
  renderAdStock(body, p, true);         // no « Monter la vidéo » there: the montage starts from the recap, with the choices
}
