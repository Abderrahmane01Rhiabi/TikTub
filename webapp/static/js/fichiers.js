// ---------- "Déposer le fichier" (failed download → local file) ----------
// One file input for the whole page, outside every re-rendered list (the
// download list redraws every second — an input inside it would vanish
// while the file dialog is open). Buttons just say which video it's for.
let uploadTargetVideo = null;

document.addEventListener('click', ev => {
  const btn = ev.target.closest('[data-upload-source]');
  if (!btn) return;
  ev.preventDefault();
  uploadTargetVideo = btn.dataset.uploadSource;
  const input = document.getElementById('sourceFileInput');
  input.value = '';
  input.click();
});

document.getElementById('sourceFileInput').addEventListener('change', async ev => {
  const file = ev.target.files[0];
  const videoId = uploadTargetVideo;
  uploadTargetVideo = null;
  if (!file || !videoId) return;
  toast(`Envoi de « ${file.name} »…`);
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`/api/videos/${encodeURIComponent(videoId)}/upload_source`, { method: 'POST', body: form });
    checkBuild(res);
    if (!res.ok){
      let detail = await res.text();
      try { detail = JSON.parse(detail).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    log('Fichier déposé — la vidéo continue dans Import → Sélection.', 'success');
    if (currentSpace === 'home') safeLoad(loadHome, 'homeKpis');
    else { pollDownloads(); safeLoad(refreshDownloadedRow, 'downloadedRow'); }
  } catch (e){ log(e.message, 'error'); }
});


// ---------- Réglages → Sauvegardes ----------

const BACKUP_REASON = { auto: ['wait', 'Automatique'], manuelle: ['ok', 'Manuelle'], 'avant restauration': ['warn', 'Avant restauration'] };

async function loadBackups(){
  const box = document.getElementById('backupList');
  box.innerHTML = spinnerHtml('Chargement...');
  const data = await api('/api/backups');
  const status = document.getElementById('backupStatus');
  const age = data.last_age_hours;
  status.className = `fact ${age == null || age > 36 ? 'warn' : ''}`;
  status.innerHTML = `${icon('clock')}<span>${age == null ? 'Aucune sauvegarde pour l\'instant.'
    : `Dernière sauvegarde il y a ${age < 1 ? 'moins d\'une heure' : Math.round(age) + ' h'}.`} Une copie automatique est faite chaque jour ; les ${data.keep} dernières sont gardées.</span>`;
  if (!data.backups.length){
    box.innerHTML = emptyState('Aucune sauvegarde', 'Clique « Sauvegarder maintenant » pour créer la première.', 'inbox');
    return;
  }
  box.innerHTML = `<article class="chcard"><div>${data.backups.map(b => {
    const [cls, label] = BACKUP_REASON[b.reason] || ['wait', b.reason || '—'];
    return `
      <div class="publish-row" data-backup="${esc(b.name)}">
        <span class="name">${esc(formatWhen(b.created_at))}</span>
        <div class="info">
          <span class="pill ${cls}">${esc(label)}</span>
          <span class="when">${(b.size / 1024 / 1024).toFixed(1)} Mo</span>
        </div>
        <div class="row-actions">
          <a class="btn ghost small" style="text-decoration:none" href="/api/backups/${encodeURIComponent(b.name)}/download">${icon('download', 12)} Télécharger</a>
          <button class="btn secondary small" data-restore>${icon('refresh', 12)} Restaurer</button>
        </div>
      </div>`;
  }).join('')}</div></article>`;

  box.querySelectorAll('[data-restore]').forEach(btn => btn.addEventListener('click', async () => {
    const row = btn.closest('[data-backup]');
    const when = row.querySelector('.name').textContent;
    if (!confirm(`Revenir à l'état du ${when} ?\n\nTout ce qui a changé depuis sera remplacé (vidéos, planning, réglages des chaînes). L'état actuel est d'abord sauvegardé : tu pourras revenir en arrière.`)) return;
    btn.disabled = true;
    try {
      const r = await api(`/api/backups/${encodeURIComponent(row.dataset.backup)}/restore`, { method: 'POST' });
      log(`Restauré. L'état d'avant est gardé dans « ${r.safety_backup} ». Recharge de la page…`, 'success');
      setTimeout(() => location.reload(), 1500);
    } catch (e){ btn.disabled = false; log(e.message, 'error'); }
  }));
}

