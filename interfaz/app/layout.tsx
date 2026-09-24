import type { Metadata } from "next";
import "./globals.css";
import "./hud.css";

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
      <body>{children}</body>
    </html>
  );
}
