import type { Metadata } from "next";
import "./globals.css";
import "./hud.css";
import "./vision.css";
import "./temas.css";
import { GUION_TEMA } from "@/lib/helios/tema";

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
    // El guion del tema pone atributos en <html> antes de que React hidrate: no es un desajuste.
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: GUION_TEMA }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- app router: this layout wraps every page */}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Russo+One&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" />
      </head>
      <body>{children}</body>
    </html>
  );
}
