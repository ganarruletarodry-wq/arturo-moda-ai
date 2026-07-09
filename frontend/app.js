// Stato applicazione
const state = {
  files: [],
  lastAnalysis: null,
  lastImages: null,
};

// Elementi DOM
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const previewGrid = document.getElementById('preview-grid');
const btnAnalyze = document.getElementById('btn-analyze');
const sectionUpload = document.getElementById('section-upload');
const sectionLoading = document.getElementById('section-loading');
const sectionResults = document.getElementById('section-results');

// ---- CARICAMENTO API KEY da localStorage + controllo server ----
let serverHasKey = false;
let passwordRequired = false;
let publishAvailable = true;

// Password dell'app (solo per versione online)
function getAppPassword() {
  if (!passwordRequired) return '';
  let p = localStorage.getItem('arturo_app_password') || '';
  if (!p) {
    p = (prompt('🔒 Inserisci la password dell\'app:') || '').trim();
    if (p) localStorage.setItem('arturo_app_password', p);
  }
  return p;
}

function handleUnauthorized() {
  localStorage.removeItem('arturo_app_password');
  showError('Password dell\'app errata. Riprova.');
}

window.addEventListener('DOMContentLoaded', async () => {
  // Se c'è un annuncio generato in precedenza, offri di riaprirlo
  try {
    const saved = JSON.parse(localStorage.getItem('arturo_last_result') || 'null');
    if (saved && saved.analysis && saved.images) {
      const when = saved.ts
        ? new Date(saved.ts).toLocaleString('it-IT', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
        : '';
      document.getElementById('restore-text').textContent =
        `“${saved.analysis.titolo || 'Ultimo annuncio'}”${when ? ' · ' + when : ''}`;
      document.getElementById('restore-bar').classList.remove('hidden');
    }
  } catch (_) {}

  // Controlla configurazione server (chiave, password, pubblicazione)
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    serverHasKey = cfg.server_has_key === true;
    passwordRequired = cfg.password_required === true;
    publishAvailable = cfg.publish_available !== false;
  } catch (_) {}

  // Online i bottoni "Pubblica" non possono aprire il browser: nascondili
  if (!publishAvailable) {
    const row = document.querySelector('.publish-row');
    if (row) row.style.display = 'none';
  }

  const apiSection = document.getElementById('api-keys-details');

  if (serverHasKey) {
    // Chiave già nel .env: nascondi completamente il pannello
    apiSection.style.display = 'none';
  } else {
    // Chiave non presente: carica da localStorage o chiedi all'utente
    const savedKey = localStorage.getItem('arturo_openai_key');
    if (savedKey) {
      document.getElementById('openai-key').value = savedKey;
      apiSection.removeAttribute('open');
    } else {
      apiSection.setAttribute('open', '');
    }
  }
});

document.getElementById('openai-key').addEventListener('change', (e) => {
  localStorage.setItem('arturo_openai_key', e.target.value.trim());
});

// ---- DRAG & DROP ----
dropzone.addEventListener('click', (e) => {
  if (!e.target.closest('.btn')) fileInput.click();
});

dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('drag-over');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  addFiles(Array.from(e.dataTransfer.files));
});

fileInput.addEventListener('change', () => {
  addFiles(Array.from(fileInput.files));
  fileInput.value = '';
});

function addFiles(newFiles) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp'];
  for (const f of newFiles) {
    if (!allowed.includes(f.type)) {
      showError(`Formato non supportato: ${f.name}. Usa JPG, PNG o WEBP.`);
      continue;
    }
    if (f.size > 10 * 1024 * 1024) {
      showError(`File troppo grande: ${f.name} (max 10 MB)`);
      continue;
    }
    if (state.files.length >= 4) {
      showError('Puoi caricare massimo 4 foto.');
      break;
    }
    state.files.push(f);
  }
  renderPreviews();
}

function renderPreviews() {
  previewGrid.innerHTML = '';
  state.files.forEach((file, i) => {
    const item = document.createElement('div');
    item.className = 'preview-item';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    img.alt = file.name;
    const removeBtn = document.createElement('button');
    removeBtn.className = 'preview-remove';
    removeBtn.textContent = '✕';
    removeBtn.onclick = () => removeFile(i);
    item.appendChild(img);
    item.appendChild(removeBtn);
    previewGrid.appendChild(item);
  });
  btnAnalyze.disabled = state.files.length === 0;
}

function removeFile(index) {
  state.files.splice(index, 1);
  renderPreviews();
}

// ---- ANALISI ----
btnAnalyze.addEventListener('click', startAnalysis);

