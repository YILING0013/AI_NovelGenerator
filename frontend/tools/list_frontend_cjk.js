// Liet ke cac CHUOI / JSX text chua chu Han trong ma frontend (bo qua comment).
// Cach dung: node frontend/tools/list_frontend_cjk.js [ thu_muc ]
const fs = require("fs");
const path = require("path");

const CJK = /[㐀-䶿一-鿿]/;
const root = path.join(__dirname, "..", process.argv[2] || "src");
const rows = [];

function stripComments(text) {
  const out = [];
  let inBlock = false;
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (inBlock) {
      out.push("");
      if (trimmed.includes("*/")) inBlock = false;
      continue;
    }
    if (trimmed.startsWith("/*")) {
      out.push("");
      if (!trimmed.includes("*/")) inBlock = true;
      continue;
    }
    if (trimmed.startsWith("//") || trimmed.startsWith("*")) {
      out.push("");
      continue;
    }
    out.push(line);
  }
  return out;
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!/node_modules|\.next|messages/.test(entry.name)) walk(p);
      continue;
    }
    if (!/\.tsx?$/.test(entry.name)) continue;
    const original = fs.readFileSync(p, "utf8").split("\n");
    const lines = stripComments(original.join("\n")).split("\n");
    lines.forEach((line, index) => {
      if (!line || !CJK.test(line)) return;
      rows.push({ file: path.relative(path.join(__dirname, ".."), p).replace(/\\/g, "/"), line: index + 1, text: line.trim().slice(0, 170) });
    });
  }
}

walk(root);
const byFile = {};
for (const r of rows) (byFile[r.file] ||= []).push(r);
const files = Object.keys(byFile).sort((a, b) => byFile[b].length - byFile[a].length);
console.log(`tong_dong=${rows.length} files=${files.length}`);
for (const f of files) {
  console.log(`\n## ${f}  (${byFile[f].length})`);
  for (const r of byFile[f]) console.log(`   ${r.line}: ${r.text}`);
}
