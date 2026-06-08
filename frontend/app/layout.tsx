import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import ServiceWorker from "@/components/ServiceWorker";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Maintenance Assistant · ICD-SBI",
  description:
    "AI maintenance assistant for FSDS, FDSS & WSP systems on LHB and Vande Bharat coaches. Voice + text, Hindi & English.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Maintenance Bot",
  },
};

export const viewport: Viewport = {
  themeColor: "#070b14",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-[100dvh] bg-bg-base text-ink antialiased">
        {children}
        <ServiceWorker />
      </body>
    </html>
  );
}
