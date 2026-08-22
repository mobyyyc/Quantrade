import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Quantrade",
  description: "Private-beta quantitative equity research.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
