import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Helios · Una presencia viva",
  description: "Un espacio para conversar. Una esfera orgánica de luz que acompaña cada momento.",
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
