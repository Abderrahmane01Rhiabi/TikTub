// ---------- Accueil ----------

// Connection checks cost a (cheap) YouTube call each: cache them a few
// minutes so going back and forth to Accueil doesn't re-check 6 channels
// every time. The Réglages → Connexion screen always checks live.
const CONNECTION_CACHE_MS = 5 * 60 * 1000;
const connectionCache = {};
async function cachedConnectionStatus(channelName){
  const hit = connectionCache[channelName];
  if (hit && Date.now() - hit.at < CONNECTION_CACHE_MS) return hit.status;
  const status = await api(`/api/channels/${channelName}/connection_status`);
  connectionCache[channelName] = { at: Date.now(), status };
  return status;
}

function formatWhen(iso){
  const d = new Date(iso);
  return d.toLocaleDateString('fr-FR', { weekday:'short', day:'2-digit', month:'2-digit' })
    + ' à ' + d.toLocaleTimeString('fr-FR', { hour:'2-digit', minute:'2-digit' });
}

function setSpaceBadge(space, n){
  const btn = document.querySelector(`#spacenav .space[data-space="${space}"]`);
  if (!btn) return;
  let badge = btn.querySelector('.badge');
  if (!n){ if (badge) badge.remove(); return; }
  if (!badge){ badge = document.createElement('span'); badge.className = 'badge'; btn.appendChild(badge); }
  badge.textContent = n;
}

const STATUS_LABELS = {
  download_failed: 'téléchargement échoué', processing_failed: 'traitement échoué',
  error: 'erreur', rendering_failed: 'génération échouée',
};

const ICONS = {
  calendar: '<path d="M8 2v4M16 2v4M3 10h18"/><rect x="3" y="4" width="18" height="18" rx="2"/>',
  gauge: '<path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  chevron: '<path d="M9 18l6-6-6-6"/>',
  link: '<path d="M15 3h6v6M10 14L21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  home: '<path d="M3 10.5L12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v7a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-7z"/>',
  sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17l.7 1.8L21.5 19.5l-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z"/>',
  rocket: '<path d="M5 15c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9a2.2 2.2 0 0 0-2.9-.1z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.9A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22 22 0 0 1-4 2z"/><path d="M9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 16v-4M12 16V8M17 16v-7"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  download: '<path d="M12 3v13"/><path d="M6 11l6 6 6-6"/><path d="M5 21h14"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  thumb: '<path d="M7 10v11H3V10z"/><path d="M7 10l4-8a3 3 0 0 1 3 3v4h5.5a2 2 0 0 1 2 2.3l-1.4 8A2 2 0 0 1 18.1 21H7"/>',
  comment: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5"/>',
  film: '<rect x="2" y="3" width="20" height="18" rx="2"/><path d="M7 3v18M17 3v18M2 8h5M2 16h5M17 8h5M17 16h5"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  skip: '<path d="M5 4l10 8-10 8z"/><path d="M19 5v14"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>',
  upload: '<path d="M12 21V8"/><path d="M6 13l6-6 6 6"/><path d="M5 3h14"/>',
};
// Static markup declares icons as data-icon="name" — filled in once at boot.
function hydrateIcons(root = document){
  root.querySelectorAll('[data-icon]').forEach(el => {
    if (el.dataset.iconDone) return;
    el.insertAdjacentHTML('afterbegin', icon(el.dataset.icon, +(el.dataset.iconSize || 15)));
    el.dataset.iconDone = '1';
  });
}
function emptyState(title, text, iconName = 'inbox'){
  return `<div class="empty-state">${icon(iconName, 26)}<b>${esc(title)}</b>${text ? `<span>${text}</span>` : ''}</div>`;
}
function icon(name, size = 14){
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
}

