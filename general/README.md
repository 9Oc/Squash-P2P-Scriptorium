# General Scripts
<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/general/globaltags.py">globaltags</a>
<a href="https://www.python.org/downloads/release/python-3100/"><img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python 3.10+"></a></h2>

`globaltags.py` generates an mkv XML tag file containing the TMDB, IMDB, and TVDB2 IDs for a given TMDB ID.

Dependencies:

`pip install tvdb_v4_official requests rich`

Note that you must provide your TMDB and TVDB API keys at the top of the script.
```
TMDB_API_KEY = "TMDB_API_KEY" # <-- your TMDB api key here
TVDB_API_KEY = "TVDB_API_KEY" # <-- your TVDB api key here
```

<hr>

### Usage
A TMDB ID is the only argument accepted.

`globaltags.py <TMDB ID>`
<hr>
Example output:

```
globaltags.py 9005
Fetching data for TMDB ID: 9005

TMDB match: The Ice Harvest (2005)
TMDB ID: 9005
TMDB URL: https://www.themoviedb.org/movie/9005

IMDB ID: tt0400525
IMDB URL: https://www.imdb.com/title/tt0400525

TVDB match: The Ice Harvest (2005)
TVDB ID: 8208
TVDB URL: https://www.thetvdb.com/movies/the-ice-harvest

XML file saved as: .global_tags_The Ice Harvest_2005.xml

<?xml version="1.0" encoding="UTF-8"?>
<Tags>
  <Tag>
    <Simple>
      <Name>TMDB</Name>
      <String>movie/9005</String>
    </Simple>
    <Simple>
      <Name>IMDB</Name>
      <String>tt0400525</String>
    </Simple>
    <Simple>
      <Name>TVDB2</Name>
      <String>movies/8208</String>
    </Simple>
  </Tag>
</Tags>
```

<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/general/ptp_bbcomp.py">ptp_bbcomp</a>
<a href="https://www.python.org/downloads/release/python-360/"><img src="https://img.shields.io/badge/Python-3.06%2B-brightgreen" alt="Python 3.06+"></a></h2>

`ptp_bbcomp.py` uploads folders of images to ptpimg and generates comparison bbcode that will work for PTP and UNIT3D torrent descriptions.

Dependencies:

`pip install requests`

Note that you must enter your ptpimg API key at the top of the script.
```
PTPIMG_API_KEY = "PTPIMG_API_KEY" # <-- your ptpimg api key here
```
<hr>

### Usage
A path to a folder is the only accepted argument.

`ptp_bbcomp.py "\path\to\folder"`

Given a path to a folder, all sub-folders containing images will be treated as a separate source for the comparisons. The name of each sub-folder is the name that will be assigned to the source in the comparison bbcode.

<hr>

Example input/output

`ptp_bbcomp.py "G:\.vsjet\vspreview\BZKNEAURQVCN2AAD"`

Folder structure
```
G:\.vsjet\vspreview\BZKNEAURQVCN2AAD
├── Ascot Elite Home Entertainment GER
│   ├── image1.png
│   ├── image2.png
│   └── image3.png
├── Lionsgate GBR-USA
│   ├── image1.png
│   ├── image2.png
│   └── image3.png
└── Metropolitan FRA
    ├── image1.png
    ├── image2.png
    └── image3.png
```

Output from the script
```
G:\.vsjet\vspreview\BZKNEAURQVCN2AAD
└── comparison_bbcode.txt

[comparison=Ascot Elite Home Entertainment GER,Lionsgate GBR-USA,Metropolitan FRA]https://ptpimg.me/65a8k1.png
https://ptpimg.me/lw310c.png
https://ptpimg.me/5idg9s.png
https://ptpimg.me/v10j15.png
https://ptpimg.me/4g2817.png
https://ptpimg.me/m94viz.png
https://ptpimg.me/9q0qkg.png
https://ptpimg.me/242928.png
https://ptpimg.me/9k103c.png[/comparison]
```

<h2><a href="https://github.com/9Oc/Squash-P2P-Scriptorium/blob/main/general/slowpic2hdb.js">slowpic2hdb</a></h2>

`slowpic2hdb.js` adds an HDB Rehost button to slowpics comparison collections to re-host the images on HDB and output the comparison bbcode in the format that HDB accepts.
<hr>

### Usage
Simply add the script to your Tampermonkey dashboard.

If you are already logged in with cookies to HDB in your browser, the re-hosting will work automatically. If not, fill out your HDB username and passkey in the script:
```
const HDB_USERNAME = ""; // leave blank if using cookie-login
const HDB_PASSKEY = ""; // leave blank if using cookie-login
```
