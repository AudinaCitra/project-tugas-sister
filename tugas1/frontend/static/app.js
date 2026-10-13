/* SI PIKET - FRONT END. Terhubung ke Aplikasi A lewat REST API.
   Tidak menyimpan kata sandi; token login disimpan hanya selama tab aktif. */
"use strict";
const API = (window.API_URL || "http://127.0.0.1:5000").replace(/\/$/, "");
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem("piket_token") || "";
let pengguna = null, anggota = [], laporan = [], opsi = null, dataGedung = null, jadwal = [];
let senin = awalSenin(new Date()), halamanAktif = "beranda", editLaporanId = null;
const NAMA_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
function awalSenin(d) { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - (x.getDay() + 6) % 7); return x; }
function tambahHari(d,n) { const x=new Date(d); x.setDate(x.getDate()+n); return x; }
function iso(d) { return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
function dariIso(s) { const [y,m,d] = s.split("-").map(Number); return new Date(y,m-1,d); }
function tgl(s) { return dariIso(s).toLocaleDateString("id-ID",{day:"numeric",month:"short",year:"numeric"}); }
function tglSingkat(d) { return d.toLocaleDateString("id-ID",{day:"numeric",month:"short"}); }
function h(tag,attrs={},...kids) {
  const el=document.createElement(tag);
  for(const [k,v] of Object.entries(attrs)) {
    if(k==="class") el.className=v;
    else if(k.startsWith("on") && typeof v==="function") el.addEventListener(k.slice(2),v);
    else if(v!==false && v!=null) el.setAttribute(k,v===true?"":String(v));
  }
  for(const child of kids.flat(Infinity)) if(child!=null) el.append(child instanceof Node?child:document.createTextNode(String(child)));
  return el;
}
function selectIsi(select,items,placeholder="",pilihanLama=null) {
  const sebelumnya=pilihanLama ?? select.value; select.replaceChildren();
  if(placeholder) select.append(h("option",{value:""},placeholder));
  items.forEach(x=>select.append(h("option",{value:x.value ?? x},x.label ?? x)));
  if([...select.options].some(o=>o.value===sebelumnya)) select.value=sebelumnya;
}
function pesan(teks,salah=false) {
  const box=$("pesan"); box.hidden=!teks; box.textContent=teks;
  box.className="toast"+(salah?" error":"");
  if(teks) window.scrollTo({top:0,behavior:"smooth"});
}
async function api(path,method="GET",data=null,ops={}) {
  try {
    const headers={}; if(data!=null) headers["Content-Type"]="application/json";
    if(token) headers.Authorization="Bearer "+token;
    const r=await fetch(API+path,{method,headers,body:data!=null?JSON.stringify(data):undefined});
    const json=await r.json(); if(!r.ok) throw new Error(json.error || "Permintaan gagal");
    return json;
  } catch(e) {
    if(!ops.silent) pesan(e.message || "Back end tidak dapat dihubungi. Pastikan port 5000 aktif.",true);
    return null;
  }
}
function admin() { return pengguna?.role==="admin"; }
function bersihLogin() { token=""; pengguna=null; sessionStorage.removeItem("piket_token"); }
function logout() { bersihLogin(); $("appShell").hidden=true; $("loginScreen").hidden=false; $("loginPassword").value=""; $("loginError").textContent=""; $("sidebar").classList.remove("open"); }
function pilihRole() { $("loginNamaWrap").hidden=$("loginRole").value==="admin"; }
async function muatNamaLogin() {
  const list=await api("/anggota", "GET", null,{silent:true});
  if(list) selectIsi($("loginNama"), list.filter(a=>a.aktif).map(a=>({value:a.id,label:`${a.nama} (${a.bagian})`})),"Pilih nama petugas");
  else $("loginNama").replaceChildren(h("option",{},"Back end belum aktif"));
}
async function masuk() {
  const role=$("loginRole").value, password=$("loginPassword").value;
  $("loginError").textContent="";
  if(!password) { $("loginError").textContent="Masukkan kata sandi dahulu."; return; }
  if(role==="petugas" && !$("loginNama").value) { $("loginError").textContent="Pilih nama petugas."; return; }
  $("btnLogin").disabled=true;
  const result=await api("/auth/login","POST",{role,password,anggota_id:role==="petugas"?Number($("loginNama").value):null},{silent:true});
  $("btnLogin").disabled=false;
  if(!result) { $("loginError").textContent="Login gagal. Periksa password, nama, dan apakah back end berjalan."; return; }
  token=result.token; pengguna=result.pengguna; sessionStorage.setItem("piket_token",token);
  $("loginPassword").value="";
  await masukDashboard();
}
async function masukDashboard() {
  $("loginScreen").hidden=true; $("appShell").hidden=false;
  $("headerNama").textContent=pengguna.nama; $("headerPeran").textContent=admin()?"Administrator":pengguna.bagian;
  $("avatar").textContent=pengguna.nama.charAt(0).toUpperCase();
  $("profileAvatar").textContent=pengguna.nama.charAt(0).toUpperCase();
  $("profilNama").textContent=pengguna.nama; $("profilBagian").textContent=pengguna.bagian;
  $("profilRole").textContent=admin()?"Administrator":"Petugas";
  $("navAdmin").hidden=!admin(); $("btnShowLaporan").hidden=!admin();
  $("sapaJudul").textContent=`Halo, ${admin()?"Administrator":pengguna.nama.split(" ")[0]}!`;
  $("sapaDeskripsi").textContent=admin()?"Berikut ringkasan aktivitas kampus hari ini.":"Lihat jadwal dan pekerjaan fasilitas yang ditugaskan kepadamu.";
  $("tanggalHariIni").textContent=new Date().toLocaleDateString("id-ID",{weekday:"long",day:"numeric",month:"long",year:"numeric"});
  $("deskripsiLaporan").textContent=admin()?"Catat barang rusak, tugaskan petugas, dan pantau progresnya.":"Lihat kerusakan yang ditugaskan kepadamu dan perbarui progres penanganannya.";
  const [dataOpsi,dataBgn]=await Promise.all([api("/opsi"),api("/gedung")]);
  if(!dataOpsi || !dataBgn) return;
  opsi=dataOpsi; dataGedung=dataBgn;
  selectIsi($("filterBagian"),Object.keys(opsi.bagian),"Semua bagian");
  selectIsi($("genBagian"),Object.keys(opsi.bagian));
  selectIsi($("angBagian"),Object.keys(opsi.bagian));
  selectIsi($("lapGedung"),dataGedung.gedung);
  selectIsi($("filterGedung"),dataGedung.gedung,"Semua gedung");
  selectIsi($("lapKondisi"),dataGedung.kondisi);
  $("legenda").replaceChildren(...Object.entries(opsi.shift).map(([s,jam])=>h("li",{class:"legend-"+s},`${s}: ${jam}`)));
  $("genMulai").value=iso(senin);
  await ambilAnggota(); await perbaruiData(); tampilHalaman("beranda");
}
async function ambilAnggota() {
  const data=await api("/anggota"); if(!data) return;
  anggota=data; const aktif=data.filter(x=>x.aktif);
  const options=aktif.map(a=>({value:a.id,label:`${a.nama} (${a.bagian})`}));
  selectIsi($("sorotNama"),options,"Semua petugas",admin()?null:String(pengguna.anggota_id));
  if(!admin()) $("sorotNama").value=String(pengguna.anggota_id);
  selectIsi($("cutiAnggota"),options);
  selectIsi($("lapPetugas"),options,"Belum ditugaskan");
}
async function perbaruiData() {
  const periode=new URLSearchParams({mulai:iso(senin),selesai:iso(tambahHari(senin,6))});
  const [dJadwal,dLaporan]=await Promise.all([api("/jadwal?"+periode),api("/laporan")]);
  jadwal=dJadwal?.jadwal||[]; laporan=dLaporan||[];
  gambarBeranda(); gambarLaporan(); gambarJadwal();
  if(admin()) { await muatStatistik(); tabelAnggota(); await muatCuti(); }
}
function tampilHalaman(nama) {
  if(nama==="admin" && !admin()) return;
  halamanAktif=nama;
  document.querySelectorAll(".page").forEach(p=>p.hidden=p.id!=="page-"+nama);
  document.querySelectorAll(".nav-link").forEach(b=>b.classList.toggle("active",b.dataset.page===nama));
  const titles={beranda:"Beranda",jadwal:"Jadwal Piket",laporan:"Barang Rusak",admin:"Kelola Admin",profil:"Profil Saya"};
  $("crumbPage").textContent=titles[nama]; $("sidebar").classList.remove("open"); pesan("");
  if(nama==="admin") { muatStatistik(); muatCuti(); }
}
function badge(status) { return h("span",{class:"status status-"+status.toLowerCase().replace(/ /g,"-")},status); }
function gambarBeranda() {
  const selesai=laporan.filter(x=>x.status==="Selesai").length;
  $("metricLabel1").textContent=admin()?"Petugas Aktif":"Shift Saya Minggu Ini";
  $("metric1").textContent=admin()?anggota.filter(x=>x.aktif).length:jadwal.filter(x=>x.anggota_id===pengguna.anggota_id).length;
  $("metricLabel2").textContent=admin()?"Penugasan Minggu Ini":"Laporan Ditugaskan";
  $("metric2").textContent=admin()?jadwal.length:laporan.length;
  $("metric3").textContent=laporan.length-selesai; $("metric4").textContent=selesai;
  const latest=laporan.slice(0,6);
  $("recentTable").replaceChildren(h("thead",{},h("tr",{},["Barang","Gedung","Status"].map(s=>h("th",{},s)))),
    h("tbody",{},latest.length?latest.map(x=>h("tr",{},h("td",{},x.barang),h("td",{},x.gedung),h("td",{},badge(x.status)))):
      h("tr",{},h("td",{colspan:3,class:"empty-table"},"Belum ada laporan kerusakan."))));
  $("ringkasJudul").textContent=admin()?"Aktivitas Admin":"Tugas Saya Minggu Ini";
  const box=$("ringkasanArea"); box.replaceChildren();
  if(admin()) {
    const todos=[`${laporan.filter(x=>!x.petugas_id).length} laporan belum diberi petugas`, `${laporan.filter(x=>x.status==="Diproses").length} pekerjaan sedang diproses`, `${jadwal.length} shift dijadwalkan minggu ini`];
    todos.forEach(s=>box.append(h("div",{class:"summary-row"},h("span",{class:"summary-bullet"},"✓"),s)));
    box.append(h("button",{class:"btn-light",onclick:()=>tampilHalaman("admin")},"Buka panel admin →"));
  } else {
    const list=jadwal.filter(x=>x.anggota_id===pengguna.anggota_id).slice(0,5);
    if(!list.length) box.append(h("p",{class:"muted"},"Belum ada jadwal piket untukmu minggu ini."));
    list.forEach(x=>box.append(h("div",{class:"summary-row"},h("span",{class:"summary-bullet"},"◷"),`${tgl(x.tanggal)} · ${x.shift}`)));
    box.append(h("button",{class:"btn-light",onclick:()=>tampilHalaman("jadwal")},"Lihat jadwal →"));
  }
}
function gambarJadwal() {
  const terakhir=tambahHari(senin,6);
  $("labelMinggu").textContent=`${tglSingkat(senin)} – ${tglSingkat(terakhir)} ${terakhir.getFullYear()}`;
  const bagian=$("filterBagian").value;
  const yangTampil=jadwal.filter(x=>!bagian || x.bagian===bagian);
  const sorotId=Number($("sorotNama").value) || pengguna.anggota_id;
  const peta={}; yangTampil.forEach(j=>(peta[`${j.bagian}|${j.tanggal}|${j.shift}`] ||= []).push(j));
  const wadah=$("grid"); wadah.replaceChildren();
  if(!yangTampil.length) wadah.append(h("div",{class:"empty-notice"},"Belum ada jadwal untuk pilihan ini. Admin dapat membuatnya di Kelola Admin."));
  for(const [nama,cfg] of Object.entries(opsi.bagian)) {
    if(bagian && nama!==bagian) continue;
    const trHead=h("tr",{},h("th",{},"Hari"),cfg.shift.map(s=>h("th",{},s,h("small",{},opsi.shift[s]))));
    const isi=h("tbody");
    for(let i=0;i<7;i++) {
      const hari=tambahHari(senin,i),tanggal=iso(hari);
      const tr=h("tr",{},h("td",{class:"date-cell"},NAMA_HARI[i],h("small",{},tglSingkat(hari))));
      if(!cfg.hari.includes(i)) tr.append(h("td",{colspan:cfg.shift.length,class:"libur"},"Libur"));
      else for(const shift of cfg.shift) {
        const cell=h("td",{class:"shift-cell shift-"+shift});
        const orang=peta[`${nama}|${tanggal}|${shift}`]||[];
        for(const j of orang) {
          const chip=h("span",{class:"person-chip"+(j.anggota_id===sorotId?" my-chip":"")},j.nama);
          if(admin()) chip.append(h("button",{class:"remove-mini",title:"Hapus penugasan",onclick:()=>hapusPenugasan(j)},"×"));
          cell.append(chip);
        }
        if(!orang.length) cell.append(h("span",{class:"muted"},"—"));
        if(admin()) cell.append(h("button",{class:"add-mini",title:"Tambah manual",onclick:()=>tambahPenugasan(nama,tanggal,shift)},"＋"));
        tr.append(cell);
      }
      isi.append(tr);
    }
    wadah.append(h("section",{class:"panel schedule-panel"},h("div",{class:"panel-head"},h("h2",{},nama)),h("div",{class:"table-scroll"},h("table",{},h("thead",{},trHead),isi))));
  }
}
async function tambahPenugasan(bagian,tanggal,shift) {
  const kandidat=anggota.filter(x=>x.aktif&&x.bagian===bagian);
  const daftar=kandidat.map(a=>`${a.id} - ${a.nama}`).join("\n");
  const id=prompt(`Masukkan ID petugas untuk ${bagian}, ${tgl(tanggal)}, shift ${shift}:\n${daftar}`);
  if(id===null) return;
  const r=await api("/jadwal","POST",{anggota_id:Number(id),tanggal,shift});
  if(r) { pesan(r.pesan); await perbaruiData(); }
}
async function hapusPenugasan(j) {
  if(!confirm(`Hapus ${j.nama} dari ${tgl(j.tanggal)} shift ${j.shift}?`)) return;
  const r=await api("/jadwal/"+j.id,"DELETE"); if(r) { pesan(r.pesan); await perbaruiData(); }
}
function gambarLaporan() {
  const gedung=$("filterGedung").value, status=$("filterStatus").value;
  const tampilan=laporan.filter(x=>(!gedung||x.gedung===gedung)&&(!status||x.status===status));
  $("totalLaporan").textContent=`${tampilan.length} laporan ditemukan`;
  const baris=tampilan.map(x=>{
    const pilih=h("select",{class:"status-select","aria-label":"Ubah status laporan " + x.id});
    const choices=admin()?["Dilaporkan","Diproses","Selesai"]:
      x.status==="Dilaporkan"?["Dilaporkan","Diproses"]:x.status==="Diproses"?["Diproses","Selesai"]:["Selesai"];
    choices.forEach(v=>pilih.append(h("option",{value:v},v))); pilih.value=x.status;
    pilih.addEventListener("change",()=>ubahStatus(x,pilih.value));
    const aksi=h("div",{class:"table-actions"},pilih);
    if(admin()) {
      aksi.append(h("button",{class:"small-outline",onclick:()=>editLaporan(x)},"Edit"));
      aksi.append(h("button",{class:"small-outline danger",onclick:()=>hapusLaporan(x)},"Hapus"));
    }
    return h("tr",{},
      h("td",{},h("b",{},x.barang),h("small",{class:"table-sub"},x.kondisi)),
      h("td",{},x.gedung,h("small",{class:"table-sub"},x.ruang)),
      h("td",{},x.nama_petugas || "Belum ditugaskan"),
      h("td",{},badge(x.status)),
      h("td",{},x.keterangan||"—",x.tindakan?h("small",{class:"table-sub"},"Tindakan: "+x.tindakan):null),
      h("td",{},aksi)
    );
  });
  $("tabelLaporan").replaceChildren(
    h("thead",{},h("tr",{},["Barang / Kondisi","Gedung / Ruang","Petugas","Status","Keterangan","Aksi"].map(s=>h("th",{},s)))),
    h("tbody",{},baris.length?baris:h("tr",{},h("td",{colspan:6,class:"empty-table"},"Belum ada laporan sesuai filter.")))
  );
}
function bukaFormLaporan() { editLaporanId=null; $("judulFormLaporan").textContent="Catat Barang Rusak"; bersihFormLaporan(); $("formLaporanBox").hidden=false; }
function bersihFormLaporan() { $("lapRuang").value=""; $("lapBarang").value=""; $("lapKet").value=""; $("lapPetugas").value=""; }
function editLaporan(x) {
  editLaporanId=x.id; $("judulFormLaporan").textContent="Edit Laporan #"+x.id;
  $("lapGedung").value=x.gedung; $("lapRuang").value=x.ruang; $("lapBarang").value=x.barang;
  $("lapKondisi").value=x.kondisi; $("lapKet").value=x.keterangan; $("lapPetugas").value=String(x.petugas_id||"");
  $("formLaporanBox").hidden=false; $("formLaporanBox").scrollIntoView({behavior:"smooth"});
}
async function simpanLaporan() {
  const d={gedung:$("lapGedung").value,ruang:$("lapRuang").value.trim(),barang:$("lapBarang").value.trim(),
    kondisi:$("lapKondisi").value,keterangan:$("lapKet").value.trim(),petugas_id:$("lapPetugas").value||null};
  if(!d.ruang||!d.barang) return pesan("Gedung, ruang, dan barang harus diisi.",true);
  $("btnSimpanLaporan").disabled=true;
  const r=editLaporanId?await api("/laporan/"+editLaporanId,"PUT",d):await api("/laporan","POST",d);
  $("btnSimpanLaporan").disabled=false;
  if(r) { $("formLaporanBox").hidden=true; editLaporanId=null; await perbaruiData(); pesan(r.pesan); }
}
async function ubahStatus(x,status) {
  if(status===x.status) return;
  const tindakan=prompt(`Catatan tindakan untuk ${x.barang} (${status}):`,x.tindakan||"");
  if(tindakan===null) { gambarLaporan(); return; }
  const r=await api(`/laporan/${x.id}/status`,"PATCH",{status,tindakan});
  if(r) { await perbaruiData(); pesan(r.pesan); } else gambarLaporan();
}
async function hapusLaporan(x) {
  if(!confirm(`Hapus laporan ${x.barang} di ${x.gedung}?`)) return;
  const r=await api("/laporan/"+x.id,"DELETE"); if(r) { await perbaruiData(); pesan(r.pesan); }
}
async function buatJadwal() {
  const bagian=$("genBagian").value,mulai=$("genMulai").value;
  if(!mulai) return pesan("Pilih tanggal mulai.",true);
  if(!confirm(`Buat ulang jadwal bagian ${bagian} mulai ${mulai}? Jadwal pada periode ini akan diganti.`)) return;
  $("btnGenerate").disabled=true;
  const r=await api("/jadwal/generate","POST",{bagian,mulai,hari:Number($("genHari").value),per_shift:Number($("genPer").value)});
  $("btnGenerate").disabled=false; if(!r) return;
  $("hasilGenerate").replaceChildren(h("div",{class:"feedback"},r.pesan),
    r.belum_terisi.length?h("p",{class:"muted"},`${r.belum_terisi.length} slot tidak terisi. Cek ketersediaan petugas dan batas shift.`):null);
  senin=awalSenin(dariIso(r.mulai)); $("filterBagian").value=bagian;
  await perbaruiData(); pesan(r.pesan);
}
async function muatStatistik() {
  if(!admin()) return;
  const q=new URLSearchParams({mulai:iso(senin),selesai:iso(tambahHari(senin,6))});
  const s=await api("/statistik?"+q); if(!s) return;
  $("labelStat").textContent=`(${tglSingkat(senin)} – ${tglSingkat(tambahHari(senin,6))})`;
  $("tabelStat").replaceChildren(h("thead",{},h("tr",{},["Nama","Bagian","Pagi","Siang","Malam","Total"].map(v=>h("th",{},v)))),
    h("tbody",{},s.anggota.map(a=>h("tr",{},h("td",{},a.nama),h("td",{},a.bagian),h("td",{},a.pagi),h("td",{},a.siang),h("td",{},a.malam),h("td",{},`${a.total} / ${a.maks_shift_minggu}`)))));
}
function tabelAnggota() {
  if(!admin()) return;
  $("tabelAnggota").replaceChildren(h("thead",{},h("tr",{},["Nama","Bagian","Batas/minggu","Status","Aksi"].map(v=>h("th",{},v)))),
    h("tbody",{},anggota.map(a=>h("tr",{},h("td",{},a.nama),h("td",{},a.bagian),h("td",{},a.maks_shift_minggu),h("td",{},a.aktif?"Aktif":"Nonaktif"),
      h("td",{},h("div",{class:"table-actions"},
        h("button",{class:"small-outline",onclick:()=>ubahAktif(a)},a.aktif?"Nonaktifkan":"Aktifkan"),
        h("button",{class:"small-outline danger",onclick:()=>hapusAnggota(a)},"Hapus")))))));
}
async function tambahAnggota() {
  const d={nama:$("angNama").value.trim(),bagian:$("angBagian").value,maks_shift_minggu:Number($("angMaks").value)};
  const r=await api("/anggota","POST",d); if(r) { $("angNama").value=""; await ambilAnggota(); await perbaruiData(); pesan(r.pesan); }
}
async function ubahAktif(a) {
  const r=await api("/anggota/"+a.id,"PUT",{aktif:!a.aktif}); if(r) { await ambilAnggota(); await perbaruiData(); pesan(r.pesan); }
}
async function hapusAnggota(a) {
  if(!confirm(`Hapus ${a.nama}? Jadwal/cutinya akan ikut terhapus.`)) return;
  const r=await api("/anggota/"+a.id,"DELETE"); if(r) { await ambilAnggota(); await perbaruiData(); pesan(r.pesan); }
}
async function muatCuti() {
  if(!admin()) return;
  const data=await api("/cuti?mulai="+iso(new Date())); if(!data) return;
  $("tabelCuti").replaceChildren(h("thead",{},h("tr",{},["Tanggal","Petugas","Alasan","Aksi"].map(v=>h("th",{},v)))),
    h("tbody",{},data.length?data.map(c=>h("tr",{},h("td",{},tgl(c.tanggal)),h("td",{},`${c.nama} (${c.bagian})`),h("td",{},c.alasan||"—"),h("td",{},h("button",{class:"small-outline danger",onclick:()=>hapusCuti(c)},"Hapus")))):
      h("tr",{},h("td",{colspan:4,class:"empty-table"},"Belum ada cuti yang tercatat."))));
}
async function tambahCuti() {
  if(!$("cutiTanggal").value) return pesan("Pilih tanggal cuti.",true);
  const d={anggota_id:Number($("cutiAnggota").value),tanggal:$("cutiTanggal").value,alasan:$("cutiAlasan").value};
  const r=await api("/cuti","POST",d); if(r) { $("cutiAlasan").value=""; await muatCuti(); pesan(r.pesan); }
}
async function hapusCuti(c) { const r=await api("/cuti/"+c.id,"DELETE"); if(r) { await muatCuti(); pesan(r.pesan); } }
async function geserMinggu(n) { senin=tambahHari(senin,n); await perbaruiData(); }

/* Event: seluruh tombol dashboard */
document.querySelectorAll(".nav-link").forEach(b=>b.addEventListener("click",()=>tampilHalaman(b.dataset.page)));
document.querySelectorAll("[data-go]").forEach(b=>b.addEventListener("click",()=>tampilHalaman(b.dataset.go)));
$("loginRole").addEventListener("change",pilihRole);
$("btnLogin").addEventListener("click",masuk);
$("loginPassword").addEventListener("keydown",e=>{if(e.key==="Enter") masuk();});
[$("sideLogout"),$("headerLogout"),$("profilKeluar")].forEach(b=>b.addEventListener("click",logout));
$("toggleNav").addEventListener("click",()=>$("sidebar").classList.toggle("open"));
$("btnSebelum").addEventListener("click",()=>geserMinggu(-7));
$("btnSesudah").addEventListener("click",()=>geserMinggu(7));
$("btnIni").addEventListener("click",()=>{senin=awalSenin(new Date());perbaruiData();});
$("filterBagian").addEventListener("change",gambarJadwal);
$("sorotNama").addEventListener("change",gambarJadwal);
$("btnCetak").addEventListener("click",()=>window.print());
$("filterGedung").addEventListener("change",gambarLaporan);
$("filterStatus").addEventListener("change",gambarLaporan);
$("btnShowLaporan").addEventListener("click",bukaFormLaporan);
[$("btnCloseLaporan"),$("btnCancelLaporan")].forEach(b=>b.addEventListener("click",()=>{$("formLaporanBox").hidden=true;editLaporanId=null;}));
$("btnSimpanLaporan").addEventListener("click",simpanLaporan);
$("btnGenerate").addEventListener("click",buatJadwal);
$("btnTambahAnggota").addEventListener("click",tambahAnggota);
$("btnTambahCuti").addEventListener("click",tambahCuti);

/* Mulai: ambil nama petugas dari API, lalu cek token lama bila tersedia. */
(async()=>{
  pilihRole(); await muatNamaLogin();
  if(token) {
    const me=await api("/auth/me","GET",null,{silent:true});
    if(me) { pengguna=me; await masukDashboard(); }
    else bersihLogin();
  }
})();
