// src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Toaster } from "react-hot-toast";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title:       "AI Migration Platform",
  description: "Convert Java monoliths to React + Spring Boot — autonomously",
  icons:       { icon: "/favicon.ico" },
};

export const viewport: Viewport = {
  themeColor: "#0d1117",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased bg-[#0d1117] text-slate-100`}>
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#161b22",
              color:      "#e6edf3",
              border:     "1px solid #30363d",
              fontFamily: "inherit",
              fontSize:   "14px",
            },
          }}
        />
      </body>
    </html>
  );
}
