# CLI Workflow Cheatsheet

1. **Create cohort**
   ```bash
   letterboxd-scraper cohort build --seed my_username --label "My Friends"
   ```
2. **Refresh follow graph**
   ```bash
   letterboxd-scraper cohort refresh 1
   ```
3. **Full scrape (initial)**
   ```bash
   letterboxd-scraper scrape full 1
   ```
4. **Refresh stats view**
   ```bash
   letterboxd-scraper stats refresh
   ```
5. **Compute rankings**
   ```bash
   letterboxd-scraper rank compute 1 --strategy bayesian
   ```
6. **Export CSV**
   ```bash
   letterboxd-scraper export csv 1 --strategy bayesian --output exported/my_friends.csv
   ```
7. **Incremental updates (RSS)**
   ```bash
   letterboxd-scraper scrape incremental 1
   letterboxd-scraper stats refresh
   letterboxd-scraper rank compute 1 --strategy bayesian
   ```
