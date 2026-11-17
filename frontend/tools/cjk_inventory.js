const fs = require("fs");
const path = require("path");
const CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
const roots = process.argv.slice(2);
if (!roots.length) roots.push("backend", "desktop_launcher", "frontend/src");

const files = [];
function walk(p) {
  const st = fs.statSync(p);
  if (st.isDirectory()) {
    if (p.includes("node_modules") || p.includes(".next") || p.includes(".venv") || p.includes(".i18n-work")) return;
    for (const e of fs.readdirSync(p)) walk(path.join(p, e));
  } else if (/\.(py|json|md|yaml|yml|ts|tsx)$/.test(p) && !/messages.(zh|en)\.json$/.test(p.replace(/\\/g, "/"))) {
    files.push(p);
  }
}
for (const r of roots) if (fs.existsSync(r)) walk(path.resolve(r));

const rows = [];
for (const f of files) {
  const t = fs.readFileSync(f, "utf8");
  const n = (t.match(new RegExp(CJK.source, "g")) || []).length;
  if (n > 0) rows.push({ file: path.relative(process.cwd(), f).replace(/\\/g, "/"), cjk: n, bytes: Buffer.byteLength(t, "utf8") });
}
rows.sort((a, b) => b.cjk - a.cjk);
const total = rows.reduce((n, r) => n + r.cjk, 0);
console.log(`files=${rows.length} cjkTotal=${total} approxEnglishChars=${Math.round(total * 1.6)}`);
for (const r of rows) console.log(`${r.cjk}\t${r.bytes}\t${r.file}`);
