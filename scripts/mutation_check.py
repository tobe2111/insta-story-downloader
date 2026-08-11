"""변이 시험 — 안전장치를 일부러 망가뜨려, 계약 검사가 정말 잡는지 확인한다.

    python scripts/mutation_check.py

왜 필요한가(2026-08-11 감사 58): 계약 검사가 초록이라는 것은 '검사가
통과했다'는 뜻이지 '장치가 동작한다'는 뜻이 아니다. 이 프로젝트의 검사
상당수가 소스에 특정 문자열이 있는지만 봤고, 그런 검사는 **배선이
사라지는 것은 잡아도 배선이 무력화되는 것은 못 잡는다.** 그리고 그날
잡은 결함은 전부 후자였다 — 킬스위치가 스케일러에 지워지고, 켈리 상한이
되돌려지고, 실적 가드가 사라지는 식.

그래서 반대로 확인한다: 프로덕션 코드를 한 줄씩 일부러 망가뜨리고 해당
검사를 돌린다. 검사가 **실패해야** 그 검사가 살아 있는 것이다. 통과하면
그 검사는 장식이고, 그 안전장치는 지금 아무도 지키지 않고 있다.

첫 실행에서 8건 중 2건이 장식이었다(켈리 상한·통합 계좌 데이터 게이트).
세 번째로 CSRF 가드도 '함수는 옳지만 호출되는지는 아무도 안 보는' 상태로
드러났다. 셋 다 행동 검사를 새로 써서 메웠다.

⚠️ 원본 문자열이 안 맞으면 그 항목은 건너뛴다(⏭️). 건너뜀은 통과가
   아니다 — 코드가 바뀌었다는 뜻이므로 변이 문자열을 갱신해야 한다.
   조용히 넘어가지 않도록 결과에 함께 센다.
"""
import pathlib, subprocess, sys

MUTATIONS = [
    # (설명, 파일, 원본, 변조, 돌릴 테스트)
    ("킬스위치 감쇠를 스케일러 앞으로 되돌린다(오늘 고친 결함 재현)",
     "quant/live/daily.py",
     "eff = w * eff_scale * vscale * guard_damp.get(key, 1.0)",
     "eff = w * eff_scale * guard_damp.get(key, 1.0) * vscale",
     "tests/test_killswitch_effective.py"),

    ("켈리 상한 clip을 지운다(무효화)",
     "quant/live/daily.py",
     "        kcap = kelly_caps.get(key)\n        if kcap is not None:\n            eff = float(np.clip(eff, -kcap, kcap))",
     "        kcap = kelly_caps.get(key)\n        if kcap is not None:\n            pass",
     "tests/test_guards_actually_bind.py"),

    ("데이터 무결성 게이트를 끈다",
     "quant/live/daily.py",
     "            if is_severe(q):",
     "            if False and is_severe(q):",
     "tests/test_guards_actually_bind.py"),

    ("입금을 낙폭 계산에서 다시 빼먹는다",
     "quant/live/daily.py",
     "    drawdown = drawdown_from_index(_series)",
     "    drawdown = 0.0 if not st['history'] else min(0.0, equity / max(float(h.get('equity', 0)) for h in st['history']) - 1.0)",
     "tests/test_killswitch_deposits.py"),

    ("CSRF 가드를 끈다",
     "quant/web/server.py",
     "if not self._same_site_ok(parsed):",
     "if False and not self._same_site_ok(parsed):",
     "tests/test_web_csrf.py"),

    ("장부 정렬(chrono)을 없앤다",
     "quant/live/daily.py",
     'return sorted(history or [], key=lambda r: str(r.get("date", "")))',
     "return list(history or [])",
     "tests/test_ledger_integrity.py"),

    ("알림 실패를 성공으로 기록한다(경보 유실)",
     "quant/live/flag_watch.py",
     "        if notifier.send(cur[k]) is False:",
     "        if False:",
     "tests/test_flag_watch.py"),

    ("부분 체결 뒤 전량 재주문(160% 초과 체결)",
     "quant/broker/retry.py",
     "                    remaining = max(0.0, qty - landed)",
     "                    remaining = qty",
     "tests/test_broker_retry_partial.py"),
]

def run(test):
    r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "--no-header", "-x"],
                       capture_output=True, text=True, timeout=900)
    return r.returncode

print(f"{'결과':4s} {'설명':60s} 검사")
print("─" * 110)
caught = missed = skipped = 0
for desc, path, old, new, test in MUTATIONS:
    p = pathlib.Path(path)
    src = p.read_text(encoding="utf-8")
    if src.count(old) != 1:
        print(f"⏭️   {desc[:58]:60s} (원본 문자열 {src.count(old)}회 — 코드가 바뀜)")
        skipped += 1
        continue
    p.write_text(src.replace(old, new), encoding="utf-8")
    try:
        rc = run(test)
    finally:
        p.write_text(src, encoding="utf-8")
    if rc != 0:
        print(f"✅   {desc[:58]:60s} {test.split('/')[-1]}")
        caught += 1
    else:
        print(f"❌   {desc[:58]:60s} {test.split('/')[-1]}  ← 못 잡음")
        missed += 1
print("─" * 110)
print(f"잡음 {caught} · 놓침 {missed} · 건너뜀 {skipped}")
