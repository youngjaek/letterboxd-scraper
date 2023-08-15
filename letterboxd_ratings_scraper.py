import requests
from bs4 import BeautifulSoup
import psycopg2
import csv

# Function to parse the user's films page and add data to the database
def parse_user_films(username, connection):
    page_number = 1
    # scraped_films_count = 0

    # print(f"Scraping {username}'s films page...")
    while True:
        # print(f"Scraping page {page_number}...")
        base_url = f"https://letterboxd.com/{username}/films/rated/.5-5/page/{page_number}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        response = requests.get(base_url, headers=headers)

        soup = BeautifulSoup(response.text, "lxml")
        films = soup.find_all("li", class_="poster-container")
        # print(f"Found {len(films)} films on this page")

        if not films:
            # No more films on this page, break the loop
            break

        for film in films:
            film_name = film.find("img")["alt"]
            film_link = film.find("div")["data-film-slug"]
            # print(f"Found film: {film_name} ({film_link})")

            rating_element = film.find("span", class_="rating")
            rating_class = rating_element["class"][-1]  # Get the last class name which contains the rating value (e.g., 'rated-7')
            rating = int(rating_class.split("-")[-1])  # Extract the rating value from the class name (e.g., '7')
            letterboxd_url = f"https://letterboxd.com{film_link}"
            # print(f"Rating: {rating}")
            # print(f"Letterboxd URL: {letterboxd_url}")

            # scraped_films_count += 1

            # Check if the film is already in the database
            film_data = fetch_film_db(film_name, letterboxd_url, connection)

            if film_data:
                # Film exists in the database, update the data
                watched_people = film_data[2] + 1
                avg_rating = (film_data[3] * film_data[2] + rating) / watched_people
                popularity = watched_people * avg_rating
                update_film_db(film_name, letterboxd_url, watched_people, avg_rating, popularity, connection)
            else:
                # Film does not exist in the database, add it
                watched_people = 1
                avg_rating = rating
                popularity = watched_people * avg_rating
                add_film_db(film_name, letterboxd_url, watched_people, avg_rating, popularity, connection)

        page_number += 1

    # print(f"Scraped {scraped_films_count} films in total")

# Function to fetch film data from the database
def fetch_film_db(title, letterboxd_url, connection):
    with connection.cursor() as cursor:
        sql = "SELECT * FROM film_database WHERE title = %s AND letterboxd_url = %s"
        cursor.execute(sql, (title, letterboxd_url))
        film_data = cursor.fetchone()
        return film_data

# Function to add film data to the database
def add_film_db(title, letterboxd_url, watched_people, avg_rating, popularity, connection):
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO film_database (title, letterboxd_url, watched_people, avg_rating, popularity, watched) VALUES (%s, %s, %s, %s, %s, FALSE)"
            cursor.execute(sql, (title, letterboxd_url, watched_people, avg_rating, popularity))
        connection.commit()
        # print(f"Added film '{title}' to the database.")
    except Exception as e:
        print(f"Error: {e}")
        connection.rollback()

# Function to update film data in the database
def update_film_db(title, letterboxd_url, watched_people, avg_rating, popularity, connection):
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE film_database SET watched_people = %s, avg_rating = %s, popularity = %s WHERE title = %s AND letterboxd_url = %s"
            cursor.execute(sql, (watched_people, avg_rating, popularity, title, letterboxd_url))
        connection.commit()
        # print(f"Updated film '{title}' in the database.")
    except Exception as e:
        print(f"Error: {e}")
        connection.rollback()

# Function to parse user's watched films page and skip if films are not in the database and if they exist, mark them as watched in the database
def parse_user_watched_films(username, connection):
    page_number = 1
    # scraped_films_count = 0

    # print(f"Scraping {username}'s watched films page...")
    while True:
        # print(f"Scraping page {page_number}...")
        base_url = f"https://letterboxd.com/{username}/films/page/{page_number}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        response = requests.get(base_url, headers=headers)

        soup = BeautifulSoup(response.text, "lxml")
        films = soup.find_all("li", class_="poster-container")
        # print(f"Found {len(films)} films on this page")

        if not films:
            # No more films on this page, break the loop
            break

        for film in films:
            film_name = film.find("img")["alt"]
            film_link = film.find("div")["data-film-slug"]

            letterboxd_url = f"https://letterboxd.com{film_link}"

            # Check if the film is already in the database
            film_data = fetch_film_db(film_name, letterboxd_url, connection)

            if film_data:
                # Film exists in the database, mark it as watched
                mark_film_watched_db(film_name, letterboxd_url, connection)
            else:
                # Film does not exist in the database, skip it
                pass

        page_number += 1

# Function to mark film as watched in the database
def mark_film_watched_db(title, letterboxd_url, connection):
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE film_database SET watched = TRUE WHERE title = %s AND letterboxd_url = %s"
            cursor.execute(sql, (title, letterboxd_url))
        connection.commit()
        # print(f"Marked film '{title}' as watched in the database.")
    except Exception as e:
        print(f"Error: {e}")
        connection.rollback()

# Function to get list of people a user follows, scraping each page
def get_following_list(username):
    page_number = 1
    following_list = []

    # print(f"Scraping {username}'s following list...")
    while True:
        # print(f"Scraping page {page_number}...")
        base_url = f"https://letterboxd.com/{username}/following/page/{page_number}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        response = requests.get(base_url, headers=headers)

        soup = BeautifulSoup(response.text, "lxml")
        people = soup.find_all("div", class_="follow-button-wrapper js-follow-button-wrapper")
        # print(f"Found {len(people)} people on this page")

        if not people:
            # No more people on this page, break the loop
            break

        for person in people:
            person_name = person["data-username"]
            following_list.append(person_name)

        page_number += 1

    return following_list

# Function to export the database to a CSV file
def export_db_to_csv(connection):
    with connection.cursor() as cursor:
        sql = "SELECT letterboxd_url, watched_people, avg_rating, popularity FROM film_database WHERE (avg_rating >= 7.0 AND watched_people >= 40 AND watched = FALSE) OR (avg_rating >= 7.4 AND watched_people >= 25 AND watched = FALSE) OR (avg_rating >= 8.0 AND watched_people >= 10 AND watched = FALSE) ORDER BY popularity DESC"
        cursor.execute(sql)
        film_data = cursor.fetchall()

        with open("film_database.csv", "w", newline="", encoding="utf-8") as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["url", "Watched People", "Average Rating", "Popularity"])
            csv_writer.writerows(film_data)

if __name__ == "__main__":
    # Replace 'your_username' with the Letterboxd username you want to scrape
    username = "thebigal"

    # Connect to the PostgreSQL database
    connection = psycopg2.connect(
        user="postgres",
        password="Letter*postgres82",
        host="localhost",
        port="5432",
        database="postgres"
    )

    # following_list = get_following_list(username)
    # for person in following_list:
    #     print(f"Scraping {person}'s films...")
    #     parse_user_films(person, connection)

    print(f"Scraping {username}'s watched films...")
    parse_user_watched_films(username, connection)

    # parse_user_films(username, connection)
    # print("Exporting database to CSV...")
    # export_db_to_csv(connection)
    print("Done!")

    # Close the database connection
    connection.close()
