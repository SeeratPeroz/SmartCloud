// static/js/patient_media.js

/* ------------------------- Helpers ------------------------- */
function getCookie(name){
  const m = document.cookie.match('(^|;)\\s*'+name+'\\s*=\\s*([^;]+)');
  return m ? m.pop() : '';
}
const CSRF_TOKEN = getCookie('csrftoken');

/* -------------------- Comments drawer ---------------------- */
const btnComments  = document.getElementById('btnComments');
const drawer       = document.getElementById('commentsDrawer');
const backdrop     = document.getElementById('commentsBackdrop');

if (btnComments && drawer && backdrop) {
  const closeBtn = document.getElementById('closeComments');
  closeBtn?.addEventListener('click', () => {
    drawer.classList.remove('open');
    backdrop.classList.remove('show');
  });
  btnComments.addEventListener('click', () => {
    drawer.classList.add('open');
    backdrop.classList.add('show');
  });
  backdrop.addEventListener('click', () => {
    drawer.classList.remove('open');
    backdrop.classList.remove('show');
  });
}

/* ------------------------ Upload --------------------------- */
const dropzone = document.getElementById('dropzone');
const picker   = document.getElementById('filePicker');

if (dropzone && picker) {
  dropzone.addEventListener('click', () => picker.click());
  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault(); dropzone.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
  });
  picker.addEventListener('change', e => handleFiles(e.target.files));
}

function handleFiles(list){
  const files = [...list];
  if (!files.length) return;

  // Infer upload endpoints from delete forms
  const U_IMG = document.querySelector('form[action*="delete_images"]')?.getAttribute('action')?.replace('delete_images','upload_images');
  const U_VID = document.querySelector('form[action*="delete_videos"]')?.getAttribute('action')?.replace('delete_videos','upload_videos');
  const patientId = document.querySelector('#models3d form')?.getAttribute('action')?.match(/patient\/(\d+)\//)?.[1];
  const U_STL = patientId ? `/patient/${patientId}/upload_models/` : null;

  (async () => {
    for (const f of files) {
      const n = (f.name||'').toLowerCase();
      const isImg = f.type.startsWith('image/');
      const isVid = f.type.startsWith('video/');
      const isStl = n.endsWith('.stl') || f.type === 'model/stl' || f.type === 'application/sla';

      let url = null, field = null;
      if (isImg)      { url = U_IMG; field = 'images'; }
      else if (isVid) { url = U_VID; field = 'videos'; }
      else if (isStl) { url = U_STL; field = 'models'; }
      if (!url) continue;

      const fd = new FormData();
      fd.append('csrfmiddlewaretoken', CSRF_TOKEN);
      fd.append(field, f);
      await fetch(url, { method:'POST', headers: { 'X-CSRFToken': CSRF_TOKEN }, body: fd });
    }
    location.reload();
  })();
}

/* ----------------- Fullscreen Image Viewer ----------------- */
let s = 1, tx = 0, ty = 0, IMAGES = [], CURRENT_INDEX = 0;
const viewer         = document.getElementById('viewer');
const viewerImg      = document.getElementById('viewerImg');
const viewerDownload = document.getElementById('viewerDownload');
const viewerEdit     = document.getElementById('viewerEdit');
const viewerBackdrop = document.getElementById('viewerBackdrop');

function collectImages(){
  IMAGES = Array.from(document.querySelectorAll('.img-thumb')).map(el => ({
    src: el.getAttribute('src'),
    id:  el.dataset.id
  }));
}
collectImages();

function openViewerIndex(i){
  if(!IMAGES.length) collectImages();
  CURRENT_INDEX = Math.max(0, Math.min(i, IMAGES.length - 1));
  openViewer(IMAGES[CURRENT_INDEX]);
}
window.openViewerIndex = openViewerIndex;

function openViewer(obj){
  s = 1; tx = 0; ty = 0;
  viewerImg.style.setProperty('--s', 1);
  viewerImg.style.setProperty('--tx', '0px');
  viewerImg.style.setProperty('--ty', '0px');
  viewerImg.src = obj.src;
  viewerDownload.href = obj.src;
  viewer.classList.remove('d-none');
}
function closeViewer(){ viewer.classList.add('d-none'); viewerImg.src = ''; }

function zoomBy(f){
  s = Math.max(1, Math.min(8, s * f));
  if (s === 1) { tx = 0; ty = 0; }
  viewerImg.style.setProperty('--s', s);
  viewerImg.style.setProperty('--tx', tx + 'px');
  viewerImg.style.setProperty('--ty', ty + 'px');
}

if (viewer) {
  viewer.addEventListener('wheel', e => {
    e.preventDefault();
    const d = e.deltaY || e.wheelDelta;
    zoomBy(d > 0 ? 1/1.15 : 1.15);
  }, { passive:false });
}

let dragging = false, sx = 0, sy = 0;
if (viewerImg) {
  viewerImg.addEventListener('mousedown', e => {
    if (s === 1) return;
    dragging = true; sx = e.clientX; sy = e.clientY; viewer.classList.add('grabbing');
  });
}
window.addEventListener('mousemove', e => {
  if(!dragging) return;
  const dx = e.clientX - sx, dy = e.clientY - sy;
  sx = e.clientX; sy = e.clientY;
  tx += dx; ty += dy;
  viewerImg.style.setProperty('--tx', tx + 'px');
  viewerImg.style.setProperty('--ty', ty + 'px');
});
window.addEventListener('mouseup', () => { dragging = false; viewer?.classList.remove('grabbing'); });
viewerBackdrop?.addEventListener('click', closeViewer);

window.addEventListener('keydown', e => {
  if (!viewer || viewer.classList.contains('d-none')) return;
  if (e.key === 'Escape')        { e.preventDefault(); closeViewer(); }
  else if (e.key === 'ArrowRight'){ e.preventDefault(); CURRENT_INDEX = (CURRENT_INDEX + 1) % IMAGES.length; openViewer(IMAGES[CURRENT_INDEX]); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); CURRENT_INDEX = (CURRENT_INDEX - 1 + IMAGES.length) % IMAGES.length; openViewer(IMAGES[CURRENT_INDEX]); }
  else if (e.key === 'd' || e.key === 'D'){ e.preventDefault(); viewerDownload.click(); }
});

