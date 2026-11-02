/* Display preferences only. No itinerary, quotes or financial data are stored here. */
(() => {
  const root = document.body;
  const key = 'furlong.workspace.preferences.v1';
  const defaults = {density: 'compact', showNotes: true, showTimeline: true};
  let prefs = {...defaults};
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '{}');
    if (saved && typeof saved === 'object') {
      if (['compact', 'detailed'].includes(saved.density)) prefs.density = saved.density;
      for (const field of ['showNotes', 'showTimeline']) {
        if (typeof saved[field] === 'boolean') prefs[field] = saved[field];
      }
    }
  } catch (_) { /* Preferences must never block planning. */ }
  const densityDefault = document.getElementById('workspace-density-default');
  const notes = document.getElementById('workspace-show-notes');
  const timeline = document.getElementById('workspace-show-timeline');
  const status = document.getElementById('preference-status');
  function apply() {
    root.dataset.density = prefs.density;
    root.dataset.showNotes = String(prefs.showNotes);
    root.dataset.showTimeline = String(prefs.showTimeline);
    for (const button of document.querySelectorAll('[data-density-choice]')) {
      button.setAttribute('aria-pressed', String(button.dataset.densityChoice === prefs.density));
    }
    densityDefault.value = prefs.density;
    notes.checked = prefs.showNotes;
    timeline.checked = prefs.showTimeline;
  }
  function save() {
    apply();
    try { localStorage.setItem(key, JSON.stringify(prefs)); status.textContent = 'Display preferences saved.'; }
    catch (_) { status.textContent = 'Applied for this visit. Browser storage is unavailable.'; }
  }
  for (const button of document.querySelectorAll('[data-density-choice]')) {
    button.addEventListener('click', () => {prefs.density = button.dataset.densityChoice; save();});
  }
  densityDefault.addEventListener('change', () => {prefs.density = densityDefault.value; save();});
  notes.addEventListener('change', () => {prefs.showNotes = notes.checked; save();});
  timeline.addEventListener('change', () => {prefs.showTimeline = timeline.checked; save();});
  apply();
  document.querySelector('.preferences-budget-link').addEventListener('click', () => {
    document.getElementById('workspace-preferences').close();
  });
  // Attention tiles and stop links keep navigation within this workspace.
  for (const link of document.querySelectorAll('.attention-tile, .atlas-city-tile, .sidebar-city-jumps a')) {
    link.addEventListener('click', () => {
      const target = document.getElementById(link.hash.slice(1));
      if (!target) return;
      for (let parent = target.parentElement; parent; parent = parent.parentElement) {
        if (parent instanceof HTMLDetailsElement) parent.open = true;
      }
      target.setAttribute('tabindex', '-1');
      target.focus({preventScroll: true});
    });
  }
  // Return to the item being edited after an explicit form submission.
  const positionKey = 'furlong.workspace.return.' + location.pathname + location.search;
  for (const form of document.querySelectorAll('.hotel-editor-drawer form, .hotel-card-actions form')) {
    form.addEventListener('submit', () => {
      const card = form.closest('article[id]');
      if (card) {try { sessionStorage.setItem(positionKey, card.id); } catch (_) {}}
    });
  }
  try {
    const id = sessionStorage.getItem(positionKey);
    sessionStorage.removeItem(positionKey);
    const card = id && document.getElementById(id);
    if (card && !location.hash) card.scrollIntoView({block: 'center'});
  } catch (_) {}
})();
