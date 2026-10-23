// ---------- Dashboard → Ce qui marche (top performers) ----------

let dashView = 'videos';
try { dashView = localStorage.getItem('tiktub.dashView') || 'videos'; } catch (_) {}
let perfData = null;

document.querySelectorAll('#dashViewSeg .seg-opt').forEach(btn => btn.addEventListener('click', () => {
  dashView = btn.dataset.v;
  try { localStorage.setItem('tiktub.dashView', dashView); } catch (_) {}
  applyDashView();
}));

function applyDashView(){
  document.querySelectorAll('#dashViewSeg .seg-opt').forEach(b => b.classList.toggle('active', b.dataset.v === dashView));
  document.getElementById('videosView').style.display = dashView === 'videos' ? '' : 'none';
  document.getElementById('perfView').style.display = dashView === 'perf' ? '' : 'none';
  document.getElementById('versionsView').style.display = dashView === 'versions' ? '' : 'none';
  document.getElementById('channelOverview').style.display = dashView === 'versions' ? 'none' : '';
  if (dashView === 'versions'){ safeLoad(loadVersions, 'versionsView'); return; }   // every channel at once
  if (!dashboardChannel) return;
  if (dashView === 'perf'){
    loadChannelOverview(dashboardChannel);
    safeLoad(() => loadPerformance(dashboardChannel), 'perfView');
  } else {
    loadDashboard(dashboardChannel, true); // also loads the channel overview
  }
}

document.getElementById('dashSyncBtn').addEventListener('click', async () => {
  const btn = document.getElementById('dashSyncBtn');
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Synchronisation…';
  try {
    const r = await api('/api/sync_youtube_statuses', { method: 'POST' });
    const parts = [
      r.published && `${r.published} publiée(s)`, r.private && `${r.private} privée(s)`,
      r.rescheduled && `${r.rescheduled} reprogrammée(s)`, r.deleted && `${r.deleted} supprimée(s) sur YouTube`,
    ].filter(Boolean);
    log(r.checked
      ? `Statuts YouTube : ${r.checked} vérifiée(s) — ${parts.join(', ') || 'rien n\'a changé'}`
        + (r.unreachable ? ` · ${r.unreachable} non vérifiée(s) (chaîne non connectée)` : '')
      : (r.unreachable ? `${r.unreachable} vidéo(s) non vérifiée(s) : chaîne non connectée` : 'Statuts déjà à jour'), 'success');
    applyDashView();
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; btn.innerHTML = label; }
});

function fmtScore(s){
  if (s >= 100) return 'virale';
  return '×' + (s >= 10 ? Math.round(s) : s.toFixed(1).replace('.', ','));
}
function scoreBadge(s){
  const cls = s >= 100 ? 'viral' : s >= 1.5 ? 'up' : s < 0.8 ? 'down' : '';
  return `<span class="score ${cls}" title="${s.toLocaleString('fr-FR')} × la médiane de la chaîne à 7 jours">${fmtScore(s)}</span>`;
}

