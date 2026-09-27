import type { Metadata } from "next";
import "./globals.css";
import "./hud.css";
import "./vision.css";

export const metadata: Metadata = {
  title: "Helios · Espacio de trabajo",
  description: "Conversación, documentos y herramientas en un mismo espacio de trabajo.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- app router: this layout wraps every page */}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Russo+One&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" />
      </head>
      <body>{children}</body>
    </html>
  );
}
