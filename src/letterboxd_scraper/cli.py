from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Set
import threading

import httpx
import re
import typer
from sqlalchemy import func, or_
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .config import Settings, load_settings
from .db import models
from .db.session import get_session, init_engine
from .services import cohorts as cohort_service
from .services import export as export_service
from .services import histograms as histogram_service
from .services import insights as insight_service
from .services import ratings as rating_service
from .services import rankings as ranking_service
from .services import stats as stats_service
from .services import telemetry as telemetry_service
from .services import workflows as workflow_service
from .services.enrichment import (
    enrich_film_metadata,
    film_enrichment_reasons,
    film_needs_enrichment,
    sync_people_metadata,
)
from .scrapers.film_pages import FilmPageScraper
from .scrapers.ratings import ProfileRatingsScraper
from .scrapers.follow_graph import FollowGraphScraper, expand_follow_graph
from .scrapers.histograms import RatingsHistogramScraper
from .scrapers.listings import PosterListingScraper
from .services.tmdb import TMDBClient, RequestRateLimiter

console = Console()
ERROR_LOG_PATH: Optional[Path] = None

app = typer.Typer(
    help="Personalized Letterboxd scraper CLI.",
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
cohort_app = typer.Typer(help="Manage cohorts (follow lists).", no_args_is_help=True)
stats_app = typer.Typer(help="Statistics/materialized view maintenance.", no_args_is_help=True)
rank_app = typer.Typer(help="Ranking computations.", no_args_is_help=True)
export_app = typer.Typer(help="Export data into consumable formats.")
user_app = typer.Typer(help="User metadata utilities.", no_args_is_help=True)
film_app = typer.Typer(help="Film metadata helpers.", no_args_is_help=True)
cleanup_app = typer.Typer(help="Data cleanup utilities.", no_args_is_help=True)

app.add_typer(cohort_app, name="cohort")
app.add_typer(stats_app, name="stats")
app.add_typer(rank_app, name="rank")
app.add_typer(export_app, name="export")
app.add_typer(user_app, name="user")
app.add_typer(film_app, name="film")
app.add_typer(cleanup_app, name="cleanup")


def get_state(ctx: typer.Context) -> Dict[str, Settings]:
    return ctx.ensure_object(dict)  # type: ignore[return-value]


def _log_enrich_error(message: str) -> None:
    if ERROR_LOG_PATH is None:
        return
    try:
        ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG_PATH.open("a", encoding="utf-8") as fh:
            timestamp = datetime.now(timezone.utc).isoformat()
            fh.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def _scrape_user_ratings(
    settings: Settings,
    username: str,
    *,
    incremental: bool = False,
    print_only: bool = False,
) -> tuple[int, Set[int]]:
    """Fetch ratings + likes for a single user and optionally persist them."""
    result = workflow_service.scrape_user_ratings(
        settings,
        username,
        incremental=incremental,
        persist=not print_only,
        include_entries=print_only,
    )
    combined = result.entries or []
    if print_only:
        mode = "incremental" if incremental else "full"
        console.print(
            f"[magenta]Preview[/magenta] @{username} ({mode}) — "
            f"{len(combined)} item(s) fetched (no DB writes)."
        )
        preview_limit = 25
        for entry in combined[:preview_limit]:
            rating_text = (
                f"{entry.rating:.1f}"
                if entry.rating is not None
                else ("liked" if entry.liked else "unrated")
            )
            flags = []
            if entry.liked and entry.rating is not None:
                flags.append("liked")
            if entry.favorite:
                flags.append("favorite")
            flag_text = f" [{' ,'.join(flags)}]" if flags else ""
            console.print(
                f"  • {entry.film_slug:<25} "
                f"{rating_text}{flag_text}"
        )
        if len(combined) > preview_limit:
            console.print(f"  … {len(combined) - preview_limit} more item(s) truncated.")
        return len(combined), set()
    return result.fetched, result.touched_film_ids


@app.callback()
def main(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to TOML config file."),
) -> None:
    """Application entry point: load configuration."""
    settings = load_settings(config_path=config)
    state = get_state(ctx)
    state["settings"] = settings
    init_engine(settings)
    console.log(f"Loaded configuration from {config or 'config/default.toml'}")


@cohort_app.command("build")
def cohort_build(
    ctx: typer.Context,
    seed: str = typer.Option(..., "--seed", "-s", help="Seed Letterboxd username."),
    label: str = typer.Option(..., "--label", "-l", help="Human readable cohort label."),
    depth: int = typer.Option(None, "--depth", "-d", help="Follow depth; overrides config default."),
    include_seed: Optional[bool] = typer.Option(None, help="Include the seed user themselves?"),
) -> None:
    """Create cohort definition and queue follow graph scrape."""
    settings = get_state(ctx)["settings"]
    depth = depth or settings.cohort_defaults.follow_depth
    include_seed = (
        include_seed if include_seed is not None else settings.cohort_defaults.include_seed
    )
    definition = {"depth": depth, "include_seed": include_seed}
    cohort_id = None
    with get_session(settings) as session:
        seed_user = cohort_service.get_or_create_user(session, seed)
        cohort = cohort_service.create_cohort(session, seed_user, label, definition)
        cohort_id = cohort.id
        if include_seed:
            cohort_service.add_member(session, cohort, seed_user, depth=0)
    console.print(f"[green]Created cohort[/green] '{label}' (id={cohort_id}) with seed '{seed}'.")


@cohort_app.command("refresh")
def cohort_refresh(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
) -> None:
    """Refresh follow graph membership for an existing cohort."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        definition = cohort.definition or {}
        depth = definition.get("depth", settings.cohort_defaults.follow_depth)
        include_seed = definition.get("include_seed", settings.cohort_defaults.include_seed)
        seed_user = session.get(models.User, cohort.seed_user_id) if cohort.seed_user_id else None
        seed_username = seed_user.letterboxd_username if seed_user else ""
        if not seed_username:
            typer.echo("Cohort seed user missing; rebuild cohort.")
            raise typer.Exit(code=1)
    with telemetry_service.timed_operation(f"cohort_refresh[{cohort_id}]"):
        scraper = FollowGraphScraper(settings)
        try:
            edges = list(expand_follow_graph(scraper, seed_username, depth))
            with get_session(settings) as session:
                cohort = cohort_service.get_cohort(session, cohort_id)
                if cohort:
                    cohort_service.refresh_cohort_members(
                        session,
                        cohort,
                        edges,
                        include_seed=include_seed,
                        seed_username=seed_username,
                    )
            console.print(f"[green]Refreshed[/green] cohort {cohort_id} members (depth={depth}).")
        finally:
            scraper.close()


@cohort_app.command("rename")
def cohort_rename(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    label: str = typer.Option(..., "--label", "-l", help="New label for the cohort."),
) -> None:
    """Update the display label for an existing cohort."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.rename_cohort(session, cohort_id, label)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
    console.print(f"[green]Renamed[/green] cohort {cohort_id} to '{label}'.")


@cohort_app.command("delete")
def cohort_delete(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt and delete immediately.",
    ),
) -> None:
    """Permanently delete a cohort and its associated data."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        label = cohort.label
    if not yes:
        confirm = typer.confirm(
            f"Delete cohort {cohort_id} ('{label}') and all associated rankings, members, and runs?",
            default=False,
        )
        if not confirm:
            typer.echo("Deletion cancelled.")
            raise typer.Exit()
    with get_session(settings) as session:
        deleted = cohort_service.delete_cohort(session, cohort_id)
    if not deleted:
        typer.echo(f"Cohort {cohort_id} not found.")
        raise typer.Exit(code=1)
    console.print(f"[green]Deleted[/green] cohort {cohort_id} ('{label}').")


@app.command("scrape")
def scrape(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    full: bool = typer.Option(
        False,
        "--full/--incremental",
        help="Force a full history scrape for all targeted users.",
    ),
    user: Optional[str] = typer.Option(
        None,
        "--user",
        help="Restrict scraping to a single cohort member (Letterboxd username).",
    ),
    print_only: bool = typer.Option(
        False,
        "--print-only",
        help="Preview newly fetched ratings without writing to the database.",
    ),
) -> None:
    """Scrape cohort members, defaulting to incremental updates when possible."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        members = cohort_service.list_member_scrape_freshness(session, cohort_id)
    if user:
        normalized = user.strip().lower()
        filtered = [
            (username, last_scraped)
            for username, last_scraped in members
            if username.lower() == normalized
        ]
        if not filtered:
            typer.echo(f"User '{user}' is not a member of cohort {cohort_id}.")
            raise typer.Exit(code=1)
        members = filtered
    if not members:
        console.print(f"[yellow]Cohort[/yellow] {cohort_id} has no members to scrape.")
        return
    jobs: list[tuple[str, bool]] = []
    brand_new = 0
    for username, last_scraped in members:
        needs_full = full or (last_scraped is None)
        if needs_full and last_scraped is None:
            brand_new += 1
        jobs.append((username, needs_full))
    run_type = "full" if full else "incremental"
    run_id = None
    if not print_only:
        with get_session(settings) as session:
            run_id = telemetry_service.record_scrape_run(
                session,
                cohort_id=cohort_id,
                run_type=run_type,
                status="running",
            )
    status = "success"
    note = None
    touched_films: set[int] = set()
    full_count = sum(1 for _, needs_full in jobs if needs_full)
    incremental_count = len(jobs) - full_count
    try:
        label = "full" if full else "incremental"
        with telemetry_service.timed_operation(f"scrape[{cohort_id}:{label}]"):
            max_workers = max(1, settings.scraper.max_concurrency)
            console.print(
                f"[green]Queued[/green] {len(jobs)} users "
                f"({full_count} full / {incremental_count} incremental) "
                f"with {max_workers} worker(s)."
            )
            futures: Dict[Any, tuple[str, bool]] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for username, needs_full in jobs:
                    futures[
                        executor.submit(
                            _scrape_user_ratings,
                            settings,
                            username,
                            incremental=not needs_full,
                            print_only=print_only,
                        )
                    ] = (username, needs_full)
                for future in as_completed(futures):
                    username, needs_full = futures[future]
                    try:
                        count, touched = future.result()
                        touched_films.update(touched)
                        mode_label = "full" if needs_full else "incremental"
                        console.print(
                            f"[cyan]{username}[/cyan]: processed {count} {mode_label} tiles."
                        )
                    except Exception as exc:
                        status = "failed"
                        if not print_only:
                            note = f"{username} failed: {exc}"
                        raise
    except Exception as exc:
        status = "failed"
        note = str(exc)
        raise
    finally:
        if run_id:
            with get_session(settings) as session:
                telemetry_service.finalize_scrape_run(
                    session, run_id, status=status, notes=note
                )
    if print_only:
        console.print("[green]Preview complete[/green]; no database changes were made.")
        return
    summary = (
        f"[green]Scrape complete[/green]; "
        f"{len(touched_films)} films touched "
        f"({full_count} full / {incremental_count} incremental users"
    )
    if brand_new and not full:
        summary += f", {brand_new} brand-new member(s) scraped fully"
    summary += ")."
    console.print(summary)
    if touched_films:
        console.print(
            f"[yellow]Next[/yellow]: run 'letterboxd-scraper enrich' "
            f"to hydrate metadata for {len(touched_films)} films."
        )


