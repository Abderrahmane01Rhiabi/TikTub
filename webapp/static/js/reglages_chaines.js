// ---------- Réglages : 3 spaces — Chaînes (one channel, every setting of it on one page), Bibliothèques, App ----------
// The settings are the same as before, only gathered: a channel's sections call the same routes
// (/adaptation, /profile, /montage, /sous_titres, /discours, /background, the connection) and the same card renderers.

let rgSelected = null;
const RG_DAYS = [['monday', 'lun'], ['tuesday', 'mar'], ['wednesday', 'mer'], ['thursday', 'jeu'], ['friday', 'ven'], ['saturday', 'sam'], ['sunday', 'dim']];

function openChannelSettings(name){
  if (name) rgSelected = name;
  goTo(18);
}

function rgSummary(d){
  const s = d.settings, fam = (d.familles || {})[s.famille_recit] || {};
  const main = (d.voices || []).find(v => v.voice_id === s.voice_id);
  const others = (d.voices || []).filter(v => (s.voix_permises || []).includes(v.voice_id));
  const style = (d.styles || []).find(x => x.name === s.style);
  const cats = (s.musique_categories || []).map(c => (d.music_categories || {})[c] || c);
  return {
    recit: fam.label || '—',
    voix: main ? `${main.display_name.split(' - ')[0]} ★${others.length ? ' + ' + others.map(v => v.display_name.split(' - ')[0]).join(', ') : ''}` : 'aucune',
    musique: cats.length ? cats.join(', ') : 'toutes les ambiances',
    look: style ? style.label.split(' (')[0] : s.style,
    langue: s.language === 'ar' ? (s.dialecte ? 'darija' : 'arabe standard') : s.language,
  };
}

async function loadChannelSettings(){
  const list = document.getElementById('rgChannelList'), page = document.getElementById('rgChannelPage');
  if (!channels.length){ list.innerHTML = ''; page.innerHTML = emptyState('Aucune chaîne', 'Ajoute ta première chaîne avec le bouton en haut.', 'settings'); return; }
  if (!rgSelected || !channels.some(c => c.name === rgSelected)) rgSelected = channels[0].name;
  if (!Object.keys(voiceLanguages).length){
    try { voiceLanguages = (await api('/api/voices')).languages || {}; } catch (e){ /* the language menu shows the code */ }
  }
  list.innerHTML = channels.map(ch => `
    <button class="rg-ch ${ch.name === rgSelected ? 'on' : ''}" data-ch="${ch.name}">
      <span class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</span>
      <span class="tiny rg-ch-sum" data-sum="${ch.name}"></span></button>`).join('');
  list.querySelectorAll('.rg-ch').forEach(b => b.onclick = () => { rgSelected = b.dataset.ch; loadChannelSettings(); });
  channels.forEach(async ch => {                       // each channel's one-line summary in the list
    try {
      const r = rgSummary(await api(`/api/channels/${ch.name}/adaptation`));
      const el = list.querySelector(`[data-sum="${ch.name}"]`);
      if (el) el.textContent = `${r.recit} · ${r.langue} · ${r.voix.split(' +')[0]}`;
    } catch (e){ /* the name alone */ }
  });
  await renderChannelPage(channels.find(c => c.name === rgSelected));
}

