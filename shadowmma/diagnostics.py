"""Bounded local recognition journal. No network, audio or landmark persistence."""
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from . import __version__
from .core import RULESET
from .metrics import atomic_json


def session_folder(parent):
    return Path(parent) / ("recognition-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])


class RecognitionReport:
    MAX_EVENTS = 5000
    MAX_IMAGES = 180

    def __init__(self, folder, *, record_frames=False, clock=perf_counter, async_writes=False):
        self.folder = Path(folder)
        self.clock, self.started = clock, clock()
        self.created = datetime.now(timezone.utc).isoformat()
        self.events = []
        self.counts = Counter()
        self.frames = Counter()
        self.record_frames = record_frames
        self.images = 0
        self.buffer = deque(maxlen=8)
        self.error = ""
        self.last_write = -1.
        self.last_capture = -1.
        self.closed = False
        self.dropped = 0
        self.stream = None
        self.writable = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report") if async_writes else None
        self.future = None
        try:
            self.folder.mkdir(parents=True, exist_ok=False)
            self.stream = (self.folder / "events.jsonl").open("x", encoding="utf-8")
            self.writable = True
        except OSError as exc:
            self.error = "Rapor yazılamıyor: " + str(exc)
        self.add("session", "Seans başladı", detail="Görsel kayıt açık" if record_frames else "Görsel kayıt kapalı")
        self.flush(force=True)

    @property
    def path(self):
        return self.folder / "report.html"

    def set_frames(self, enabled):
        self.record_frames = bool(enabled)
        self.buffer.clear()
        self.add("settings", "Görsel kayıt açıldı" if enabled else "Görsel kayıt kapatıldı",
                 detail="Yalnız sonraki olay kareleri yerel saklanır. Önceki kayıtlar rapor klasöründe kalır.")

    def observe(self, pixels, *, valid, body, guard):
        self.frames["processed"] += 1
        self.frames["valid"] += int(valid)
        self.frames["body"] += int(body)
        self.frames["guard"] += int(guard)
        now = self.clock()
        if self.record_frames and self.images < self.MAX_IMAGES and now - self.last_capture >= .10:
            # Only a short RAM buffer, encoded at a bounded resolution.
            from PIL import Image
            import io
            picture = Image.fromarray(pixels[:, :, ::-1])
            picture.thumbnail((480, 360))
            target = io.BytesIO()
            picture.save(target, format="JPEG", quality=75)
            self.buffer.append((round(now-self.started, 3), target.getvalue()))
            self.last_capture = now

    def add(self, kind, title, *, detail="", move="", expected="", event=0, attempt=0, checks=None, measures=None, evidence=False):
        if self.closed:
            return
        self.counts[kind] += 1
        if kind == "detected" and move in ("left_punch", "right_punch", "uppercut"):
            self.counts["move_"+move] += 1
        if kind == "game" and detail in ("hit", "defeated"):
            self.counts["scored"] += 1
        if kind == "game" and detail == "wrong":
            self.counts["wrong_target"] += 1
        if len(self.events) >= self.MAX_EVENTS:
            self.dropped += 1
            return
        row = dict(id=len(self.events)+1, t=round(max(0., self.clock()-self.started), 3),
                   kind=str(kind)[:32], title=str(title)[:240], detail=str(detail)[:600],
                   move=str(move)[:32], expected=str(expected)[:32], event=int(event), attempt=int(attempt))
        if checks:
            # Explicit boolean whitelist: never serialize feature/landmark objects.
            row["checks"] = {side: {str(k)[:40]: v for k, v in values.items() if type(v) is bool}
                             for side, values in checks.items() if side in ("left", "right")}
        if measures:
            # Quantized threshold percentages/timing only. No landmark or raw
            # displacement coordinates, arbitrary fields, or nonfinite floats.
            allowed = {"hareket_yuzdesi", "ileri_yuzdesi", "yana_yuzdesi", "yukari_yuzdesi", "kare_araligi_ms"}
            row["measures"] = {key: max(0, min(1000, value)) for key, value in measures.items()
                               if key in allowed and type(value) is int}
        row["images"] = []
        if evidence and self.record_frames and self.buffer and not self.error:
            candidates = list(self.buffer)
            for index in sorted({0, len(candidates)//2, len(candidates)-1}):
                if self.images >= self.MAX_IMAGES:
                    break
                timestamp, content = candidates[index]
                name = f"frame-{self.images+1:04d}.jpg"
                try:
                    (self.folder / name).write_bytes(content)
                    row["images"].append({"file": name, "t": timestamp})
                    self.images += 1
                except OSError as exc:
                    self.error = "Görsel yazılamıyor: " + str(exc)
                    break
        self.events.append(row)
        if self.stream and not self.error:
            try:
                self.stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                self.stream.flush()
            except OSError as exc:
                self.error = "Olay kaydı yazılamıyor: " + str(exc)

    def flush(self, *, force=False):
        if not self.writable:
            return
        now = self.clock()
        if not force and now-self.last_write < 3.:
            return
        if self.future is not None:
            if not force and not self.future.done():
                return  # At most one snapshot in flight; never accumulate work.
            self.future.result()
            self.future = None
        self.last_write = now
        data = {"schema": 2, "ruleset": RULESET, "version": __version__, "created_utc": self.created,
                "duration_s": round(max(0., now-self.started), 2), "closed": self.closed,
                "counts": dict(self.counts), "frames": dict(self.frames), "images_saved": self.images,
                "record_frames": self.record_frames, "dropped_events": self.dropped,
                "limits": {"events": self.MAX_EVENTS, "images": self.MAX_IMAGES}, "error": self.error,
                "privacy": "Local only. Optional event stills; no audio/video or body coordinate files.",
                "accuracy": "Recognition observations, not user-confirmed accuracy.", "events": list(self.events)}
        if self.executor and not force:
            self.future = self.executor.submit(self._write_snapshot, data)
        else:
            self._write_snapshot(data)

    def _write_snapshot(self, data):
        try:
            atomic_json(self.folder / "report.json", data)
            temporary = self.folder / ".report.html.tmp"
            temporary.write_text(render_html(data), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            self.error = "Rapor güncellenemiyor: " + str(exc)

    def close(self):
        if self.closed:
            return
        self.add("session", "Seans kapandı")
        self.closed = True
        self.buffer.clear()
        self.flush(force=True)
        if self.executor:
            self.executor.shutdown(wait=True)
        if self.stream:
            try:
                self.stream.close()
            except OSError:
                pass


def render_html(data):
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return HTML.replace("__DATA__", payload).replace("__VERSION__", escape(data["version"]))


HTML = '''<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>ShadowMMA · Algılama raporu</title>
<style>
:root{color-scheme:dark;font:16px/1.5 system-ui;background:#141516;color:#e8e1d3}body{max-width:1120px;margin:auto;padding:32px 24px}
h1{font-size:36px;margin:8px 0}h2{font-size:22px}p{color:#bcb7ac}small{color:#bcb7ac}.eyebrow{color:#d7ad6f;letter-spacing:3px;font-size:12px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}.card,article{background:#202122;border:1px solid #383735;border-radius:12px;padding:20px}.card b{display:block;font-size:30px}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}select,input,button{font:inherit;color:inherit;background:#272828;border:1px solid #656052;border-radius:6px;padding:10px}input{flex:1;min-width:150px}button{cursor:pointer}
article{margin:14px 0}article[data-kind="detected"],article[data-kind="game"]{border-left:4px solid #8ca777}article[data-kind="rejected"]{border-left:4px solid #c58965}article header{display:flex;justify-content:space-between;gap:16px}article h3{margin:0;font-size:18px}
.gallery{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}figure{margin:0;flex:1;min-width:180px;max-width:320px}img{width:100%;border-radius:6px}figcaption{font-size:12px;color:#bcb7ac}summary{cursor:pointer}pre{white-space:pre-wrap;font-size:13px}.notice{border-left:3px solid #d7ad6f;padding:10px 16px;background:#24221e}a{color:#ddbd8a}
@media(max-width:650px){.cards{grid-template-columns:repeat(2,1fr)}body{padding:20px 14px}h1{font-size:28px}article header{display:block}}
</style>
<div class="eyebrow">SHADOWMMA · __VERSION__ · YEREL SEANS</div><h1>Algılayıcı ne gördü?</h1>
<p id="meta"></p><p>Bu rapor yazılımın gözlemlerini gösterir. Tanınmayan her olay bir yumruk değildir; doğruluk oranı için yaptığın hareketin ayrıca etiketlenmesi gerekir.</p>
<div id="notice" class="notice"></div><div class="cards" id="cards"></div><p id="moves"></p><p id="mismatch"></p>
<h2>Olayları incele</h2><p>Deneme numarası aynı hareketin başlangıç, hareket yönü, algılama ve oyun sonucunu birleştirir. Görseller varsa olay öncesi ve olay anından seçilmiş yerel karelerdir.</p>
<div class="controls"><select id="filter" aria-label="Olay türü"><option value="">Tüm olaylar</option><option value="detected">Tanınan hareketler</option><option value="rejected">Sayılmayan denemeler</option><option value="game">Oyun sonuçları</option><option value="tracking">Takip / görünürlük</option><option value="motion">Hareket kanıtı</option></select><input id="search" aria-label="Olaylarda ara" placeholder="Sol yumruk, aşağıdan, deneme numarası…"><button onclick="location.reload()">Güncelle</button></div>
<small id="amount"></small><main id="events"></main><button id="more">Daha fazla göster</button>
<p>Makineyle inceleme: <a href="report.json">report.json</a> · Kesinti günlüğü: <a href="events.jsonl">events.jsonl</a>. Seans açıkken dosya yaklaşık 3 saniyede bir güncellenir; yeni durum için Güncelle'ye bas.</p>
<script id="data" type="application/json">__DATA__</script><script>
const names={left_punch:"Sol yumruk",right_punch:"Sağ yumruk",uppercut:"Aşağıdan vur"};
const d=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);let limit=100;
el('mismatch').textContent=(d.counts.wrong_target||0)+' hareket tanındı fakat istenen sınıfla eşleşmedi. Mesafe yüzdesi, yazılımın hareket eşiğine göredir; teknik kalite veya doğruluk puanı değildir.';
el('moves').textContent=Object.entries(names).map(([key,title])=>title+': '+(d.counts['move_'+key]||0)).join(' · ');
el('meta').textContent=new Date(d.created_utc).toLocaleString('tr-TR')+' · '+d.duration_s+' saniye · '+(d.closed?'Seans kapandı':'Seans açık / kesintide kalmış olabilir');
el('notice').textContent=(d.record_frames?'Görsel kayıt açık.':'Görsel kayıt kapalı.')+' Saklanan kare: '+d.images_saved+'/'+d.limits.images+'. '+(d.images_saved>=d.limits.images?'Görsel sınırına ulaşıldı; yeni görseller saklanmıyor. ':'')+(d.dropped_events?'Olay sınırı nedeniyle ayrıntısı yazılmayan: '+d.dropped_events+'. ':'')+d.error;
for(const [title,value] of [['Tanınan hareket',d.counts.detected||0],['Sayılmayan deneme',d.counts.rejected||0],['Puanlanan vuruş',d.counts.scored||0],['İşlenen kare',d.frames.processed||0]]){const a=document.createElement('div');a.className='card';const b=document.createElement('b');b.textContent=value;a.append(b,document.createTextNode(title));el('cards').append(a)}
function render(){const term=el('search').value.toLocaleLowerCase('tr');const rows=d.events.filter(x=>(!el('filter').value||x.kind===el('filter').value)&&JSON.stringify(x).toLocaleLowerCase('tr').includes(term)).reverse();el('events').replaceChildren();el('amount').textContent=rows.length+' olay · en yeni önce';
for(const r of rows.slice(0,limit)){const a=document.createElement('article');a.dataset.kind=r.kind;const h=document.createElement('header'),title=document.createElement('h3'),stamp=document.createElement('small');title.textContent=r.title;stamp.textContent=r.t.toFixed(2)+' s'+(r.attempt?' · Deneme '+r.attempt:'');h.append(title,stamp);a.append(h);const p=document.createElement('p');p.textContent=[r.detail,r.expected?'İstenen: '+(names[r.expected]||r.expected):'',r.move?'Algılanan: '+(names[r.move]||r.move):'',r.event?'Olay: '+r.event:''].filter(Boolean).join(' · ');a.append(p);
if(r.measures){const m=r.measures,p=document.createElement('p');p.className='measures';p.textContent='Hareket eşiği: %'+m.hareket_yuzdesi+' · İleri: %'+m.ileri_yuzdesi+' · Yana: %'+m.yana_yuzdesi+' · Yukarı: %'+m.yukari_yuzdesi+' · Kare aralığı: '+m.kare_araligi_ms+' ms';a.append(p)}
if(r.checks){const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Algılamaya dayanak olan koşullar (true: sağlandı, false: sağlanmadı)';pre.textContent=JSON.stringify(r.checks,null,2);details.append(summary,pre);a.append(details)}
if(r.images.length){const gallery=document.createElement('div');gallery.className='gallery';for(const im of r.images){const f=document.createElement('figure'),link=document.createElement('a'),img=document.createElement('img'),caption=document.createElement('figcaption');link.href=im.file;link.target='_blank';link.rel='noopener';img.src=im.file;img.loading='lazy';img.alt=r.title+' · '+im.t+' saniye';caption.textContent=im.t+' s · büyütmek için aç';link.append(img);f.append(link,caption);gallery.append(f)}a.append(gallery)}el('events').append(a)}el('more').hidden=rows.length<=limit}
el('filter').onchange=el('search').oninput=()=>{limit=100;render()};el('more').onclick=()=>{limit+=100;render()};render();
</script></html>'''
