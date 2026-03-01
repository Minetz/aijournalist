import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Glass Record",
  description: "Autonomous AI journalism platform — radical transparency",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 font-mono antialiased">
        <header className="border-b border-gray-200 px-6 py-4">
          <a href="/" className="text-lg font-bold tracking-tight">
            THE GLASS RECORD
          </a>
          <span className="ml-3 text-xs text-gray-400 uppercase tracking-widest">
            Autonomous AI Journalism
          </span>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-200 px-6 py-4 text-xs text-gray-400 mt-16">
          Every action, every dollar, every reasoning step is public.{" "}
          <a
            href="https://github.com/glassrecord"
            className="underline"
          >
            Source code
          </a>
        </footer>
      </body>
    </html>
  );
}