async function renderChannelPage(ch){
  const page = document.getElementById('rgChannelPage');
  const scroll = window.scrollY;
  const [d, prof] = await Promise.all([api(`/api/channels/${ch.name}/adaptation`), api(`/api/channels/${ch.name}/profile`)]);
  const s = d.settings, r = rgSummary(d);
  const voice = d.voices.find(v => v.voice_id === s.voice_id);
  const musicUrl = f => `/api/channels/${ch.name}/assets/music/${encodeURIComponent(f)}`;
  const fam = (d.familles || {})[s.famille_recit] || {};
  page.innerHTML = `
    <article class="chcard rg-summary">
      <div class="chcard-head"><div class="who"><div class="name" style="font-size:18px"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div>
        <div class="meta" style="margin-left:0">La chaîne en une ligne. Chaque section ci-dessous en règle un morceau.</div></div>
        <span class="pill wait" data-role="pill">Connexion…</span></div>
      <div class="chcard-body"><div class="rg-chips">
        <span class="rg-chip"><b>Récit</b> ${esc(r.recit)}</span>
        <span class="rg-chip"><b>Voix</b> ${esc(r.voix)}</span>
        <span class="rg-chip"><b>Musique</b> ${esc(r.musique)}</span>
        <span class="rg-chip"><b>Look</b> ${esc(r.look)}</span>
        <span class="rg-chip"><b>Langue</b> ${esc(r.langue)}</span></div></div>
      <div class="chcard-body conn-body"></div>
      <div class="chcard-foot" data-role="foot"></div>
    </article>

    <div class="rg-grid">
      <article class="chcard rg-sec">
        <div class="chcard-head"><div class="who"><div class="name">Identité</div>
          <div class="meta" style="margin-left:0">Qui est la chaîne et comment YouTube la voit.</div></div></div>
        <div class="chcard-body">
          <label class="f">Nom affiché dans l'app</label><input class="f rg-name" value="${esc(prof.display_name || ch.display_name)}">
          <label class="f">Langue (celle de ses titres et de sa voix)</label>
          <select class="f ad-lang">${Object.entries(voiceLanguages).map(([k, l]) => `<option value="${k}" ${k === s.language ? 'selected' : ''}>${esc(l)}</option>`).join('') || `<option>${esc(s.language)}</option>`}</select>
          ${s.language === 'ar' ? `<label class="f">Arabe parlé (voix et sous-titres)</label>
            <select class="f ad-dialect"><option value="" ${s.dialecte ? '' : 'selected'}>Arabe standard (fusha)</option>
              ${Object.entries(d.dialects || {}).map(([k, l]) => `<option value="${k}" ${k === s.dialecte ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
            <div class="tiny">En darija : la voix et les sous-titres en darija ; titre, description et tags restent en fusha (ce que les gens tapent).</div>` : ''}
          <label class="f">Catégorie YouTube</label>
          <select class="f ad-cat">${Object.entries(d.categories || {}).map(([k, l]) => `<option value="${k}" ${k === d.youtube_category ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
        </div>
      </article>

      <article class="chcard rg-sec">
        <div class="chcard-head"><div class="who"><div class="name">Récit</div>
          <div class="meta" style="margin-left:0">Comment ses vidéos racontent. L'IA choisit le style parmi ceux allumés.</div></div></div>
        <div class="chcard-body">
          <label class="f">Famille</label>
          <select class="f ad-famille">${Object.entries(d.familles || {}).map(([k, f]) => `<option value="${k}" ${k === s.famille_recit ? 'selected' : ''}>${esc(f.label)}</option>`).join('')}</select>
          <div class="mc-chips ad-styles">${Object.entries(fam.styles || {}).map(([k, l]) =>
            `<button class="mc-chip ${(s.styles_exclus || []).includes(k) ? '' : 'on'}" data-style="${k}">${esc(l)}</button>`).join('')}</div>
          <div class="tiny">Clique un style pour l'éteindre. Les 3 derniers utilisés sont évités. Tu le changes aussi à l'écran du script de chaque vidéo.</div>
        </div>
      </article>

      <article class="chcard rg-sec">
        <div class="chcard-head"><div class="who"><div class="name">Voix</div>
          <div class="meta" style="margin-left:0">Sa signature, et les autres voix que l'IA peut prendre.</div></div></div>
        <div class="chcard-body">
          <label class="f">Voix principale ★</label>
          <select class="f ad-voice"><option value="">— aucune —</option>${d.voices.map(v =>
            `<option value="${v.voice_id}" ${v.voice_id === s.voice_id ? 'selected' : ''}>${esc(voiceLabel(v))}${(v.tons || []).length ? ' · ' + esc(v.tons.join(', ')) : ''}${v.note ? ' · ' + v.note + '/10' : ''}</option>`).join('')}</select>
          ${voice && voice.has_preview ? `<audio controls preload="none" src="${voice.preview_url}" style="width:100%;height:32px"></audio>` :
            (d.voices.length ? '' : '<div class="tiny">Aucune voix dans cette langue : ajoute-en dans Bibliothèques → Voix.</div>')}
          <label class="f">Autres voix permises</label>
          <div class="ad-allowed rg-checks">${d.voices.filter(v => v.voice_id !== s.voice_id && (s.dialecte !== 'darija' || v.accent === 'moroccan')).map(v =>
            `<label class="tiny"><input type="checkbox" value="${v.voice_id}" ${(s.voix_permises || []).includes(v.voice_id) ? 'checked' : ''}>${esc(v.display_name.split(' - ')[0])}${v.accent ? ' (' + esc(v.accent) + ')' : ''}</label>`).join('') || '<span class="tiny">aucune autre voix dans cette langue</span>'}</div>
          <label class="f">Choix de la voix</label>
          <select class="f ad-vmode"><option value="auto" ${s.voix_mode !== 'principale' ? 'selected' : ''}>L'IA choisit selon le sujet (la ★ sauf vraie raison)</option>
            <option value="principale" ${s.voix_mode === 'principale' ? 'selected' : ''}>Toujours la voix principale</option></select>
          ${s.dialecte === 'darija' ? '<div class="tiny">En darija, seules les voix marocaines sont prises.</div>' : ''}
        </div>
      </article>

      <article class="chcard rg-sec">
        <div class="chcard-head"><div class="who"><div class="name">Musique</div>
          <div class="meta" style="margin-left:0">Les ambiances permises. L'IA prend celle qui colle à la vidéo.</div></div></div>
        <div class="chcard-body">
          <div class="mc-chips ad-mcats">${Object.entries(d.music_categories || {}).map(([k, l]) =>
            `<button class="mc-chip ${(s.musique_categories || []).includes(k) ? 'on' : ''}" data-cat="${k}">${esc(l)}</button>`).join('')}</div>
          <label class="tiny rg-inline"><input type="checkbox" class="ad-nolyrics" ${s.musique_sans_paroles ? 'checked' : ''}> Seulement des musiques sans paroles</label>
          <div class="tiny">Aucune ambiance allumée = toutes. Les musiques et leurs catégories : Bibliothèques → Musiques.</div>
          <label class="f">Musique de la chaîne (Adaptation, Sources et Script d'abord)</label>
          <select class="f ad-music"><option value="">— aucune —</option>${d.music_files.map(f => `<option ${f === s.music_file ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>
          ${d.music_files.length ? '' : '<div class="tiny">Aucun morceau propre à la chaîne : c\'est normal. En « Idée d\'abord », l\'IA choisit dans Bibliothèques → Musiques. Pour un morceau fixe, ajoute-le dans Avancé → Montage auto → Ajouter.</div>'}
          ${s.music_file ? `<audio class="ad-audio" controls preload="none" src="${musicUrl(s.music_file)}" style="width:100%;height:32px"></audio>
            <div class="entry-row"><input class="f ad-start" type="number" min="0" step="0.5" value="${s.music_start}"><span class="tiny">s : départ (${fmtSec(s.music_start)})</span>
            <button class="btn secondary small ad-take">Prendre l'instant du lecteur</button></div>` : ''}
        </div>
      </article>

      <article class="chcard rg-sec">
        <div class="chcard-head"><div class="who"><div class="name">Look</div>
          <div class="meta" style="margin-left:0">L'habillage de toutes ses vidéos.</div></div></div>
        <div class="chcard-body">
          <label class="f">Style visuel</label>
          <select class="f ad-style">${(d.styles || []).map(st => `<option value="${st.name}" ${st.name === s.style ? 'selected' : ''}>${esc(st.label)}</option>`).join('')}</select>
          <img class="ad-style-prev" src="/api/adaptation/styles/${s.style}/preview?lang=${s.language}" alt="Aperçu du style visuel" style="width:100%;border-radius:8px;display:block">
          <label class="f">Ton du montage</label>
          <select class="f ad-tone"><option value="" ${s.ton ? '' : 'selected'}>Selon le sujet (l'IA le devine)</option>
            ${[['calme', 'Calme'], ['explicatif', 'Explicatif'], ['spectaculaire', 'Spectaculaire'], ['drole', 'Drôle']].map(([v, l]) =>
              `<option value="${v}" ${s.ton === v ? 'selected' : ''}>Toujours ${l}</option>`).join('')}</select>
        </div>
      </article>

      <article class="chcard rg-sec">
        <div class="chcard-head"><div class="who"><div class="name">Publication</div>
          <div class="meta" style="margin-left:0">Ses textes YouTube et ses horaires préférés.</div></div></div>
        <div class="chcard-body">
          <label class="f">Consigne de l'IA pour ses titres, descriptions et tags (vidéos importées)</label>
          <textarea class="f rg-prompt" rows="4">${esc(prof.ai_style_prompt || '')}</textarea>
          <label class="f">Jours préférés</label>
          <div class="rg-checks rg-days">${RG_DAYS.map(([k, l]) =>
            `<label class="tiny"><input type="checkbox" value="${k}" ${(prof.preferred_days || []).includes(k) ? 'checked' : ''}>${l}</label>`).join('')}</div>
          <label class="f">Heures préférées</label>
          <input class="f rg-hours" value="${esc((prof.preferred_hours || []).join(', '))}" placeholder="ex : 09:00, 17:00, 20:00">
          <div class="tiny">Le planning prend d'abord les heures où son public regarde (statistiques YouTube) ; ces jours et heures servent quand il n'y en a pas.</div>
          <div class="ad-row"><button class="btn secondary small rg-save-pub">Enregistrer</button><span class="note rg-pub-note"></span></div>
        </div>
      </article>
    </div>

    <details class="rg-advanced" id="rgAdvanced">
      <summary>Avancé — modèle de voix, fond, Montage auto, sous-titres, Discours</summary>
      <div class="rg-grid">
        <article class="chcard rg-sec">
          <div class="chcard-head"><div class="who"><div class="name">Modèle de voix (ElevenLabs)</div></div></div>
          <div class="chcard-body">
            <select class="f ad-model"><option value="" ${s.voice_model ? '' : 'selected'}>Par défaut : eleven_v4 (le plus naturel, suit les manières de dire)</option>
              ${(d.voice_models || []).map(m => `<option value="${m}" ${m === s.voice_model ? 'selected' : ''}>${m}</option>`).join('')}</select>
            <div class="tiny">v4 suit les manières ([sérieux], [chuchoté]…) mais ignore la vitesse ; v3 l'inverse.</div>
          </div>
        </article>
        <div><div class="rg-slot-title">Fond (bordures des vidéos importées)</div><div class="rg-slot" data-slot="background"></div></div>
        <div><div class="rg-slot-title">Montage auto (vidéos importées)</div><div class="rg-slot" data-slot="montage"></div></div>
        <div><div class="rg-slot-title">Sous-titres (Adaptation et Reprise)</div><div class="rg-slot" data-slot="captions"></div></div>
        <div><div class="rg-slot-title">Discours</div><div class="rg-slot" data-slot="discours"></div></div>
      </div>
    </details>`;
  hydrateIcons(page);
  window.scrollTo(0, scroll);

  // the connection, in the summary card (the same renderer as before)
  if (ch.has_credentials){
    api(`/api/channels/${ch.name}/connection_status`)
      .then(st => { connectionCache[ch.name] = { at: Date.now(), status: st }; renderConnectionBody(page.querySelector('.conn-body'), ch, st); })
      .catch(e => renderConnectionBody(page.querySelector('.conn-body'), ch, { state: 'error', reason: e.message }));
  } else {
    renderConnectionBody(page.querySelector('.conn-body'), ch, { state: 'never' });
  }

  const save = async body => {
    try { await api(`/api/channels/${ch.name}/adaptation`, { method:'PUT', body: JSON.stringify(body) }); toast('Enregistré', 'success'); }
    catch (e){ log(e.message, 'error'); }
    const open = page.querySelector('#rgAdvanced').open;
    await renderChannelPage(ch);
    if (open) page.querySelector('#rgAdvanced').open = true;
  };
  const on = (sel, ev, fn) => { const el = page.querySelector(sel); if (el) el[ev] = fn; };
  on('.ad-lang', 'onchange', e => save({ language: e.target.value, settings: { voice_id: null } }));
  on('.ad-dialect', 'onchange', e => save({ settings: { dialecte: e.target.value || null } }));
  on('.ad-cat', 'onchange', e => save({ youtube_category: e.target.value }));
  on('.ad-famille', 'onchange', e => save({ settings: { famille_recit: e.target.value, styles_exclus: [] } }));
  page.querySelectorAll('.ad-styles .mc-chip').forEach(b => b.onclick = () => {
    b.classList.toggle('on');
    save({ settings: { styles_exclus: [...page.querySelectorAll('.ad-styles .mc-chip:not(.on)')].map(x => x.dataset.style) } });
  });
  on('.ad-voice', 'onchange', e => save({ settings: { voice_id: e.target.value || null } }));
  page.querySelectorAll('.ad-allowed input').forEach(cb => cb.onchange = () =>
    save({ settings: { voix_permises: [...page.querySelectorAll('.ad-allowed input:checked')].map(x => x.value) } }));
  on('.ad-vmode', 'onchange', e => save({ settings: { voix_mode: e.target.value } }));
  page.querySelectorAll('.ad-mcats .mc-chip').forEach(b => b.onclick = () => {
    b.classList.toggle('on');
    save({ settings: { musique_categories: [...page.querySelectorAll('.ad-mcats .mc-chip.on')].map(x => x.dataset.cat) } });
  });
  on('.ad-nolyrics', 'onchange', e => save({ settings: { musique_sans_paroles: e.target.checked } }));
  on('.ad-music', 'onchange', e => save({ settings: { music_file: e.target.value || null } }));
  const start = page.querySelector('.ad-start'), audio = page.querySelector('.ad-audio');
  if (start) start.onchange = () => save({ settings: { music_start: parseFloat(start.value) || 0 } });
  if (start && audio) on('.ad-take', 'onclick', () => save({ settings: { music_start: Math.round(audio.currentTime * 2) / 2 } }));
  on('.ad-style', 'onchange', e => save({ settings: { style: e.target.value } }));
  on('.ad-tone', 'onchange', e => save({ settings: { ton: e.target.value || null } }));
  on('.ad-model', 'onchange', e => save({ settings: { voice_model: e.target.value || null } }));
  on('.rg-name', 'onchange', async e => {
    try { await api(`/api/channels/${ch.name}/profile`, { method:'PUT', body: JSON.stringify({ display_name: e.target.value.trim() }) });
          ch.display_name = e.target.value.trim(); toast('Nom enregistré', 'success'); loadChannelSettings(); }
    catch (err){ log(err.message, 'error'); }
  });
  on('.rg-save-pub', 'onclick', async () => {
    const hours = page.querySelector('.rg-hours').value.split(/[\s,;]+/).map(x => x.trim()).filter(Boolean);
    if (hours.some(h => !/^\d{1,2}:\d{2}$/.test(h))){ log('Heures au format 09:00, 17:00…', 'error'); return; }
    try {
      await api(`/api/channels/${ch.name}/profile`, { method:'PUT', body: JSON.stringify({
        ai_style_prompt: page.querySelector('.rg-prompt').value,
        preferred_days: [...page.querySelectorAll('.rg-days input:checked')].map(x => x.value),
        preferred_hours: hours.map(h => h.padStart(5, '0')) }) });
      page.querySelector('.rg-pub-note').textContent = 'Enregistré ✓';
    } catch (e){ log(e.message, 'error'); }
  });

  // « Avancé »: the same per-channel cards as before (fond, Montage auto, sous-titres, Discours), made when opened
  const adv = page.querySelector('#rgAdvanced');
  adv.ontoggle = () => { if (adv.open && !adv.dataset.loaded){ adv.dataset.loaded = '1'; rgAdvancedCards(adv, ch); } };
}

async function rgAdvancedCards(adv, ch){
  const slot = n => adv.querySelector(`[data-slot="${n}"]`);
  loadBackgrounds(slot('background'), [ch]);
  const card = (n, title) => { slot(n).innerHTML = `<article class="chcard" data-channel="${ch.name}">${spinnerHtml(title + '…')}</article>`; return slot(n).firstElementChild; };
  const m = card('montage', 'Montage auto');
  api(`/api/channels/${ch.name}/montage`).then(dd => renderMontageSettingsCard(m, ch, dd)).catch(e => showLoadError(m, e, () => rgAdvancedCards(adv, ch)));
  const c = card('captions', 'Sous-titres');
  try {
    if (!capCatalog) capCatalog = await api('/api/captions/styles');
    renderCapChannelCard(c, ch, await api(`/api/channels/${ch.name}/sous_titres`));
  } catch (e){ showLoadError(c, e, () => rgAdvancedCards(adv, ch)); }
  const dsc = card('discours', 'Discours');
  api(`/api/channels/${ch.name}/discours`).then(dd => dsChannelCard(dsc, ch, dd)).catch(e => showLoadError(dsc, e, () => rgAdvancedCards(adv, ch)));
}

// ---------- the tabs of Bibliothèques and App ----------

const LIB_LOADERS = { voix: () => loadVoiceSettings(), musiques: () => loadSongs(), sfx: () => loadSfxSettings(),
                      drones: () => loadBrollLibrary(), soustitres: () => loadCaptionSettings() };
const APP_LOADERS = { ia: () => loadAiModels(), sauvegardes: () => loadBackups(), stockage: () => loadStorage() };
let libTab = 'voix', appTab = 'ia';

function rgTabs(barId, screenIdx, loaders, current, set){
  const screen = document.querySelector(`.screen[data-idx="${screenIdx}"]`);
  document.querySelectorAll(`#${barId} .seg-opt`).forEach(b => {
    b.classList.toggle('active', b.dataset.tab === current);
    b.onclick = () => { set(b.dataset.tab); rgTabs(barId, screenIdx, loaders, b.dataset.tab, set); };
  });
  screen.querySelectorAll('.rg-panel').forEach(p => { p.hidden = p.dataset.panel !== current; });
  const panel = screen.querySelector(`.rg-panel[data-panel="${current}"]`);
  return safeLoad(loaders[current], (panel.querySelector('.stack, .cap-gallery, .broll-grid') || panel).id || null);
}
function loadLibraries(){ return rgTabs('libTabs', 19, LIB_LOADERS, libTab, t => { libTab = t; }); }
function loadAppSettings(){ return rgTabs('appTabs', 20, APP_LOADERS, appTab, t => { appTab = t; }); }
function openLibrary(tab){ if (tab) libTab = tab; goTo(19); }
