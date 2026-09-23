// ==UserScript==
// @name         Movie/TV Database Circus
// @namespace    http://tampermonkey.net/
// @version      1.94
// @description  Add extenal ID buttons to tmdb.org, imdb.com, and thetvdb.com
// @author       SiUwU squashski
// @match        https://www.imdb.com/title/*
// @match        https://www.themoviedb.org/movie/*
// @match        https://www.themoviedb.org/tv/*
// @match        https://www.thetvdb.com/movies/*
// @match        https://www.thetvdb.com/series/*
// @grant        GM_xmlhttpRequest
// @connect      api.themoviedb.org
// @connect      api4.thetvdb.com
// @connect      lostimg.cc
// ==/UserScript==

(function () {
    'use strict';

    const TMDB_API_KEY = ''; // Your TMDb API key
    const TVDB_API_KEY = ''; // Your TVDB API key
    const TVDB_PIN = ''; // Your TVDB pin if you set one, otherwise leave blank

    // Logo sources for each button. Primary: Simple Icons (https://simpleicons.org),
    // a free CDN of brand-colored SVG logos. Fallback: that site's own favicon via
    // Google's favicon service, which works for essentially any domain (used in case
    // a brand isn't in the Simple Icons catalog, e.g. thetvdb.com).
    const LOGO_CONFIG = {
        TMDB: { slug: 'themoviedatabase', domain: 'themoviedb.org', source: null },
        IMDB: { slug: 'imdb', domain: 'imdb.com', source: null },
        TVDB: { slug: 'thetvdb', domain: 'thetvdb.com', source: null },
        LETTERBOXD: { slug: 'letterboxd', domain: 'letterboxd.com', source: null },
        BLURAY: {slug: 'bluray', domain: 'us.blu-raydisc.com', source: 'https://lostimg.cc/43aeTexT.png' },
    };
    const LOGO_HEIGHT = '44px'; // default logo height when no explicit button height is set

    const tmdbButton = document.createElement('button');
    const imdbButton = document.createElement('button');
    const tvdbButton = document.createElement('button');
    const letterboxdButton = document.createElement('button');
    const blurayButton = document.createElement('button');
    styleButton(tmdbButton, 'TMDB');
    styleButton(imdbButton, 'IMDB');
    styleButton(tvdbButton, 'TVDB');
    styleButton(letterboxdButton, 'LETTERBOXD');
    styleButton(blurayButton, 'BLURAY');

    let tvdbToken = null;
    let imdbId = null;
    let tvdbSlug = null;
    let tmdbId = null;

    function styleButton(button, text) {
        // The button itself is now just an invisible, clickable frame around the
        // logo image -- no background, border, padding, or text color like before.
        button.id = text;
        button.title = text; // accessible / hover name, since there's no visible text label
        button.setAttribute('aria-label', text);
        button.style.marginLeft = '10px';
        button.style.padding = '0';
        button.style.background = 'transparent';
        button.style.border = 'none';
        button.style.cursor = 'pointer';
        button.style.verticalAlign = 'middle';
        // Flex-center the logo (or fallback text) within the button's box, and let
        // the image fill whatever height the button ends up with (see applyButtonHeight).
        button.style.display = 'inline-flex';
        button.style.alignItems = 'center';
        button.style.justifyContent = 'center';
        button.style.lineHeight = '0';
        button.style.height = LOGO_HEIGHT; // overridden by applyButtonHeight() where used

        const config = LOGO_CONFIG[text];
        const img = document.createElement('img');
        img.alt = text;
        img.style.height = '100%'; // tracks the button's height, so applyTalapplyButtonHeightlButtons still works
        img.style.width = 'auto';
        img.style.maxWidth = 'none';
        img.style.display = 'block';
        img.style.pointerEvents = 'none'; // clicks still go to the button, not the image
        if (config.source != null) {
            img.src = config.source;
        } else if (button == letterboxdButton || button == imdbButton) {
            img.src = `https://www.google.com/s2/favicons?sz=64&domain=${config.domain}`;
        } else {
            img.src = `https://cdn.simpleicons.org/${config.slug}`;
        }

        let triedFavicon = false;
        img.onerror = () => {
            if (!triedFavicon) {
                // Brand not in the Simple Icons catalog (or CDN hiccup) -- fall back
                // to that site's own favicon, which works for any domain.
                triedFavicon = true;
                img.src = `https://www.google.com/s2/favicons?sz=64&domain=${config.domain}`;
                return;
            }
            // Both sources failed (e.g. offline) -- fall back to a plain text label
            // so the button is still usable instead of blank.
            img.remove();
            button.innerText = text;
            button.style.padding = '5px 10px';
            button.style.backgroundColor = '#16707f';
            button.style.color = '#ffffff';
            button.style.borderRadius = '5px';
            button.style.fontSize = '16px';
        };
        button.appendChild(img);
    }

    function applyButtonHeight(height) {
        tmdbButton.style.height = height;
        imdbButton.style.height = height;
        tvdbButton.style.height = height;
        letterboxdButton.style.height = height;
        blurayButton.style.height = height;
    }

    function fetch(method, url, body = null, headers = {}) {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method,
                url,
                headers: Object.assign(
                    body ? { 'Content-Type': 'application/json' } : {},
                    headers
                ),
                data: body ? JSON.stringify(body) : null,
                onload: (resp) => {
                    if (resp.status >= 200 && resp.status < 300) {
                        try {
                            const parsed = resp.responseText ? JSON.parse(resp.responseText) : null;
                            resolve(parsed);
                        } catch {
                            resolve(null);
                        }
                        return;
                    }
                    let errorMsg = `HTTP ${resp.status}`;
                    try {
                        const errJson = JSON.parse(resp.responseText);
                        if (errJson?.message) errorMsg = errJson.message;
                    } catch {}

                    reject({ error: errorMsg });
                },
                onerror: (err) => reject(err),
                ontimeout: (err) => reject(err),
            });
        });
    }

    async function getTVDBToken(apikey, pin = '') {
        const url = 'https://api4.thetvdb.com/v4/login';
        const body = pin ? { apikey, pin } : { apikey };
        const resp = await fetch('POST', url, body);
        if (resp.error) {
            throw new Error(resp.error);
        }
        const token = resp.data?.token;
        if (!token) throw new Error('No token found in login response');
        return token;
    }

    async function tvdbSearchByRemoteId(remoteid) {
        const encoded = encodeURIComponent(remoteid);
        const url = `https://api4.thetvdb.com/v4/search/remoteid/${encoded}`;
        const resp = await fetch('GET', url, null, { Authorization: `Bearer ${tvdbToken}` });
        if ("error" in resp) throw new Error(resp.error);
        return resp.data;
    }

    async function getTVDBSlug() {
        const hostname = window.location.hostname;
        if (hostname === 'www.themoviedb.org' || hostname === 'www.imdb.com') {
            const results = await tvdbSearchByRemoteId(imdbId, tvdbToken);
            let slug = null;
            let contentType = null;
            try {
                slug = results[0].movie.slug;
                contentType = "movies"
            } catch (error) {
                try {
                    slug = results[0].series.slug;
                    contentType = "series"
                } catch (error) {return null;}
            }
            return `${contentType}/${slug}`;
        } else if (hostname === 'www.thetvdb.com') {
            return window.location.pathname.slice(1);
        }
        return null;
    }

    async function getIMDbID() {
        const hostname = window.location.hostname;
        if (hostname === 'www.themoviedb.org') {
            const urlParts = window.location.pathname.split('/');
            const contentType = urlParts[1]; // "movie" or "tv"
            const contentId = urlParts[2].match(/^\d+/)[0]; // extract only the numeric ID
            const url = `https://api.themoviedb.org/3/${contentType}/${contentId}/external_ids?api_key=${TMDB_API_KEY}`;
            const data = await fetch('GET', url, null);
            if ("error" in data) throw new Error(data.error);
            return data.imdb_id;
        } else if (hostname === 'www.thetvdb.com') {
            const contentType = window.location.href.includes("/series/") ? "series" : "movies";
            const items = document.querySelectorAll("li.list-group-item");
            let contentId = null;
            for (const li of items) {
                const label = li.querySelector("strong")?.textContent.trim();
                if (label === "TheTVDB.com Series ID" || label === "TheTVDB.com Movie ID") {
                    contentId = li.querySelector("span")?.textContent.trim();
                    break;
                }
            }

            const url = `https://api4.thetvdb.com/v4/${contentType}/${contentId}/extended?meta=translations`;
            const data = await fetch('GET', url, null, { Authorization: `Bearer ${tvdbToken}` });
            if ("error" in data) throw new Error(data.error);
            const remoteIds = data.data?.remoteIds;
            const imdbId = remoteIds.find(r =>
                                          (r.sourceName ?? "").toLowerCase().includes("imdb")
                                         )?.id ?? null;
            if (imdbId == null) throw new Error("Could not find IMDb ID in tvdb response.");
            return imdbId;
        } else if (hostname === 'www.imdb.com') {
            return window.location.pathname.split('/')[2];
        }
        return null;
    }

    async function getTMDbID() {
        const hostname = window.location.hostname;
        if (hostname === 'www.themoviedb.org') {
            const urlParts = window.location.pathname.split('/');
            return urlParts[2].match(/^\d+/)[0]; // extract only the numeric ID
        } else if (hostname === 'www.thetvdb.com' || hostname === 'www.imdb.com') {
            const url = `https://api.themoviedb.org/3/find/${imdbId}?api_key=${TMDB_API_KEY}&external_source=imdb_id`;
            const data = await fetch('GET', url, null);
            if ("error" in data) throw new Error(data.error);
            if (hostname === "www.imdb.com") {
                let contentType = null;
                const script = document.querySelector('script[type="application/ld+json"]');
                try {
                    const data = JSON.parse(script.textContent);
                    contentType = data['@type']
                } catch (e) {
                    // Ignore invalid JSON-LD
                }

                switch (contentType) {
                    case "Movie":
                        return data.movie_results[0].id ?? null;
                    case "TVSeries":
                        return data.tv_results[0].id ?? null;
                    case "TVEpisode":
                        return data.tv_episode_results[0].show_id ?? null;
                    default:
                        return null;
                }
            } else if (hostname === 'www.thetvdb.com') {
                const tvdbUrl = window.location.href;
                let contentType = tvdbUrl.includes("/movies/") ? "Movie" : "TVSeries";
                switch (contentType) {
                    case "Movie":
                        return data.movie_results[0].id ?? null;
                    case "TVSeries":
                        return data.tv_results[0].id ?? null;
                    default:
                        return null;
                }
            }
        }
        return null;
    }

    function displayStreamingProviders(data) {
        if (!data.results) return;
        let visible = true;

        const btn = document.createElement('button');
        btn.innerText = 'Hide Providers';
        btn.style.cssText = `
            position: fixed;
            top: calc(50vh - 300px - 30px);
            right: 20px;
            padding: 4px 10px;
            font-size: 13px;
            background: #16707f;
            color: #fff;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            z-index: 1001;`;

        const panel = document.createElement('div');
        panel.style.cssText = `
            position: fixed;
            top: calc(50vh - 300px);
            right: 20px;
            width: 400px;
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #ddd;
            background: #f9f9f9;
            z-index: 1000;`;

        const table = document.createElement('table');
        table.style.cssText = `width: 100%; border-collapse: collapse; font-family: Helvetica, sans-serif;`;

        const header = table.insertRow();
        header.style.background = '#f2f2f2';
        header.style.fontWeight = 'bold';
        header.style.color = '#000000';

        const ccHeader = header.insertCell()
        ccHeader.innerText = 'CC';
        ccHeader.style.padding = '6px';
        const cHeader = header.insertCell();
        cHeader.innerText = 'Country';
        cHeader.style.padding = '6px';
        const pHeader = header.insertCell();
        pHeader.innerText = 'Providers';
        pHeader.style.padding = '6px';

        const countryNames = new Intl.DisplayNames(['en'], { type: 'region' });

        for (const [code, info] of Object.entries(data.results)) {
            const row = table.insertRow();
            row.style.border = '1px solid #ddd';
            const c1 = row.insertCell();
            const c2 = row.insertCell();
            const c3 = row.insertCell();
            c1.innerText = code;
            c2.innerText = countryNames.of(code) || 'Unknown';

            let list = [];
            if (info.flatrate) list.push(...info.flatrate.map(p => `${p.provider_name} (Flatrate)`));
            if (info.ads) list.push(...info.ads.map(p => `${p.provider_name} (Ads)`));
            if (info.rent) list.push(...info.rent.map(p => `${p.provider_name} (Rent)`));
            if (info.buy) list.push(...info.buy.map(p => `${p.provider_name} (Buy)`));
            c3.innerText = list.length ? list.join(', ') : 'N/A';

            for (const cell of row.cells) {
                cell.style.cssText = `padding: 6px; background: #f9f9f9; color: #000; border: 1px solid #ddd;`;
            }
        }

        panel.appendChild(table);

        btn.onclick = () => {
            visible = !visible;
            panel.style.display = visible ? 'block' : 'none';
            btn.innerText = visible ? 'Hide Providers' : 'Show Providers';
        };

        document.body.appendChild(btn);
        document.body.appendChild(panel);
    }

    (async () => {
        // fetch tvdb token if we are not on tvdb.com
        tvdbToken = await getTVDBToken(TVDB_API_KEY);
        imdbId = await getIMDbID();
        tvdbSlug = await getTVDBSlug();
        tmdbId = await getTMDbID();
        let contentType = null;

        letterboxdButton.onclick = () => window.open(`https://letterboxd.com/tmdb/${tmdbId}/`, '_blank');
        blurayButton.onclick = () => window.open(`https://www.blu-ray.com/search/?quicksearch=1&quicksearch_keyword=${imdbId}&section=theatrical`, `_blank`);

        // IMDb
        if (window.location.hostname === 'www.imdb.com') {
            if (imdbId) {
                const titleElement = document.querySelector('h1[data-testid="hero__pageTitle"]') || document.querySelector('h1');
                if (titleElement) {
                    const script = document.querySelector('script[type="application/ld+json"]');
                    try {
                        const data = JSON.parse(script.textContent);
                        contentType = data['@type']
                    } catch (e) {
                        // Ignore invalid JSON-LD
                    }
                    contentType = contentType === "Movie" ? "movie" : "tv";
                    tmdbButton.onclick = () => window.open(`https://www.themoviedb.org/${contentType}/${tmdbId}`, '_blank');
                    tvdbButton.onclick = () => window.open(`https://www.thetvdb.com/${tvdbSlug}`, '_blank');

                    const wrapper = document.createElement('div');
                    wrapper.style.display = 'flex';
                    wrapper.style.alignItems = 'center';
                    wrapper.style.flexWrap = 'wrap';

                    const buttonGroup = document.createElement('div');
                    buttonGroup.style.display = 'flex';
                    buttonGroup.style.alignItems = 'center';
                    buttonGroup.style.flexShrink = '0'; // never let the group itself get squished/split
                    if (tmdbId) buttonGroup.appendChild(tmdbButton);
                    if (tvdbSlug) buttonGroup.appendChild(tvdbButton);
                    if (tmdbId && contentType === "movie") buttonGroup.appendChild(letterboxdButton);
                    if (imdbId) buttonGroup.appendChild(blurayButton);

                    const parent = titleElement.parentNode;
                    parent.insertBefore(wrapper, titleElement);
                    wrapper.appendChild(titleElement);
                    wrapper.appendChild(buttonGroup);
//                     const parent = titleElement.parentNode;
//                     parent.insertBefore(wrapper, titleElement);
//                     wrapper.appendChild(titleElement);
//                     if (tmdbId) wrapper.appendChild(tmdbButton);
//                     if (tvdbSlug) wrapper.appendChild(tvdbButton);
//                     if (tmdbId && contentType === "movie") wrapper.appendChild(letterboxdButton);
//                     if (imdbId) wrapper.appendChild(blurayButton);
                    applyButtonHeight(window.getComputedStyle(titleElement).lineHeight - 10)
                }
            }
        }

        // TMDb
        if (window.location.hostname === 'www.themoviedb.org') {
            contentType = window.location.href.includes("/tv/") ? "tv" : "movie";
            const titleElement = document.querySelector('span[class="tag release_date"]')
            if (titleElement) {
                imdbButton.onclick = () => window.open(`https://www.imdb.com/title/${imdbId}/`, '_blank');
                tvdbButton.onclick = () => window.open(`https://www.thetvdb.com/${tvdbSlug}`, '_blank');
                if (imdbId) titleElement.parentNode.insertBefore(blurayButton, titleElement.nextSibling);
                if (contentType === "movie") titleElement.parentNode.insertBefore(letterboxdButton, titleElement.nextSibling);
                if (tvdbSlug) titleElement.parentNode.insertBefore(tvdbButton, titleElement.nextSibling);
                if (imdbId) titleElement.parentNode.insertBefore(imdbButton, titleElement.nextSibling);
                const span = document.createElement("span");
                span.textContent = ` [${tmdbId}]`;
                span.style.fontSize = "22px";
                span.style.paddingLeft = "8px";
                span.style.paddingRight = "8px";
                if (tmdbId) titleElement.parentNode.insertBefore(span, titleElement.nextSibling);
                applyButtonHeight(window.getComputedStyle(titleElement).lineHeight);
            }
        }

        // TVDb
        if (window.location.hostname === 'www.thetvdb.com') {
            contentType = window.location.href.includes("/series/") ? "tv" : "movie";
            imdbButton.onclick = () => window.open(`https://www.imdb.com/title/${imdbId}/`, '_blank');
            tmdbButton.onclick = () => window.open(`https://www.themoviedb.org/${contentType}/${tmdbId}`, '_blank');

            const titleElement = document.querySelector('h1');
            if (titleElement) {
                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';

                const parent = titleElement.parentNode;
                parent.insertBefore(wrapper, titleElement);
                wrapper.appendChild(titleElement);
                if (imdbId) wrapper.appendChild(imdbButton);
                if (tmdbId) wrapper.appendChild(tmdbButton);
                if (tmdbId && contentType === "movie") wrapper.appendChild(letterboxdButton);
                if (imdbId) wrapper.appendChild(blurayButton);
                applyButtonHeight(window.getComputedStyle(titleElement).lineHeight);
            }
        }

        // fetch and display streaming providers
        if (contentType) {
            const providerApiUrl = `https://api.themoviedb.org/3/${contentType}/${tmdbId}/watch/providers?api_key=${TMDB_API_KEY}`;
            const providerData = await fetch('GET', providerApiUrl, null);
            displayStreamingProviders(providerData);
        }
    })();
})();
