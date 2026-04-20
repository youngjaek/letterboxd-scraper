import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kinoboxd",
  description: "Search a Letterboxd user's friends' canon of films.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="site-shell">
          <SiteHeader />
          <main className="site-main">{children}</main>

          <footer className="site-footer">
            <div className="site-footer__inner">
              <div className="site-footer__top">
                <div>
                  <p className="site-footer__title">Kinoboxd</p>
                  <p className="site-footer__copy">Search and browse a user&apos;s friends&apos; canon of films.</p>
                </div>
                <div className="site-footer__links">
                  <Link href="/cohorts">Search</Link>
                  <Link href="/about">About</Link>
                  <Link href="/faq">FAQ</Link>
                  <Link href="/login">Log in</Link>
                  <Link href="/signup">Sign up</Link>
                </div>
              </div>
              <p className="site-footer__meta">
                Uses public Letterboxd data and TMDB metadata. Not affiliated with Letterboxd or TMDB.
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
