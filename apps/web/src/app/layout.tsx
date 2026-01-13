import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Letterboxd Cohort",
  description: "Private alpha UI for cohort dashboards and rankings",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="text-slate-50">
        <main className="min-h-screen px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
