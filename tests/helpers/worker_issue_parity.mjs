// 워커의 실제 발급 코드를 그대로 떼어내 실행한다 — 파이썬 구현과
// 바이트 단위로 같은 키·지문이 나오는지 확인하기 위한 도구.
// tests/test_license_path.py 가 node로 이 파일을 실행한다.
// 사용법: node tests/helpers/worker_issue_parity.mjs <비밀> <이메일>
import { readFileSync } from "node:fs";
const src = readFileSync("worker.js", "utf-8");
const grab = (name) => {
  const i = src.indexOf(name);
  if (i < 0) throw new Error("not found: " + name);
  let d = 0, j = src.indexOf("{", i);
  for (let k = j; k < src.length; k++) {
    if (src[k] === "{") d++;
    else if (src[k] === "}") { d--; if (!d) return src.slice(i, k + 1); }
  }
};
const code = [
  src.match(/const B32_ALPHABET = "[^"]+";/)[0],
  grab("function b32("),
  grab("async function fingerprint("),
  grab("async function issueKey("),
].join("\n");
const mod = await import("data:text/javascript," + encodeURIComponent(
  code + "\nexport { b32, fingerprint, issueKey };"));
const env = { ADMIN_ID: "a", ADMIN_PW: "b", LICENSE_SECRET: process.argv[2] };
const url = new URL("https://x/api/admin/issue?owner=" + encodeURIComponent(process.argv[3]));
globalThis.json = (o) => new Response(JSON.stringify(o));
const r = await mod.issueKey(url, env);
console.log(JSON.stringify(await r.json()));
