from pathlib import Path

from letterboxd_scraper.scrapers.histograms import RatingsHistogramScraper


def read_fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def test_parse_histogram_summary():
    html = read_fixture("ratings_summary_mulholland_drive.html")
    summary = RatingsHistogramScraper.parse_html("mulholland-drive", html)
    assert summary.slug == "mulholland-drive"
    assert summary.fan_count and summary.fan_count > 0
    assert summary.weighted_average and 0 < summary.weighted_average < 5
    assert summary.rating_count and summary.rating_count > 0
    assert len(summary.buckets) >= 10
    first_bucket = summary.buckets[0]
    assert first_bucket.count > 0
    assert 0 <= first_bucket.percentage <= 100
    assert 0 <= first_bucket.rating_value <= 5
