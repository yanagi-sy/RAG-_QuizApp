import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RAG Quiz App",
  description: "QA and Quiz application",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-dvh`}
      >
        <header className="border-b border-gray-200 bg-white shadow-sm">
          <nav className="max-w-5xl mx-auto px-4 sm:px-6">
            <div className="flex flex-wrap gap-4 h-14 items-center">
              <Link
                href="/"
                className="text-base font-medium text-gray-900 hover:text-gray-700 transition-colors"
              >
                QA
              </Link>
              <Link
                href="/quiz/generate"
                className="text-base font-medium text-gray-900 hover:text-gray-700 transition-colors"
              >
                クイズ生成
              </Link>
              <Link
                href="/quiz/manage"
                className="text-base font-medium text-gray-900 hover:text-gray-700 transition-colors"
              >
                クイズ管理
              </Link>
              <Link
                href="/quiz"
                className="text-base font-medium text-gray-500 hover:text-gray-700 transition-colors"
              >
                クイズ（旧）
              </Link>
            </div>
          </nav>
        </header>
        <main className="min-h-dvh">{children}</main>
      </body>
    </html>
  );
}