// Short, DISTINCT label for a source URL instead of an 80-character link:
// "TikTok · @user · …1234" / "Instagram · DcxcO8TsXk-" (posts have no
// username in the URL — the post code is what tells two apart).
function sourceLabel(url){
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '');
    const parts = u.pathname.split('/').filter(Boolean);
    if (host.includes('tiktok')){
      const user = parts.find(p => p.startsWith('@'));
      const id = parts[parts.length - 1] || '';
      const kind = parts.includes('photo') ? ' (photo)' : '';
      if (!user) return `TikTok · ${id || 'vidéo'}`; // short links: vm.tiktok.com/ZMabc/
      return `TikTok · ${user}${/^\d{6,}$/.test(id) ? ' · …' + id.slice(-4) : ''}${kind}`;
    }
    if (host.includes('instagram')){
      const i = parts.findIndex(p => ['p', 'reel', 'reels', 'tv'].includes(p));
      return `Instagram · ${i >= 0 && parts[i + 1] ? parts[i + 1] : 'publication'}`;
    }
    if (host.includes('facebook') || host.startsWith('fb.')){
      const id = parts[parts.length - 1];
      return `Facebook · ${id && id.length <= 24 ? id : 'vidéo'}`;
    }
    return host;
  } catch (_) { return url || 'vidéo'; }
}

document.getElementById('homeRefreshBtn').addEventListener('click', () => {
  Object.keys(connectionCache).forEach(k => delete connectionCache[k]);
  safeLoad(loadHome, 'homeKpis');
});

async function loadHome(){
  const kpis = document.getElementById('homeKpis');
  const grid = document.getElementById('homeChannels');
  kpis.innerHTML = `<div class="stat zero">${spinnerHtml('Chargement...')}</div>`;
  grid.innerHTML = '';
  const data = await api('/api/overview');
  const t = data.totals;
  const hasGeneration = channels.some(ch => ch.generation_mode);

  setSpaceBadge('import', t.to_sort);
  setSpaceBadge('publication', t.ready);
  setSpaceBadge('generation', t.generating);

  const waiting = t.to_sort + t.ready + t.generating;
  document.getElementById('homeSub').textContent = waiting
    ? `${waiting} vidéo(s) attendent une action de ta part.`
    : (t.errors ? `Rien en attente — ${t.errors} erreur(s) à regarder ou retirer.` : 'Tout est à jour. Rien en attente.');

  const kpiDefs = [
    { n: t.to_sort, l: 'à trier', go: 'Import → Sélection', action: () => goTo(3) },
    hasGeneration && { n: t.generating, l: 'en génération', go: 'Génération', action: () => openSpace('generation') },
    { n: t.ready, l: 'prêtes à publier', go: 'Publication', action: () => goTo(5) },
    { n: t.scheduled, l: 'programmées', go: 'Dashboard', action: () => openSpace('dashboard') },
    { n: t.errors, l: 'en erreur', go: 'Voir ↓', cls: 'bad', action: () => {
        const first = document.querySelector('.chcard details.errs');
        if (first){ first.open = true; first.scrollIntoView({behavior:'smooth', block:'center'}); } } },
  ].filter(Boolean);
  kpis.innerHTML = kpiDefs.map((k, i) => `
    <button class="stat ${k.n ? (k.cls || '') : 'zero'}" data-k="${i}" ${k.n ? '' : 'tabindex="-1"'}>
      <span class="n">${k.n}</span><span class="l">${esc(k.l)}</span><span class="go">${esc(k.go)} →</span>
    </button>`).join('');
  kpis.querySelectorAll('.stat').forEach(btn => btn.addEventListener('click', () => {
    const k = kpiDefs[+btn.dataset.k]; if (k.n) k.action();
  }));

  grid.innerHTML = data.channels.map(c => channelHomeCard(c)).join('');
  wireHomeCards(grid, data.channels);
  loadHomeSuggestion().catch(() => {});  // a bonus: never blocks or breaks the home screen
  loadHomeHealth().catch(() => {});
  loadHomeCost().catch(() => {});
}

