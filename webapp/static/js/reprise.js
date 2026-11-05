// ---------- Adaptation › Reprise : the friend's Short taken again (adaptation/reprise_pipeline.py) ----------
// The cleaning to check (original | clean side by side, each element « garder » / « cacher »), one script per
// language, then each channel's video with its voice, its voice model and the sound chosen.

const RP_SONS = [
  ['notre_musique', 'Notre musique', 'la musique de la chaîne'],
  ['sa_musique', 'Sa musique', 'celle de la vidéo d\'origine, sans sa voix — ⚠️ YouTube peut réclamer les droits si c\'est un son connu'],
  ['intelligente', 'Musique intelligente', 'une chanson de la liste commune, sa montée calée sur le moment fort (C\'est pour ça et لهذا السبب pour l\'instant ; les autres chaînes prennent leur musique)'],
  ['sans_musique', 'Sans musique', 'la voix seule'],
];
const RP_TYPES = { sous_titres: 'Sous-titres', numero: 'Numéro', autocollant: 'Dessin / autocollant', logo: 'Logo', pseudo: 'Pseudo / filigrane' };

function rpSoundPicker(son, volume){
  return `<label class="f" style="margin-top:6px">Le son</label>
    <div class="ad-row" style="flex-direction:column;align-items:flex-start;gap:4px">${RP_SONS.map(([v, l, d]) =>
      `<label class="switch" style="color:var(--text)"><input type="radio" name="rpSon" value="${v}" ${v === son ? 'checked' : ''}>
        <b>${l}</b> <span class="tiny">${esc(d)}</span></label>`).join('')}</div>
    <label class="tiny" style="display:flex;gap:8px;align-items:center;margin-top:4px">Volume de la musique
      <input type="range" class="rp-vol" min="6" max="30" step="1" value="${volume || 16}" style="width:160px">
      <span class="rp-vol-out">${volume || 16} dB sous la voix</span></label>`;
}

function rpBindSound(box){
  const range = box.querySelector('.rp-vol'), out = box.querySelector('.rp-vol-out');
  if (range) range.oninput = () => { out.textContent = `${range.value} dB sous la voix`; };
}
document.addEventListener('input', e => {            // the creation form's picker is drawn by adaptation.js
  if (e.target.classList && e.target.classList.contains('rp-vol')){
    const out = e.target.parentElement.querySelector('.rp-vol-out');
    if (out) out.textContent = `${e.target.value} dB sous la voix`;
  }
});

function rpSoundOf(box){
  return { son: (box.querySelector('input[name="rpSon"]:checked') || {}).value || 'notre_musique',
           volume_db: Number((box.querySelector('.rp-vol') || {}).value || 16) };
}

function rpChannelName(ch){ return (channels.find(c => c.name === ch) || {}).display_name || ch; }

function renderReprise(body, p){
  if (p.status === 'cleaning_review'){ rpCleaning(body, p); return true; }
  if (p.status === 'script_review'){ rpScript(body, p); return true; }
  if (p.status === 'preview_review'){ rpPreviews(body, p); return true; }
  return false;                                       // done, error…: the usual screens
}

async function rpPost(url, method, data){
  try { await api(url, { method, body: data ? JSON.stringify(data) : undefined }); adProject = null; loadAdProject(); }
  catch (e){ log(e.message, 'error'); }
}

// ---------------------------------------------------------------- the cleaning to check

