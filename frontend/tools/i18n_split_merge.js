const fs = require("fs");
const path = require("path");

const SRC_DIR = path.join(__dirname, "..", "src", "i18n", "messages");
const WORK_DIR = path.join(__dirname, "..", ".i18n-work");
const CHUNK_DIR = path.join(WORK_DIR, "chunks");
const VI_DIR = path.join(WORK_DIR, "vi");
const MAX_CHUNK_BYTES = 24 * 1024;

function leaves(node, prefix, out) {
  if (node === null || typeof node !== "object") {
    out.push({ key: prefix, value: node });
    return out;
  }
  for (const [k, v] of Object.entries(node)) {
    if (prefix === "" ) leaves(v, k, out);
    else leaves(v, prefix + "." + k, out);
  }
  return out;
}

function setLeaf(root, dotted, value) {
  const parts = dotted.split(".");
  let cur = root;
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== "object" || cur[parts[i]] === null) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}

function getLeaf(root, dotted) {
  return dotted.split(".").reduce((o, k) => (o == null ? undefined : o[k]), root);
}

function splitCmd() {
  const en = JSON.parse(fs.readFileSync(path.join(SRC_DIR, "en.json"), "utf8"));
  fs.rmSync(WORK_DIR, { recursive: true, force: true });
  fs.mkdirSync(CHUNK_DIR, { recursive: true });
  fs.mkdirSync(VI_DIR, { recursive: true });

  const manifest = [];
  for (const [ns, tree] of Object.entries(en)) {
    if (typeof tree !== "object" || tree === null) {
      const id = `${ns}__00`;
      fs.writeFileSync(path.join(CHUNK_DIR, id + ".json"), JSON.stringify([[ns, tree]], null, 0));
      manifest.push({ id, namespace: ns, count: 1 });
      continue;
    }
    let group = 0;
    let bucket = [];
    let bytes = 0;
    const flush = () => {
      if (!bucket.length) return;
      const id = `${ns}__${String(group).padStart(2, "0")}`;
      fs.writeFileSync(path.join(CHUNK_DIR, id + ".json"), JSON.stringify(bucket, null, 0));
      manifest.push({ id, namespace: ns, count: bucket.length });
      bucket = [];
      bytes = 0;
      group++;
    };
    const walk = (node, prefix) => {
      if (typeof node !== "object" || node === null) {
        const cost = JSON.stringify([prefix, node]).length;
        if (bytes + cost > MAX_CHUNK_BYTES && bucket.length) flush();
        bucket.push([prefix, node]);
        bytes += cost;
        return;
      }
      for (const [k, v] of Object.entries(node)) walk(v, prefix ? prefix + "." + k : k);
    };
    for (const [k, v] of Object.entries(tree)) {
      // nhánh con phẳng (giá trị lá ngay cấp 1) gộp theo lô nhỏ để giữ thứ tự
      if (typeof v !== "object" || v === null) {
        const cost = JSON.stringify([k, v]).length;
        if (bytes + cost > MAX_CHUNK_BYTES && bucket.length) flush();
        bucket.push([k, v]);
        bytes += cost;
        continue;
      }
      // nhánh con lớn thì tách độc lập, nhánh nhỏ thì đi tiếp
      const size = JSON.stringify(v).length;
      if (size > MAX_CHUNK_BYTES) {
        flush();
        walk(v, k);
        flush();
      } else {
        walk(v, k);
      }
    }
    flush();
  }
  fs.writeFileSync(path.join(WORK_DIR, "manifest.json"), JSON.stringify(manifest, null, 1));
  const total = manifest.reduce((n, m) => n + m.count, 0);
  console.log(`chunks=${manifest.length} leaves=${total} work=${WORK_DIR}`);
  for (const m of manifest) {
    const p = path.join(CHUNK_DIR, m.id + ".json");
    console.log(`${m.id}\t${m.count}\t${fs.statSync(p).size}`);
  }
}

function mergeCmd() {
  const en = JSON.parse(fs.readFileSync(path.join(SRC_DIR, "en.json"), "utf8"));
  const zh = JSON.parse(fs.readFileSync(path.join(SRC_DIR, "zh.json"), "utf8"));
  const manifest = JSON.parse(fs.readFileSync(path.join(WORK_DIR, "manifest.json"), "utf8"));
  const vi = {};
  const missingChunks = [];
  const rows = [];
  const placeholdersOf = (s) => (typeof s === "string" ? (s.match(/\{[a-zA-Z0-9_,\[\]\.:-]*\}/g) || []).sort().join(",") : "");

  for (const m of manifest) {
    const file = path.join(VI_DIR, m.id + ".json");
    if (!fs.existsSync(file)) {
      missingChunks.push(m.id);
      continue;
    }
    const pairs = JSON.parse(fs.readFileSync(file, "utf8"));
    for (const [key, value] of pairs) {
      rows.push({ namespace: m.namespace, key, en: getLeaf(en, `${m.namespace}.${key}`), zh: getLeaf(zh, `${m.namespace}.${key}`), vi: value });
    }
  }
  // fallback: lá chưa dịch thì lấy nguyên English để không vỡ UI
  const seen = new Set(rows.map((r) => `${r.namespace}.${r.key}`));
  for (const leaf of leaves(en, "", [])) {
    if (seen.has(leaf.key)) continue;
    setLeaf(vi, leaf.key, leaf.value);
  }
  for (const r of rows) setLeaf(vi, `${r.namespace}.${r.key}`, r.vi);

  const enKeys = new Set(leaves(en, "", []).map((l) => l.key));
  const viKeys = new Set(leaves(vi, "", []).map((l) => l.key));
  const missing = [...enKeys].filter((k) => !viKeys.has(k));
  const extra = [...viKeys].filter((k) => !enKeys.has(k));
  const placeholderDiff = [];
  const untranslated = [];
  for (const r of rows) {
    const full = `${r.namespace}.${r.key}`;
    if (typeof r.en === "string" && typeof r.vi === "string") {
      if (placeholdersOf(r.en) !== placeholdersOf(r.vi)) placeholderDiff.push(full);
      if (r.vi.trim() === r.en.trim() && /[A-Za-z]{4}/.test(r.en) && !/^[A-Z0-9_ .:\/-]+$/.test(r.en)) untranslated.push(full);
    }
  }

  fs.writeFileSync(path.join(SRC_DIR, "vi.json"), JSON.stringify(vi, null, 2) + "\n", "utf8");
  const report = {
    en_leaves: enKeys.size,
    vi_leaves: viKeys.size,
    zh_leaves: new Set(leaves(zh, "", []).map((l) => l.key)).size,
    translated_rows: rows.length,
    missing_chunks: missingChunks,
    missing_in_vi: missing,
    extra_in_vi: extra,
    placeholder_diff: placeholderDiff,
    suspect_untranslated: untranslated,
  };
  fs.writeFileSync(path.join(WORK_DIR, "report.json"), JSON.stringify(report, null, 1));
  console.log(
    `en=${enKeys.size} vi=${viKeys.size} zh=${report.zh_leaves} translated=${rows.length} missingChunks=${missingChunks.length} missing=${missing.length} extra=${extra.length} placeholderDiff=${placeholderDiff.length} suspectUntranslated=${untranslated.length}`
  );
  if (missingChunks.length) console.log("missing chunks: " + missingChunks.join(", "));
  if (placeholderDiff.length) console.log("placeholder diff sample: " + placeholderDiff.slice(0, 15).join(", "));
}

const cmd = process.argv[2];
if (cmd === "split") splitCmd();
else if (cmd === "merge") mergeCmd();
else console.log("usage: node i18n_split_merge.js split|merge");
