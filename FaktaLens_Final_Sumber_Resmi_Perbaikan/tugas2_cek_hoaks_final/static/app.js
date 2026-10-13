const $ = (id) => document.getElementById(id);
const icon = (name) => `<svg class="icon"><use href="#i-${name}"></use></svg>`;
const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const validUrl = (value) => { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; } catch { return ''; } };
const shortDate = (value) => { try { return new Date(value.replace(' ', 'T') + (value.includes('Z') ? '' : '')).toLocaleDateString('id-ID', {day:'numeric',month:'short',year:'numeric'}); } catch { return value || '-'; } };
const pages = {beranda:'Dashboard',teks:'Cek Teks',gambar:'Cek Gambar',tautan:'Cek Tautan',hasil:'Hasil Pemeriksaan',riwayat:'Riwayat',tentang:'Tentang Aplikasi'};
let currentResult = null;
let recentHistory = [];
let selectedFile = null;
let filePreview = '';
let toastTimer;

function notify(message, error = false) {
  const target = $('toast');
  target.textContent = message;
  target.classList.toggle('error', error);
  target.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => target.hidden = true, 4700);
}

function openPage(name) {
  if (!pages[name]) return;
  document.querySelectorAll('.page').forEach(page => page.hidden = page.id !== `page-${name}`);
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.nav === name));
  $('currentPage').textContent = pages[name];
  $('sidebar').classList.remove('open');
  window.scrollTo({top: 0, behavior: 'smooth'});
  if (name === 'beranda') loadStats();
  if (name === 'riwayat') renderHistory();
}

async function requestAPI(url, options = {}) {
  let response;
  try { response = await fetch(url, options); }
  catch { throw new Error('Gagal menghubungi aplikasi. Pastikan server Flask menyala.'); }
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error('Respons server tidak dapat dibaca.'); }
  if (!response.ok) throw new Error(payload.error || 'Terjadi kesalahan pada server.');
  return payload;
}

function setLoading(button, loading) {
  if (loading) { button.dataset.oldHTML = button.innerHTML; button.disabled = true; button.textContent = 'Sedang memeriksa...'; }
  else { button.disabled = false; if (button.dataset.oldHTML) button.innerHTML = button.dataset.oldHTML; }
}

async function submitCheck(data, button) {
  setLoading(button, true);
  try {
    const result = await requestAPI('/api/cek', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
    });
    displayResult(result);
    await Promise.all([loadStats(), loadHistory()]);
    openPage('hasil');
    notify('Pemeriksaan selesai. Baca sumber untuk konteks lengkapnya.');
  } catch (error) { notify(error.message, true); }
  finally { setLoading(button, false); }
}

function scoreType(name) {
  if (['Hoaks', 'Kemungkinan hoaks'].includes(name)) return 'risk';
  if (['Fakta', 'Nyata', 'Kemungkinan benar'].includes(name)) return 'good';
  return '';
}