document.getElementById('backupNowBtn').addEventListener('click', async () => {
  const btn = document.getElementById('backupNowBtn');
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Sauvegarde…';
  try {
    const b = await api('/api/backups', { method: 'POST' });
    log(`Sauvegarde créée (${(b.size / 1024 / 1024).toFixed(1)} Mo)`, 'success');
    safeLoad(loadBackups, 'backupList');
  } catch (e){ log(e.message, 'error'); }
  finally { btn.disabled = false; btn.innerHTML = label; }
});


// ---------- Réglages → Stockage ----------

function mo(bytes){ return `${(bytes / 1024 / 1024).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mo`; }

async function loadStorage(){
  const box = document.getElementById('storageView');
  box.innerHTML = spinnerHtml('Analyse du disque…');
  const d = await api('/api/storage');
  const t = d.totals;
  const freeable = t.published.size + t.orphans.size;
  const rows = [
    { label: 'Restes de vidéos déjà publiées', hint: 'fichiers de travail et vidéos finales déjà envoyées sur YouTube', v: t.published, cls: 'ok', free: true },
    { label: 'Fichiers orphelins', hint: 'ne correspondent plus à aucune vidéo (effacés après 24 h)', v: t.orphans, cls: 'ok', free: true },
    { label: 'Vidéos décochées', hint: 'tu les as décochées dans Sélection — effaçables à la demande', v: t.rejected, cls: 'warn' },
    { label: 'Vidéos en cours (gardées)', hint: 'à trier, prêtes, en échec qu\'on peut retraiter, brouillons…', v: t.in_use, cls: 'wait' },
    { label: 'Fonds et musiques des chaînes', hint: 'tes assets de génération — jamais touchés', v: { size: d.assets }, cls: 'wait' },
    { label: 'Sauvegardes', hint: 'les 14 dernières', v: { size: d.backups }, cls: 'wait' },
    { label: 'Base de données', hint: '', v: { size: d.database }, cls: 'wait' },
  ];
  const max = Math.max(...rows.map(r => r.v.size), 1);
  box.innerHTML = `
    <article class="chcard">
      <div class="chcard-head">
        <div class="who"><div class="name">Récupérable maintenant</div>
          <div class="meta" style="margin-left:0">Fait aussi automatiquement chaque jour (restes publiés et orphelins de plus de 24 h).</div></div>
        <span class="pill ${freeable ? 'ok' : 'wait'}">${mo(freeable)}</span>
      </div>
      <div class="gbars">${rows.map(r => `
        <div class="gbar">
          <div class="lbl"><span title="${esc(r.hint)}">${esc(r.label)}${r.v.count != null ? ` <span class="tiny">(${r.v.count})</span>` : ''}</span>
            <div class="track"><div class="fill ${r.free ? '' : 'low'}" style="width:${Math.max(2, r.v.size / max * 100).toFixed(0)}%"></div></div></div>
          <span class="x">${mo(r.v.size)}</span>
        </div>`).join('')}</div>
      <div class="chcard-foot">
        <button class="btn primary small" data-clean="safe" ${freeable ? '' : 'disabled'}>Libérer ${mo(freeable)}</button>
        ${t.rejected.size ? `<button class="btn ghost small danger push" data-clean="rejected" title="Leur fichier source sera effacé : elles disparaîtront de Sélection et ne pourront plus être recochées.">Effacer aussi les ${t.rejected.count} vidéo(s) décochée(s) (${mo(t.rejected.size)})</button>` : ''}
      </div>
    </article>`;
  box.querySelectorAll('[data-clean]').forEach(btn => btn.addEventListener('click', async () => {
    const withRejected = btn.dataset.clean === 'rejected';
    if (withRejected && !confirm('Effacer définitivement les vidéos décochées ? Elles disparaîtront de Sélection et ne pourront plus être recochées (il faudra réimporter le lien).')) return;
    btn.disabled = true;
    try {
      const r = await api('/api/storage/cleanup', { method: 'POST', body: JSON.stringify({ include_rejected: withRejected }) });
      log(`${mo(r.freed_total)} libérés (${r.removed} élément(s))`, 'success');
      safeLoad(loadStorage, 'storageView');
    } catch (e){ btn.disabled = false; log(e.message, 'error'); }
  }));
}