@app.command("enrich")
def scrape_enrich(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(None, "--limit", help="Maximum films to enrich."),
    slug: Optional[str] = typer.Option(
        None, "--slug", help="Restrict enrichment to a single film slug."
    ),
    include_tmdb: bool = typer.Option(True, "--tmdb/--no-tmdb", help="Pull metadata from TMDB."),
    include_histograms: bool = typer.Option(
        True, "--histograms/--no-histograms", help="Refresh Letterboxd histogram stats."
    ),
    workers: Optional[int] = typer.Option(
        None,
        "--workers",
        "-w",
        help="Number of parallel enrichment workers (defaults to scraper.max_concurrency).",
    ),
    tmdb_rps: float = typer.Option(
        10.0,
        "--tmdb-rps",
        help="Global TMDB request cap (requests per second).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Refresh metadata even if it already exists.",
    ),
    people: bool = typer.Option(
        True,
        "--people/--no-people",
        help="Refresh TMDB person metadata before film jobs.",
    ),
    people_limit: Optional[int] = typer.Option(
        None,
        "--people-limit",
        help="Maximum TMDB person records to refresh before film enrichment.",
    ),
) -> None:
    """Hydrate films with TMDB metadata and/or Letterboxd histograms."""
    settings = get_state(ctx)["settings"]
    global ERROR_LOG_PATH
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ERROR_LOG_PATH = Path("logs") / f"enrich_failures_{timestamp}.log"
    if not include_tmdb and not include_histograms:
        typer.echo("Enable at least one of --tmdb or --histograms.")
        raise typer.Exit(code=1)
    if include_tmdb and not settings.tmdb.api_key:
        console.print("[yellow]TMDB API key not configured[/yellow]; skipping TMDB enrichment.")
        include_tmdb = False
    tmdb_enabled = include_tmdb and bool(settings.tmdb.api_key)
    worker_count = workers or settings.scraper.max_concurrency
    worker_count = max(1, worker_count)

    @dataclass
    class EnrichmentJob:
        film_id: int
        slug: str
        needs_tmdb: bool
        needs_histogram: bool
        tmdb_reasons: List[str] = field(default_factory=list)

    @dataclass
    class EnrichmentResultRow:
        slug: str
        tmdb_success: bool
        tmdb_elapsed: float
        tmdb_error: Optional[str]
        histogram_success: bool
        histogram_elapsed: float
        histogram_error: Optional[str]
        touched: bool

    @dataclass
    class WorkerResources:
        tmdb_client: Optional[TMDBClient] = None
        film_page_scraper: Optional[FilmPageScraper] = None
        histogram_scraper: Optional[RatingsHistogramScraper] = None

        def close(self) -> None:
            if self.tmdb_client:
                self.tmdb_client.close()
            if self.film_page_scraper:
                self.film_page_scraper.close()
            if self.histogram_scraper:
                self.histogram_scraper.close()

    worker_local = threading.local()
    worker_resources: List[WorkerResources] = []
    worker_lock = threading.Lock()
    tmdb_rate_limiter = RequestRateLimiter(tmdb_rps) if tmdb_enabled and tmdb_rps > 0 else None

    def _get_worker_resources() -> WorkerResources:
        ctx = getattr(worker_local, "ctx", None)
        if ctx is None:
            ctx = WorkerResources()
            if tmdb_enabled:
                ctx.tmdb_client = TMDBClient(settings, rate_limiter=tmdb_rate_limiter)
                ctx.film_page_scraper = FilmPageScraper(settings)
            if include_histograms:
                ctx.histogram_scraper = RatingsHistogramScraper(settings)
            setattr(worker_local, "ctx", ctx)
            with worker_lock:
                worker_resources.append(ctx)
        return ctx

    def _close_worker_resources() -> None:
        with worker_lock:
            for ctx in worker_resources:
                ctx.close()
            worker_resources.clear()

    def _process_job(job: EnrichmentJob) -> EnrichmentResultRow:
        ctx = _get_worker_resources()
        tmdb_elapsed = 0.0
        histogram_elapsed = 0.0
        tmdb_success = False
        histogram_success = False
        tmdb_error = None
        histogram_error = None
        touched = False
        with get_session(settings) as session:
            film = session.get(
                models.Film,
                job.film_id,
            )
            if not film:
                return EnrichmentResultRow(
                    slug=job.slug,
                    tmdb_success=False,
                    tmdb_elapsed=0.0,
                    tmdb_error="missing film",
                    histogram_success=False,
                    histogram_elapsed=0.0,
                    histogram_error=None,
                    touched=False,
                )
            if job.needs_tmdb and not job.tmdb_reasons:
                job.tmdb_reasons = film_enrichment_reasons(film)
            if job.needs_tmdb and ctx.tmdb_client:
                tmdb_start = perf_counter()
                try:
                    tmdb_success = enrich_film_metadata(
                        session,
                        film,
                        client=ctx.tmdb_client,
                        film_page_scraper=ctx.film_page_scraper,
                    )
                except Exception as exc:  # pragma: no cover - defensive log
                    tmdb_error = str(exc)
                else:
                    touched = touched or tmdb_success
                finally:
                    tmdb_elapsed = perf_counter() - tmdb_start
            if job.needs_histogram and ctx.histogram_scraper:
                histogram_start = perf_counter()
                try:
                    summary = ctx.histogram_scraper.fetch(film.slug)
                    histogram_service.upsert_global_histogram(session, film, summary)
                    histogram_success = True
                    touched = True
                except Exception as exc:  # pragma: no cover
                    histogram_error = str(exc)
                finally:
                    histogram_elapsed = perf_counter() - histogram_start
            if touched:
                session.flush()
        return EnrichmentResultRow(
            slug=job.slug,
            tmdb_success=tmdb_success,
            tmdb_elapsed=tmdb_elapsed,
            tmdb_error=tmdb_error,
            histogram_success=histogram_success,
            histogram_elapsed=histogram_elapsed,
            histogram_error=histogram_error,
            touched=touched,
        )

    if tmdb_enabled and people:
        console.print("[cyan]Syncing TMDB people metadata…[/cyan]")
        person_client = TMDBClient(settings, rate_limiter=tmdb_rate_limiter)
        try:
            with get_session(settings) as session:
                refreshed = sync_people_metadata(
                    session,
                    person_client,
                    limit=people_limit,
                    progress=lambda person: console.print(
                        f"[green]TMDB person[/green] {escape(person.name or 'Unknown')} "
                        f"(tmdb_id={person.tmdb_id})"
                    ),
                    on_error=lambda person, exc: console.print(
                        f"[red]TMDB person failed[/red] {escape(person.name or 'Unknown')} "
                        f"(tmdb_id={person.tmdb_id}): {exc}"
                    ),
                )
        finally:
            person_client.close()
        console.print(f"[green]TMDB people[/green] refreshed {refreshed} record(s).")

    jobs: List[EnrichmentJob] = []
    force_enrich = bool(slug) or force
    with get_session(settings) as session:
        query = session.query(models.Film).order_by(models.Film.id)
        if slug:
            query = query.filter(models.Film.slug == slug)
        films = query.all()
        if slug and not films:
            console.print(f"[red]Film '{slug}' not found.[/red]")
            raise typer.Exit(code=1)
        for film in films:
            tmdb_reasons: List[str] = []
            if tmdb_enabled:
                if force_enrich:
                    tmdb_reasons = film_enrichment_reasons(film)
                    if not tmdb_reasons:
                        tmdb_reasons = ["force"]
                    needs_tmdb = True
                else:
                    tmdb_reasons = film_enrichment_reasons(film)
                    needs_tmdb = bool(tmdb_reasons)
            else:
                needs_tmdb = False
            needs_histogram = include_histograms and (force_enrich or histogram_service.film_needs_histogram(film))
            if not (needs_tmdb or needs_histogram):
                continue
            jobs.append(
                EnrichmentJob(
                    film_id=film.id,
                    slug=film.slug,
                    needs_tmdb=needs_tmdb,
                    needs_histogram=needs_histogram,
                    tmdb_reasons=tmdb_reasons if needs_tmdb else [],
                )
            )
            if limit and len(jobs) >= limit:
                break
    if not jobs:
        console.print("[yellow]No films required enrichment.[/yellow]")
        return
    worker_count = min(worker_count, len(jobs))
    processed = 0
    tmdb_calls = 0
    histogram_calls = 0
    tmdb_elapsed_total = 0.0
    histogram_elapsed_total = 0.0
    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(_process_job, job): job for job in jobs
            }
            for future in as_completed(future_map):
                job = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # pragma: no cover
                    console.print(f"[red]Enrichment failed[/red] {job.slug}: {exc}")
                    _log_enrich_error(f"Enrichment failed {job.slug}: {exc}")
                    continue
                if result.tmdb_success:
                    tmdb_calls += 1
                    tmdb_elapsed_total += result.tmdb_elapsed
                    reason_text = (
                        f" {escape('[' + ', '.join(job.tmdb_reasons) + ']')}" if job.tmdb_reasons else ""
                    )
                    console.print(f"[green]TMDB[/green] {result.slug}{reason_text} ({result.tmdb_elapsed:.2f}s)")
                elif job.needs_tmdb and result.tmdb_error:
                    reason_text = (
                        f" {escape('[' + ', '.join(job.tmdb_reasons) + ']')}" if job.tmdb_reasons else ""
                    )
                    console.print(
                        f"[red]TMDB failed[/red] {result.slug}{reason_text} "
                        f"({result.tmdb_elapsed:.2f}s): {result.tmdb_error}"
                    )
                    _log_enrich_error(f"TMDB failed {result.slug}: {result.tmdb_error}")
                if result.histogram_success:
                    histogram_calls += 1
                    histogram_elapsed_total += result.histogram_elapsed
                    console.print(f"[cyan]Histogram[/cyan] {result.slug} ({result.histogram_elapsed:.2f}s)")
                elif job.needs_histogram and result.histogram_error:
                    console.print(
                        f"[red]Histogram failed[/red] {result.slug} "
                        f"({result.histogram_elapsed:.2f}s): {result.histogram_error}"
                    )
                    _log_enrich_error(f"Histogram failed {result.slug}: {result.histogram_error}")
                if result.touched:
                    processed += 1
    finally:
        _close_worker_resources()
    console.print(f"[green]Enrichment complete[/green]; processed {processed} film(s).")
    if tmdb_calls:
        avg_tmdb = tmdb_elapsed_total / tmdb_calls
        console.print(
            f"[blue]TMDB avg[/blue]: {avg_tmdb:.2f}s across {tmdb_calls} film(s). "
            f"Est. per-100: {avg_tmdb * 100:.1f}s (~{avg_tmdb * 100 / 60:.1f} min)."
        )
    if histogram_calls:
        avg_hist = histogram_elapsed_total / histogram_calls
        console.print(
            f"[magenta]Histogram avg[/magenta]: {avg_hist:.2f}s across {histogram_calls} film(s). "
            f"Est. per-100: {avg_hist * 100:.1f}s (~{avg_hist * 100 / 60:.1f} min)."
        )


