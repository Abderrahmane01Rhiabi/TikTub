// ---------- Dashboard : published videos + live YouTube stats ----------

const dashboardScreen = document.getElementById('dashboardScreen');
let dashboardChannel = null;
let dashVideos = [];
let dashFilter = 'all';

document.getElementById('dashBackBtn').addEventListener('click', () => openSpace('home'));
document.getElementById('dashRefreshBtn').addEventListener('click', () => applyDashView());
document.querySelectorAll('#dashFilterSeg .seg-opt').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('#dashFilterSeg .seg-opt').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  dashFilter = btn.dataset.f;
  renderDashGrid();
}));

function dashCategory(v){
  const ps = v.privacy_status || (v.local_status === 'scheduled_on_youtube' ? 'private' : v.local_status === 'uploaded' ? 'public' : null);
  if (ps === 'public') return 'public';
  if (ps === 'private') return v.publish_at ? 'scheduled' : 'private';
  return 'unknown';
}
function openDashboard(){
  screens.forEach(el => el.classList.remove('active'));
  dashboardScreen.classList.add('active');
  if (!dashboardChannel && channels.length) dashboardChannel = channels[0].name;
  renderDashChannelChips();
  applyDashView();
}

function renderDashChannelChips(){
  const seg = document.getElementById('dashChannelSeg');
  seg.innerHTML = channels.map(ch => `
    <button class="seg-opt ${ch.name === dashboardChannel ? 'active' : ''}" data-ch="${ch.name}">
      <span class="dot" style="background:${channelColor(ch.name)};display:inline-block;margin-right:5px"></span>${esc(ch.display_name)}
    </button>`).join('');
  seg.querySelectorAll('.seg-opt').forEach(btn => btn.addEventListener('click', () => {
    dashboardChannel = btn.dataset.ch;
    renderDashChannelChips();
    applyDashView();
  }));
}

let dashAnalyticsAvailable = false;

async function loadDashboard(channelName, refresh){
  const grid = document.getElementById('dashGrid');
  const note = document.getElementById('dashNote');
  grid.innerHTML = spinnerHtml('Chargement...');
  try {
    const data = await api(`/api/channels/${channelName}/dashboard${refresh ? '?refresh=true' : ''}`);
    dashVideos = data.videos;
    dashAnalyticsAvailable = !!data.analytics_available;
    renderDashGrid();
    note.textContent = refresh
      ? (data.stats_available ? 'Stats à jour' : 'Chaîne non connectée — stats indisponibles')
      : (data.videos.length ? 'Clique "Actualiser les stats" pour charger vues/likes réels' : '');
    loadChannelOverview(channelName);
  } catch (e){
    showLoadError(grid, e, () => loadDashboard(channelName, refresh));
    log(e.message, 'error');
  }
}

async function loadChannelOverview(channelName){
  const box = document.getElementById('channelOverview');
  box.innerHTML = '';
  try {
    const data = await api(`/api/channels/${channelName}/channel_analytics?days=30`);
    box.innerHTML = renderChannelOverview(data);
    box.querySelector('details').addEventListener('toggle', ev => {
      try { localStorage.setItem(OVERVIEW_OPEN_KEY, ev.target.open ? '1' : '0'); } catch (_) {}
    });
  } catch (e){
    // 403 (scope not granted yet) or not connected — just hide the section
    box.innerHTML = '';
  }
}