async function loadPerformance(channelName){
  const box = document.getElementById('perfView');
  box.innerHTML = spinnerHtml('Analyse des performances…');
  perfData = await api(`/api/channels/${channelName}/performance`);
  const ch = channels.find(c => c.name === channelName) || { display_name: channelName };
  const d = perfData;

  if (!d.analyzed){
    box.innerHTML = emptyState('Pas encore assez de recul',
      d.too_recent ? `${d.too_recent} vidéo(s) publiée(s) ont moins de 7 jours — reviens quand elles auront une semaine.` : 'Aucune vidéo publiée sur cette chaîne pour l\'instant.', 'chart');
    return;
  }

  const head = `
    <article class="chcard">
      <div class="chcard-head">
        <div class="who"><div class="name"><span class="dot" style="background:${channelColor(channelName)}"></span>Ce qui marche sur ${esc(ch.display_name)}</div></div>
        <span class="pill wait">${d.analyzed} vidéo${d.analyzed > 1 ? 's' : ''} comparée${d.analyzed > 1 ? 's' : ''}</span>
      </div>
      <div class="facts">
        <div class="fact">${icon('clock')}<span>Toutes comparées au même âge : <b style="color:var(--text)">7 jours après leur publication</b>.</span></div>
        <div class="fact">${icon('gauge')}<span>Une vidéo « habituelle » de la chaîne fait <b style="color:var(--text)">${Math.round(d.median_views_7d).toLocaleString('fr-FR')} vues</b> en 7 jours (médiane) — « ×2 » = deux fois plus.</span></div>
        ${d.median_retention_7d != null
          ? `<div class="fact">${icon('eye')}<span>En moyenne, les gens regardent <b style="color:var(--text)">${fmtPct(d.median_retention_7d)}</b> d'une vidéo la 1re semaine (rétention) — plus c'est haut, plus YouTube la pousse.</span></div>`
          : `<div class="fact">${icon('eye')}<span>Rétention (% regardé) : mesurée automatiquement 9 jours après chaque publication — il faut que la chaîne ait autorisé les statistiques YouTube.</span></div>`}
        ${d.too_recent ? `<div class="fact">${icon('calendar')}<span>${d.too_recent} vidéo(s) trop récente(s) pas encore comptée(s).</span></div>` : ''}
      </div>
    </article>`;

  const insights = d.insights.length ? `
    <div class="grid-3">${d.insights.slice(0, 6).map(insightCardHtml).join('')}</div>`
    : emptyState('Pas encore de tendance', 'Il faut au moins 2 vidéos par option (format, fond, jour…) pour comparer.', 'chart');

  const ranking = `
    <article class="chcard">
      <div class="chcard-head">
        <div class="who"><div class="name">Classement à 7 jours</div><div class="meta" style="margin-left:0">Les meilleures en haut. « Refaire ce style » relance un lot de scripts sur le même modèle.</div></div>
      </div>
      <div>${d.videos.slice(0, 15).map((v, i) => rankRowHtml(v, i)).join('')}</div>
    </article>`;

  box.innerHTML = head + insights + ranking;
  box.querySelectorAll('[data-remake]').forEach(btn => btn.addEventListener('click', () =>
    openRemakeDialog(channelName, d.videos.find(v => v.video_id === btn.dataset.remake))));
  box.querySelectorAll('[data-curve]').forEach(btn => btn.addEventListener('click', () => openFicheDialog(btn.dataset.curve)));
  box.querySelectorAll('[data-remake-ad]').forEach(btn => btn.addEventListener('click', () => openAdaptRemakeDialog(btn.dataset.remakeAd)));
}

// The same Short in one version per channel: an A/B test of the angle and the hook (same pictures)
async function loadVersions(){
  const box = document.getElementById('versionsView');
  box.innerHTML = spinnerHtml('Comparaison des versions…');
  const groups = await api('/api/versions');
  if (!groups.length){
    box.innerHTML = emptyState('Pas encore de Short en plusieurs versions',
      'Crée une Adaptation avec « Une version différente par chaîne » : chaque chaîne aura son angle et son accroche, sur les mêmes images.', 'chart');
    return;
  }
  const chName = c => (channels.find(x => x.name === c) || {}).display_name || c;
  const age = iso => iso ? Math.max(0, Math.floor((Date.now() - new Date(iso)) / 86400000)) : null;
  box.innerHTML = `
    <article class="chcard"><div class="facts">
      <div class="fact">${icon('chart')}<span>Mêmes images, angle et accroche différents : la version qui <b style="color:var(--text)">garde le plus longtemps</b> l'emporte (rétention de la 1re semaine, sinon la part de ceux qui ont commencé que l'accroche garde). Les vues sont comparées à l'habituel de <b style="color:var(--text)">chaque chaîne</b> : un public français et un public arabe ne sont pas de la même taille.</span></div>
    </div></article>
    ${groups.map((g, gi) => `
    <article class="chcard">
      <div class="chcard-head">
        <div class="who"><div class="name">${esc(g.versions[0].titre || 'Short')}</div>
          <div class="meta" style="margin-left:0"><a href="${esc(g.reference_url)}" target="_blank" rel="noopener">Short modèle ↗</a>
          ${g.gagnant ? ` · <b style="color:var(--ok)">${esc(chName(g.versions.find(v => v.video_id === g.gagnant).channel))} garde mieux</b> (+${g.ecart} points, ${esc(g.critere)})`
            : g.critere ? ` · égalité (${esc(g.critere)}, ${g.ecart} point${g.ecart > 1 ? 's' : ''} d'écart)` : ' · pas encore mesuré'}</div></div>
        <button class="btn ghost small" data-cmp="${gi}">${icon('chart', 13)} Comparer les courbes</button>
      </div>
      <div class="chcard-body"><div class="grid-2">${g.versions.map(v => `
        <div class="recap" style="${v.video_id === g.gagnant ? 'border-color:var(--ok)' : ''}">
          <div class="line"><span class="k"><span class="dot" style="background:${channelColor(v.channel)}"></span>${esc(chName(v.channel))}</span>
            <span class="v">${v.youtube_url ? `<a href="${esc(v.youtube_url)}" target="_blank" rel="noopener">voir ↗</a>` : ''}</span></div>
          ${v.angle ? `<div class="line"><span class="k">Angle</span><span class="v">${esc(v.angle)}</span></div>` : ''}
          <div class="line"><span class="k">Accroche</span><span class="v" ${v.langue === 'ar' ? 'dir="rtl"' : ''}>« ${esc(v.accroche || '')} »${v.accroche_s ? ` · ${v.accroche_s} s` : ''}</span></div>
          <div class="line"><span class="k">Durée</span><span class="v">${v.duree_s ? Math.round(v.duree_s) + ' s' : '—'}${v.plans ? ` · ${v.plans} plans` : ''}</span></div>
          <div class="line"><span class="k">Vues</span><span class="v">${v.published && new Date(v.published) > Date.now()
            ? `programmée le ${new Date(v.published).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}`
            : v.views_7d != null ? `${v.views_7d.toLocaleString('fr-FR')} à 7 j ${scoreBadge(v.score)}`
            : v.views_latest != null ? `${v.views_latest.toLocaleString('fr-FR')} en ${age(v.published)} j (7 j pas encore atteints)` : '—'}</span></div>
          <div class="line"><span class="k">Rétention 1re semaine</span><span class="v">${v.retention_7d != null ? fmtPct(v.retention_7d) : 'mesurée à 9 jours'}</span></div>
          <div class="line"><span class="k">Gardés par l'accroche</span><span class="v" title="Part de ceux qui ont commencé la vidéo encore là à la fin de l'accroche">${v.apres_accroche != null ? Math.round(v.apres_accroche) + ' %' : '—'}</span></div>
        </div>`).join('')}</div></div>
    </article>`).join('')}`;
  box.querySelectorAll('[data-cmp]').forEach(b => b.onclick = () => openCompareDialog(groups[+b.dataset.cmp]));
}

