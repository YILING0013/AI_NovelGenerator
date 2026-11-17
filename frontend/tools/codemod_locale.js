// One-shot codemod: thay cách suy locale từ pathname bằng helper localeFromPath().
// Dùng replace literal (split/join), không dùng regex.
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "src");
const files = [
  "components/writing/WritingSidebar.tsx",
  "components/writing/novel-info/NovelInfoWorkspace.tsx",
  "components/settings/ThemeCard.tsx",
  "components/settings/SettingsContent.tsx",
  "components/layout/Navbar.tsx",
  "components/bookshelf/NewNovelPanel.tsx",
  "components/bookshelf/NovelDetail.tsx",
];

const OLD_LOCALE = 'pathname.startsWith("/en") ? "en" : "zh"';
const IMPORT_LINE = 'import { localeFromPath } from "@/lib/locale";';

function addImport(text) {
  if (text.includes(IMPORT_LINE)) return text;
  const lines = text.split("\n");
  let last = -1;
  lines.forEach((line, i) => {
    // chỉ nhận dòng import hoàn chỉnh (có "from") để không chèn vào giữa import nhiều dòng
    if (line.startsWith("import ") && line.includes(" from ")) last = i;
    if (line.startsWith('"use client"')) last = Math.max(last, i);
  });
  if (last === -1) return IMPORT_LINE + "\n" + text;
  lines.splice(last + 1, 0, IMPORT_LINE);
  return lines.join("\n");
}

for (const rel of files) {
  const p = path.join(SRC, rel);
  const text = fs.readFileSync(p, "utf8");
  let next = text.split(`const locale = ${OLD_LOCALE};`).join("const locale = localeFromPath(pathname);");
  next = next.split(`const currentLocale = ${OLD_LOCALE};`).join("const currentLocale = localeFromPath(pathname);");
  if (next === text) {
    console.log("SKIP (no match) " + rel);
    continue;
  }
  fs.writeFileSync(p, addImport(next), "utf8");
  console.log("OK " + rel);
}
