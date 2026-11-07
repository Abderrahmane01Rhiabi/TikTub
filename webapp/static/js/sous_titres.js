// ---------- Réglages → Sous-titres : the caption library (captions/) — gallery + each channel's style ----------

let capCatalog = null, capLang = 'fr', capGroup = '';
const CAP_SPACES = { generation: 'Génération', montage: 'Montage auto', adaptation: 'Adaptation', reprise: 'Reprise', discours: 'Discours' };

async function loadCaptionSettings(){
  if (!capCatalog) capCatalog = await api('/api/captions/styles');
  const sel = document.getElementById('capGroupSel');
  sel.innerHTML = `<option value="">Tous les groupes (${capCatalog.styles.length})</option>` +
    capCatalog.groups.map(g => `<option value="${esc(g)}" ${g === capGroup ? 'selected' : ''}>${esc(g)}</option>`).join('');
  sel.onchange = () => { capGroup = sel.value; renderCapGallery(); };
  document.querySelectorAll('#capLangSeg .seg-opt').forEach(b => {
    b.classList.toggle('active', b.dataset.l === capLang);
    b.onclick = () => { capLang = b.dataset.l; document.querySelectorAll('#capLangSeg .seg-opt').forEach(x => x.classList.toggle('active', x === b)); renderCapGallery(); };
  });
  renderCapGallery();
  if (document.getElementById('capChannels')) await renderCapChannels();   // each channel's card: on its page
}

function capPreviewUrl(id, lang, params, channel){
  const q = new URLSearchParams({ lang });
  if (params && Object.keys(params).length) q.set('params', JSON.stringify(params));
  if (channel) q.set('channel', channel);
  return `/api/captions/preview/${encodeURIComponent(id)}?${q}`;
}

function renderCapGallery(){
  const box = document.getElementById('capGallery');
  const list = capCatalog.styles.filter(s => !capGroup || s.group === capGroup);
  box.innerHTML = list.map(s => {
    const usable = s.spaces.map(x => CAP_SPACES[x] || x).join(', ');
    const arabic = s.arabic ? '' : '<span class="pill warn" title="Lettres arabes détachées ou mal placées : pas proposé aux chaînes arabes">pas en arabe</span>';
    return `<article class="chcard cap-card" data-id="${esc(s.id)}">
      <div class="chcard-head"><div class="who"><div class="name">${s.number ? `<span class="pill">${s.number}</span> ` : ''}${esc(s.label)}</div>
        <div class="meta" style="margin-left:0">${esc(s.group)}</div></div>${arabic}</div>
      <div class="chcard-body">
        <div class="cap-video"><button class="btn secondary small cap-play" data-icon="play">Voir</button></div>
        <div class="tiny">${esc(s.description)}</div>
        <div class="tiny" style="color:var(--muted)">${usable ? `Utilisable : ${esc(usable)}` : 'Propre à son espace (aperçu seulement)'}
          ${s.needs.includes('faces') ? ' · trouve les visages' : ''}${s.needs.includes('mask') ? ' · carte graphique (SAM 2.1)' : ''}</div>
      </div></article>`;
  }).join('') || emptyState('Aucun style', 'Aucun style dans ce groupe.', 'settings');
  hydrateIcons(box);
  box.querySelectorAll('.cap-card').forEach(card => {
    card.querySelector('.cap-play').onclick = () => {
      const id = card.dataset.id;
      const slot = card.querySelector('.cap-video');
      slot.innerHTML = `${spinnerHtml('Préparation de l\'aperçu…')}`;
      const v = document.createElement('video');
      Object.assign(v, { autoplay: true, loop: true, playsInline: true, controls: true, muted: id !== 'clic' });
      v.src = capPreviewUrl(id, capLang);
      v.oncanplay = () => { slot.innerHTML = ''; slot.appendChild(v); };
      v.onerror = () => { slot.innerHTML = '<span class="tiny" style="color:var(--danger)">Aperçu impossible.</span>'; };
      v.load();
    };
  });
}

// ---- each channel: its style (Adaptation, Reprise) and that style's settings ----

function capParamInput(p, value){
  const v = value === undefined ? p.default : value;
  if (p.kind === 'int') return `<span style="display:flex;gap:8px;align-items:center"><input type="range" class="cap-p" data-name="${p.name}" data-kind="int"
      min="${p.lo}" max="${p.hi}" step="1" value="${v}" style="flex:1"><span class="tiny cap-out">${v}</span></span>`;
  if (p.kind === 'colour') return `<input type="color" class="cap-p" data-name="${p.name}" data-kind="colour" value="${esc(v)}" style="width:44px;height:28px">`;
  if (p.kind === 'bool') return `<label class="switch"><input type="checkbox" class="cap-p" data-name="${p.name}" data-kind="bool" ${v ? 'checked' : ''}> oui</label>`;
  return `<select class="f cap-p" data-name="${p.name}" data-kind="choice" style="width:auto">${(p.choices || []).map(c =>
    `<option value="${esc(c.value)}" ${c.value === v ? 'selected' : ''}>${esc(c.label)}</option>`).join('')}</select>`;
}

