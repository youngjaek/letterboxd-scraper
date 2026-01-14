from letterboxd_scraper.services import rankings


def test_distribution_label_strong_left():
    label, bonus = rankings.classify_distribution_label(
        watchers=100,
        count_gte_4_5=55,
        count_4_0_4_5=15,
        count_3_5_4_0=15,
        count_3_0_3_5=10,
        count_2_5_3_0=3,
        count_lt_2_5=2,
    )
    assert label == "strong-left"
    assert bonus > 0.2


def test_distribution_label_right_skew():
    label, bonus = rankings.classify_distribution_label(
        watchers=80,
        count_gte_4_5=5,
        count_4_0_4_5=7,
        count_3_5_4_0=10,
        count_3_0_3_5=18,
        count_2_5_3_0=20,
        count_lt_2_5=20,
    )
    assert label == "right"
    assert bonus < 0


def test_distribution_label_bimodal_low_high():
    label, bonus = rankings.classify_distribution_label(
        watchers=120,
        count_gte_4_5=40,
        count_4_0_4_5=15,
        count_3_5_4_0=10,
        count_3_0_3_5=5,
        count_2_5_3_0=30,
        count_lt_2_5=20,
    )
    assert label == "bimodal-low-high"
    assert bonus >= 0


def test_distribution_label_handles_zero_watchers():
    label, bonus = rankings.classify_distribution_label(
        watchers=0,
        count_gte_4_5=0,
        count_4_0_4_5=0,
        count_3_5_4_0=0,
        count_3_0_3_5=0,
        count_2_5_3_0=0,
        count_lt_2_5=0,
    )
    assert label == "unknown"
    assert bonus == 0
