"""변이 전수 경보가 **무슨 병인지** 말한다 (감사 301).

사장님 지적(2026-08-22): *"계속 변이 전수 실패라고 떠. '안전장치 중 일부가
지금 아무도 안 지키고 있다'라고 떠."*

야간 전수는 2026-08-16부터 엿새 연속 실패했고, 폰으로 온 경보는 매번 같은
한 문장이었다. 그런데 그날의 실제 결과는 이랬다.

    잡음 934 · 놓침 4 · 건너뜀 0 · 검사 자체 고장 19

23건 중 19건은 **검사가 그 환경에서 아예 안 돈 것**이다. 이건 "안전장치가
무방비"와 전혀 다른 병이다.

  · 놓침 — 코드를 망가뜨렸는데 검사가 통과했다. **진짜 무방비**다.
  · 검사 자체 고장 — 원본 코드에서 이미 검사가 실패한다. 무방비가 아니라
    **못 쟀다**는 뜻이고, 대개 환경 문제다(패키지·데이터·브라우저).

둘을 같은 문장으로 말하면 읽는 쪽은 아무것도 못 고친다. 그래서 엿새가
지나갔다 — 경보는 매일 울렸는데, 울린 내용이 아무것도 알려 주지 않았으니까.

여기서 지키는 것:
  · 전수가 끝나면 요약 파일을 남긴다(무엇이 몇 건인지, 어느 검사인지).
  · 워크플로의 경보 단계가 **그 요약을 실제로 실어 보낸다.**
  · 여러 줄·따옴표가 섞여도 보내는 본문이 깨지지 않는다 — 경보가 조용히
    안 나가는 것이 이 잡의 최악이다.

⚠️ 이 검사는 소스에 특정 문자열이 있는지 보지 않는다. 워크플로에 적힌
   **그 쉘을 실제로 돌리고**, 가짜 웹훅으로 받은 본문을 읽는다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SWEEP = ROOT / ".github" / "workflows" / "mutation-sweep.yml"

# 실제 전수가 남기는 모양 그대로 — 따옴표와 여러 줄이 섞여 있다.
_SUMMARY = '''잡음 934 · 놓침 4 · 건너뜀 0 · 검사 자체 고장 19

💥 검사 자체 고장 19건 — 검사가 원본 코드에서 실패했다("무방비"가 아니라 "못 쟀다"):
   · tests/test_the_ledger_never_goes_backwards.py
❌ 놓침 4건 — 코드를 망가뜨려도 검사가 통과했다. **이것이 진짜 무방비다**:
   · 자산군 코어를 비운다(위험자산 한 덩어리로 되돌아간다)
'''


def _alert_script() -> str:
    """워크플로에서 '실패 경보' 단계의 쉘을 그대로 떼어 온다."""
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(SWEEP.read_text("utf-8"))
    steps = doc["jobs"]["sweep"]["steps"]
    hit = [s for s in steps if "경보" in (s.get("name") or "")]
    assert len(hit) == 1, f"경보 단계를 못 찾았다: {[s.get('name') for s in steps]}"
    script = hit[0]["run"]
    # ${{ ... }}는 액션스 표현식이다 — 여기서는 고정 문자열로 바꿔 돌린다.
    import re
    return re.sub(r"\$\{\{[^}]*\}\}", "FAKE", script)


class _Catcher(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        type(self).received.append(self.rfile.read(n).decode("utf-8"))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture()
def _sent(tmp_path):
    """가짜 웹훅을 세우고, 워크플로의 경보 쉘을 진짜로 돌린 뒤 받은 본문."""
    if not shutil.which("bash"):
        pytest.skip("bash 없음")
    _Catcher.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Catcher)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    hook = f"http://127.0.0.1:{srv.server_address[1]}/hook"
    (tmp_path / "mutation_summary.txt").write_text(_SUMMARY, encoding="utf-8")
    try:
        r = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", _alert_script()],
            cwd=tmp_path, capture_output=True, text=True, timeout=120,
            env={**os.environ, "DISCORD_WEBHOOK_URL": hook,
                 "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "",
                 "PATH": os.environ.get("PATH", ""),
                 # 러너에서는 python3이 PATH에 있다. 이 검사에서도 같게 둔다.
                 })
        assert r.returncode == 0, f"경보 쉘이 죽었다:\n{r.stdout}\n{r.stderr}"
    finally:
        srv.shutdown()
    assert _Catcher.received, "경보가 아예 안 나갔다 — 이 잡의 최악이다"
    return _Catcher.received[0]


def test_the_alarm_is_valid_json(_sent):
    """본문이 깨지지 않는다.

    예전 코드는 `-d "{\\"content\\":\\"$MSG\\"}"`로 JSON을 손으로 짰다.
    한 줄짜리 메시지에서는 문제가 없었지만, 요약을 실으면 줄바꿈과
    따옴표가 들어온다 — 그러면 페이로드가 깨져 **경보가 조용히 안 나간다.**
    """
    body = json.loads(_sent)          # 깨졌으면 여기서 죽는다
    assert body.get("content"), f"본문이 비어 있다: {_sent[:200]}"


def test_the_alarm_carries_the_actual_numbers(_sent):
    """폰만 보고도 무슨 일인지 알 수 있어야 한다."""
    content = json.loads(_sent)["content"]
    for must in ("놓침 4", "검사 자체 고장 19"):
        assert must in content, (
            f"경보에 '{must}'가 없다 — 숫자가 없으면 매일 같은 소리로만 "
            f"들리고, 실제로 엿새가 그렇게 지나갔다:\n{content}")


def test_the_alarm_separates_the_two_diseases(_sent):
    """'못 쟀다'와 '무방비'를 구별해서 말한다."""
    content = json.loads(_sent)["content"]
    assert "진짜 무방비" in content, (
        "놓침(진짜 무방비)과 검사 고장(못 쟀다)을 구별하는 말이 없다 — "
        f"둘은 고치는 곳이 다르다:\n{content}")


def test_the_alarm_still_speaks_when_the_sweep_died_early(tmp_path):
    """대조군 — 요약 파일이 아예 없어도 경보는 나가야 한다.

    전수가 설치 단계에서 죽으면 요약이 없다. 그때 경보가 침묵하면
    **가장 위험한 고장이 가장 조용해진다.** 요약이 없다는 사실 자체를
    말하고 나가야 한다.
    """
    _Catcher.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Catcher)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    hook = f"http://127.0.0.1:{srv.server_address[1]}/hook"
    try:                              # mutation_summary.txt를 **안** 만든다
        r = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", _alert_script()],
            cwd=tmp_path, capture_output=True, text=True, timeout=120,
            env={**os.environ, "DISCORD_WEBHOOK_URL": hook,
                 "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""})
        assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    finally:
        srv.shutdown()
    assert _Catcher.received, "요약이 없을 때 경보가 통째로 침묵했다"
    content = json.loads(_Catcher.received[0])["content"]
    assert "요약 없음" in content, (
        f"요약이 없다는 사실을 말하지 않는다: {content}")


def test_the_sweep_keeps_the_summary_as_evidence():
    """요약 파일이 실행물로 보존된다 — 나중에 되짚을 수 있어야 한다."""
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(SWEEP.read_text("utf-8"))
    steps = doc["jobs"]["sweep"]["steps"]
    keep = [s for s in steps
            if (s.get("uses") or "").startswith("actions/upload-artifact")]
    assert keep, "결과를 아무것도 보존하지 않는다"
    paths = str(keep[0].get("with", {}).get("path") or "")
    assert "mutation_summary.txt" in paths, (
        f"요약을 보존하지 않는다 — 로그는 90일 뒤 사라진다: {paths}")


def test_the_tool_can_ask_only_why_the_checks_are_broken():
    """--baseline 문이 실제로 있다(전수 3시간을 돌리지 않고 원인만 묻는 길).

    ⚠️ 이 도구는 **import하면 그 자리에서 전수가 돈다.** 그래서 열어서
       읽지 않고, 하위 프로세스로 도움말만 물어본다.
    """
    src = (ROOT / "scripts" / "mutation_check.py").read_text("utf-8")
    assert '"--baseline" in sys.argv' in src, (
        "원인만 따로 묻는 문이 없다 — 그러면 다음에도 전수 3시간을 돌려 "
        "로그를 손으로 읽어야 한다")
    # 문이 실제로 열리는지: 목록 정합성 검사(--dry-run)와 함께 있어야 한다.
    r = subprocess.run([sys.executable, "scripts/mutation_check.py", "--dry-run"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"--dry-run이 죽었다:\n{r.stdout}\n{r.stderr}"


def test_the_sweep_actually_writes_the_summary(tmp_path):
    """전수가 요약 파일을 **정말 쓴다** — 문자열이 있는지가 아니라 돌려서 본다.

    ⚠️ 이 도구는 import하면 그 자리에서 전수가 돈다. 그래서 하위
       프로세스로, 그것도 **한 항목만** 걸리는 부분 실행으로 부른다.

    부분 실행에서도 요약을 쓰되 첫 줄이 '부분 실행'이라고 못박는다.
    안 쓰면 이 기능이 살아 있는지 확인할 길이 전수(3시간)뿐이고, 그러면
    요약이 조용히 멈춰도 아무도 모른다 — 이 저장소가 이미 두 번 겪은 병이다.
    """
    work = tmp_path / "run"
    work.mkdir()
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutation_check.py"),
         "첫 화면이 확정값을"],
        cwd=ROOT, capture_output=True, text=True, timeout=900)
    out = (ROOT / "mutation_summary.txt")
    try:
        assert out.exists(), (
            f"요약 파일을 안 썼다 — 경보가 실을 내용이 사라진다:\n{r.stdout[-600:]}")
        text = out.read_text("utf-8")
        assert text.splitlines()[0].startswith("⚠️ 부분 실행"), (
            "부분 실행 결과인데 그 사실을 첫 줄에 안 적었다 — 부분을 전부로 "
            f"읽히게 두면 안 된다:\n{text}")
        assert "잡음" in text, f"결과 줄이 요약에 없다:\n{text}"
    finally:
        out.unlink(missing_ok=True)