// the settings by section, in the order they first appear (Texte, Contour et ombre, Placement, Fond, Animation, Son…)
function capSections(params){
  const out = [];
  params.forEach(p => {
    const sec = p.section || 'Style';
    let entry = out.find(([s]) => s === sec);
    if (!entry){ entry = [sec, []]; out.push(entry); }
    entry[1].push(p);
  });
  return out;
}

function capReadParams(card){
  const out = {};
  card.querySelectorAll('.cap-p').forEach(el => {
    out[el.dataset.name] = el.dataset.kind === 'int' ? Number(el.value) : el.dataset.kind === 'bool' ? el.checked : el.value;
  });
  return out;
}

async function renderCapChannels(){
  const grid = document.getElementById('capChannels');
  grid.innerHTML = channels.map(ch => `<article class="chcard" data-channel="${ch.name}">${spinnerHtml('Chargement...')}</article>`).join('');
  await Promise.all(channels.map(async ch => {
    const card = grid.querySelector(`[data-channel="${ch.name}"]`);
    try { renderCapChannelCard(card, ch, await api(`/api/channels/${ch.name}/sous_titres`)); }
    catch (e){ showLoadError(card, e, () => renderCapChannels()); }
  }));
}

function renderCapChannelCard(card, ch, d){
  const allowed = capCatalog.styles.filter(s => (s.spaces.includes('adaptation') || s.spaces.includes('reprise')) && (s.arabic || d.language !== 'ar'));
  const st = capCatalog.styles.find(s => s.id === d.style);
  card.innerHTML = `
    <div class="chcard-head"><div class="who"><div class="name"><span class="dot" style="background:${channelColor(ch.name)}"></span>${esc(ch.display_name)}</div>
      <div class="meta" style="margin-left:0">${esc(d.language)} · couleur de la chaîne <span class="dot" style="background:${esc(d.colour)}"></span></div></div></div>
    <div class="chcard-body">
      <label class="f">Style de sous-titres (Adaptation, Reprise)</label>
      <div class="tiny" style="margin-bottom:4px">Position « Auto » : chaque groupe de mots va là où il ne cache ni un visage ni les détails de l'image (en Reprise : là où étaient ses sous-titres). « Lisibilité auto » renforce le contour sur un fond clair.</div>
      <select class="f cap-style"><option value="">Celui de l'espace (style visuel de l'Adaptation, jaune mot par mot en Reprise)</option>
        ${allowed.map(s => `<option value="${esc(s.id)}" ${s.id === d.style ? 'selected' : ''}>${s.number ? `${s.number} · ` : ''}${esc(s.label)} — ${esc(s.group)}</option>`).join('')}</select>
      ${st ? `<div class="stack cap-params" style="gap:4px;margin-top:6px">${capSections(st.params).map(([sec, ps], i) =>
        `<details ${i === 0 ? 'open' : ''}><summary class="tiny" style="cursor:pointer;font-weight:600;margin:4px 0">${esc(sec)}</summary>
          <div class="stack" style="gap:6px">${ps.map(p => `<div><label class="f" style="margin:0">${esc(p.label)}</label>${capParamInput(p, d.params[p.name])}</div>`).join('')}</div></details>`).join('')}</div>
        <div class="cap-video" style="max-width:240px"></div>` : ''}
    </div>
    <div class="chcard-foot">${st ? '<button class="btn secondary small cap-chprev" data-icon="play">Aperçu avec ces réglages</button>' : ''}
      <span class="note push cap-saved"></span></div>`;
  hydrateIcons(card);
  const save = async (style, params) => {
    try {
      const nd = await api(`/api/channels/${ch.name}/sous_titres`, { method: 'PUT', body: JSON.stringify({ style: style || null, params: params || {} }) });
      renderCapChannelCard(card, ch, nd);
      card.querySelector('.cap-saved').textContent = 'Enregistré ✓';
    } catch (e){ log(e.message, 'error'); }
  };
  card.querySelector('.cap-style').onchange = e => save(e.target.value, {});
  let timer = null;
  card.querySelectorAll('.cap-p').forEach(el => {
    const ev = el.dataset.kind === 'int' ? 'input' : 'change';
    el.addEventListener(ev, () => {
      if (el.dataset.kind === 'int') el.parentElement.querySelector('.cap-out').textContent = el.value;
      clearTimeout(timer);
      timer = setTimeout(() => save(d.style, capReadParams(card)), 500);
    });
  });
  const prev = card.querySelector('.cap-chprev');
  if (prev) prev.onclick = () => {
    const slot = card.querySelector('.cap-video');
    slot.innerHTML = spinnerHtml('Préparation de l\'aperçu…');
    const v = document.createElement('video');
    Object.assign(v, { autoplay: true, loop: true, playsInline: true, controls: true, muted: d.style !== 'clic' });
    v.style.width = '100%';
    v.src = capPreviewUrl(d.style, d.language, capReadParams(card), ch.name);
    v.oncanplay = () => { slot.innerHTML = ''; slot.appendChild(v); };
    v.onerror = () => { slot.innerHTML = '<span class="tiny" style="color:var(--danger)">Aperçu impossible.</span>'; };
    v.load();
  };
}