// What the AI (Gemini) cost this month, per step — and the same calls at January 2027 prices (Flash doubles)
async function loadHomeCost(){
  const box = document.getElementById('homeCost');
  const r = await api('/api/usage/ai');
  if (!r.appels){ box.innerHTML = ''; return; }
  const usd = x => `${Number(x).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
  const month = new Date(r.mois + '-01').toLocaleDateString('fr-FR', { month: 'long' });
  box.innerHTML = `<details class="tiny" style="margin:2px 0 8px">
    <summary style="cursor:pointer">💶 IA en ${esc(month)} : <b>${usd(r.total)}</b> · ${r.appels} appels${r.echecs ? ` (${r.echecs} en échec)` : ''}
      ${r.au_prix_de_janvier > r.total ? ` · aux prix de janvier 2027 : ${usd(r.au_prix_de_janvier)}` : ''}</summary>
    <div style="margin-top:6px;display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;gap:3px 14px;max-width:760px">
      <b>Étape</b><b>Modèle</b><b>Appels</b><b>Coût</b>
      ${r.par_etape.map(s => `<span title="${esc(s.etape)}">${esc(s.quoi || s.etape)}</span>
        <span>${esc(s.modele_actuel.replace('gemini-', '').replace('-latest', ''))}</span><span>${s.appels}</span><span>${usd(s.cout)}</span>`).join('')}
    </div>
    <div style="margin-top:6px">Le modèle de chaque étape se change dans <code>ai_models.py</code> (ou <code>database/ai_models.json</code>).</div>
  </details>`;
}

// ---------- Downloads health: three small test downloads a day (YouTube, YouTube via bgutil, TikTok) ----------
function agoText(iso){
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 60 ? `il y a ${Math.max(1, m)} min` : m < 48 * 60 ? `il y a ${Math.round(m / 60)} h` : `il y a ${Math.round(m / 1440)} jours`;
}

async function loadHomeHealth(note){
  const box = document.getElementById('homeHealth');
  const st = await api('/api/health/downloads');
  const d = st.dernier, v = st.versions || {};
  const vers = `yt-dlp ${esc(v['yt-dlp'] || '?')} · bgutil ${esc(v['bgutil-ytdlp-pot-provider'] || '?')}`;
  const buttons = `<button class="btn ghost small" data-act="check" ${st.en_cours ? 'disabled' : ''}>${st.en_cours ? spin('contrôle en cours…') : 'Vérifier maintenant'}</button>
    <button class="btn ghost small" data-act="update" ${st.en_cours ? 'disabled' : ''} title="Installe la dernière version de yt-dlp, refait le contrôle et remet l'ancienne toute seule si la nouvelle marche moins bien (1 à 3 min)">Mettre à jour yt-dlp</button>`;
  const allOk = d && d.total && d.ok === d.total;
  box.innerHTML = !d
    ? `<div class="tiny" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0">🩺 Téléchargements : pas encore vérifiés. ${buttons}</div>`
    : allOk
    ? `<div class="tiny" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0" title="${esc(d.resultats.map(r => `${r.label} : ${r.secondes} s, ${r.hauteur}p`).join(' · '))}">
         ✅ Téléchargements OK (${d.ok}/${d.total}) · vérifiés ${agoText(d.le)} · ${vers} ${buttons}</div>`
    : `<div class="warnbox" style="border-color:var(--danger)">
         <b>❌ Téléchargements : ${d.ok}/${d.total} test(s) passent</b>${st.casse_depuis ? ` — cassé depuis ${agoText(st.casse_depuis).replace('il y a ', '')}` : ''} · vérifiés ${agoText(d.le)}
         ${(d.resultats || []).filter(r => !r.ok).map(r => `<div class="tiny">• ${esc(r.label)} : ${esc(r.erreur || '')}</div>`).join('')}
         ${d.erreur ? `<div class="tiny">• ${esc(d.erreur)}</div>` : ''}
         ${d.bgutil_actif === false ? '<div class="tiny">• Le service bgutil (jetons YouTube) est arrêté : redémarre le serveur.</div>' : ''}
         <div class="tiny" style="margin-top:4px">Souvent, YouTube ou TikTok a changé : <b>Mettre à jour yt-dlp</b> suffit. En attendant, « Déposer un fichier » marche toujours. ${vers}</div>
         <div style="display:flex;gap:8px;margin-top:6px">${buttons}</div></div>`;
  if (note) box.insertAdjacentHTML('beforeend', `<div class="tiny" style="margin:4px 0">${esc(note)}</div>`);
  const run = async (path, label) => {
    box.querySelectorAll('button').forEach(b => b.disabled = true);
    box.querySelector(`[data-act="${path === 'check' ? 'check' : 'update'}"]`).innerHTML = spin(label);
    try {
      const r = await api(`/api/health/downloads/${path}`, { method: 'POST' });
      const m = r.mise_a_jour;
      if (m) toast(m.message, m.annule ? 'error' : 'success');
      await loadHomeHealth(m ? m.message : null);
    } catch (e){ log(e.message, 'error'); await loadHomeHealth(); }
  };
  box.querySelector('[data-act="check"]').onclick = () => run('check', 'contrôle (30 s)…');
  box.querySelector('[data-act="update"]').onclick = () => {
    if (confirm("Installer la dernière version de yt-dlp ? Elle est testée tout de suite, et l'ancienne revient toute seule si la nouvelle marche moins bien.")) run('update', 'mise à jour (1 à 3 min)…');
  };
}