function rpCleaning(body, p){
  const r = p.reprise, n = r.nettoyage || {};
  body.innerHTML = `<article class="chcard">
      <div class="chcard-head"><div class="who"><div class="name">Vérifie le nettoyage</div>
        <div class="meta" style="margin-left:0">À gauche la vidéo de ton ami, à droite la version propre : il ne doit rester ni ses textes, ni ses logos, ni ses autocollants.
          ${n.relues ? ` La relecture a repris ${n.relues} image(s).` : ''}</div></div></div>
      <div class="chcard-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div><div class="tiny">Original</div><video id="rpOrig" src="${r.original_url}" controls playsinline muted style="width:100%;max-height:60vh;background:#000"></video></div>
          <div><div class="tiny">Propre</div><video id="rpClean" src="${r.propre_url}?v=${Date.now()}" controls playsinline style="width:100%;max-height:60vh;background:#000"></video></div>
        </div>
        <div class="ad-row" style="margin-top:6px"><button class="btn ghost small" id="rpSync" data-icon="play">Lire les deux ensemble</button>
          <span class="tiny">${r.credit ? `Images de ${esc(r.credit)} (crédité dans la description)` : ''}</span></div>
        <label class="f" style="margin-top:10px">Ce que son créateur a ajouté</label>
        <div class="stack" style="gap:6px">${r.elements.map(e => `
          <div class="ad-row rp-el" data-i="${e.index}" style="justify-content:space-between">
            <span><b>${esc(RP_TYPES[e.type] || e.type)}</b> <span class="tiny">${esc(e.description || '')} · ${fmtSec(e.debut)}–${fmtSec(e.fin)}${e.raison ? ' · ' + esc(e.raison) : ''}</span></span>
            <select class="f rp-action" style="width:auto">
              <option value="cacher" ${e.action === 'cacher' ? 'selected' : ''}>cacher</option>
              <option value="garder" ${e.action === 'garder' ? 'selected' : ''}>garder</option></select></div>`).join('')}</div>
        <div class="tiny" style="margin-top:6px">« Garder » un dessin qui aide à comprendre l'image (une croix, une flèche, un cercle). Les textes, logos, pseudos et boutons sont à cacher.</div>
      </div>
      <div class="chcard-foot"><button class="btn secondary small" id="rpCleanAgain" data-icon="refresh" disabled>Nettoyer à nouveau</button>
        <button class="btn primary push" id="rpCleanOk" data-icon="check">C'est propre → écrire le script</button></div>
    </article>`;
  hydrateIcons(body);
  const o = document.getElementById('rpOrig'), c = document.getElementById('rpClean');
  document.getElementById('rpSync').onclick = () => { o.currentTime = c.currentTime = 0; o.play(); c.play(); };
  c.addEventListener('seeked', () => { if (Math.abs(o.currentTime - c.currentTime) > 0.3) o.currentTime = c.currentTime; });
  let changed = false;
  body.querySelectorAll('.rp-el').forEach(row => {
    row.querySelector('.rp-action').onchange = async ev => {
      try { await api(`/api/adaptations/${p.project_id}/reprise/elements/${row.dataset.i}`, { method: 'POST',
              body: JSON.stringify({ action: ev.target.value }) });
            changed = true; document.getElementById('rpCleanAgain').disabled = false;
            toast('Noté : clique « Nettoyer à nouveau » pour le voir', 'success'); }
      catch (e){ log(e.message, 'error'); }
    };
  });
  document.getElementById('rpCleanAgain').onclick = () => rpPost(`/api/adaptations/${p.project_id}/reprise/clean-again`, 'POST');
  document.getElementById('rpCleanOk').onclick = () => {
    if (changed && !confirm('Tu as changé des éléments sans nettoyer à nouveau : continuer avec la vidéo actuelle ?')) return;
    rpPost(`/api/adaptations/${p.project_id}/reprise/cleaning/approve`, 'POST');
  };
}

// ---------------------------------------------------------------- the script, per language