@rank_app.command("compute")
def rank_compute(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    strategy: str = typer.Option("bayesian", "--strategy", "-s", help="Ranking strategy id."),
) -> None:
    """Compute ranking values for a cohort."""
    settings = get_state(ctx)["settings"]
    with telemetry_service.timed_operation(f"rank[{cohort_id}:{strategy}]"):
        with get_session(settings) as session:
            if strategy == "bayesian":
                m_value = settings.cohort_defaults.m_value
                results = ranking_service.compute_bayesian(session, cohort_id, m_value)
                ranking_service.persist_rankings(
                    session,
                    cohort_id,
                    strategy,
                    results,
                    params={"m_value": float(m_value)},
                )
                console.print(f"[green]Computed[/green] {len(results)} rankings (showing top 5):")
                for result in results[:5]:
                    console.print(
                        f"#{result.rank}: film_id={result.film_id} "
                        f"score={result.score:.3f} watchers={result.metadata['watchers']}"
                    )
            else:
                console.print(f"[yellow]TODO[/yellow]: strategy '{strategy}' not implemented yet.")


@rank_app.command("buckets")
def rank_buckets(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    strategy: str = typer.Option("bayesian", "--strategy", "-s", help="Ranking strategy id."),
    release_start: Optional[int] = typer.Option(None, "--release-start", help="Minimum release year."),
    release_end: Optional[int] = typer.Option(None, "--release-end", help="Maximum release year."),
    watched_year: Optional[int] = typer.Option(
        None,
        "--watched-year",
        help="Only include films last logged in the provided year.",
    ),
    watched_since: Optional[datetime] = typer.Option(
        None, "--watched-since", help="Only include films last logged on/after this timestamp."
    ),
    watched_until: Optional[datetime] = typer.Option(
        None, "--watched-until", help="Only include films last logged on/before this timestamp."
    ),
    recent_years: Optional[int] = typer.Option(
        None,
        "--recent-years",
        help="Shortcut to filter to films watched within the last N years.",
    ),
    load_timeframe: Optional[str] = typer.Option(
        None,
        "--load",
        help="Load previously stored buckets for a timeframe key instead of recomputing.",
    ),
    persist: bool = typer.Option(
        False,
        "--persist/--no-persist",
        help="Persist computed buckets for later reuse.",
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-n",
        help="Number of entries to display per bucket (<=0 shows all).",
    ),
) -> None:
    """
    Surface percentile-based buckets and engagement/sentiment cluster labels.
    """
    settings = get_state(ctx)["settings"]
    filter_opts = [release_start, release_end, watched_year, watched_since, watched_until, recent_years]
    if load_timeframe and any(value is not None for value in filter_opts):
        typer.echo("--load cannot be combined with filter options.")
        raise typer.Exit(code=1)
    if load_timeframe and persist:
        typer.echo("--persist is not applicable when loading saved buckets.")
        raise typer.Exit(code=1)
    if watched_year and (watched_since or watched_until or recent_years):
        typer.echo("Use either --watched-year or the watched date range options, not both.")
        raise typer.Exit(code=1)
    if recent_years is not None and recent_years <= 0:
        typer.echo("--recent-years must be greater than zero.")
        raise typer.Exit(code=1)
    filters: insight_service.BucketFilters
    computation: Optional[insight_service.InsightComputation] = None
    with get_session(settings) as session:
        if load_timeframe:
            computation = insight_service.load_saved_buckets(
                session, cohort_id=cohort_id, strategy=strategy, timeframe_key=load_timeframe
            )
            if not computation:
                console.print(
                    f"[yellow]No saved buckets[/yellow] found for timeframe '{load_timeframe}'."
                )
                return
        else:
            resolved_since = watched_since
            if recent_years:
                now = datetime.now(tz=timezone.utc)
                resolved_since = resolved_since or now - timedelta(days=365 * recent_years)
            resolved_since = _ensure_timezone(resolved_since)
            resolved_until = _ensure_timezone(watched_until)
            if resolved_since and resolved_until and resolved_since > resolved_until:
                typer.echo("--watched-since must be before --watched-until.")
                raise typer.Exit(code=1)
            if release_start and release_end and release_start > release_end:
                typer.echo("--release-start must be <= --release-end.")
                raise typer.Exit(code=1)
            filters = insight_service.BucketFilters(
                release_start=release_start,
                release_end=release_end,
                watched_year=watched_year,
                watched_since=resolved_since,
                watched_until=resolved_until,
            )
            computation = insight_service.compute_ranking_buckets(
                session, cohort_id=cohort_id, strategy=strategy, filters=filters
            )
            if persist and computation.insights:
                insight_service.persist_insights(session, computation)
                console.print(
                    f"[green]Persisted[/green] {len(computation.insights)} rows "
                    f"under timeframe '{computation.timeframe_key}'."
                )
    if not computation:
        console.print("[yellow]No results[/yellow] to display.")
        return
    insights = computation.insights
    if not insights:
        console.print("[yellow]No films[/yellow] satisfied the provided filters.")
        return
    buckets: Dict[str, list[insight_service.FilmInsight]] = {}
    for insight in insights:
        buckets.setdefault(insight.bucket_label, []).append(insight)
    total_buckets = len(buckets)
    console.print(
        f"[green]{'Loaded' if computation.source == 'stored' else 'Computed'}[/green] "
        f"{len(insights)} films across {total_buckets} buckets "
        f"(timeframe '{computation.timeframe_key}')."
    )
    summary = Table(title="Bucket Overview")
    summary.add_column("Bucket", style="cyan")
    summary.add_column("Films", justify="right")
    summary.add_column("Top Cluster")
    sorted_buckets = sorted(
        buckets.items(),
        key=lambda entry: (-len(entry[1]), entry[0]),
    )
    for bucket_label, bucket_rows in sorted_buckets:
        cluster_counts = Counter(row.cluster_label for row in bucket_rows)
        top_cluster = cluster_counts.most_common(1)[0][0] if cluster_counts else "-"
        summary.add_row(bucket_label, str(len(bucket_rows)), top_cluster)
    console.print(summary)
    per_bucket_limit = None if limit <= 0 else limit
    for bucket_label, bucket_rows in sorted_buckets:
        console.print(f"[bold]{bucket_label}[/bold] ({len(bucket_rows)} films)")
        ordered = sorted(
            bucket_rows,
            key=lambda item: (-item.rating_percentile, -item.watchers_percentile),
        )
        preview = ordered if per_bucket_limit is None else ordered[:per_bucket_limit]
        for insight in preview:
            console.print(
                f"- {insight.title} ({insight.slug}) avg={insight.avg_rating:.2f} "
                f"watchers={insight.watchers} "
                f"rating_pct={insight.rating_percentile:.1f} "
                f"watchers_pct={insight.watchers_percentile:.1f} "
                f"cluster={insight.cluster_label}"
            )