// ---------- "Idée de la semaine" (winning style worth relaunching) ----------
function isoWeek(d = new Date()){
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const w = Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
  return `${t.getUTCFullYear()}-W${w}`;
}
const RECIPE_LABELS = { script_format: 'Format', background: 'Fond', music: 'Musique', caption_style: 'Sous-titres', hour_slot: 'Heure de publication' };
function recipeHtml(items){
  return `<div class="recipe">${items.map(r => `
    <div class="recipe-row">
      <span class="k">${esc(RECIPE_LABELS[r.dimension] || r.dimension_label)}</span>
      <span class="v" title="${esc(r.label)}">${esc(r.label)}</span>
      <span class="s">${r.from_model
        ? '<span class="tiny" title="Pas encore assez de vidéos pour désigner un gagnant">celui du modèle</span>'
        : `${fmtScore(r.score)} · ${r.count} vidéos${r.median_retention_7d != null ? ` · ${fmtPct(r.median_retention_7d)} regardé` : ''}${r.dimension === 'hour_slot' ? ' · conseil pour le planning' : ''}`}</span>
    </div>`).join('')}</div>`;
}
function suggestionKey(s){ return `tiktub.suggest.${s.channel}`; }
function suggestionDismissed(s){
  try { return localStorage.getItem(suggestionKey(s)) === `${isoWeek()}:${s.dimension}:${s.value}`; } catch { return false; }
}

async function loadHomeSuggestion(){
  const box = document.getElementById('homeSuggest');
  const list = (await api('/api/suggestions')).filter(s => !suggestionDismissed(s));
  if (!list.length){ box.innerHTML = ''; return; }
  const s = list.sort((a, b) => b.score - a.score)[0];  // one idea at a time: the strongest
  const ch = channels.find(c => c.name === s.channel) || { display_name: s.channel };
  box.innerHTML = `
    <article class="chcard suggest-card">
      <div class="chcard-head">
        <div class="who"><div class="name">${icon('sparkle', 15)} Idée de la semaine</div></div>
        <span class="pill ok">${fmtScore(s.score)} la médiane</span>
      </div>
      <div class="chcard-body">
        <div>Sur <b><span class="dot" style="background:${channelColor(s.channel)}"></span> ${esc(ch.display_name)}</b>, les vidéos
          <b>${esc(s.dimension_label.toLowerCase())} « ${esc(s.label)} »</b> font <b>${fmtScore(s.score)}</b> les vues habituelles
          (${s.count} vidéos${s.median_retention_7d != null ? `, ${fmtPct(s.median_retention_7d)} regardé` : ''}).
          Lancer 3 nouvelles vidéos avec la recette gagnante ?</div>
        ${recipeHtml(s.recipe)}
        <div class="tiny">Script calqué sur « ${esc(s.video.title)} » (${s.video.views_7d.toLocaleString('fr-FR')} vues à 7 j), sur un nouveau sujet. Rien n'est envoyé à ElevenLabs avant que tu valides les scripts.</div>
      </div>
      <div class="chcard-foot">
        <button class="btn ghost small" data-act="later">Pas cette semaine</button>
        <button class="btn secondary small" data-act="see">Voir « Ce qui marche »</button>
        <button class="btn primary small push" data-act="go">${icon('sparkle', 13)} Lancer 3 vidéos</button>
      </div>
    </article>`;
  box.querySelector('[data-act="go"]').addEventListener('click', () => openRemakeDialog(s.channel, s.video, s));
  box.querySelector('[data-act="see"]').addEventListener('click', () => { dashboardChannel = s.channel; dashView = 'perf'; openSpace('dashboard'); });
  box.querySelector('[data-act="later"]').addEventListener('click', () => {
    try { localStorage.setItem(suggestionKey(s), `${isoWeek()}:${s.dimension}:${s.value}`); } catch {}
    loadHomeSuggestion().catch(() => {});  // maybe another channel has an idea
  });
}