function rpScript(body, p){
  const sc = p.reprise.script;
  const role = x => x.role === 'accroche' ? 'Accroche' : x.role === 'chute' ? 'Fin' : x.numero ? `#${x.numero}` : 'Étape';
  const intro = sc.genre === 'top'
    ? `Un <b>top</b> : ${sc.reordonne ? 'les points ont été <b>réordonnés</b>' : 'l\'ordre est gardé'} — ${esc(sc.pourquoi || '')}`
    : `Une <b>histoire</b> : l'ordre est gardé, sans numéros — ${esc(sc.pourquoi || '')}`;
  body.innerHTML = `<div class="tiny">${intro}</div>` + p.targets.map(t => {
    const code = t.language.split('-')[0], yt = (sc.youtube || {})[code] || {};
    return `<article class="chcard rp-sc" data-channel="${t.channel}" data-code="${code}">
      <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(t.channel)}"></span>
        ${esc(rpChannelName(t.channel))} · ${esc(t.language_label)}</div></div>
        ${t.approved ? `<span class="pill ok">${icon('check', 11)} validé</span>` : '<span class="pill warn">à relire</span>'}</div>
      <div class="chcard-body" ${t.rtl ? 'dir="rtl"' : ''}>
        <label class="f">Titre YouTube</label><input class="f rp-yt-title" maxlength="100" value="${esc(yt.titre || '')}">
        <label class="f">Description</label><textarea class="f rp-yt-desc" rows="3">${esc(yt.description || '')}</textarea>
        <label class="f">Tags <span class="tiny">(séparés par des virgules)</span></label><input class="f rp-yt-tags" value="${esc((yt.tags || []).join(', '))}">
        <label class="f">Titre de la miniature <span class="tiny">(court)</span></label><input class="f rp-title" value="${esc((sc.titre || {})[code] || '')}">
        ${sc.parties.map((x, i) => `<label class="f" style="margin-top:6px">${role(x)} <span class="tiny">(plans ${x.plans.map(k => k + 1).join(', ')})</span></label>
          <textarea class="f rp-text" rows="2">${esc(x[code] || '')}</textarea>`).join('')}
      </div>
      <div class="chcard-foot"><button class="btn secondary small rp-save" data-icon="check">Enregistrer mes changements</button>
        <button class="btn primary small push rp-approve" data-icon="check" ${t.approved ? 'disabled' : ''}>Valider ce script</button></div>
    </article>`;
  }).join('') + `<div class="navbar"><span class="progress-text">${p.targets.filter(t => t.approved).length}/${p.targets.length} script(s) validé(s)</span><span></span>
      <button class="btn primary" id="rpVoices" ${p.targets.every(t => t.approved) ? '' : 'disabled'} data-icon="mic">Voix et vidéos →</button></div>`;
  hydrateIcons(body);
  body.querySelectorAll('.rp-sc').forEach(card => {
    const ch = card.dataset.channel;
    card.querySelector('.rp-save').onclick = () => rpPost(`/api/adaptations/${p.project_id}/targets/${ch}/reprise-script`, 'PUT',
      { texts: [...card.querySelectorAll('.rp-text')].map(x => x.value), title: card.querySelector('.rp-title').value,
        youtube: { titre: card.querySelector('.rp-yt-title').value, description: card.querySelector('.rp-yt-desc').value,
                   tags: card.querySelector('.rp-yt-tags').value.split(',').map(x => x.trim()).filter(Boolean) } });
    card.querySelector('.rp-approve').onclick = () => rpPost(`/api/adaptations/${p.project_id}/targets/${ch}/approve`, 'POST');
  });
  document.getElementById('rpVoices').onclick = () => rpPost(`/api/adaptations/${p.project_id}/voices`, 'POST');
}

// ---------------------------------------------------------------- the timeline (reprise_pipeline.frise)

const RP_PX_S = 40;                       // the timeline: pixels per second

function rpPartName(x){
  if (x.numero) return `#${x.numero}`;
  return x.role ? x.role.charAt(0).toUpperCase() + x.role.slice(1) : 'Partie';
}

function rpMusicSvg(m, total){
  const w = Math.ceil(total * RP_PX_S), h = 40, lv = m.niveau || [];
  if (!lv.length) return '';
  const y = db => (h - 2) * (1 - (Math.max(-70, Math.min(-10, db)) + 70) / 60) + 1;
  const pts = lv.map((db, i) => `${(i * m.pas * RP_PX_S).toFixed(1)},${y(db).toFixed(1)}`);
  return `<svg class="rp-wave" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polygon points="0,${h} ${pts.join(' ')} ${((lv.length - 1) * m.pas * RP_PX_S).toFixed(1)},${h}"/></svg>`;
}

function rpMusicSummary(m){
  if (!m) return 'Sans musique.';
  const bits = [m.entree > 0.05 ? `entre à ${fmtSec(m.entree)}` : 'là dès la 1re seconde'];
  if (m.montee != null) bits.push(`monte à ${fmtSec(m.montee)}`);
  if (m.coupe) bits.push(`coupée sur un temps fort à ${fmtSec(m.coupe)}, la salle (réverbération) la porte jusqu'à la fin`);
  return `🎵 ${esc(m.titre || '')}${m.debut_chanson != null ? ` (prise à ${fmtSec(m.debut_chanson)} de la chanson)` : ''} : ${bits.join(', ')}.`;
}