def _ensure_timezone(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

@rank_app.command("subset")
def rank_subset(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    strategy: str = typer.Option("bayesian", "--strategy", "-s", help="Ranking strategy id."),
    list_path: Optional[str] = typer.Option(
        None,
        "--list-path",
        help="Path or URL to a Letterboxd list (supports pagination).",
    ),
    filmography_path: Optional[str] = typer.Option(
        None,
        "--filmography-path",
        "--filmo-path",
        "-F",
        help="Path or URL to a Letterboxd filmography page (single page).",
    ),
    html_file: Optional[Path] = typer.Option(
        None,
        "--html-file",
        help="Local HTML file containing a list or filmography (single page).",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results to display."),
) -> None:
    """
    Filter previously computed rankings down to films contained in a list/filmography.
    """
    settings = get_state(ctx)["settings"]
    sources = [bool(list_path), bool(filmography_path), bool(html_file)]
    if sum(1 for enabled in sources if enabled) != 1:
        typer.echo(
            "Provide exactly one of --list-path, --filmography-path/--filmo-path, or --html-file."
        )
        raise typer.Exit(code=1)
    entries = []
    scraper: Optional[PosterListingScraper] = None
    try:
        if html_file:
            html = html_file.read_text(encoding="utf-8")
            entries = PosterListingScraper.parse_html(html)
        else:
            scraper = PosterListingScraper(settings)
            if list_path:
                entries = list(scraper.iter_list_entries(list_path))
            else:
                entries = list(scraper.iter_single_page(filmography_path or ""))
    finally:
        if scraper:
            scraper.close()
    if not entries:
        typer.echo("No films found in the provided source.")
        raise typer.Exit(code=1)
    slugs = [entry.slug for entry in entries if entry.slug]
    if not slugs:
        typer.echo("No film slugs detected in the source HTML.")
        raise typer.Exit(code=1)
    with get_session(settings) as session:
        film_rows = (
            session.query(models.Film.id, models.Film.slug)
            .filter(models.Film.slug.in_(slugs))
            .all()
        )
        film_by_slug = {row.slug: row for row in film_rows}
        missing_slugs = [slug for slug in slugs if slug not in film_by_slug]
        ordered_ids: list[int] = []
        seen_ids: set[int] = set()
        for slug in slugs:
            film = film_by_slug.get(slug)
            if not film:
                continue
            film_id = int(film.id)
            if film_id in seen_ids:
                continue
            seen_ids.add(film_id)
            ordered_ids.append(film_id)
        ranking_rows = ranking_service.fetch_rankings_for_film_ids(
            session,
            cohort_id=cohort_id,
            strategy=strategy,
            film_ids=ordered_ids,
        )
    if not ranking_rows:
        console.print("[yellow]No ranking data[/yellow] matched the provided films. Run 'rank compute' first?")
        return
    display_rows = ranking_rows if limit <= 0 else ranking_rows[:limit]
    limit_text = "all" if limit <= 0 else str(limit)
    console.print(
        f"[green]Matched[/green] {len(ranking_rows)} ranked films "
        f"from {len(slugs)} source entries (limit {limit_text})."
    )
    for row in display_rows:
        rank_display = row.rank if row.rank is not None else "-"
        watchers = row.watchers if row.watchers is not None else "-"
        avg_text = f"{row.avg_rating:.2f}" if row.avg_rating is not None else "-"
        console.print(
            f"#{rank_display} {row.title} ({row.slug}) "
            f"score={row.score:.3f} watchers={watchers} avg={avg_text}"
        )
    if missing_slugs:
        preview = ", ".join(sorted(set(missing_slugs))[:5])
        console.print(f"[yellow]Missing in DB[/yellow]: {preview}")
    ranked_ids = {row.film_id for row in ranking_rows}
    missing_ranked = []
    for slug in slugs:
        film = film_by_slug.get(slug)
        if not film:
            continue
        film_id = int(film.id)
        if film_id not in ranked_ids:
            missing_ranked.append(slug)
    if missing_ranked:
        preview = ", ".join(sorted(set(missing_ranked))[:5])
        console.print(f"[yellow]No ranking rows[/yellow] for: {preview}")

@export_app.command("csv")
def export_csv(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    strategy: str = typer.Option("bayesian", "--strategy", "-s", help="Ranking strategy id."),
    min_score: float = typer.Option(0.0, "--min-score", help="Score threshold."),
    output: Path = typer.Option(Path("exported/cohort.csv"), "--output", "-o", help="Output CSV."),
) -> None:
    """Export ranking results to CSV."""
    settings = get_state(ctx)["settings"]
    with telemetry_service.timed_operation(f"export[{cohort_id}:{strategy}]"):
        with get_session(settings) as session:
            count = export_service.export_rankings_to_csv(
                session,
                cohort_id=cohort_id,
                strategy=strategy,
                min_score=min_score,
                output_path=output,
            )
    console.print(
        f"[green]Exported[/green] {count} rows for cohort {cohort_id} strategy {strategy} to {output}"
    )


@stats_app.command("refresh")
def stats_refresh(ctx: typer.Context, concurrent: bool = typer.Option(False, "--concurrent/--no-concurrent")) -> None:
    """Refresh the cohort_film_stats materialized view."""
    settings = get_state(ctx)["settings"]
    with telemetry_service.timed_operation("stats_refresh"):
        with get_session(settings) as session:
            stats_service.refresh_cohort_stats(session, concurrently=concurrent)
    console.print("[green]Refreshed[/green] cohort_film_stats view.")


@user_app.command("sync-following")
def user_sync_following(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Letterboxd username whose following list will be scraped."),
    print_only: bool = typer.Option(
        False,
        "--print-only",
        help="Preview fetched metadata instead of persisting it.",
    ),
) -> None:
    """Pull a user's following list and update stored display names/avatars."""
    settings = get_state(ctx)["settings"]
    scraper = FollowGraphScraper(settings)
    console.print(f"[cyan]Fetching[/cyan] @{username}'s following list…")
    try:
        profile_meta = scraper.fetch_profile_metadata(username)
        results = scraper.fetch_following(username)
    finally:
        scraper.close()
    if not results:
        console.print(f"[yellow]No accounts found[/yellow] for @{username}.")
        return
    if print_only:
        console.print("[magenta]Previewing fetched metadata (no DB writes):[/magenta]")
        for entry in results:
            console.print(
                f" @{entry.username:<20} "
                f"name={entry.display_name!r} "
                f"avatar={entry.avatar_url or ''}"
            )
        if profile_meta:
            console.print(
                f" [green](seed)[/green] @{profile_meta.username:<20} "
                f"name={profile_meta.display_name!r} "
                f"avatar={profile_meta.avatar_url or ''}"
            )
        return
    updated = 0
    with get_session(settings) as session:
        for entry in results:
            cohort_service.get_or_create_user(
                session,
                entry.username,
                entry.display_name,
                entry.avatar_url,
            )
            updated += 1
        if profile_meta:
            cohort_service.get_or_create_user(
                session,
                profile_meta.username,
                profile_meta.display_name,
                profile_meta.avatar_url,
            )
            updated += 1
    console.print(
        f"[green]Updated[/green] metadata for {updated} user(s) "
        f"from @{username}'s following list."
    )


@user_app.command("favorites")
def user_favorites(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Letterboxd username whose profile favorites will be fetched."),
) -> None:
    """Preview a user's four profile favorites without touching the database."""
    settings = get_state(ctx)["settings"]
    scraper = ProfileRatingsScraper(settings)
    console.print(f"[cyan]Fetching[/cyan] @{username}'s profile favorites…")
    try:
        favorites = scraper.fetch_profile_favorites(username)
    finally:
        scraper.close()
    if not favorites:
        console.print(f"[yellow]No favorites found[/yellow] for @{username}.")
        return
    table = Table(title=f"@{username}'s favorites")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Title")
    table.add_column("Slug")
    table.add_column("Rating")
    for idx, entry in enumerate(favorites, start=1):
        rating_text = (
            f"{entry.rating:.1f}"
            if entry.rating is not None
            else ("liked" if entry.liked else "unrated")
        )
        table.add_row(str(idx), entry.film_title, entry.film_slug, rating_text)
    console.print(table)


@film_app.command("ids")
def film_ids(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Letterboxd film slug."),
) -> None:
    """Print TMDB + IMDb identifiers discovered from the film page buttons."""
    settings = get_state(ctx)["settings"]
    scraper = FilmPageScraper(settings)
    console.print(f"[cyan]Fetching[/cyan] metadata for film '{slug}'…")
    try:
        details = scraper.fetch(slug)
    finally:
        scraper.close()
    if not details:
        console.print(f"[red]Failed[/red] to fetch metadata for '{slug}'.")
        raise typer.Exit(code=1)
    table = Table(title=f"Identifiers for {details.slug}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Title", details.title or "")
    table.add_row("Canonical slug", details.slug)
    table.add_row("TMDB ID", str(details.tmdb_id or ""))
    table.add_row("TMDB media type", details.tmdb_media_type or "")
    table.add_row("IMDb ID", details.imdb_id or "")
    table.add_row("Letterboxd film id", str(details.letterboxd_film_id or ""))
    console.print(table)


@film_app.command("sync-ids")
def film_sync_ids(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Letterboxd film slug."),
    apply: bool = typer.Option(
        False,
        "--apply/--no-apply",
        help="Persist the scraped TMDB/IMDb identifiers to the database.",
    ),
) -> None:
    """Fetch TMDB/IMDb identifiers from the Letterboxd film page and optionally update the DB."""
    settings = get_state(ctx)["settings"]
    letterboxd_hint = None
    existing_film_id = None
    with get_session(settings) as session:
        existing = session.query(models.Film).filter(models.Film.slug == slug).one_or_none()
        if existing:
            existing_film_id = existing.id
            letterboxd_hint = existing.letterboxd_film_id
    scraper = FilmPageScraper(settings)
    console.print(f"[cyan]Fetching[/cyan] identifiers for '{slug}'…")
    try:
        details = scraper.fetch(slug, letterboxd_id=letterboxd_hint)
    finally:
        scraper.close()
    table = Table(title=f"Identifiers for {details.slug}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Title", details.title or "")
    table.add_row("Canonical slug", details.slug)
    table.add_row("TMDB ID", str(details.tmdb_id or ""))
    table.add_row("TMDB media type", details.tmdb_media_type or "")
    table.add_row("IMDb ID", details.imdb_id or "")
    table.add_row("Letterboxd film id", str(details.letterboxd_film_id or ""))
    console.print(table)
    if not apply:
        console.print("[yellow]Dry run[/yellow]: pass --apply to persist these identifiers.")
        return
    with get_session(settings) as session:
        filters = [models.Film.slug == slug]
        if existing_film_id:
            filters.append(models.Film.id == existing_film_id)
        if details.slug and details.slug != slug:
            filters.append(models.Film.slug == details.slug)
        if details.letterboxd_film_id:
            filters.append(models.Film.letterboxd_film_id == details.letterboxd_film_id)
        if details.tmdb_id:
            filters.append(models.Film.tmdb_id == details.tmdb_id)
        film = session.query(models.Film).filter(or_(*filters)).first()
        if not film:
            console.print(f"[red]Film '{details.slug}' not found in the database.[/red]")
            raise typer.Exit(code=1)
        changes = []
        if film.slug != details.slug:
            film.slug = details.slug
            changes.append("slug")
        if details.title and film.title != details.title:
            film.title = details.title
            changes.append("title")
        for attr, value in (
            ("tmdb_id", details.tmdb_id),
            ("tmdb_media_type", details.tmdb_media_type),
            ("imdb_id", details.imdb_id),
            ("letterboxd_film_id", details.letterboxd_film_id),
        ):
            if getattr(film, attr) != value and value is not None:
                setattr(film, attr, value)
                changes.append(attr)
        # reset episode-specific fields; they'll be re-populated on next enrichment
        film.tmdb_show_id = None
        film.tmdb_season_number = None
        film.tmdb_episode_number = None
        session.flush()
    if changes:
        console.print(f"[green]Updated[/green] {', '.join(changes)} for '{details.slug}'.")
    else:
        console.print("[yellow]No changes[/yellow]; existing identifiers already match.")
@cohort_app.command("list")
def cohort_list(ctx: typer.Context) -> None:
    """List existing cohorts."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohorts = cohort_service.list_cohorts(session)
    table = Table(title="Cohorts")
    table.add_column("ID", style="cyan")
    table.add_column("Label")
    table.add_column("Seed")
    table.add_column("Members")
    for cohort_id, label, seed_id, member_count in cohorts:
        table.add_row(str(cohort_id), label, str(seed_id or ""), str(member_count))
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
@cleanup_app.command("dedupe-films")
def cleanup_dedupe_films(
    ctx: typer.Context,
    fix_samples: bool = typer.Option(False, "--fix-samples", help="Auto-merge known renamed films."),
    prune_orphans: bool = typer.Option(True, "--prune-orphans/--keep-orphans", help="Delete films that no longer exist on Letterboxd."),
    log: Optional[Path] = typer.Option(None, "--log", help="Only process slugs listed in the given error log."),
) -> None:
    """Fix duplicate slugs/letterboxd IDs and remove 404 films."""
    settings = get_state(ctx)["settings"]
    scraper = FilmPageScraper(settings)
    deleted = 0
    merged = 0
    errors: list[str] = []
    slug_filter: Optional[set[str]] = None
    slug_pairs: dict[str, str] = {}
    orphan_ids: set[int] = set()
    if log:
        slug_filter = set()
        for line in log.read_text(encoding="utf-8").splitlines():
            match = re.search(r"\] Enrichment failed ([^:]+):", line)
            if match:
                current = match.group(1).strip()
                slug_filter.add(current)
                slug_pairs.setdefault(current, "")
                continue
            match = re.search(r"Key \(slug\)=\(([^)]+)\)", line)
            if match and slug_pairs:
                canonical = match.group(1).strip()
                for orig, dest in list(slug_pairs.items()):
                    if not dest:
                        slug_pairs[orig] = canonical
                        slug_filter.add(canonical)
                        break
            match = re.search(r"film:([0-9]+)", line)
            if match and "404 Not Found" in line:
                orphan_ids.add(int(match.group(1)))
        if slug_filter:
            console.print(f"[cyan]Restricting cleanup to[/cyan] {len(slug_filter)} slug(s) from {log}")

    def _merge_into(session: Session, primary: models.Film, duplicate: models.Film) -> None:
        nonlocal merged
        if primary.id == duplicate.id:
            return
        dup_ratings = session.query(models.Rating).filter(models.Rating.film_id == duplicate.id).all()
        for rating in dup_ratings:
            existing = (
                session.query(models.Rating)
                .filter(models.Rating.film_id == primary.id, models.Rating.user_id == rating.user_id)
                .one_or_none()
            )
            if existing:
                session.delete(rating)
            else:
                rating.film_id = primary.id
        session.query(models.FilmPerson).filter(models.FilmPerson.film_id == duplicate.id).delete()
        session.query(models.FilmHistogram).filter(models.FilmHistogram.film_id == duplicate.id).delete()
        session.delete(duplicate)
        merged += 1

    try:
        with get_session(settings) as session:
            for orig_slug, canonical_slug in slug_pairs.items():
                duplicate = session.query(models.Film).filter(models.Film.slug == orig_slug).one_or_none()
                primary = (
                    session.query(models.Film).filter(models.Film.slug == canonical_slug).one_or_none()
                    if canonical_slug else None
                )
                if duplicate and primary:
                    console.print(f"[yellow]Merging logged slug[/yellow]: {duplicate.slug} -> {primary.slug}")
                    _merge_into(session, primary, duplicate)
                elif duplicate and canonical_slug and not primary:
                    console.print(f"[cyan]Renaming[/cyan] {duplicate.slug} -> {canonical_slug}")
                    duplicate.slug = canonical_slug

            slug_conflicts = (
                session.query(models.Film.slug)
                .group_by(models.Film.slug)
                .having(func.count(models.Film.id) > 1)
                .all()
            )
            for (slug,) in slug_conflicts:
                if slug_filter and slug not in slug_filter:
                    continue
                films = session.query(models.Film).filter(models.Film.slug == slug).order_by(models.Film.id).all()
                if len(films) < 2:
                    continue
                primary = films[0]
                for dup in films[1:]:
                    console.print(f"[yellow]Merging slug duplicate[/yellow]: {dup.slug} -> {primary.slug}")
                    _merge_into(session, primary, dup)

            id_conflicts = (
                session.query(models.Film.letterboxd_film_id)
                .filter(models.Film.letterboxd_film_id.isnot(None))
                .group_by(models.Film.letterboxd_film_id)
                .having(func.count(models.Film.id) > 1)
                .all()
            )
            for (lb_id,) in id_conflicts:
                films = session.query(models.Film).filter(models.Film.letterboxd_film_id == lb_id).order_by(models.Film.id).all()
                if slug_filter and not any(f.slug in slug_filter for f in films):
                    continue
                primary = films[0]
                for dup in films[1:]:
                    console.print(f"[yellow]Merging Letterboxd ID duplicate[/yellow]: {dup.slug} -> {primary.slug}")
                    _merge_into(session, primary, dup)
            session.flush()
    except Exception as exc:
        errors.append(f"Failed to merge duplicates: {exc}")

    try:
        with get_session(settings) as session:
            query = session.query(models.Film.id, models.Film.slug, models.Film.letterboxd_film_id)
            if slug_filter:
                query = query.filter(models.Film.slug.in_(slug_filter))
            films = query.all()
        for film_id, slug, lb_id in films:
            hint = lb_id
            if fix_samples and hint:
                try:
                    scraper.fetch(slug, letterboxd_id=hint)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404 and prune_orphans:
                        with get_session(settings) as session:
                            film = session.get(models.Film, film_id)
                            if film:
                                console.print(f"[yellow]Deleting orphan[/yellow] {slug} (letterboxd id={lb_id})")
                                session.delete(film)
                                deleted += 1
                    else:
                        errors.append(f"{slug}: {exc}")
        if orphan_ids and prune_orphans:
            with get_session(settings) as session:
                to_delete = session.query(models.Film).filter(models.Film.letterboxd_film_id.in_(list(orphan_ids))).all()
                for film in to_delete:
                    console.print(f"[yellow]Deleting orphan[/yellow] {film.slug} (letterboxd id={film.letterboxd_film_id})")
                    session.delete(film)
                    deleted += 1
    except Exception as exc:
        errors.append(f"Failed to prune orphaned films: {exc}")
    console.print(f"[green]Merged duplicates[/green]: {merged}, [red]Deleted orphans[/red]: {deleted}")
    if errors:
        console.print("[red]Errors:[/red]")
        for err in errors:
            console.print(f"  - {err}")
    scraper.close()
