// ---------- Boot ----------

// ---------- Alerts (polled; also shown as Windows notifications if allowed) ----------
const ALERT_POLL_MS = 60000;
const ALERT_ACTIONS = {
  connection: { label: 'Reconnecter', run: () => goTo(0) },
  publish: { label: 'Voir Publier', run: () => goTo(7) },
  deleted: { label: 'Voir le Dashboard', run: a => { if (a.channel) dashboardChannel = a.channel; openSpace('dashboard'); } },
};

function notifiedAlerts(){
  try { return new Set(JSON.parse(localStorage.getItem('tiktub.alerts.notified') || '[]')); } catch { return new Set(); }
}
function notifyNewAlerts(list){
  const seen = notifiedAlerts();
  const fresh = list.filter(a => !seen.has(a.key + a.created_at));
  if (!fresh.length) return;
  if ('Notification' in window && Notification.permission === 'granted'){
    fresh.slice(0, 3).forEach(a => {
      try {
        const n = new Notification(`TikTub — ${a.title}`, { body: a.message || '', tag: a.key });
        n.onclick = () => { window.focus(); n.close(); };
      } catch {}
    });
  }
  fresh.forEach(a => seen.add(a.key + a.created_at));
  try { localStorage.setItem('tiktub.alerts.notified', JSON.stringify([...seen].slice(-200))); } catch {}
}

async function loadAlerts(){
  const bar = document.getElementById('alertBar');
  let list;
  try { list = await api('/api/alerts'); } catch { return; }  // a hiccup must not blank the bar
  notifyNewAlerts(list);
  const canAsk = list.length && 'Notification' in window && Notification.permission === 'default';
  bar.innerHTML = list.map((a, i) => {
    const act = ALERT_ACTIONS[a.kind];
    return `
    <div class="alert-item ${esc(a.kind)}" data-i="${i}">
      ${icon('alert', 18)}
      <div class="txt"><b>${esc(a.title)}</b><span>${esc(a.message || '')}</span></div>
      <div class="acts">
        ${act ? `<button class="btn secondary small" data-act="go">${esc(act.label)}</button>` : ''}
        <button class="btn ghost small" data-act="ok" title="Masquer — elle reviendra si le problème réapparaît après avoir été réglé">OK</button>
      </div>
    </div>`;
  }).join('') + (canAsk ? `<button class="btn ghost small alert-notif" data-act="notif">${icon('bell', 13)} Recevoir aussi ces alertes en notification Windows</button>` : '');
  bar.querySelectorAll('.alert-item').forEach(el => {
    const a = list[+el.dataset.i];
    el.querySelector('[data-act="go"]')?.addEventListener('click', () => ALERT_ACTIONS[a.kind].run(a));
    el.querySelector('[data-act="ok"]').addEventListener('click', async () => {
      el.remove();
      try { await api(`/api/alerts/${encodeURIComponent(a.key)}/dismiss`, { method: 'POST' }); } catch {}
      loadAlerts();
    });
  });
  bar.querySelector('[data-act="notif"]')?.addEventListener('click', async () => {
    try { await Notification.requestPermission(); } catch {}
    loadAlerts();
  });
}

async function boot(){
  hydrateIcons(); // tabs + static buttons declared with data-icon
  channels = await api('/api/channels');
  if (!channels.some(ch => ch.generation_mode)) document.getElementById('generationBtn').style.display = 'none';
  renderUrlsGrid();
  await refreshDownloadedRow();
  openSpace('home');
  loadAlerts();
  setInterval(loadAlerts, ALERT_POLL_MS);
}
boot()
  .catch(e => log(e.message, 'error'))
  .finally(() => document.getElementById('bootOverlay').classList.add('hidden'));