function displayResult(data) {
  currentResult = data;
  const outcome = escapeText(data.kesimpulan || 'Belum ditemukan');
  const matches = (data.hasil || []);
  const query = escapeText(data.kueri || 'Gambar / tautan yang diperiksa');
  const type = scoreType(data.kesimpulan);
  const intro = data.tautan_asli || null;
  let html = `<div class="verdict-top"><span class="verdict-mark ${type}">${icon(type === 'risk' ? 'alert' : 'shield')}</span><div><small>KESIMPULAN PENCARIAN</small><h2>${outcome}</h2></div><span class="verdict-chip">${matches.length} ulasan Google${(data.referensi || []).length ? ` · ${(data.referensi || []).length} referensi` : ''}</span></div>`;
  html += `<div class="result-query"><small>KLAIM YANG DIPERIKSA</small>${query}</div>`;
  html += `<p class="field-note" style="margin-top:8px">${escapeText(data.label_penjelasan || 'Penilaian berdasarkan sumber cek fakta terkait; bukan jaminan kebenaran seluruh pesan.')}</p>`;
  if ((data.kata_kunci_dicoba || []).length > 1) {
    html += `<div class="search-tries"><strong>Alternatif pencarian otomatis</strong><div>${data.kata_kunci_dicoba.map(word => `<span>${escapeText(word)}</span>`).join('')}</div><small>Google diperiksa dengan beberapa kata kunci. Tidak ditemukan hasil bukan berarti klaim benar.</small></div>`;
  }
  html += `<div class="summary-box">${escapeText(data.ringkasan)}</div>`;
  if (data.alasan && data.jumlah_hasil > 0) {
    html += `<p class="field-note" style="margin-top:8px"><b>Dasar kesimpulan:</b> ${escapeText(data.alasan)}</p>`;
  }
  if ((data.referensi || []).length) {
    html += `<div class="result-section-title"><h3>Referensi sumber resmi</h3><span>Pemerintah</span></div>`;
    html += `<p class="field-note">Bukti sumber resmi yang relevan untuk klaim khusus. Referensi terkurasi, bukan pengambilan data langsung setiap pencarian.</p>`;
    for (const ref of data.referensi) {
      const link = validUrl(ref.url);
      html += `<article class="review-card"><div class="review-head"><span class="review-badge">Sumber resmi</span></div><h4>${escapeText(ref.judul)}</h4><p>${escapeText(ref.kutipan)}</p>${link ? `<a class="source-link" href="${escapeText(link)}" target="_blank" rel="noopener noreferrer">Baca sumber resmi ${icon('external')}</a>` : ''}</article>`;
    }
  }
  if (intro && intro.url) {
    const link = validUrl(intro.url);
    const img = validUrl(intro.gambar);
    html += `<div class="source-preview">${img ? `<img src="${escapeText(img)}" alt="Pratinjau tautan" loading="lazy">` : ''}<div><strong>${escapeText(intro.judul || 'Tautan yang diperiksa')}</strong><small>${escapeText(intro.situs || '')}</small>${link ? `<br><a class="source-link" target="_blank" rel="noopener noreferrer" href="${escapeText(link)}">Buka tautan asal ${icon('external')}</a>` : ''}</div></div>`;
  }
  html += `<div class="result-section-title"><h3>Ulasan pemeriksa fakta</h3><span>${matches.length} hasil terkait</span></div>`;
  if (!matches.length) {
    html += `<div class="empty-small">Belum ada ulasan Google Fact Check yang cukup cocok. ${((data.referensi || []).length ? 'Referensi tambahan tersedia di atas.' : 'Coba klaim lebih spesifik atau tinjau sumber lain.')}</div>`;
  } else {
    for (const item of matches) {
      const link = validUrl(item.url);
      const match = Number(item.relevansi);
      const note = Number.isFinite(match) ? `<small>Kecocokan teks ${Math.round(match*100)}% (bukan akurasi fakta)</small>` : '';
      html += `<article class="review-card"><div class="review-head"><span class="review-badge">${escapeText(item.rating || 'Penilaian belum jelas')}</span><small>${escapeText(item.tanggal || '')}</small></div><h4>${escapeText(item.judul || item.klaim)}</h4><p>${escapeText(item.klaim)}</p>${note}${link ? `<br><a class="source-link" href="${escapeText(link)}" target="_blank" rel="noopener noreferrer">${escapeText(item.penerbit || 'Sumber')} ${icon('external')}</a>` : ''}</article>`;
    }
  }
  $('resultContent').innerHTML = html;

  const articles = data.berita_terkait || [];
  $('relatedNews').innerHTML = articles.length ? articles.map(item => {
    const link = validUrl(item.url);
    return `<a class="news-card" href="${escapeText(link || '#')}" target="_blank" rel="noopener noreferrer"><strong>${escapeText(item.judul)}</strong><small>${escapeText(item.situs)} · Berita terkait, belum diverifikasi</small></a>`;
  }).join('') : '<div class="empty-small">Belum ada berita terkait yang dapat dimuat saat ini.</div>';
  const googleUrl = validUrl(data.tautan_google);
  const youtubeUrl = validUrl(data.tautan_youtube);
  const newsUrl = validUrl(data.tautan_berita);
  $('searchLinks').innerHTML = `${googleUrl ? `<a target="_blank" rel="noopener noreferrer" href="${escapeText(googleUrl)}">${icon('search')} Telusuri informasi lain di Google ${icon('external')}</a>` : ''}${youtubeUrl ? `<a target="_blank" rel="noopener noreferrer" href="${escapeText(youtubeUrl)}">${icon('youtube')} Cari video terkait di YouTube ${icon('external')}</a>` : ''}${newsUrl ? `<a target="_blank" rel="noopener noreferrer" href="${escapeText(newsUrl)}">${icon('file')} Cari berita lain di Google News ${icon('external')}</a>` : ''}<p class="field-note">Tautan pencarian bukan rekomendasi bahwa semua hasilnya benar.</p>`;
}