function renderDailyViewsSvg(daily){
  if (!daily.length) return '<span class="empty-note">Pas de données.</span>';
  // Drawn in a fixed coordinate space and stretched to the card's full
  // width; non-scaling-stroke keeps the line thin whatever the width.
  const w = 1000, h = 90, pad = 6;
  const maxY = Math.max(1, ...daily.map(p => p.views));
  const stepX = (w - pad * 2) / Math.max(1, daily.length - 1);
  const pts = daily.map((p, i) => {
    const x = pad + i * stepX;
    const y = h - pad - (p.views / maxY) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="display:block">
    <polyline points="${pts}" fill="none" stroke="#6d8dfd" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
  </svg>`;
}

// YouTube Analytics traffic source codes → readable French labels
const TRAFFIC_LABELS = {
  YT_SEARCH: 'Recherche YouTube', SHORTS: 'Fil Shorts', YT_CHANNEL: 'Page de la chaîne', EXT_URL: 'Sites externes',
  PLAYLIST: 'Playlists', YT_OTHER_PAGE: 'Autres pages YouTube', RELATED_VIDEO: 'Vidéos suggérées',
  SUBSCRIBER: 'Abonnés (accueil, notifications)', NOTIFICATION: 'Notifications', NO_LINK_OTHER: 'Accès direct / inconnu',
  BROWSE: 'Accueil YouTube', YT_PLAYLIST_PAGE: 'Page de playlist', END_SCREEN: 'Écrans de fin', HASHTAGS: 'Hashtags',
  SOUND_PAGE: 'Page du son', ADVERTISING: 'Publicité', CAMPAIGN_CARD: 'Fiches de campagne', ANNOTATION: 'Annotations',
};

const OVERVIEW_OPEN_KEY = 'tiktub.dashOverviewOpen';
function overviewOpen(){
  try { return localStorage.getItem(OVERVIEW_OPEN_KEY) !== '0'; } catch (_) { return true; }
}

function renderChannelOverview(data){
  const t = data.totals || {};
  const fmt = v => typeof v === 'number' ? v.toLocaleString() : v;
  const tiles = [
    ['Abonnés', data.subscriber_count ?? '—'],
    ['Vues (30 j)', t.views ?? '—'],
    ['Minutes regardées', t.estimated_minutes_watched ?? '—'],
    // Shorts replay in a loop, so this can exceed 100 %
    ['% moyen regardé', t.average_view_percentage != null ? t.average_view_percentage.toFixed(1) + ' %' : '—'],
    ['Abonnés gagnés', t.subscribers_gained ?? '—'],
    ['Abonnés perdus', t.subscribers_lost ?? '—'],
  ];
  const traffic = (data.traffic_sources || []).slice().sort((a, b) => b.views - a.views).slice(0, 6);
  const topVideos = data.top_videos || [];
  const summary = [
    data.subscriber_count != null && `${fmt(data.subscriber_count)} abonnés`,
    t.views != null && `${fmt(t.views)} vues`,
    t.average_view_percentage != null && `${t.average_view_percentage.toFixed(0)} % regardé`,
  ].filter(Boolean).join(' · ');

  return `
  <details class="chcard overview-card" ${overviewOpen() ? 'open' : ''}>
    <summary class="overview-summary">
      ${icon('chevron')}
      <span class="name" style="font-size:13px;font-weight:700">Vue d'ensemble · 30 derniers jours</span>
      <span class="overview-mini">${esc(summary)}</span>
    </summary>
    <div class="analytics-grid" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      ${tiles.map(([label, val]) => `<div class="astat"><span class="alabel">${label}</span><span class="aval">${esc(fmt(val))}</span></div>`).join('')}
    </div>
    <div class="asection">
      <div class="atitle">Vues par jour</div>
      ${renderDailyViewsSvg(data.daily_views || [])}
    </div>
    <div style="display:flex;gap:28px;flex-wrap:wrap">
      <div class="asection" style="flex:1;min-width:200px">
        <div class="atitle">Sources de trafic</div>
        ${traffic.length ? traffic.map(s => `<div class="aline"><span title="${esc(s.type)}">${esc(TRAFFIC_LABELS[s.type] || s.type)}</span><span>${fmt(s.views)}</span></div>`).join('') : '<span class="empty-note">Aucune donnée.</span>'}
      </div>
      <div class="asection" style="flex:2;min-width:260px">
        <div class="atitle">Meilleures vidéos (30 j)</div>
        ${topVideos.length ? topVideos.map(v => `<div class="aline"><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1;margin-right:12px">${esc(v.title)}</span><span style="flex:none">${fmt(v.views)} vues</span></div>`).join('') : '<span class="empty-note">Aucune donnée.</span>'}
      </div>
    </div>
  </details>`;
}

function renderDashGrid(){
  const grid = document.getElementById('dashGrid');
  const channelName = dashboardChannel;
  const videos = dashFilter === 'all' ? dashVideos : dashVideos.filter(v => dashCategory(v) === dashFilter);

  if (!dashVideos.length){ grid.innerHTML = emptyState('Aucune vidéo publiée', 'Rien n\'a encore été publié sur cette chaîne depuis TikTub.', 'chart'); return; }
  if (!videos.length){ grid.innerHTML = emptyState('Aucune vidéo dans ce filtre', '', 'chart'); return; }

  grid.innerHTML = videos.map(v => {
    const cat = dashCategory(v);
    const status = cat === 'public' ? ['ok', 'globe', 'Publique'] : cat === 'scheduled' ? ['warn', 'calendar', 'Programmée']
      : cat === 'private' ? ['wait', 'lock', 'Privée'] : ['wait', 'clock', v.local_status || '—'];
    const thumbStyle = v.thumbnail_url
      ? `background-image:url('${v.thumbnail_url}')`
      : `background:linear-gradient(160deg,${channelColor(channelName)},#171a21 120%)`;
    const currentPrivacy = v.privacy_status || (cat === 'scheduled' ? 'private' : cat === 'public' ? 'public' : 'private');
    // No re-scheduling here — YouTube's API refuses a new publishAt on a video
    // that already went through a publish cycle once (confirmed by testing).
    // Only immediate private ⇄ public is offered; real scheduling happens once,
    // at upload time, in the Planning/Publier steps.
    const toggleLabel = currentPrivacy === 'public' ? 'Rendre privée' : 'Rendre publique';
    const toggleTarget = currentPrivacy === 'public' ? 'private' : 'public';
    const when = v.published_at || v.scheduled_time;

    return `
    <div class="dvcard" data-yid="${v.youtube_id}">
      <div class="dvthumb" style="${thumbStyle}"></div>
      <div class="dvbody">
        <div style="display:flex;align-items:center;gap:8px;justify-content:space-between">
          <span class="pill ${status[0]}">${icon(status[1], 11)} ${esc(status[2])}</span>
          ${when ? `<span class="dvmeta">${esc(formatWhen(when))}</span>` : ''}
        </div>
        <div class="dvtitle">${esc(v.title)}</div>
        <div class="dvstats">
          ${v.view_count != null ? `<span title="Vues">${icon('eye', 12)}<b>${v.view_count.toLocaleString()}</b></span>` : ''}
          ${v.like_count != null ? `<span title="Likes">${icon('thumb', 12)}<b>${v.like_count.toLocaleString()}</b></span>` : ''}
          ${v.comment_count != null ? `<span title="Commentaires">${icon('comment', 12)}<b>${v.comment_count.toLocaleString()}</b></span>` : ''}
        </div>
        <div class="dvtags">${(v.tags || []).slice(0, 5).map(t => `<span>${esc(t)}</span>`).join('')}</div>
      </div>
      <div class="dvedit" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
        <button class="btn secondary small dv-toggle" data-target="${toggleTarget}">${toggleLabel}</button>
        ${dashAnalyticsAvailable ? `<button class="btn ghost small dv-analytics-toggle">Stats détaillées</button>` : ''}
        <button class="btn ghost small dv-fiche" title="Résultats, courbe plan par plan et recette (vidéos faites avec TikTub)">${icon('chart', 12)} Fiche</button>
        ${v.youtube_url ? `<a class="btn ghost small" style="margin-left:auto;text-decoration:none" href="${v.youtube_url}" target="_blank" rel="noopener">${icon('link', 12)} YouTube</a>` : ''}
      </div>
      ${dashAnalyticsAvailable ? `<div class="dv-analytics-panel" style="display:none"></div>` : ''}
    </div>`;
  }).join('');

  grid.querySelectorAll('.dvcard').forEach(card => {
    const yid = card.dataset.yid;
    card.querySelector('.dv-fiche').addEventListener('click', () => openFicheDialog(yid, { youtube: true }));
    card.querySelector('.dv-toggle').addEventListener('click', async (e) => {
      const btn = e.target;
      const privacy_status = btn.dataset.target;
      btn.disabled = true; btn.textContent = '...';
      try {
        await api(`/api/channels/${dashboardChannel}/videos/${yid}/visibility`, {
          method: 'PATCH', body: JSON.stringify({ privacy_status, publish_at: null })
        });
        log('Vidéo mise à jour', 'success');
        loadDashboard(dashboardChannel, true);
      } catch (e2){
        log(e2.message, 'error');
        btn.disabled = false; btn.textContent = privacy_status === 'public' ? 'Rendre publique' : 'Rendre privée';
      }
    });

    const analyticsBtn = card.querySelector('.dv-analytics-toggle');
    if (analyticsBtn) analyticsBtn.addEventListener('click', async () => {
      const panel = card.querySelector('.dv-analytics-panel');
      if (panel.dataset.loaded === '1'){
        const showing = panel.style.display !== 'none';
        panel.style.display = showing ? 'none' : 'block';
        analyticsBtn.textContent = showing ? 'Stats détaillées' : 'Masquer les stats';
        return;
      }
      analyticsBtn.disabled = true;
      analyticsBtn.innerHTML = '<span class="spinner"></span> Chargement...';
      try {
        const data = await api(`/api/channels/${dashboardChannel}/videos/${yid}/analytics`);
        panel.innerHTML = renderAnalyticsPanel(data);
        panel.dataset.loaded = '1';
        panel.style.display = 'block';
        analyticsBtn.textContent = 'Masquer les stats';
      } catch (e2){
        log(e2.message, 'error');
        analyticsBtn.textContent = 'Stats détaillées';
      } finally {
        analyticsBtn.disabled = false;
      }
    });
  });
}

function renderRetentionSvg(curve){
  if (!curve.length) return '<span class="empty-note">Pas de données de rétention.</span>';
  const w = 260, h = 80, pad = 4;
  const maxY = Math.max(1, ...curve.map(p => p.watch_ratio));
  const pts = curve.map(p => {
    const x = pad + p.elapsed_ratio * (w - pad * 2);
    const y = h - pad - (p.watch_ratio / maxY) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="display:block;max-width:100%">
    <polyline points="${pts}" fill="none" stroke="#6d8dfd" stroke-width="1.6"/>
  </svg>`;
}

function renderAnalyticsPanel(data){
  const t = data.totals || {};
  const rows = [
    ['Vues', t.views ?? '—'],
    ['⏱ Minutes regardées', t.estimated_minutes_watched ?? '—'],
    ['⏳ Durée moy. de visionnage', (t.average_view_duration ?? '—') + 's'],
    ['📈 % moyen regardé', t.average_view_percentage != null ? t.average_view_percentage.toFixed(1) + '%' : '—'],
    ['Likes', t.likes ?? '—'],
    ['Commentaires', t.comments ?? '—'],
    ['➕ Abonnés gagnés', t.subscribers_gained ?? '—'],
    ['➖ Abonnés perdus', t.subscribers_lost ?? '—'],
  ];
  const traffic = (data.traffic_sources || []).slice().sort((a, b) => b.views - a.views).slice(0, 6);
  const terms = (data.search_terms || []).slice(0, 8);

  return `
    <div class="analytics-grid">
      ${rows.map(([label, val]) => `<div class="astat"><span class="alabel">${label}</span><span class="aval">${esc(val)}</span></div>`).join('')}
    </div>
    <div class="asection">
      <div class="atitle">Sources de trafic</div>
      ${traffic.length ? traffic.map(s => `<div class="aline"><span>${esc(s.type)}</span><span>${s.views}</span></div>`).join('') : '<span class="empty-note">Aucune donnée.</span>'}
    </div>
    <div class="asection">
      <div class="atitle">Termes de recherche réels</div>
      ${terms.length ? terms.map(s => `<div class="aline"><span>${esc(s.term)}</span><span>${s.views}</span></div>`).join('') : '<span class="empty-note">Aucune donnée (pas assez de trafic recherche).</span>'}
    </div>
    <div class="asection">
      <div class="atitle">Courbe de rétention</div>
      ${renderRetentionSvg(data.retention_curve || [])}
    </div>
  `;
}
