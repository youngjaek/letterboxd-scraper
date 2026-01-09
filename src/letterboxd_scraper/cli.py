from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Set

import typer
from rich.console import Console
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
from .services.enrichment import enrich_film_metadata, film_needs_enrichment
from .scrapers.film_pages import FilmPageScraper
from .scrapers.person_pages import PersonPageScraper
from .scrapers.follow_graph import FollowGraphScraper, expand_follow_graph
from .scrapers.histograms import RatingsHistogramScraper
from .scrapers.listings import PosterListingScraper
from .scrapers.ratings import FilmRating, ProfileRatingsScraper
from .services.tmdb import TMDBClient

console = Console()

app = typer.Typer(
    help="Personalized Letterboxd scraper CLI.",
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
cohort_app = typer.Typer(help="Manage cohorts (follow lists).", no_args_is_help=True)
scrape_app = typer.Typer(help="Scraping commands.", no_args_is_help=True)
stats_app = typer.Typer(help="Statistics/materialized view maintenance.", no_args_is_help=True)
rank_app = typer.Typer(help="Ranking computations.", no_args_is_help=True)
export_app = typer.Typer(help="Export data into consumable formats.")
user_app = typer.Typer(help="User metadata utilities.", no_args_is_help=True)

app.add_typer(cohort_app, name="cohort")
app.add_typer(scrape_app, name="scrape")
app.add_typer(stats_app, name="stats")
app.add_typer(rank_app, name="rank")
app.add_typer(export_app, name="export")
app.add_typer(user_app, name="user")


def get_state(ctx: typer.Context) -> Dict[str, Settings]:
    return ctx.ensure_object(dict)  # type: ignore[return-value]


def _scrape_user_ratings(
    settings: Settings,
    username: str,
    *,
    incremental: bool = False,
) -> tuple[int, Set[int]]:
    """Fetch ratings + likes for a single user and persist them."""
    with get_session(settings) as session:
        snapshot = rating_service.get_user_rating_snapshot(session, username)
    scraper = ProfileRatingsScraper(settings)
    try:
        ratings: list[FilmRating] = []
        for payload in scraper.fetch_user_ratings(username):
            if rating_service.rating_matches_snapshot(snapshot, payload):
                break
            ratings.append(payload)
        rated_slugs = {item.film_slug for item in ratings}
        likes: list[FilmRating] = []
        for payload in scraper.fetch_user_liked_films(username):
            if payload.film_slug in rated_slugs:
                continue
            if rating_service.rating_matches_snapshot(snapshot, payload):
                break
            likes.append(payload)
    finally:
        scraper.close()
    likes_only = [item for item in likes if item.film_slug not in rated_slugs]
    combined = ratings + likes_only
    with get_session(settings) as session:
        touched = rating_service.upsert_ratings(
            session,
            username,
            combined,
            touch_last_full=not incremental,
            touch_last_incremental=incremental,
        )
    return len(combined), touched


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


@scrape_app.command("full")
def scrape_full(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    resume: bool = typer.Option(False, "--resume/--no-resume", help="Resume from last checkpoint."),
    user: Optional[str] = typer.Option(
        None,
        "--user",
        help="Restrict scraping to a single cohort member (Letterboxd username).",
    ),
) -> None:
    """Run a full historical scrape for every user in the cohort."""
    settings = get_state(ctx)["settings"]
    usernames: list[str] = []
    skipped: list[str] = []
    with get_session(settings) as session:
        if not cohort_service.get_cohort(session, cohort_id):
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
    total_members = len(members)
    ttl_hours = max(0, getattr(settings.scraper, "full_scrape_ttl_hours", 0))
    cutoff = None
    if ttl_hours > 0 and not user:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    for username, last_scraped in members:
        if cutoff and last_scraped and last_scraped >= cutoff:
            skipped.append(username)
            continue
        usernames.append(username)
    if skipped:
        preview = ", ".join(skipped[:5])
        extra = f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else ""
        console.print(
            f"[yellow]Skipping[/yellow] {len(skipped)} recently scraped user(s) "
            f"(last < {ttl_hours}h): {preview}{extra}"
        )
    if not usernames:
        if total_members:
            console.print(
                f"[green]Cohort[/green] {cohort_id}: all {total_members} members were scraped < {ttl_hours}h ago."
            )
        else:
            console.print(f"[yellow]Cohort[/yellow] {cohort_id} has no members to scrape.")
        return
    run_id = None
    with get_session(settings) as session:
        run_id = telemetry_service.record_scrape_run(
            session,
            cohort_id=cohort_id,
            run_type="full",
            status="running",
        )
    status = "success"
    note = None
    touched_films: set[int] = set()
    try:
        with telemetry_service.timed_operation(f"scrape_full[{cohort_id}]"):
            max_workers = max(1, settings.scraper.max_concurrency)
            console.print(
                f"[green]Queued[/green] {len(usernames)} users "
                f"with {max_workers} worker(s)."
            )
            futures: Dict[Any, str] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for username in usernames:
                    futures[executor.submit(_scrape_user_ratings, settings, username)] = username
                for future in as_completed(futures):
                    username = futures[future]
                    try:
                        count, touched = future.result()
                        touched_films.update(touched)
                        console.print(
                            f"[cyan]{username}[/cyan]: processed {count} ratings/likes."
                        )
                    except Exception as exc:
                        status = "failed"
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
    console.print(f"[green]Completed[/green] full scrape for cohort {cohort_id}.")
    console.print(
        f"[yellow]Next[/yellow]: run 'letterboxd-scraper scrape enrich' to hydrate "
        f"metadata for {len(touched_films)} films."
    )


@scrape_app.command("incremental")
def scrape_incremental(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    user: Optional[str] = typer.Option(
        None,
        "--user",
        help="Restrict incremental scraping to a single cohort member (Letterboxd username).",
    ),
) -> None:
    """Apply incremental updates via rated-date scraping."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        usernames = cohort_service.list_member_usernames(session, cohort_id)
    if user:
        normalized = user.strip().lower()
        filtered = [name for name in usernames if name.lower() == normalized]
        if not filtered:
            typer.echo(f"User '{user}' is not a member of cohort {cohort_id}.")
            raise typer.Exit(code=1)
        usernames = filtered
    if not usernames:
        console.print(f"[yellow]Cohort[/yellow] {cohort_id} has no members to scrape.")
        return
    run_id = None
    with get_session(settings) as session:
        run_id = telemetry_service.record_scrape_run(
            session,
            cohort_id=cohort_id,
            run_type="incremental",
            status="running",
        )
    status = "success"
    note = None
    touched_films: set[int] = set()
    try:
        with telemetry_service.timed_operation(f"scrape_incremental[{cohort_id}]"):
            max_workers = max(1, settings.scraper.max_concurrency)
            console.print(
                f"[green]Queued[/green] {len(usernames)} users "
                f"with {max_workers} worker(s)."
            )
            futures: Dict[Any, str] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for username in usernames:
                    futures[
                        executor.submit(
                            _scrape_user_ratings,
                            settings,
                            username,
                            incremental=True,
                        )
                    ] = username
                for future in as_completed(futures):
                    username = futures[future]
                    try:
                        count, touched = future.result()
                        touched_films.update(touched)
                        console.print(
                            f"[cyan]{username}[/cyan]: processed {count} incremental tiles."
                        )
                    except Exception as exc:
                        status = "failed"
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
    console.print(f"[green]Incremental update complete[/green]; {len(touched_films)} films touched.")
    if touched_films:
        console.print(
            f"[yellow]Next[/yellow]: run 'letterboxd-scraper scrape enrich' "
            f"to hydrate metadata for {len(touched_films)} films."
        )


@scrape_app.command("enrich")
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
) -> None:
    """Hydrate films with TMDB metadata and/or Letterboxd histograms."""
    settings = get_state(ctx)["settings"]
    if not include_tmdb and not include_histograms:
        typer.echo("Enable at least one of --tmdb or --histograms.")
        raise typer.Exit(code=1)
    if include_tmdb and not settings.tmdb.api_key:
        console.print("[yellow]TMDB API key not configured[/yellow]; skipping TMDB enrichment.")
        include_tmdb = False
    tmdb_client = None
    film_page_scraper = None
    person_page_scraper = None
    histogram_scraper: Optional[RatingsHistogramScraper] = None
    if include_tmdb and settings.tmdb.api_key:
        tmdb_client = TMDBClient(settings)
        film_page_scraper = FilmPageScraper(settings)
        person_page_scraper = PersonPageScraper(settings)
    if include_histograms:
        histogram_scraper = RatingsHistogramScraper(settings)
    processed = 0
    tmdb_elapsed_total = 0.0
    histogram_elapsed_total = 0.0
    tmdb_calls = 0
    histogram_calls = 0
    try:
        with get_session(settings) as session:
            if slug:
                film = session.query(models.Film).filter(models.Film.slug == slug).one_or_none()
                if not film:
                    console.print(f"[red]Film '{slug}' not found.[/red]")
                    raise typer.Exit(code=1)
                films = [film]
            else:
                films = session.query(models.Film).order_by(models.Film.id).all()
            for film in films:
                touched = False
                force_enrich = bool(slug)
                run_tmdb = include_tmdb and tmdb_client and (force_enrich or film_needs_enrichment(film))
                if run_tmdb:
                    tmdb_start = perf_counter()
                    try:
                        success = enrich_film_metadata(
                            session,
                            film,
                            client=tmdb_client,
                            film_page_scraper=film_page_scraper,
                            person_page_scraper=person_page_scraper,
                        )
                        if success:
                            elapsed = perf_counter() - tmdb_start
                            tmdb_calls += 1
                            tmdb_elapsed_total += elapsed
                            console.print(
                                f"[green]TMDB[/green] {film.slug} ({elapsed:.2f}s)"
                            )
                        touched = touched or success
                    except Exception as exc:  # pragma: no cover - safety log
                        elapsed = perf_counter() - tmdb_start
                        console.print(
                            f"[red]TMDB failed[/red] {film.slug} ({elapsed:.2f}s): {exc}"
                        )
                if include_histograms and histogram_scraper and histogram_service.film_needs_histogram(film):
                    histogram_start = perf_counter()
                    try:
                        summary = histogram_scraper.fetch(film.slug)
                        histogram_service.upsert_global_histogram(session, film, summary)
                        elapsed = perf_counter() - histogram_start
                        histogram_calls += 1
                        histogram_elapsed_total += elapsed
                        console.print(
                            f"[cyan]Histogram[/cyan] {film.slug} ({elapsed:.2f}s)"
                        )
                        touched = True
                    except Exception as exc:  # pragma: no cover
                        elapsed = perf_counter() - histogram_start
                        console.print(
                            f"[red]Histogram failed[/red] {film.slug} ({elapsed:.2f}s): {exc}"
                        )
                if touched:
                    processed += 1
                    session.flush()
                    if limit and processed >= limit:
                        break
    finally:
        if film_page_scraper:
            film_page_scraper.close()
        if person_page_scraper:
            person_page_scraper.close()
        if tmdb_client:
            tmdb_client.close()
        if histogram_scraper:
            histogram_scraper.close()
    console.print(f"[green]Enrichment complete[/green]; processed {processed} films.")
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