function renderRecent(list) {
  if (!list.length) return '<div class="empty-small">Belum ada pemeriksaan. Mulai dari menu Cek Teks.</div>';
  return list.map(item => `<button class="recent-row" data-history="${Number(item.id)}"><span class="sm-icon">${icon(item.jenis === 'gambar' ? 'image' : item.jenis === 'tautan' ? 'link' : 'file')}</span><span><strong>${escapeText(item.teks)}</strong><small>${escapeText(shortDate(item.waktu))} · ${escapeText(item.jenis)}</small></span><span class="state">${escapeText(item.kesimpulan || '')}</span></button>`).join('');
}

async function loadHistory() {
  try {
    recentHistory = await requestAPI('/api/riwayat');
    $('homeHistory').innerHTML = renderRecent(recentHistory.slice(0, 4));
    $('sideHistory').innerHTML = recentHistory.length ? recentHistory.slice(0, 3).map(item => `<button data-history="${Number(item.id)}">${escapeText(item.teks.slice(0, 80))}</button>`).join('') : '<p>Belum ada pemeriksaan.</p>';
    renderHistory();
  } catch (error) { console.warn(error.message); }
}

function renderHistory() {
  const selected = $('historyFilter').value;
  const filtered = recentHistory.filter(item => !selected || item.jenis === selected);
  $('historyCount').textContent = `${filtered.length} pemeriksaan ditampilkan`;
  $('historyList').innerHTML = filtered.length ? filtered.map(item => `<button class="history-item" data-history="${Number(item.id)}"><span class="history-symbol">${icon(item.jenis === 'gambar' ? 'image' : item.jenis === 'tautan' ? 'link' : 'file')}</span><span class="history-copy"><strong>${escapeText(item.teks)}</strong><small>${escapeText(item.jenis)} · ${escapeText(shortDate(item.waktu))} · ${Number(item.jumlah_hasil)} sumber</small></span><span class="history-status ${scoreType(item.kesimpulan)}">${escapeText(item.kesimpulan || 'Belum ada hasil')}</span></button>`).join('') : '<div class="empty-small">Belum ada riwayat untuk pilihan ini.</div>';
}

async function loadStats() {
  try {
    const data = await requestAPI('/api/statistik');
    $('statTotal').textContent = data.total || 0;
    $('statTeks').textContent = data.per_jenis?.teks || 0;
    $('statGambar').textContent = data.per_jenis?.gambar || 0;
    $('statTautan').textContent = data.per_jenis?.tautan || 0;
  } catch (error) { console.warn(error.message); }
}

async function showHistoryDetail(id) {
  try {
    const data = await requestAPI(`/api/riwayat/${id}`);
    displayResult(data);
    openPage('hasil');
  } catch (error) { notify(error.message, true); }
}

function cleanOCR(value) {
  return String(value || '').split(/\r?\n/)
    .map(line => line.replace(/\s+/g, ' ').replace(/^[\s:•-]+|[\s:•-]+$/g, '').trim())
    .filter(line => line && !/^(diteruskan berkali-kali|forwarded many times|ketik pesan|hari ini|bagikan ke keluarga|share ke grup|pesan diteruskan|baca selengkapnya|lihat lainnya|read more)$/i.test(line))
    .join(' ').replace(/\bditeruskan berkali-kali\b/gi, '').replace(/\s+/g, ' ').trim();
}

function useImage(file) {
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) { notify('Pilih gambar PNG, JPG, atau WebP.', true); return; }
  if (file.size > 8 * 1024 * 1024) { notify('Ukuran gambar maksimal 8 MB.', true); return; }
  selectedFile = file;
  if (filePreview) URL.revokeObjectURL(filePreview);
  filePreview = URL.createObjectURL(file);
  $('imagePreview').src = filePreview;
  $('imageFilename').textContent = file.name;
  $('imageFileSize').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
  $('imagePreviewBox').hidden = false;
  $('ocrStatus').textContent = 'Gambar siap. Klik Baca teks gambar (OCR).';
  $('ocrText').value = '';
}

