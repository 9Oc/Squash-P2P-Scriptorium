#!/usr/bin/env python3
"""
Generates an MKV global tags XML file using TMDB ID.

Dependencies:
pip install tvdb_v4_official requests rich
"""

import re
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

import requests
from rich import print
from tvdb_v4_official import TVDB

# config
TMDB_API_KEY = "TMDB_API_KEY" # <-- your TMDB api key here
TVDB_API_KEY = "TVDB_API_KEY" # <-- your TVDB api key here

tvdb = TVDB(TVDB_API_KEY)


def sanitize(text):
        """Return a filesystem-safe version of a string."""
        if not text:
            return ""
        text = re.sub(r'[\/\\:\*\?"<>\|\-—·.,^]+', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


def get_imdb_id_from_tmdb(tmdb_id: str) -> str | None:
    """Get IMDB ID from TMDB movie ID."""
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        imdb_id = data.get("imdb_id")
        title = data.get("title")
        year = None
        
        release_date = data.get("release_date")
        if release_date and len(release_date) >= 4:
            year = release_date[:4]
        
        return imdb_id, title, year
    except Exception as e:
        print(f"Error fetching TMDB data: {e}")
        return None, None, None


def get_tvdb_movie_id(title: str, year: str = None) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Search TVDB for movie ID using title and optional year.
    Returns a tuple (tvdb_id, matched_title, matched_year, slug)
    """
    try:
        results = tvdb.search(title, year=year, type="movie", lang="eng")
        
        if not results or len(results) == 0:
            print(f"No TVDB results found for: {title}")
            return None, None, None, None
        
        best_match = None
        
        if year:
            for result in results:
                result_year = result.get('year', '')
                if str(result_year) == str(year):
                    best_match = result
                    break
        
        if not best_match:
            best_match = results[0]
        
        tvdb_id = best_match.get('tvdb_id')
        matched_title = best_match.get('name', title)
        matched_year = best_match.get('year', '')
        slug = best_match.get('slug', str(tvdb_id))
        
        return tvdb_id, matched_title, matched_year, slug
        
    except Exception as e:
        print(f"Error searching TVDB: {e}")
        return None, None, None, None


def generate_xml(tmdb_id: str, imdb_id: str, tvdb_id: str) -> str:
    """Generate MKV global tags XML."""
    # create XML structure
    tags = ET.Element('Tags')
    tag = ET.SubElement(tags, 'Tag')
    
    # TMDB entry
    tmdb_simple = ET.SubElement(tag, 'Simple')
    ET.SubElement(tmdb_simple, 'Name').text = 'TMDB'
    ET.SubElement(tmdb_simple, 'String').text = f'movie/{tmdb_id}'
    
    # IMDB entry
    if imdb_id:
        imdb_simple = ET.SubElement(tag, 'Simple')
        ET.SubElement(imdb_simple, 'Name').text = 'IMDB'
        ET.SubElement(imdb_simple, 'String').text = imdb_id
    
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
    
    imdb_id, title, tmdb_year = get_imdb_id_from_tmdb(tmdb_id)
    
    if not title:
        print("Error: Could not fetch movie data from TMDB")
        sys.exit(1)
    
    print(f"\nTMDB match: [sea_green2]{title}[/sea_green2] ({tmdb_year})")
    print(f"TMDB ID: [orange1]{tmdb_id}[/orange1]")
    print(f"TMDB URL: [dodger_blue1]https://www.themoviedb.org/movie/{tmdb_id}[/dodger_blue1]")
    if imdb_id:
        print(f"\nIMDB ID: [orange1]{imdb_id}[/orange1]")
        print(f"IMDB URL: [dodger_blue1]https://www.imdb.com/title/{imdb_id}[/dodger_blue1]")
    else:
        print("Warning: IMDB ID not found")
    
    tvdb_id, matched_title, matched_year, slug = get_tvdb_movie_id(title, tmdb_year)
    
    if tvdb_id:
        print(f"\nTVDB match: [sea_green2]{matched_title}[/sea_green2] ({matched_year})")
        print(f"TVDB ID: [orange1]{tvdb_id}[/orange1]")
        print(f"TVDB URL: [dodger_blue1]https://www.thetvdb.com/movies/{slug}[/dodger_blue1]")
    else:
        print("\nTVDB ID not found")
    
    xml_content = generate_xml(tmdb_id, imdb_id, tvdb_id)
    
    # save to file
    output_filename = f".global_tags_{title}_{tmdb_year}.xml"
    output_title = sanitize(output_title)
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    
    print(f"\nXML file saved as: [dodger_blue1]{output_filename}[/dodger_blue1]\n")
    print(xml_content)


if __name__ == "__main__":
    main()