async function startAnalysis() {
  const openaiKey = serverHasKey ? '' : document.getElementById('openai-key').value.trim();

  if (!serverHasKey && !openaiKey) {
    showError('Inserisci la tua API key OpenAI prima di continuare.');
    document.getElementById('api-keys-details').setAttribute('open', '');
    return;
  }

  sectionUpload.classList.add('hidden');
  sectionLoading.classList.remove('hidden');

  // Simula progress step 1 subito
  setStepActive('step-analyze');

  try {
    const formData = new FormData();
    state.files.forEach((f) => formData.append('files', f));
    formData.append('openai_key', openaiKey);

    // Dopo 3s simula passaggio allo step 2
    const stepTimer = setTimeout(() => {
      setStepDone('step-analyze');
      setStepActive('step-images');
      document.getElementById('loading-sub').textContent =
        'Generazione delle 4 immagini in alta fedeltà… (può richiedere 1-2 minuti)';
    }, 3000);

    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: passwordRequired ? { 'X-App-Password': getAppPassword() } : {},
      body: formData,
    });

    clearTimeout(stepTimer);

    if (response.status === 401) {
      handleUnauthorized();
      throw new Error('Password dell\'app richiesta.');
    }
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Errore sconosciuto' }));
      throw new Error(err.detail || `Errore server ${response.status}`);
    }

    const data = await response.json();

    setStepDone('step-analyze');
    setStepDone('step-images');
    setStepActive('step-done');

    setTimeout(() => showResults(data), 600);
  } catch (err) {
    sectionLoading.classList.add('hidden');
    sectionUpload.classList.remove('hidden');
    showError(err.message);
  }
}

function setStepActive(id) {
  document.querySelector(`#${id} .step-dot`).classList.add('active');
}
function setStepDone(id) {
  const dot = document.querySelector(`#${id} .step-dot`);
  dot.classList.remove('active');
  dot.classList.add('done');
}

// ---- RISULTATI ----
const MISURE_LABELS = {
  petto_busto: 'Petto / Busto',
  spalle: 'Spalle',
  vita: 'Vita',
  fianchi: 'Fianchi',
  lunghezza_totale: 'Lunghezza totale',
  lunghezza_gamba: 'Lunghezza gamba',
  maniche: 'Maniche',
};

function formatMisure(misure) {
  if (!misure) return '';
  const lines = [];
  for (const [key, label] of Object.entries(MISURE_LABELS)) {
    if (misure[key] && misure[key] !== 'null') {
      lines.push(`• ${label}: ${misure[key]}`);
    }
  }
  return lines.join('\n');
}

function showResults(data) {
  const a = data.analysis;
  const images = data.images;

  document.getElementById('res-titolo').textContent = a.titolo || '';

  // Descrizioni con misure in coda
  const misureTesto = formatMisure(a.misure);
  const misureSezione = misureTesto ? `\n\n📏 Misure:\n${misureTesto}` : '';
  document.getElementById('res-vinted').textContent = (a.descrizione_vinted || '') + misureSezione;
  document.getElementById('res-catawiki').textContent = (a.descrizione_catawiki || '') + misureSezione;

  document.getElementById('res-hashtag').textContent = (a.hashtag || []).join(' ');
  document.getElementById('res-prezzo').textContent =
    `€${a.prezzo_suggerito_min} – €${a.prezzo_suggerito_max}`;

  // Sezione misure visiva
  const misure = a.misure || {};
  const lista = document.getElementById('res-misure');
  lista.innerHTML = '';
  let hasMisure = false;
  for (const [key, label] of Object.entries(MISURE_LABELS)) {
    if (misure[key] && misure[key] !== 'null') {
      hasMisure = true;
      const li = document.createElement('li');
      li.innerHTML = `<span class="misure-key">${label}:</span><span class="misure-val">${misure[key]}</span>`;
      lista.appendChild(li);
    }
  }
  document.getElementById('block-misure').style.display = hasMisure ? '' : 'none';
  if (misure.note_misure) {
    document.getElementById('res-misure-note').textContent = `ℹ️ ${misure.note_misure}`;
  }

  // Info chips
  const chips = document.getElementById('info-chips');
  chips.innerHTML = '';
  const infos = [
    a.categoria, a.genere, a.taglia ? `Taglia: ${a.taglia}` : null,
    a.brand || null, a.condizione, ...(a.colori || []),
    a.materiale || null,
  ].filter(Boolean);
  infos.forEach((txt) => {
    const c = document.createElement('span');
    c.className = 'chip';
    c.textContent = txt;
    chips.appendChild(c);
  });

  // Immagini modella
  const modelRow = document.getElementById('images-model');
  modelRow.innerHTML = '';
  ['model_front', 'model_lifestyle'].forEach((key) => {
    if (images[key]) modelRow.appendChild(buildImageCard(images[key]));
  });

  // Immagini sfondo bianco
  const productRow = document.getElementById('images-product');
  productRow.innerHTML = '';
  ['product_flat', 'product_hanger'].forEach((key) => {
    if (images[key]) productRow.appendChild(buildImageCard(images[key]));
  });

  // Salva stato per pubblicazione + persistenza per riaprire senza rigenerare
  state.lastAnalysis = a;
  state.lastImages = images;
  try {
    localStorage.setItem('arturo_last_result', JSON.stringify({ analysis: a, images, ts: Date.now() }));
  } catch (_) {}

  sectionLoading.classList.add('hidden');
  sectionResults.classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function buildImageCard(filename) {
  const card = document.createElement('div');
  card.className = 'image-card';
  const img = document.createElement('img');
  img.src = `/api/image/${filename}`;
  img.alt = 'Immagine generata';
  img.loading = 'lazy';
  const actions = document.createElement('div');
  actions.className = 'image-card-actions';
  const dl = document.createElement('button');
  dl.className = 'btn-download';
  dl.textContent = '⬇ Scarica';
  dl.onclick = () => { window.location.href = `/api/download/${filename}`; };
  actions.appendChild(dl);
  card.appendChild(img);
  card.appendChild(actions);
  return card;
}

// ---- TABS ----
document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach((c) => c.classList.add('hidden'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.remove('hidden');
  });
});

