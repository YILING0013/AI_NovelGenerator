import { apiPostForm } from "@/lib/api";
import zh from "@/i18n/messages/zh.json";
import en from "@/i18n/messages/en.json";

/**
 * 保存项目内导出副本，同时保留浏览器另存入口。
 * Args: link 原导出链接；先读取 Blob，调用方随后可释放原 URL。
 * Returns: 无；项目副本失败时保留浏览器下载并明确提示。
 */
export function downloadExport(link: HTMLAnchorElement): void {
  const filename = link.download;
  let blobRequest: Promise<Blob>;
  try { blobRequest = fetch(link.href).then((response) => response.blob()); }
  catch (error) { blobRequest = Promise.reject(error); }
  // 点击仍同步执行，原调用者可捕获浏览器下载失败并保留当前草稿。
  try { link.click(); }
  catch (error) { void blobRequest.catch(() => {}); throw error; }
  void blobRequest.then(async (blob) => {
    const form = new FormData();
    form.append("file", blob, filename);
    await apiPostForm<{ path: string }>("/api/exports", form);
  }).catch(() => {
    window.alert((document.documentElement.lang.startsWith("zh") ? zh : en).userStorage.exportFailed);
  });
}
