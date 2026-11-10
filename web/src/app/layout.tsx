import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kimiko AI Dashboard",
  description: "Your local intelligent AI assistant platform",
};

export const viewport: Viewport = {
  themeColor: "#0a0b0f",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-[var(--bg-primary)] text-[var(--text-primary)] font-sans antialiased">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          {/* Bottom padding on mobile leaves room for the fixed bottom nav. */}
          <main className="flex-1 flex flex-col overflow-hidden pb-16 md:pb-0">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
