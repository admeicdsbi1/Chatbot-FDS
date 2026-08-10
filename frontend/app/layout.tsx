import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import ServiceWorker from "@/components/ServiceWorker";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Coach Maintenance Assistant · ICD Sabarmati",
  description:
    "Maintenance knowledge for LHB, ICF, Vande Bharat and Amrit Bharat coaches — " +
    "fire safety, brakes, running gear, electrical, HVAC, interiors and shop schedules. " +
    "Voice and text, Hindi and English.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Coach Maint",
  },
};

export const viewport: Viewport = {
  // Matches the --bg-base token in each theme.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6fa" },
    { media: "(prefers-color-scheme: dark)", color: "#070b14" },
  ],
  width: "device-width",
  initialScale: 1,
  // Pinch-zoom stays available (WCAG 1.4.4). Technical tables and clause
  // numbers are exactly the content a user needs to zoom into on a phone.
  viewportFit: "cover",
};

// Applies the saved theme before first paint so there is no flash of the wrong
// palette. Kept tiny and dependency-free; falls back to the OS setting.
const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem("cma.theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})()`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body className="min-h-[100dvh] bg-bg-base text-ink antialiased">
        {children}
        <ServiceWorker />
      </body>
    </html>
  );
}