async function openCompareDialog(g){
  const dlg = document.getElementById('curveDialog');
  dlg.innerHTML = `<div class="chcard" style="border:none"><div class="chcard-body">${spinnerHtml('Courbes de rétention…')}</div></div>`;
  if (!dlg.open) dlg.showModal();
  const curves = await Promise.all(g.versions.map(v => api(`/api/videos/${v.video_id}/retention`).catch(e => ({ error: e.message, points: [] }))));
  const chName = c => (channels.find(x => x.name === c) || {}).display_name || c;
  const W = 700, H = 240, pad = 30;
  const tint = ['var(--accent)', '#f59e0b', '#4ade80', '#f472b6'];   // two channels can share a colour (both grey)
  const maxY = Math.max(1.2, ...curves.flatMap(c => (c.points || []).map(p => p[1])));
  const X = r => pad + r * (W - pad - 8), Y = w => H - 22 - (w / maxY) * (H - 40);
  const paths = curves.map((c, i) => (c.points || []).length ? `<path d="${c.points.map((p, j) => `${j ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}"
      fill="none" stroke="${tint[i % tint.length]}" stroke-width="2.2"/>` : '').join('');
  dlg.innerHTML = `
    <div class="chcard curve" style="border:none">
      <div class="chcard-head">
        <div class="who"><div class="name">${icon('chart', 15)} Quelle version garde le mieux</div><div class="meta" style="margin-left:0">${esc(g.versions[0].titre || '')}</div></div>
        <button class="btn ghost small" data-act="close">${icon('x', 14)}</button>
      </div>
      <div class="chcard-body">
        ${curves.filter(c => c.error).map(c => `<div class="warnbox">${esc(c.error)}</div>`).join('')}
        <svg class="curve-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Courbes de rétention des versions">
          <line x1="${pad}" y1="${Y(1)}" x2="${W - 8}" y2="${Y(1)}" stroke="var(--muted)" stroke-width=".6" opacity=".6"/>
          <text x="${pad - 4}" y="${Y(1) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">100</text>
          <text x="${pad - 4}" y="${Y(0) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">0</text>
          <text x="${pad}" y="${H - 6}" font-size="10" fill="var(--muted)">début</text>
          <text x="${W - 8}" y="${H - 6}" font-size="10" text-anchor="end" fill="var(--muted)">fin</text>
          ${paths}
        </svg>
        <div style="display:flex;gap:6px 18px;flex-wrap:wrap">${g.versions.map((v, i) => `<span class="tiny"><span class="dot" style="background:${tint[i % tint.length]}"></span>${esc(chName(v.channel))}${curves[i].apres_accroche != null ? ` · l'accroche garde ${Math.round(curves[i].apres_accroche)} %` : ''}</span>`).join('')}</div>
        <div class="tiny">Les deux vidéos n'ont pas forcément la même durée : l'axe va du début à la fin de chacune. Au-dessus de 100, des gens revoient le passage.</div>
      </div>
    </div>`;
  dlg.querySelector('[data-act="close"]').onclick = () => dlg.close();
  hydrateIcons(dlg);
}

// A video's card: its results, where viewers leave (YouTube's curve over its shots), its recipe, its links
function ficheCurveSvg(points, plans, duration, pire){
  const W = 700, H = 220, pad = 30;
  if (!(points || []).length) return '';
  const maxY = Math.max(1.2, ...points.map(p => p[1]));
  const X = r => pad + r * (W - pad - 8), Y = w => H - 22 - (w / maxY) * (H - 40);
  const shots = duration ? (plans || []).filter(p => p.debut != null && p.fin != null).map(p => {
    const x0 = X(p.debut / duration), x1 = X(Math.min(1, p.fin / duration));
    return `${p.k === pire ? `<rect x="${x0}" y="10" width="${Math.max(1, x1 - x0)}" height="${H - 32}" fill="var(--danger)" opacity=".12"/>` : ''}
      <line x1="${x0}" y1="10" x2="${x0}" y2="${H - 22}" stroke="var(--border)" stroke-dasharray="3 3"/>
      <text x="${(x0 + x1) / 2}" y="${H - 6}" font-size="11" text-anchor="middle" fill="var(--muted)">${p.k + 1}</text>`;
  }).join('') : '';
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ');
  return `<svg class="curve-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Courbe de rétention">${shots}
    <line x1="${pad}" y1="${Y(1)}" x2="${W - 8}" y2="${Y(1)}" stroke="var(--muted)" stroke-width=".6" opacity=".6"/>
    <text x="${pad - 4}" y="${Y(1) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">100</text>
    <text x="${pad - 4}" y="${Y(0) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">0</text>
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2.2"/></svg>`;
}

async function openFicheDialog(id, opts = {}){
  const dlg = document.getElementById('curveDialog');
  dlg.innerHTML = `<div class="chcard" style="border:none"><div class="chcard-body">${spinnerHtml('Fiche de la vidéo…')}</div></div>`;
  if (!dlg.open) dlg.showModal();
  const q = opts.youtube ? `youtube_id=${encodeURIComponent(id)}` : `video_id=${encodeURIComponent(id)}`;
  let d;
  try { d = await api(`/api/fiche?${q}${opts.refresh ? '&refresh=true' : ''}`); }
  catch (e){ dlg.innerHTML = `<div class="chcard" style="border:none"><div class="chcard-body"><div class="warnbox">${esc(e.message)}</div><button class="btn ghost small" data-act="close">Fermer</button></div></div>`;
             dlg.querySelector('[data-act="close"]').onclick = () => dlg.close(); return; }
  const rec = d.recette || {}, st = rec.structure || {}, det = rec.details || {}, mus = rec.musique || {}, r = d.resultats || {};
  const chName = c => (channels.find(x => x.name === c) || {}).display_name || c;
  const n = x => x == null ? '—' : Number(x).toLocaleString('fr-FR');
  const worst = (d.plans || []).find(p => p.k === d.courbe.pire);
  const fx = p => [p.fleche && (p.fleche.type === 'cercle' ? '◯ cercle' : '➜ flèche'),
                   ...Object.entries(p.effets_appliques || {}).filter(([k, v]) => v && k !== 'chiffre').map(([k]) => k),
                   (p.effets_appliques || {}).chiffre && `chiffre « ${p.effets_appliques.chiffre} »`].filter(Boolean).join(', ');
  const recipe = [
    rec.type && ['Type', ({adaptation: 'Adaptation', generation: 'Génération', montage: 'Montage auto', import: 'Import'})[rec.type] + (det.mode ? ` · ${det.mode === 'script' ? "Script d'abord" : "Sources d'abord"}` : '')],
    det.angle && ['Angle', det.angle],
    d.duree && ['Durée', `${Math.round(d.duree)} s` + (st.plans > 1 ? ` · ${st.plans} plans · ${st.plan_moyen_s} s par plan` : '')],
    (rec.accroche || {}).texte && ['Accroche', rec.accroche.texte, rec.accroche.duree_s ? `${rec.accroche.duree_s} s` : ''],
    mus.fichier && ['Musique', mus.fichier + (mus.debut_s != null ? ` · à partir de ${mus.debut_s} s` : '') + (mus.gain != null ? ` · niveau ${mus.gain}` : '')],
    (rec.voix || {}).id && ['Voix', d.voix_nom || rec.voix.id],
    (rec.style || {}).visuel && ['Style', rec.style.visuel],
    (det.effets_sonores || []).length && ['Effets sonores', det.effets_sonores.map(e => `${e.son.replace(/\.mp3$/, '')} (${e.pourquoi})`).join(', ')],
  ].filter(Boolean);
  dlg.innerHTML = `
    <div class="chcard curve" style="border:none">
      <div class="chcard-head">
        <div class="who"><div class="name">${icon('film', 15)} Fiche vidéo</div>
          <div class="meta" style="margin-left:0"><span class="dot" style="background:${channelColor(d.channel)}"></span>${esc(chName(d.channel))}${d.publiee ? ` · ${d.a_venir ? 'programmée le' : 'publiée le'} ${new Date(d.publiee).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })}` : ''}</div></div>
        ${rec.type === 'adaptation' ? `<button class="btn secondary small" data-act="remake" title="Un autre Short modèle, fait comme celle-ci">${icon('sparkle', 13)} Refaire ce style</button>` : ''}
        <button class="btn ghost small" data-act="refresh" title="Redemander les chiffres à YouTube">${icon('refresh', 13)}</button>
        <button class="btn ghost small" data-act="close">${icon('x', 14)}</button>
      </div>
      <div class="chcard-body">
        <div style="display:flex;gap:12px;align-items:flex-start">
          ${d.thumbnail_url ? `<img src="${esc(d.thumbnail_url)}" alt="" style="width:96px;border-radius:8px;flex:none">` : ''}
          <div class="stack" style="gap:4px;min-width:0"><b>${esc(d.titre || '')}</b>
            <div class="row" style="display:flex;gap:10px;flex-wrap:wrap">
              ${d.youtube_url ? `<a href="${esc(d.youtube_url)}" target="_blank" rel="noopener">YouTube ↗</a>` : ''}
              ${d.modele_url ? `<a href="${esc(d.modele_url)}" target="_blank" rel="noopener">Short modèle ↗</a>` : ''}
              ${d.source_url ? `<a href="${esc(d.source_url)}" target="_blank" rel="noopener">Source ↗</a>` : ''}
              ${(d.versions || []).map(v => `<a href="#" data-other="${esc(v.video_id)}">Version ${esc(chName(v.channel))} →</a>`).join('')}
            </div></div>
        </div>
        <div class="recap">
          <div class="line"><span class="k">Vues à 7 jours</span><span class="v">${r.vues_7j != null ? `${n(r.vues_7j)} ${scoreBadge(r.score)}` : d.a_venir ? 'pas encore publiée' : '7 jours pas encore atteints'}</span></div>
          <div class="line"><span class="k">Vues aujourd'hui</span><span class="v">${n(r.vues)} · ${n(r.likes)} likes · ${n(r.commentaires)} commentaires</span></div>
          ${r.mediane_chaine != null ? `<div class="line"><span class="k">Habituel de la chaîne</span><span class="v">${n(Math.round(r.mediane_chaine))} vues à 7 jours</span></div>` : ''}
          <div class="line"><span class="k">Rétention 1re semaine</span><span class="v">${r.retention_7j != null ? `${Math.round(r.retention_7j)} % regardé` + (r.temps_moyen_s ? ` (${Math.round(r.temps_moyen_s)} s en moyenne)` : '') : 'mesurée 9 jours après la publication'}</span></div>
          ${r.accroche_garde != null ? `<div class="line"><span class="k">L'accroche garde</span><span class="v">${Math.round(r.accroche_garde)} % de ceux qui commencent</span></div>` : ''}
        </div>
        ${d.courbe.error ? `<div class="warnbox">${esc(d.courbe.error)}</div>` : ''}
        ${ficheCurveSvg(d.courbe.points, d.plans, d.duree, d.courbe.pire)}
        ${worst ? `<div class="warnbox" style="border-color:var(--danger)">Le plan ${worst.k + 1} perd le plus de monde : ${worst.perte} points en ${(worst.fin - worst.debut).toFixed(1)} s${worst.texte ? ` — « ${esc(worst.texte)} »` : ''}.</div>` : ''}
        ${(d.plans || []).length > 1 ? `<div><div class="tiny" style="margin-bottom:4px">Plan par plan${d.courbe.points.length ? ' (spectateurs au début → à la fin du plan)' : ''}</div>${d.plans.map(p => `
          <div class="shot-row ${p.k === d.courbe.pire ? 'worst' : ''}" style="grid-template-columns:28px 92px 1fr 70px"><b>${p.k + 1}</b>
            <span>${p.debut != null ? `${Number(p.debut).toFixed(1)}–${Number(p.fin).toFixed(1)} s` : ''}</span>
            <span class="t" title="${esc((p.bandeau || '') + ' — ' + (p.texte || ''))}"><bdi>${p.bandeau ? `<b>${esc(p.bandeau)}</b> · ` : ''}${esc(p.texte || '')}</bdi>${fx(p) ? ` <span class="tiny">· ${esc(fx(p))}</span>` : ''}</span>
            <span>${p.debut_pct != null ? `${Math.round(p.debut_pct)} → ${Math.round(p.fin_pct)}` : ''}</span></div>`).join('')}</div>` : ''}
        ${recipe.length ? `<div class="recap">${recipe.map(([k, v, extra]) => `<div class="line"><span class="k">${esc(k)}</span><span class="v"><bdi>${esc(String(v))}</bdi>${extra ? ` · ${esc(extra)}` : ''}</span></div>`).join('')}</div>` : ''}
        ${d.description ? `<details><summary class="tiny" style="cursor:pointer">Description et tags</summary><div class="tiny" style="white-space:pre-wrap;margin-top:6px">${esc(d.description)}</div>
          ${(d.tags || []).length ? `<div class="dvtags" style="margin-top:6px">${d.tags.map(t => `<span>${esc(t)}</span>`).join('')}</div>` : ''}</details>` : ''}
      </div>
    </div>`;
  dlg.querySelector('[data-act="close"]').onclick = () => dlg.close();
  dlg.querySelector('[data-act="refresh"]').onclick = () => openFicheDialog(id, { ...opts, refresh: true });
  const remake = dlg.querySelector('[data-act="remake"]');
  if (remake) remake.onclick = () => { dlg.close(); openAdaptRemakeDialog(d.video_id); };
  dlg.querySelectorAll('[data-other]').forEach(a => a.onclick = ev => { ev.preventDefault(); openFicheDialog(a.dataset.other); });
  hydrateIcons(dlg);
}

function fmtPct(x){ return `${Math.round(x)} %`; }

function insightCardHtml(ins){
  const max = Math.max(...ins.groups.map(g => g.score), 1);
  const best = ins.best;
  return `
  <article class="chcard perf-insight">
    <div class="chcard-head">
      <div class="who"><div class="name" style="font-size:12.5px;color:var(--muted);font-weight:600">${esc(ins.label)}</div></div>
      ${best.reliable ? '' : '<span class="pill warn" title="Moins de 3 vidéos dans ce groupe">Peu de données</span>'}
    </div>
    <div class="best">
      <span class="v" title="${esc(best.label)}">${esc(best.label)}</span>
      <span class="s">${fmtScore(best.score)} la médiane · ${best.count} vidéos · ${Math.round(best.median_views_7d).toLocaleString('fr-FR')} vues typiques${best.median_retention_7d != null ? ` · ${fmtPct(best.median_retention_7d)} regardé` : ''}</span>
    </div>
    <div class="gbars">
      ${ins.groups.slice(0, 5).map(g => `
        <div class="gbar">
          <div class="lbl"><span title="${esc(g.label)}">${esc(g.label)} <span class="tiny">(${g.count})</span></span>
            <div class="track"><div class="fill ${g.score < 1 ? 'low' : ''}" style="width:${Math.max(4, Math.min(100, g.score / max * 100)).toFixed(0)}%"></div></div></div>
          <span class="x">${fmtScore(g.score)}</span>
        </div>`).join('')}
    </div>
  </article>`;
}

function rankRowHtml(v, i){
  const a = v.attrs;
  const chips = [
    a.script_format && `Format ${a.script_format}`, a.background && `Fond ${a.background}`,
    a.caption_style && `Sous-titres ${a.caption_style}`, a.weekday && `${a.weekday} ${a.hour_slot || ''}`,
  ].filter(Boolean);
  return `
  <div class="rank-row">
    <span class="n">${i + 1}</span>
    <div class="th" style="${v.thumbnail_url ? `background-image:url('${v.thumbnail_url}')` : ''}"></div>
    <div class="t">
      ${v.youtube_url ? `<a href="${v.youtube_url}" target="_blank" rel="noopener" title="${esc(v.title)}">${esc(v.title)}</a>` : `<a title="${esc(v.title)}">${esc(v.title)}</a>`}
      <div class="chips">${chips.map(c => `<span title="${esc(c)}">${esc(c)}</span>`).join('')}</div>
    </div>
    <div class="views"><b>${v.views_7d.toLocaleString('fr-FR')}</b>vues à 7 j ${scoreBadge(v.score)}${v.retention_7d != null ? `<span class="ret" title="Part moyenne de la vidéo regardée la 1re semaine">${fmtPct(v.retention_7d)} regardé</span>` : ''}</div>
    <div class="stack" style="gap:4px">
      ${v.youtube_url ? `<button class="btn ghost small" data-curve="${esc(v.video_id)}" title="Ses résultats, où les gens décrochent plan par plan, sa recette">${icon('chart', 13)} Fiche vidéo</button>` : ''}
      ${v.remakeable ? `<button class="btn secondary small" data-remake="${esc(v.video_id)}">${icon('sparkle', 13)} Refaire ce style</button>` : ''}
      ${v.remake_adaptation ? `<button class="btn secondary small" data-remake-ad="${esc(v.video_id)}" title="Un autre Short modèle, fait comme celle-ci">${icon('sparkle', 13)} Refaire ce style</button>` : ''}
    </div>
  </div>`;
}

let genPreferredBatch = null; // opens Génération on the batch just launched from here

function openRemakeDialog(channelName, v, suggestion){
  const dlg = document.getElementById('remakeDialog');
  const a = v.attrs;
  const reused = suggestion ? [] : [
    a.script_format && ['Format et structure du script', `${a.script_format} · ${({A: 'Affirmations', B: 'Storytime', D: 'Liste éducative'})[a.script_format] || ''}`],
    a.background && ['Fond vidéo', a.background],
    a.music && ['Musique', a.music],
    a.caption_style && ['Sous-titres', a.caption_style],
  ].filter(Boolean);
  dlg.innerHTML = `
    <div class="chcard" style="border:none">
      <div class="chcard-head">
        <div class="who"><div class="name">${icon('sparkle', 15)} Refaire ce style</div><div class="meta" style="margin-left:0">${esc(v.title)} · ${v.views_7d.toLocaleString('fr-FR')} vues à 7 j</div></div>
        <button class="btn ghost small" data-act="close">${icon('x', 14)}</button>
      </div>
      <div class="chcard-body">
        <div class="muted">L'IA écrit de <b style="color:var(--text)">nouveaux scripts sur d'autres sujets</b>, en reprenant ${suggestion ? 'la recette qui marche le mieux sur la chaîne' : 'ce qui a fait marcher celui-ci'} :</div>
        ${suggestion ? recipeHtml(suggestion.recipe) : `<div class="recap">${reused.map(([k, val]) => `<div class="line"><span class="k">${esc(k)}</span><span class="v">${esc(val)}</span></div>`).join('')}</div>`}
        <div class="tiny">Le décor est pré-rempli à l'étape Décor et reste modifiable. Rien n'est envoyé à ElevenLabs avant que tu valides les scripts.</div>
        <div><label class="f">Nombre de vidéos</label><input class="f" type="number" data-role="count" value="3" min="1" max="${MAX_BATCH_COUNT}" style="width:90px"></div>
        <span class="tiny" data-role="err" style="color:var(--danger)"></span>
      </div>
      <div class="chcard-foot">
        <button class="btn ghost small" data-act="close">Annuler</button>
        <button class="btn primary small push" data-act="go">Écrire les scripts →</button>
      </div>
    </div>`;
  dlg.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => dlg.close()));
  dlg.querySelector('[data-act="go"]').addEventListener('click', async () => {
    const count = Math.max(1, Math.min(MAX_BATCH_COUNT, parseInt(dlg.querySelector('[data-role="count"]').value, 10) || 1));
    const go = dlg.querySelector('[data-act="go"]');
    go.disabled = true;
    try {
      const res = await api(`/api/channels/${channelName}/generation_draft`, { method: 'POST', body: JSON.stringify({ count, inspired_by: v.video_id, recipe: suggestion ? suggestion.recipe_values : null }) });
      dlg.close();
      log(`${count} script(s) en cours d'écriture dans le style de « ${v.title} »`, 'success');
      genChannel = channelName;
      genPreferredBatch = res.batch_id;
      openSpace('generation');
    } catch (e){ go.disabled = false; dlg.querySelector('[data-role="err"]').textContent = e.message; }
  });
  dlg.showModal();
}