/* ---------------------- TUI Editor ------------------------- */
let tuiEditor = null, currentEditUrl = null, currentEditId = null;
const modalEl = document.getElementById('imageEditorModal');

function openTUIEditor(url, id){
  currentEditUrl = url; currentEditId = id;
  closeViewer();

  const onShown = () => {
    try { tuiEditor?.destroy(); } catch(_) {}
    // global "tui" provided by CDN
    tuiEditor = new tui.ImageEditor('#tui-editor-wrap', {
      includeUI: {
        loadImage: { path: currentEditUrl, name: 'image' },
        menu: ['crop','draw','shape','text','filter','rotate','flip'],
        initMenu: 'crop',
        menuBarPosition: 'bottom'
      },
      cssMaxWidth: 1600,
      cssMaxHeight: 1000,
      selectionStyle: { cornerSize: 16, rotatingPointOffset: 40 }
    });
    setTimeout(() => { try { tuiEditor.ui.resizeEditor(); } catch(_){} }, 50);

    document.getElementById('btnReset').onclick = async () => {
      try {
        await tuiEditor.loadImageFromURL(currentEditUrl, 'image');
        tuiEditor.clearUndoStack();
        setTimeout(() => { try { tuiEditor.ui.resizeEditor(); } catch(_){} }, 30);
      } catch(e){ alert('Zurücksetzen fehlgeschlagen.'); }
    };
    document.getElementById('btnSave').onclick = async () => {
      try {
        const dataURL = tuiEditor.toDataURL();
        const blob = await (await fetch(dataURL)).blob();
        const fd = new FormData();
        fd.append('image', new File([blob], 'edited.png', { type:'image/png' }));
        const res = await fetch(`/image/${currentEditId}/edit/`, { method:'POST', headers:{'X-CSRFToken':CSRF_TOKEN}, body: fd });
        if(!res.ok) throw new Error();
        location.reload();
      } catch(_){ alert('Speichern fehlgeschlagen.'); }
    };
    document.getElementById('btnSaveCopy').onclick = async () => {
      try {
        const dataURL = tuiEditor.toDataURL();
        const blob = await (await fetch(dataURL)).blob();
        const fd = new FormData();
        fd.append('image', new File([blob], 'edited.png', { type:'image/png' }));
        fd.append('as_new','1');
        const res = await fetch(`/image/${currentEditId}/edit/`, { method:'POST', headers:{'X-CSRFToken':CSRF_TOKEN}, body: fd });
        if(!res.ok) throw new Error();
        location.reload();
      } catch(_){ alert('Speichern fehlgeschlagen.'); }
    };
    document.getElementById('btnDownload').onclick = () => {
      const a = document.createElement('a');
      a.href = tuiEditor.toDataURL();
      a.download = `image-${currentEditId || 'edited'}.png`;
      document.body.appendChild(a); a.click(); a.remove();
    };
  };

  modalEl?.addEventListener('shown.bs.modal', onShown, { once:true });
  window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

if (viewerEdit) {
  viewerEdit.addEventListener('click', () => {
    const item = IMAGES[CURRENT_INDEX];
    if (!item) return;
    openTUIEditor(item.src, item.id);
  });
}

/* Enforce full width when the TUI modal shows (beats theme caps) */
document.getElementById('imageEditorModal')?.addEventListener('shown.bs.modal', function(){
  // Also override Bootstrap's modal width variable for this modal
  this.style.setProperty('--bs-modal-width', '100vw');
  const dlg = this.querySelector('.modal-dialog');
  if (!dlg) return;
  dlg.classList.add('modal-fullscreen');
  dlg.style.setProperty('width', '100vw', 'important');
  dlg.style.setProperty('max-width', '100vw', 'important');
  dlg.style.setProperty('margin', '0', 'important');
});

/* ------------- Three.js STL viewer (fullscreen) ------------ */
window.openStlViewer = async (url) => {
  // Use esm.sh so we don't depend on import maps
  const THREE = await import('https://esm.sh/three@0.158.0');
  const { OrbitControls } = await import('https://esm.sh/three@0.158.0/examples/jsm/controls/OrbitControls.js');
  const { STLLoader } = await import('https://esm.sh/three@0.158.0/examples/jsm/loaders/STLLoader.js');

  // Build modal
  const md = document.createElement('div');
  md.className = 'modal fade stl-modal';
  md.innerHTML = `
    <div class="modal-dialog modal-fullscreen">
      <div class="modal-content">
        <div class="modal-header">
          <h6 class="modal-title">3D Vorschau (.stl)</h6>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Schließen"></button>
        </div>
        <div class="modal-body position-relative">
          <div id="stlWrap" style="width:100vw;height:1px;background:#111"></div>
          <div class="stl-controls">
            <label>Objekt</label>
            <input type="color" id="colModel" class="color" value="#29a3ff" title="Modellfarbe">
            <label>Hintergrund</label>
            <input type="color" id="colBg" class="color" value="#111111" title="Hintergrundfarbe">
            <label>Glanz</label>
            <input type="range" id="shininess" min="0" max="120" value="40" title="Shininess">
            <label class="check"><input type="checkbox" id="wire"> Wireframe</label>
            <label class="check"><input type="checkbox" id="autorotate"> Auto-Rotate</label>
          </div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(md);

  // Kill the 500px cap everywhere
  md.style.setProperty('--bs-modal-width', '100vw');
  const dlg = md.querySelector('.modal-dialog');
  dlg.style.setProperty('width', '100vw', 'important');
  dlg.style.setProperty('max-width', '100vw', 'important');
  dlg.style.setProperty('margin', '0', 'important');

  const modal  = new window.bootstrap.Modal(md);
  const wrap   = md.querySelector('#stlWrap');
  const header = md.querySelector('.modal-header');

  // Three.js setup
  const scene    = new THREE.Scene(); scene.background = new THREE.Color(0x111111);
  const camera   = new THREE.PerspectiveCamera(60, 1, 0.1, 5000);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  wrap.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  let userInteracted = false;
  controls.addEventListener('start', () => { userInteracted = true; });

  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const dir = new THREE.DirectionalLight(0xffffff, 0.8); dir.position.set(1,1,1); scene.add(dir);

  function fitCameraToObject(object, fitOffset = 1.25){
    const box    = new THREE.Box3().setFromObject(object);
    const size   = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    object.position.sub(center);

    // Compute distance to fit on both axes
    const halfFovY = THREE.MathUtils.degToRad(camera.fov * 0.5);
    const halfFovX = Math.atan(Math.tan(halfFovY) * camera.aspect);
    const distY    = (size.y * 0.5) / Math.tan(halfFovY);
    const distX    = (size.x * 0.5) / Math.tan(halfFovX);
    const dist     = Math.max(distX, distY, size.z) * fitOffset;

    camera.position.set(dist, dist * 0.8, dist);
    camera.near = Math.max(0.1, dist / 100);
    camera.far  = dist * 100;
    camera.updateProjectionMatrix();
    controls.target.set(0,0,0);
    controls.update();
  }

  function sizeWrap(refit = false){
    const headerH = header ? header.getBoundingClientRect().height : 0;
    const h = Math.max(220, (window.innerHeight || 0) - headerH);
    wrap.style.height = h + 'px';

    const w = Math.max(window.innerWidth || 0, document.documentElement.clientWidth || 0);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();

    if (mesh && (refit || !userInteracted)) fitCameraToObject(mesh, 1.25);
  }

  // Resize handling
  md.addEventListener('shown.bs.modal', () => sizeWrap(true), { once:true });
  const onWinResize = () => sizeWrap(false);
  window.addEventListener('resize', onWinResize, { passive:true });

  let mesh = null;
  const material = new THREE.MeshPhongMaterial({ color: 0x29a3ff, shininess: 40 });
  const loader   = new STLLoader();
  loader.load(url, (geom) => {
    if (geom.computeVertexNormals) geom.computeVertexNormals();
    mesh = new THREE.Mesh(geom, material);
    scene.add(mesh);
    sizeWrap(true);
    fitCameraToObject(mesh, 1.25);
    render();
  }, undefined, () => {
    wrap.innerHTML = '<div class="p-3 text-danger">STL konnte nicht geladen werden.</div>';
  });

  // UI controls
  const colModel   = md.querySelector('#colModel');
  const colBg      = md.querySelector('#colBg');
  const shininess  = md.querySelector('#shininess');
  const wire       = md.querySelector('#wire');
  const autorotate = md.querySelector('#autorotate');

  colModel.addEventListener('input', () => { material.color     = new THREE.Color(colModel.value); });
  colBg.addEventListener('input',    () => { scene.background   = new THREE.Color(colBg.value);   });
  shininess.addEventListener('input',() => { material.shininess = Number(shininess.value);        });
  wire.addEventListener('change',    () => { material.wireframe = wire.checked;                   });

  let alive = true;
  function render(){
    if (!alive) return;
    requestAnimationFrame(render);
    if (autorotate.checked && mesh) mesh.rotation.y += 0.01;
    controls.update();
    renderer.render(scene, camera);
  }

  md.addEventListener('hidden.bs.modal', () => {
    alive = false;
    window.removeEventListener('resize', onWinResize);
    renderer.dispose();
    md.remove();
  }, { once:true });

  modal.show();
};
