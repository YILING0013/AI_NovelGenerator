import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Novel Generator",
  description: "AI-powered novel generation platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}