function channelHomeCard(c){
  const ch = channels.find(x => x.name === c.channel) || { display_name: c.channel };
  const counts = c.counts;
  const q = c.quota;
  const stats = [
    { n: counts.to_sort, l: 'À trier', go: '3' },
    ch.generation_mode && { n: counts.generating, l: 'Génération', go: 'generation' },
    { n: counts.ready, l: 'Prêtes', go: '5' },
    { n: counts.scheduled, l: 'Programmées', go: 'dashboard' },
    { n: counts.errors, l: 'Erreurs', go: 'errors', cls: 'bad' },
  ].filter(Boolean);

  const quotaFact = q.exhausted
    ? `<div class="fact bad">${icon('gauge')}<span>Quota YouTube du jour atteint</span></div>`
    : `<div class="fact ${q.estimated_uploads_left < 3 ? 'warn' : ''}">${icon('gauge')}<span>Quota : ${q.uploads_today} aujourd'hui · ≈ ${q.estimated_uploads_left} restant(s)</span></div>`;

  const errors = c.errors.length ? `
    <details class="errs">
      <summary>${icon('chevron')}${icon('alert')} ${counts.errors} erreur(s) à traiter
        <span class="all" data-dismiss-all role="button">Tout retirer</span></summary>
      <div class="err-list">
        ${c.errors.map(e => `
          <div class="err-item" data-video="${esc(e.video_id)}">
            <div class="err-title">${e.url
              ? `<a href="${esc(e.url)}" target="_blank" rel="noopener" title="${esc(e.url)}">${esc(e.title || sourceLabel(e.url))} ${icon('link', 11)}</a>`
              : esc(e.title || e.video_id)}</div>
            <div class="err-why">${esc(STATUS_LABELS[e.status] || e.status)} · ${esc(e.message || 'raison non enregistrée (échec antérieur à cette version)')}</div>
            <div class="err-actions">
              ${e.status === 'download_failed' ? `<button class="btn secondary small" data-upload-source="${esc(e.video_id)}" title="Tu as la vidéo sur ton ordinateur ? Dépose-la, elle continuera normalement.">${icon('upload', 12)} Déposer</button>` : ''}
              <button class="btn ghost small" data-dismiss>Retirer</button>
            </div>
          </div>`).join('')}
      </div>
    </details>` : '';

  return `
  <article class="chcard" data-channel="${c.channel}">
    <div class="chcard-head">
      <div class="who">
        <div class="name"><span class="dot" style="background:${channelColor(c.channel)}"></span>${esc(ch.display_name)}</div>
        <div class="yt" data-role="yt">&nbsp;</div>
      </div>
      <span class="pill wait" data-role="conn">Vérification…</span>
    </div>
    <div class="ministats">
      ${stats.map(s => `<button class="ministat ${s.n ? (s.cls || '') : 'zero'}" data-go="${s.go}" ${s.n ? '' : 'tabindex="-1"'}>
        <div class="n">${s.n}</div><div class="l">${s.l}</div></button>`).join('')}
    </div>
    <div class="facts">
      <div class="fact">${icon('calendar')}<span>${c.next_publish ? `Prochaine publication : ${esc(formatWhen(c.next_publish))}` : 'Rien de programmé'}</span></div>
      ${quotaFact}
    </div>
    ${errors}
  </article>`;
}

