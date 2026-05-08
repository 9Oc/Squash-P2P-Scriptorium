#!/usr/bin/env python3
"""
Generates an MKV global tags XML file using TMDB ID.

Dependencies:
pip install tvdb_v4_official requests rich

@version 1.5
"""

import re
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

import requests
from rich import print
from tvdb_v4_official import TVDB

# config
TMDB_API_KEY = ""
TVDB_API_KEY = ""

tvdb = TVDB(TVDB_API_KEY)

def sanitize(text: str) -> str:
    """Return a filesystem-safe version of a string."""
    if not text:
        return ""
    text = re.sub(r'[\/\\:\*\?"<>\|\-—·.,^]+', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def get_tmdb_info(tmdb_id: str) -> dict[str | None]:
    """Get IMDB ID from TMDB movie ID."""
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY}
    movie = {"imdb_id": None, "title": None, "year": None}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        movie["imdb_id"] = data.get("imdb_id")
        movie["title"] = data.get("title")

        release_date = data.get("release_date")
        if release_date and len(release_date) >= 4:
            movie["year"] = release_date[:4]

        return movie
    except Exception as e:
        print(f"Error fetching TMDB data: {e}")
        return movie


def find_movie_objects(obj: list[dict] | dict) -> list[dict]:
    """
    Return all movie objects from tvdb search by remote ID results.
    """
    movies: list[dict] = []

    def recurse(o):
        if isinstance(o, dict):
            # if there's a 'movie' key here, collect it
            if 'movie' in o:
                m = o['movie']
                if isinstance(m, dict):
                    movies.append(m)
                elif isinstance(m, list):
                    for mi in m:
                        if isinstance(mi, dict):
                            movies.append(mi)

            for v in o.values():
                recurse(v)
        elif isinstance(o, list):
            for item in o:
                recurse(item)
        # primitives: nothing to do

    recurse(obj)
    return movies


def find_movie_ids_tvdb(obj: list[dict]) -> list[str]:
    """
    Return a list of movie ids found in the tvdb movie objects.
    """
    ids: list[int] = []
    for m in find_movie_objects(obj):
        mid = m.get('id')
        if isinstance(mid, int):
            ids.append(mid)
        else:
            try:
                if isinstance(mid, str) and mid.isdigit():
                    ids.append(mid)
            except Exception:
                pass
    return ids


def get_first_movie_id_tvdb(obj) -> str | None:
    ids = find_movie_ids(obj)
    return ids[0] if ids else None


def get_tvdb_movie_id(imdb_id: str, title: str, year: str = None) -> dict:
    """
    Search TVDB for movie ID using title and optional year.
    Returns a dict with the keys: tvdb_id, title, year, slug
    """
    tvdb_movie: dict = {
        "tvdb_id": None,
        "title": None,
        "year": None,
        "slug": None
    }
    try:
        results = tvdb.search_by_remote_id(imdb_id)

        if not results or len(results) == 0:
            results = tvdb.search(title, year=year, type="movie", lang="eng")
            if not results or len(results) == 0:
                print(f"No TVDB results found for: {title}")
                return tvdb_movie

        best_match = None
        movie_objects = find_movie_objects(results)

        if movie_objects is not None and len(movie_objects) > 0:
            best_match = movie_objects[0]

        if best_match is None:
            for result in results:
                remote_ids = result.get('remoteIds')
                if remote_ids is None or not remote_ids:
                    continue

                result_imdb_id = next(
                    (r.get('id') for r in remote_ids
                    if "imdb" in (r.get('sourceName') or "").lower()),
                    None
                )

                if result_imdb_id is None:
                    continue

                if str(result_imdb_id) == str(imdb_id):
                    best_match = result
                    break

        if best_match is None:
            best_match = results[0]

        tvdb_movie["tvdb_id"] = best_match.get('tvdb_id') or best_match.get('id')
        tvdb_movie["title"] = best_match.get('name', title)
        tvdb_movie["year"] = best_match.get('year', '')
        tvdb_movie["slug"] = best_match.get('slug', str(tvdb_movie["tvdb_id"]))

        return tvdb_movie
        
    except Exception as e:
        print(f"Error searching TVDB: {e}")
        return tvdb_movie