async function runOCR() {
  if (!selectedFile) { notify('Pilih gambar terlebih dahulu.', true); return; }
  if (typeof Tesseract === 'undefined') {
    notify('Modul OCR belum dimuat. Pastikan laptop terhubung internet lalu refresh halaman.', true);
    return;
  }
  const button = $('runOCR');
  const text = $('ocrStatus');
  button.disabled = true;
  text.textContent = 'Menyiapkan pembaca gambar...';
  let worker;
  try {
    worker = await Tesseract.createWorker(['ind', 'eng'], 1, {
      logger: (progress) => {
        if (progress.status === 'recognizing text') text.textContent = `Membaca teks: ${Math.round((progress.progress || 0) * 100)}%`;
      }
    });
    const result = await worker.recognize(selectedFile);
    const extracted = cleanOCR(result.data?.text || '');
    $('ocrText').value = extracted.slice(0, 3500);
    text.textContent = extracted ? 'Teks sudah dirapikan otomatis. Kamu masih bisa mengoreksi sebelum memeriksa.' : 'Tidak ada teks terbaca. Coba gambar lebih jelas atau ketik manual.';
    if (extracted) notify('OCR selesai. Koreksi teks bila perlu, lalu klik Periksa gambar.');
  } catch (error) { notify('Gagal membaca gambar. Coba format JPG/PNG atau periksa koneksi internet.', true); text.textContent = 'OCR gagal.'; }
  finally { if (worker) await worker.terminate().catch(() => {}); button.disabled = false; }
}

function initialize() {
  $('todayLabel').textContent = new Date().toLocaleDateString('id-ID', {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
  document.querySelectorAll('[data-nav]').forEach(button => button.addEventListener('click', event => { event.preventDefault(); openPage(button.dataset.nav); }));
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-history]');
    if (target) showHistoryDetail(Number(target.dataset.history));
  });
  $('menuToggle').addEventListener('click', () => $('sidebar').classList.toggle('open'));
  $('quickSearch').addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.value.trim()) { $('textClaim').value = event.target.value.trim(); $('textCount').textContent = `${$('textClaim').value.length} / 3500 karakter`; openPage('teks'); }
  });
  $('textClaim').addEventListener('input', () => $('textCount').textContent = `${$('textClaim').value.length} / 3500 karakter`);
  $('checkText').addEventListener('click', () => submitCheck({jenis: 'teks', teks: $('textClaim').value}, $('checkText')));
  const drop = $('dropZone');
  drop.addEventListener('click', () => $('imageFile').click());
  drop.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); $('imageFile').click(); } });
  ['dragenter', 'dragover'].forEach(type => drop.addEventListener(type, event => {event.preventDefault(); drop.classList.add('dragging');}));
  ['dragleave', 'drop'].forEach(type => drop.addEventListener(type, event => {event.preventDefault(); drop.classList.remove('dragging');}));
  drop.addEventListener('drop', event => useImage(event.dataTransfer.files[0]));
  $('imageFile').addEventListener('change', event => useImage(event.target.files[0]));
  $('removeImage').addEventListener('click', () => {
    selectedFile = null; $('imageFile').value = ''; $('imagePreviewBox').hidden = true; $('ocrText').value = ''; $('ocrStatus').textContent = 'Belum ada gambar dipilih';
    if (filePreview) URL.revokeObjectURL(filePreview);
    filePreview = '';
  });
  $('runOCR').addEventListener('click', runOCR);
  $('checkImage').addEventListener('click', () => submitCheck({jenis: 'gambar', teks: $('ocrText').value, image_url: $('imageUrl').value.trim()}, $('checkImage')));
  $('checkLink').addEventListener('click', () => submitCheck({jenis: 'tautan', url: $('linkUrl').value.trim(), teks: $('linkClaim').value}, $('checkLink')));
  $('historyFilter').addEventListener('change', renderHistory);
  $('clearHistory').addEventListener('click', async () => {
    if (!recentHistory.length || !confirm('Hapus semua riwayat pemeriksaan?')) return;
    try { await requestAPI('/api/riwayat', {method:'DELETE'}); await Promise.all([loadHistory(), loadStats()]); notify('Riwayat berhasil dihapus.'); }
    catch (error) { notify(error.message, true); }
  });
  $('printResult').addEventListener('click', () => { if (currentResult) window.print(); });
  requestAPI('/api/status').then(data => {
    const active = data.google_aktif;
    $('keyIndicator').textContent = active ? 'API siap' : 'API key belum diisi';
    $('keyIndicator').classList.add(active ? 'ok' : 'bad');
    $('integrationText').textContent = active ? 'API key siap digunakan. Mulai periksa klaim untuk menguji koneksinya.' : 'Isi GOOGLE_FACTCHECK_API_KEY pada file .env terlebih dahulu.';
  }).catch(() => { $('keyIndicator').textContent = 'Server tidak aktif'; $('keyIndicator').classList.add('bad'); $('integrationText').textContent = 'Tidak bisa memeriksa server.'; });
  loadHistory(); loadStats();
}

document.addEventListener('DOMContentLoaded', initialize);