function wireHomeCards(grid, channelData){
  grid.querySelectorAll('.ministat').forEach(btn => btn.addEventListener('click', () => {
    if (btn.classList.contains('zero')) return;
    const go = btn.dataset.go;
    if (go === 'errors'){
      const d = btn.closest('.chcard').querySelector('details.errs');
      if (d){ d.open = true; d.scrollIntoView({behavior:'smooth', block:'nearest'}); }
    } else if (/^\d+$/.test(go)) goTo(+go);
    else openSpace(go);
  }));

  grid.querySelectorAll('[data-dismiss]').forEach(btn => btn.addEventListener('click', async () => {
    const item = btn.closest('.err-item');
    btn.disabled = true;
    try {
      await api(`/api/videos/${item.dataset.video}/dismiss`, { method: 'POST' });
      item.remove();
      refreshHomeCounts();
    } catch (e){ btn.disabled = false; log(e.message, 'error'); }
  }));

  grid.querySelectorAll('[data-dismiss-all]').forEach(el => el.addEventListener('click', async (ev) => {
    ev.preventDefault(); // don't toggle the <details>
    const card = el.closest('.chcard');
    const items = [...card.querySelectorAll('.err-item')];
    if (!confirm(`Retirer les ${items.length} erreur(s) de cette chaîne ? Les URL pourront être réimportées plus tard.`)) return;
    for (const item of items){
      try { await api(`/api/videos/${item.dataset.video}/dismiss`, { method: 'POST' }); item.remove(); }
      catch (e){ log(e.message, 'error'); break; }
    }
    refreshHomeCounts();
  }));

  // Connection states fill in as they arrive (one cheap YouTube call each)
  channelData.forEach(async c => {
    const card = grid.querySelector(`.chcard[data-channel="${c.channel}"]`);
    const pill = card.querySelector('[data-role="conn"]');
    const yt = card.querySelector('[data-role="yt"]');
    const chObj = channels.find(x => x.name === c.channel);
    if (chObj && !chObj.has_credentials){
      pill.className = 'pill bad'; pill.textContent = 'Pas de credentials';
      return;
    }
    try {
      const s = await cachedConnectionStatus(c.channel);
      if (s.state === 'connected'){
        pill.className = 'pill ok'; pill.innerHTML = `${icon('check', 11)} Connectée`;
        yt.textContent = s.youtube_channel_title ? `YouTube · ${s.youtube_channel_title}` : '';
      } else {
        const label = { expired: 'Expirée', not_connected: 'Non connectée' }[s.state] || 'Erreur';
        pill.className = `pill ${s.state === 'expired' ? 'warn' : 'bad'}`;
        pill.innerHTML = `${label} · <button type="button">reconnecter</button>`;
        pill.querySelector('button').addEventListener('click', () => goTo(0));
        yt.textContent = s.reason || '';
      }
    } catch (e){
      pill.className = 'pill bad'; pill.textContent = 'Vérification impossible';
    }
  });
}

// After a dismiss: re-read the counts without redrawing the cards (keeps
// open <details> and scroll position).
async function refreshHomeCounts(){
  try {
    const data = await api('/api/overview');
    const t = data.totals;
    document.querySelectorAll('#homeKpis .stat.bad .n').forEach(n => { n.textContent = t.errors; });
    data.channels.forEach(c => {
      const card = document.querySelector(`.chcard[data-channel="${c.channel}"]`);
      if (!card) return;
      const errStat = card.querySelector('.ministat[data-go="errors"]');
      if (errStat){
        errStat.querySelector('.n').textContent = c.counts.errors;
        errStat.classList.toggle('zero', !c.counts.errors);
        errStat.classList.toggle('bad', !!c.counts.errors);
      }
      const details = card.querySelector('details.errs');
      if (details && !c.counts.errors) details.remove();
    });
    if (!t.errors) document.querySelectorAll('#homeKpis .stat.bad').forEach(el => { el.classList.remove('bad'); el.classList.add('zero'); });
  } catch (_) {}
}
