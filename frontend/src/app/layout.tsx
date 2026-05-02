import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nexus PDF",
  description: "Chat with your PDFs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

