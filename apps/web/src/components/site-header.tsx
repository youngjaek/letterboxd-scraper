"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-[2]">
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-4.35-4.35" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-[2]">
      <path d="M6 6l12 12" />
      <path d="M18 6l-12 12" />
    </svg>
  );
}

export function SiteHeader() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    inputRef.current?.focus();
  }, [open]);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (query.trim()) {
      params.set("query", query.trim());
    }
    const href = (params.toString() ? `/cohorts?${params.toString()}` : "/cohorts") as Route;
    setOpen(false);
    router.push(href);
  }

  return (
    <header className="shell-header">
      <div className="shell-header__inner">
        <Link href="/" className="brand-lockup" aria-label="Kinoboxd home">
          <span className="brand-mark" aria-hidden="true">
            <span className="brand-film">
              <span className="brand-frame brand-frame--green" />
              <span className="brand-frame brand-frame--orange" />
              <span className="brand-frame brand-frame--blue" />
            </span>
          </span>
          <span className="brand-copy">
            <span className="brand-name">Kinoboxd</span>
          </span>
        </Link>

        <nav className="shell-nav" aria-label="Primary">
          <Link href="/about">About</Link>
          <Link href="/faq">FAQ</Link>
        </nav>

        <div className="shell-actions">
          <button
            type="button"
            className="icon-button"
            onClick={() => setOpen((current) => !current)}
            aria-label={open ? "Close search" : "Open search"}
            aria-expanded={open}
          >
            {open ? <CloseIcon /> : <SearchIcon />}
          </button>
          <Link href="/login" className="button-ghost">
            Log in
          </Link>
          <Link href="/signup" className="button-primary">
            Sign up
          </Link>
        </div>
      </div>

      {open ? (
        <div className="shell-search">
          <form onSubmit={handleSubmit} className="shell-search__form">
            <SearchIcon />
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a Letterboxd username"
              className="shell-search__input"
            />
            <button type="submit" className="button-secondary px-4 py-2 text-xs">
              Search
            </button>
          </form>
        </div>
      ) : null}
    </header>
  );
}