// ---- COPIA TESTO ----
function copyText(elementId) {
  const el = document.getElementById(elementId);
  const text = el.textContent || '';
  navigator.clipboard.writeText(text).then(() => {
    const btn = el.closest('.copy-row')?.querySelector('.btn-copy');
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '✓ Copiato!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('copied');
      }, 2000);
    }
  });
}

// ---- RIPRENDI ULTIMO ANNUNCIO ----
function restoreLast() {
  try {
    const saved = JSON.parse(localStorage.getItem('arturo_last_result') || 'null');
    if (!saved || !saved.analysis || !saved.images) {
      showError('Nessun annuncio salvato trovato.');
      return;
    }
    showResults({ analysis: saved.analysis, images: saved.images });
  } catch (_) {
    showError('Impossibile ripristinare l\'ultimo annuncio.');
  }
}

// ---- RESET ----
function resetApp() {
  state.files = [];
  state.lastAnalysis = null;
  state.lastImages = null;
  previewGrid.innerHTML = '';
  btnAnalyze.disabled = true;
  // reset steps
  document.querySelectorAll('.step-dot').forEach((d) => {
    d.classList.remove('active', 'done');
  });
  document.getElementById('loading-sub').textContent = 'GPT-4o sta esaminando le tue foto';
  sectionResults.classList.add('hidden');
  sectionLoading.classList.add('hidden');
  sectionUpload.classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---- PUBBLICA ----
let currentPlatform = null;

function openPublishModal(platform) {
  currentPlatform = platform;
  const labels = { vinted: 'Pubblica su Vinted', catawiki: 'Pubblica su Catawiki' };
  document.getElementById('modal-title').textContent = labels[platform];
  document.getElementById('modal-desc').textContent = 'Come funziona:';
  document.getElementById('publish-modal').classList.remove('hidden');
}

function closePublishModal() {
  document.getElementById('publish-modal').classList.add('hidden');
  document.getElementById('publish-btn-text').textContent = 'Apri e precompila';
  document.getElementById('btn-publish-confirm').disabled = false;
}

async function confirmPublish() {
  if (!state.lastAnalysis || !state.lastImages) {
    showError('Dati annuncio non trovati. Ricarica la pagina.');
    return;
  }

  const btn = document.getElementById('btn-publish-confirm');
  btn.disabled = true;
  document.getElementById('publish-btn-text').textContent =
    'In corso… guarda la finestra del browser';

  const imageFilenames = Object.values(state.lastImages).filter(Boolean);

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (passwordRequired) headers['X-App-Password'] = getAppPassword();
    const res = await fetch(`/api/publish/${currentPlatform}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        analysis: state.lastAnalysis,
        image_filenames: imageFilenames,
      }),
    });

    if (res.status === 401) {
      handleUnauthorized();
      throw new Error('Password dell\'app richiesta.');
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Errore sconosciuto');

    closePublishModal();
    let msg = data.message || 'Annuncio precompilato!';
    if (data.mancanti && data.mancanti.length > 0) {
      msg += ` Da compilare a mano: ${data.mancanti.join(', ')}.`;
    }
    document.getElementById('success-msg').textContent = msg;
    const link = document.getElementById('success-link');
    if (data.url) {
      link.href = data.url;
      link.classList.remove('hidden');
    } else {
      link.classList.add('hidden');
    }
    document.getElementById('success-toast').classList.remove('hidden');
    setTimeout(() => {
      document.getElementById('success-toast').classList.add('hidden');
    }, 15000);
  } catch (err) {
    btn.disabled = false;
    document.getElementById('publish-btn-text').textContent = 'Apri e precompila';
    showError(`Errore pubblicazione: ${err.message}`);
  }
}

// Chiudi modale cliccando fuori
document.getElementById('publish-modal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('publish-modal')) closePublishModal();
});

// ---- ERRORI ----
function showError(msg) {
  document.getElementById('error-msg').textContent = msg;
  document.getElementById('error-toast').classList.remove('hidden');
  setTimeout(hideError, 6000);
}
function hideError() {
  document.getElementById('error-toast').classList.add('hidden');
}