function rpFrise(f, pid){
  if (!f) return '';
  const w = Math.ceil(f.total * RP_PX_S) + 40, x = t => Math.round(t * RP_PX_S), m = f.musique;
  const ticks = Array.from({ length: Math.floor(f.total) + 1 }, (_, s) =>
    `<span class="ds-tick" style="left:${x(s)}px">${s % 5 ? '' : fmtSec(s)}</span>`).join('');
  const parts = f.parties.map((pa, k) => `<div class="rp-part rp-part-${k % 2}" data-t="${pa.debut}" style="left:${x(pa.debut)}px;width:${Math.max(4, x(pa.fin - pa.debut) - 2)}px"
      title="${esc(rpPartName(pa))} · ${fmtSec(pa.debut)} → ${fmtSec(pa.fin)} · images à ×${pa.vitesse}\n${esc(pa.texte)}"><b>${esc(rpPartName(pa))}</b> <span>${esc(pa.texte)}</span></div>`).join('');
  const imgs = f.images.map(im => `<div class="rp-img ${im.fige ? 'rp-fige' : ''}" data-t="${im.debut}" style="left:${x(im.debut)}px;width:${Math.max(3, x(im.fin - im.debut) - 1)}px;
      background-image:url('/api/adaptations/${pid}/reprise/frame?t=${im.source}')"
      title="${im.fige ? "Plus d'images pour cette partie : la dernière reste figée" : `Plan ${im.plan + 1} de la vidéo d'origine (${fmtSec(im.source)})`} · ${fmtSec(im.debut)} → ${fmtSec(im.fin)}"></div>`).join('');
  const marks = m ? [
    m.entree > 0.05 ? `<div class="rp-mark rp-in" style="left:${x(m.entree)}px" title="La musique entre"><span>entrée</span></div>` : '',
    m.montee != null ? `<div class="rp-mark rp-rise" style="left:${x(m.montee)}px" title="La montée de la chanson"><span>montée</span></div>` : '',
    m.coupe ? `<div class="rp-mark rp-cut" style="left:${x(m.coupe)}px" title="Coupée sur un temps fort, puis la réverbération"><span>fin + salle</span></div>` : '',
  ].join('') : '';
  return `<div class="rp-frise-box">
    <div class="tiny" style="margin-bottom:4px"><b>Timeline</b> — clique une partie ou une image pour la voir dans la vidéo. ${rpMusicSummary(m)}</div>
    <div class="rp-frise-wrap"><div class="rp-lbls"><span>voix</span><span>images</span><span>musique</span></div>
    <div class="ds-frise"><div class="rp-track" style="width:${w}px">
      <div class="ds-row ds-ticks">${ticks}</div>
      <div class="ds-row rp-row-voix">${parts}</div>
      <div class="ds-row rp-row-img">${imgs}</div>
      <div class="ds-row rp-row-mus">${m ? rpMusicSvg(m, f.total) : '<span class="tiny" style="padding:12px 8px;display:block">sans musique</span>'}</div>
      ${marks}
      <div class="ds-head rp-head" style="left:0"></div>
    </div></div></div></div>`;
}

function rpBindFrise(card){
  const v = card.querySelector('video'), head = card.querySelector('.rp-head'), frise = card.querySelector('.ds-frise');
  if (!v || !head) return;
  v.ontimeupdate = v.onseeked = () => {
    const xpx = v.currentTime * RP_PX_S;
    head.style.left = Math.round(xpx) + 'px';
    if (xpx < frise.scrollLeft || xpx > frise.scrollLeft + frise.clientWidth - 40) frise.scrollLeft = Math.max(0, xpx - 80);
  };
  card.querySelectorAll('.rp-part, .rp-img').forEach(el => el.onclick = () => {
    v.currentTime = Number(el.dataset.t) + 0.01; v.play().catch(() => {});
  });
}

// ---------------------------------------------------------------- each channel's video

async function rpPreviews(body, p){
  const r = p.reprise, voicesByLang = {};
  await Promise.all([...new Set(p.targets.map(t => t.language))].map(async lg => {
    voicesByLang[lg] = (await api(`/api/voices?language=${lg}`)).voices;
  }));
  const m = r.musique;
  const sonLabel = v => (RP_SONS.find(x => x[0] === v) || [v, v])[1];
  body.innerHTML = `<article class="chcard" id="rpSonCard"><div class="chcard-body">${rpSoundPicker(r.son, r.volume_db)}
      ${m ? `<div class="tiny" style="margin-top:6px">🎵 <b>${esc(m.titre)}</b> : sa montée tombe sur la partie ${m.partie + 1} — ${esc(m.pourquoi_partie || m.comment || '')}
        ${m.attention ? `<br>⚠️ ${esc(m.attention)}` : ''}</div>` : ''}</div>
      <div class="chcard-foot"><span class="tiny">Changer le son refait les vidéos sans refaire les voix (pas de crédits ElevenLabs).</span>
        <button class="btn secondary small push" id="rpSonGo" data-icon="refresh">Refaire avec ce son</button></div></article>`
    + p.targets.map(t => {
      const vs = voicesByLang[t.language] || [], cur = vs.find(v => v.voice_id === t.voice_id), ok = t.checks && t.checks.ok;
      return `<article class="chcard ad-prev-card" data-channel="${t.channel}">
        <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(t.channel)}"></span>
          ${esc(rpChannelName(t.channel))} · ${esc(t.language_label)}${t.duration ? ` · ${fmtSec(t.duration)}` : ''} · ${esc(sonLabel(t.son))}</div></div>
          ${t.video_id ? `<span class="pill ok">${icon('check', 11)} dans Publication</span>` : t.validated ? `<span class="pill ok">${icon('check', 11)} validé</span>` : '<span class="pill warn">à regarder</span>'}</div>
        <div class="chcard-body"><div class="ad-preview">
          <div>${t.preview_url ? `<video src="${t.preview_url}?v=${Date.now()}" controls playsinline></video>` : ''}</div>
          <div class="stack" style="gap:10px">
            ${ok ? `<div class="okbox">${icon('check', 12)} La vidéo a la durée de la voix.</div>`
                 : `<div class="errbox">${((t.checks || {}).problems || ['Pas encore contrôlée']).map(esc).join('<br>')}</div>`}
            <div><label class="f">Voix</label><select class="f pv-voice">${vs.map(v => `<option value="${v.voice_id}" ${v.voice_id === t.voice_id ? 'selected' : ''}>${esc(voiceLabel(v))}</option>`).join('')}</select>
              ${cur && cur.has_preview ? `<audio class="pv-sample" controls preload="none" src="${cur.preview_url}" style="width:100%;height:32px;margin-top:6px"></audio>` : ''}</div>
            <div><label class="f">Modèle de voix (ElevenLabs)</label><select class="f pv-model">${r.voice_models.map(x =>
              `<option value="${x}" ${x === t.voice_model_used ? 'selected' : ''}>${x}</option>`).join('')}</select></div>
            <button class="btn secondary small pv-revoice">Refaire avec cette voix / ce modèle</button>
          </div>
        </div>${rpFrise(t.frise, p.project_id)}</div>
        <div class="chcard-foot">${t.video_id ? '' : `<button class="btn primary small push pv-validate" data-icon="check" ${ok && !t.validated ? '' : 'disabled'}>Valider cette vidéo</button>`}</div>
      </article>`;
    }).join('') + `<div class="navbar"><span class="progress-text">${p.targets.filter(t => t.validated).length}/${p.targets.length} vidéo(s) validée(s)</span><span></span>
      <button class="btn primary" id="rpRender" ${p.targets.some(t => t.validated && !t.video_id) ? '' : 'disabled'} data-icon="film">Envoyer les vidéos validées à Publication →</button></div>`;
  hydrateIcons(body);
  rpBindSound(document.getElementById('rpSonCard'));
  document.getElementById('rpSonGo').onclick = () => rpPost(`/api/adaptations/${p.project_id}/reprise/son`, 'PATCH',
    rpSoundOf(document.getElementById('rpSonCard')));
  body.querySelectorAll('.ad-prev-card').forEach(card => {
    const ch = card.dataset.channel, t = p.targets.find(x => x.channel === ch);
    const sel = card.querySelector('.pv-voice'), model = card.querySelector('.pv-model');
    rpBindFrise(card);
    sel.onchange = () => {
      const v = (voicesByLang[t.language] || []).find(x => x.voice_id === sel.value), sample = card.querySelector('.pv-sample');
      if (sample && v) sample.src = v.preview_url;
    };
    card.querySelector('.pv-revoice').onclick = () => rpPost(`/api/adaptations/${p.project_id}/targets/${ch}/voice`, 'PATCH',
      { voice_id: sel.value, model: model.value });
    const val = card.querySelector('.pv-validate');
    if (val) val.onclick = () => rpPost(`/api/adaptations/${p.project_id}/targets/${ch}/validate`, 'POST');
  });
  document.getElementById('rpRender').onclick = () => rpPost(`/api/adaptations/${p.project_id}/render`, 'POST');
}
