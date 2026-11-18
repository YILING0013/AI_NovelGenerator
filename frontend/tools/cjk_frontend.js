// Liet ke chuoi/debug chua chu Han trong ma Nguon frontend, phan loai comment vs string.
// Cach dung: node frontend/tools/cjk_frontend.js [thu_muc]
const fs = require("fs");
const path = require("path");

const CJK = /[㐀-䶿一-鿿豈-﫿]/;
const QUOTED = /(["'`])(?:\\.|(?!\1)[^\\])*?\1/g;
const root = process.argv[2] || path.join(__dirname, "..", "src");

const rows = [];
let block = false;

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!/node_modules|\.next|messages/.test(p)) walk(p);
      continue;
    }
    if (!/\.tsx?$/.test(entry.name)) continue;
    const text = fs.readFileSync(p, "utf8");
    const lines = text.split("\n");
    block = false;
    const hits = [];
    lines.forEach((raw, index) => {
      const line = raw;
      const opens = (line.match(/\/\*/g) || []).length;
      const closes = (line.match(/\*\//g) || []).length;
      const wasInBlock = block;
      if (opens > closes) block = true;
      else if (closes >= opens) block = false;
      if (!CJK.test(line)) return;
      const commentLine = /^\s*(\/\/|\*|\/\*)/.test(line) || wasInBlock;
      if (commentLine) {
        hits.push({ line: index + 1, kind: "comment", text: line.trim().slice(0, 100) });
        return;
      }
      const strings = line.match(QUOTED) || [];
      const cnStrings = strings.filter((s) => CJK.test(s));
      if (cnStrings.length) {
        hits.push({ line: index + 1, kind: "string", text: cnStrings.join(" ~ ").slice(0, 120) });
      } else {
        hits.push({ line: index + 1, kind: "code", text: line.trim().slice(0, 120) });
      }
    });
    if (hits.length) {
      const count = (kind) => hits.filter((h) => h.kind === kind).length;
      rows.push({
        file: path.relative(path.join(__dirname, "..", ".."), p).replace(/\\/g, "/"),
        total: hits.length,
        comment: count("comment"),
        string: count("string"),
        code: count("code"),
        samples: hits.filter((h) => h.kind !== "comment").slice(0, 5),
      });
    }
  }
}

walk(root);
rows.sort((a, b) => b.string + b.code - (a.string + a.code) || b.total - a.total);
const sum = (key) => rows.reduce((n, r) => n + r[key], 0);
console.log(`files=${rows.length}  dong=${sum("total")}  comment=${sum("comment")}  string=${sum("string")}  code=${sum("code")}`);
for (const r of rows) {
  if (!r.string && !r.code) continue;
  console.log(`\n${r.file}  string=${r.string} code=${r.code} comment=${r.comment}`);
  for (const s of r.samples) console.log(`   ${s.line} [${s.kind}] ${s.text}`);
}
