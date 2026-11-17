import { routing } from "@/i18n/routing";

export type AppLocale = (typeof routing.locales)[number];

export const LOCALES = routing.locales as readonly AppLocale[];

/** Lấy locale từ đoạn đường dẫn đầu tiên ("/vi/writing/1" -> "vi"); không khớp thì dùng defaultLocale. */
export function localeFromPath(pathname: string | null | undefined): AppLocale {
  const first = (pathname ?? "").split("/")[1] ?? "";
  return (LOCALES as readonly string[]).includes(first) ? (first as AppLocale) : routing.defaultLocale;
}

/** Nối tiền tố locale vào đường dẫn con: link("vi", "/settings") -> "/vi/settings". */
export function localePath(locale: AppLocale, sub = ""): string {
  if (!sub) return `/${locale}`;
  return `/${locale}${sub.startsWith("/") ? sub : `/${sub}`}`;
}

/** Bỏ tiền tố locale bất kỳ, trả về đường dẫn con (mặc định "/"). */
export function stripLocalePrefix(pathname: string): string {
  const rest = pathname.replace(/^\/(zh|en|vi)(?=\/|$)/, "");
  return rest === "" ? "/" : rest;
}

/** Nhãn hiển thị trên công tắc chuyển ngôn ngữ (viết bằng chính ngôn ngữ đó). */
export const LOCALE_LABELS: Record<AppLocale, string> = {
  zh: "中文",
  en: "English",
  vi: "Tiếng Việt",
};

/** Dấu phân cách khi nối danh sách nhãn theo ngôn ngữ. */
export function listSeparator(locale: AppLocale): string {
  return locale === "zh" ? "、" : ", ";
}