// "Refaire ce style" for an Adaptation: another model Short, made with the same
// channels, mode, voices, music and look (subject, script, angle: from the new Short)
async function openAdaptRemakeDialog(videoId){
  const dlg = document.getElementById('remakeDialog');
  dlg.innerHTML = `<div class="chcard" style="border:none"><div class="chcard-body">${spinnerHtml('Ce qui sera repris…')}</div></div>`;
  if (!dlg.open) dlg.showModal();
  let st;
  try { st = await api(`/api/videos/${encodeURIComponent(videoId)}/remake_style`); }
  catch (e){ dlg.innerHTML = `<div class="chcard" style="border:none"><div class="chcard-body"><div class="warnbox">${esc(e.message)}</div><button class="btn ghost small" data-act="close">Fermer</button></div></div>`;
             dlg.querySelector('[data-act="close"]').onclick = () => dlg.close(); return; }
  const per = Object.values(st.par_chaine);
  const lines = [
    ['Mode', st.mode === 'script' ? "Script d'abord" : "Sources d'abord"],
    ['Chaînes', per.map(s => s.chaine_nom).join(' + ') + (st.versions ? ' (une version par chaîne)' : '')],
    ...per.flatMap(s => [
      [`Voix · ${s.chaine_nom}`, s.voix_nom || 'celle de la chaîne'],
      [`Musique · ${s.chaine_nom}`, s.music_file ? `${s.music_file}${s.music_start != null ? ` · à partir de ${s.music_start} s` : ''}` : "choisie par l'IA"],
      [`Style · ${s.chaine_nom}`, s.style || 'celui de la chaîne'],
    ]),
  ];
  dlg.innerHTML = `
    <div class="chcard" style="border:none">
      <div class="chcard-head">
        <div class="who"><div class="name">${icon('sparkle', 15)} Refaire ce style</div><div class="meta" style="margin-left:0">Un autre Short modèle, fait comme celle-ci</div></div>
        <button class="btn ghost small" data-act="close">${icon('x', 14)}</button>
      </div>
      <div class="chcard-body">
        <div class="muted">Repris de cette vidéo :</div>
        <div class="recap">${lines.map(([k, v]) => `<div class="line"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('')}</div>
        <div class="tiny">Le sujet, le script et l'angle viennent du nouveau Short. Les effets suivent les règles habituelles.</div>
        <div><label class="f">Lien du nouveau Short modèle</label><input class="f" type="url" data-role="url" placeholder="https://www.youtube.com/shorts/…"></div>
        <span class="tiny" data-role="err" style="color:var(--danger)"></span>
      </div>
      <div class="chcard-foot">
        <button class="btn ghost small" data-act="close">Annuler</button>
        <button class="btn primary small push" data-act="go">Lancer l'adaptation →</button>
      </div>
    </div>`;
  dlg.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = () => dlg.close());
  const go = dlg.querySelector('[data-act="go"]'), err = dlg.querySelector('[data-role="err"]');
  go.onclick = async () => {
    const url = dlg.querySelector('[data-role="url"]').value.trim();
    if (!/^https?:\/\//.test(url)) { err.textContent = 'Colle le lien du Short modèle.'; return; }
    go.disabled = true; err.textContent = '';
    try {
      const p = await api('/api/adaptations/remake', { method: 'POST', body: JSON.stringify({ video_id: videoId, reference_url: url }) });
      dlg.close();
      log("Adaptation lancée dans le style de la vidéo qui a marché", 'success');
      adCurrent = p.project_id; adProject = null;
      openSpace('adaptation');
    } catch (e){ go.disabled = false; err.textContent = e.message; }
  };
  hydrateIcons(dlg);
}