def generate_xml(tmdb_id: str, imdb_id: str, tvdb_id: str) -> str:
    """Generate MKV global tags XML."""
    # create XML structure
    tags = ET.Element('Tags')
    tag = ET.SubElement(tags, 'Tag')
    
    # IMDB entry
    if imdb_id:
        imdb_simple = ET.SubElement(tag, 'Simple')
        ET.SubElement(imdb_simple, 'Name').text = 'IMDB'
        ET.SubElement(imdb_simple, 'String').text = imdb_id
    
    # TMDB entry
    tmdb_simple = ET.SubElement(tag, 'Simple')
    ET.SubElement(tmdb_simple, 'Name').text = 'TMDB'
    ET.SubElement(tmdb_simple, 'String').text = f'movie/{tmdb_id}'
    
    # TVDB entry
    if tvdb_id:
        tvdb_simple = ET.SubElement(tag, 'Simple')
        ET.SubElement(tvdb_simple, 'Name').text = 'TVDB2'
        ET.SubElement(tvdb_simple, 'String').text = f'movies/{tvdb_id}'
    
    # pretty print XML
    xml_str = ET.tostring(tags, encoding='unicode')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='UTF-8').decode('utf-8')
    
    return pretty_xml


def main():
    if len(sys.argv) < 2:
        print("Less than 2 arguments were provided\nUsage: globaltags.py <TMDB_ID>")
        sys.exit(1)

    tmdb_id = sys.argv[1]

    print(f"Fetching data for TMDB ID: [orange1]{tmdb_id}[/orange1]")

    tmdb_movie = get_tmdb_info(tmdb_id)
    imdb_id = tmdb_movie.get("imdb_id")
    title = tmdb_movie.get("title")
    year = tmdb_movie.get("year")

    if not title:
        print("Error: Could not fetch movie data from TMDB")
        sys.exit(1)

    print(f"\nTMDB match: [sea_green2]{title}[/sea_green2] ({year})")
    print(f"TMDB ID: [orange1]{tmdb_id}[/orange1]")
    print(f"TMDB URL: [dodger_blue1]https://www.themoviedb.org/movie/{tmdb_id}[/dodger_blue1]")
    if imdb_id:
        print(f"\nIMDB ID: [orange1]{imdb_id}[/orange1]")
        print(f"IMDB URL: [dodger_blue1]https://www.imdb.com/title/{imdb_id}[/dodger_blue1]")
    else:
        print("Warning: IMDB ID not found")

    tvdb_movie = get_tvdb_movie_id(imdb_id, title, year)
    tvdb_id = tvdb_movie["tvdb_id"]
    tvdb_title = tvdb_movie["title"]
    tvdb_year = tvdb_movie["year"]
    tvdb_slug = tvdb_movie["slug"]

    if tvdb_id:
        print(f"\nTVDB match: [sea_green2]{tvdb_title}[/sea_green2] ({tvdb_year})")
        print(f"TVDB ID: [orange1]{tvdb_id}[/orange1]")
        print(f"TVDB URL: [dodger_blue1]https://www.thetvdb.com/movies/{tvdb_slug}[/dodger_blue1]")
    else:
        print("\nTVDB ID not found")

    xml_content = generate_xml(tmdb_id, imdb_id, tvdb_id)

    # save to file
    output_title = title.replace(" ", "_")
    output_title = sanitize(output_title)
    output_filename = f".global_tags_{output_title}_{year}.xml"
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    print(f"\nXML file saved as: [dodger_blue1]{output_filename}[/dodger_blue1]\n")
    print(xml_content)


if __name__ == "__main__":
    main()
