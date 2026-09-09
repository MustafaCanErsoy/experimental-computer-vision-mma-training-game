"""Offline HTML smoke test in an isolated headless Edge profile; invented pixels only."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadowmma.diagnostics import RecognitionReport
import numpy as np


def main():
    target = Path(tempfile.mkdtemp(prefix="report-ui-", dir=ROOT / "build"))
    report = RecognitionReport(target / "session", record_frames=True)
    report.observe(np.full((240, 320, 3), 85, dtype=np.uint8), valid=True, body=True, guard=False)
    report.add("detected", "Algılandı: Sol yumruk", move="left_punch", attempt=1, evidence=True,
               measures={"hareket_yuzdesi":130,"ileri_yuzdesi":130,"yana_yuzdesi":0,"yukari_yuzdesi":0,"kare_araligi_ms":130})
    report.add("game", "Oyun vuruşu puanladı", detail="hit", move="left_punch", expected="left_punch", event=1, attempt=1)
    report.add("rejected", "Uzanış iki net karede doğrulanamadı", attempt=2, evidence=True)
    report.add("game","Hareket tanındı; hedef farklı",detail="wrong",move="uppercut",expected="left_punch",attempt=3)
    report.close()
    # Execute real page controls after load; assertions are emitted into visible DOM.
    probe = '''<script>setTimeout(()=>{try{
const assert=(x,s)=>{if(!x)throw Error(s)};
document.getElementById('filter').value='detected';document.getElementById('filter').dispatchEvent(new Event('change'));
assert(document.querySelectorAll('article').length===1,'recognition filter');
assert(document.querySelector('article').textContent.includes('Sol yumruk'),'simple move visible');
assert(document.querySelector('.measures').textContent.includes('%130'),'threshold percentage visible');
assert(document.getElementById('mismatch').textContent.startsWith('1 hareket'),'wrong target total visible');
document.getElementById('filter').value='rejected';document.getElementById('filter').dispatchEvent(new Event('change'));
assert(document.querySelectorAll('article').length===1,'rejection filter');
document.getElementById('filter').value='';document.getElementById('search').value='puanladı';document.getElementById('search').dispatchEvent(new Event('input'));
assert(document.querySelectorAll('article').length===1,'Turkish search');
document.getElementById('search').value='';document.getElementById('filter').value='detected';document.getElementById('filter').dispatchEvent(new Event('change'));
const img=document.querySelector('article img');img.loading='eager';
img.onload=()=>{document.body.dataset.qa=img.naturalWidth===320?'passed':'bad image'};
if(img.complete&&img.naturalWidth===320)document.body.dataset.qa='passed';
}catch(e){document.body.dataset.qa='failed:'+e.message}},100);</script>'''
    page = report.folder / "ui-test.html"
    page.write_text(report.path.read_text(encoding="utf-8").replace('</html>', probe+'</html>'), encoding="utf-8")
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    result = subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                             "--disable-background-networking", f"--user-data-dir={target / 'profile'}", "--dump-dom",
                             "--virtual-time-budget=2500", "--window-size=1360,1100",
                             f"--screenshot={target / 'report.png'}", page.as_uri()],
                            capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    (target / "dom.html").write_bytes(result.stdout)
    assert result.returncode == 0 and b'data-qa="passed"' in result.stdout, str(target)
    assert (target / "report.png").is_file()
    print(json.dumps({"report_ui": "passed", "checks": ["filter detected", "filter rejected", "Turkish search", "local JPEG loads", "threshold progress", "wrong target total"],
                      "camera_opened": False, "folder": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
