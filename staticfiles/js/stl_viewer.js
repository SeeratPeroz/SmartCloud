// static/js/stl_viewer.js  (STEP 1: popup only, no 3D)

const popupOnly = () => {
  const md = document.createElement('div');
  md.className = 'modal fade stl-modal';
  md.innerHTML = `
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h6 class="modal-title">3D Vorschau — Test</h6>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Schließen"></button>
        </div>
        <div class="modal-body d-flex align-items-center justify-content-center">
          <div class="text-center p-4">
            <div class="mb-2 fs-5">✅ Popup works & is fullscreen</div>
            <div class="small text-muted">
              Viewport: <span id="vw"></span> × <span id="vh"></span>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(md);

  // make sure width isn’t capped by any theme
  const dlg = md.querySelector('.modal-dialog');
  dlg.style.setProperty('width','100vw','important');
  dlg.style.setProperty('max-width','100vw','important');
  dlg.style.setProperty('margin','0','important');
  md.style.setProperty('--bs-modal-width','100vw');

  md.addEventListener('shown.bs.modal', () => {
    md.querySelector('#vw').textContent = Math.max(window.innerWidth, document.documentElement.clientWidth);
    md.querySelector('#vh').textContent = Math.max(window.innerHeight, document.documentElement.clientHeight);
  }, { once:true });

  md.addEventListener('hidden.bs.modal', () => md.remove(), { once:true });

  new bootstrap.Modal(md).show();
};

// override AFTER all other scripts have run
window.addEventListener('load', () => {
  try { delete window.openStlViewer; } catch(e) {}
  window.openStlViewer = popupOnly;
  console.log('[STL] Popup-only override active');
});
