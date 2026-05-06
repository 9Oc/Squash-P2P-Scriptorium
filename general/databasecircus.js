// ==UserScript==
// @name         Movie/TV Database Circus
// @namespace    http://tampermonkey.net/
// @version      1.5
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
// ==/UserScript==

(function () {
    'use strict';

    const TMDB_API_KEY = ''; // Your TMDb API key
    const TVDB_API_KEY = ''; // Your TVDB API key
    const TVDB_PIN = ''; // Your TVDB pin if you set one, otherwise leave blank

    const tmdbButton = document.createElement('button');
    const imdbButton = document.createElement('button');
    const tvdbButton = document.createElement('button');
    styleButton(tmdbButton, 'TMDB');
    styleButton(imdbButton, 'IMDB');
    styleButton(tvdbButton, 'TVDB');

    let tvdbToken = null;
    let imdbId = null;
    let tvdbSlug = null;
    let tmdbId = null;

    function styleButton(button, text) {
        button.innerText = text;
        button.id = text;
        button.style.marginLeft = '10px';
        button.style.padding = '5px 10px';
        button.style.backgroundColor = '#16707f';
        button.style.color = '#ffffff';
        button.style.border = 'none';
        button.style.borderRadius = '5px';
        button.style.cursor = 'pointer';
        button.style.fontSize = '16px';
        button.style.verticalAlign = 'middle';
    }

    function applyTallButtons(height) {
        imdbButton.style.height = height;
        tvdbButton.style.height = height;
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
                slug = results[0].series.slug;
                contentType = "series"
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
            try {
                return data.movie_results[0].id;
            } catch (error) {
                return data.tv_results[0].id;
            }
        }
        return null;
    }

    function displayStreamingProviders(data) {
        if (data.results) {
            const container = document.createElement('div');
            container.style.position = 'fixed';
            container.style.top = '50%';
            container.style.right = '20px';
            container.style.transform = 'translateY(-50%)';
            container.style.width = '350px';
            container.style.padding = '10px';
            container.style.border = '1px solid #ddd';
            container.style.backgroundColor = '#f9f9f9';
            container.style.maxHeight = '50vh';
            container.style.overflowY = 'auto';
            container.style.zIndex = '1000';

            const table = document.createElement('table');
            table.style.width = '100%';
            table.style.border = '1px solid #ddd';
            table.style.borderCollapse = 'collapse';
            table.style.fontFamily = "Helvetica, sans-serif";

            const header = table.insertRow();
            header.style.backgroundColor = '#f2f2f2';
            header.style.fontWeight = 'bold';
            header.style.color = '#000000';
            header.insertCell().innerText = 'CC';
            header.insertCell().innerText = 'Country';
            header.insertCell().innerText = 'Providers';

            const countryNames = new Intl.DisplayNames(['en'], { type: 'region' });

            for (const [countryCode, providerInfo] of Object.entries(data.results)) {
                const row = table.insertRow();
                row.style.border = '1px solid #ddd';

                const countryCodeCell = row.insertCell();
                countryCodeCell.innerText = countryCode;
                countryCodeCell.style.padding = '8px';

                const countryNameCell = row.insertCell();
                countryNameCell.innerText = countryNames.of(countryCode) || 'Unknown';
                countryNameCell.style.padding = '8px';

                const providersCell = row.insertCell();
                providersCell.style.padding = '8px';
                let providerDetails = [];

                if (providerInfo.flatrate) {
                    providerDetails.push(
                        ...providerInfo.flatrate.map(
                            provider => `${provider.provider_name} (Flatrate)`
                        )
                    );
                }
                if (providerInfo.ads) {
                    providerDetails.push(
                        ...providerInfo.ads.map(
                            provider => `${provider.provider_name} (Ads)`
                        )
                    );
                }
                if (providerInfo.rent) {
                    providerDetails.push(
                        ...providerInfo.rent.map(
                            provider => `${provider.provider_name} (Rent)`
                        )
                    );
                }
                if (providerInfo.buy) {
                    providerDetails.push(
                        ...providerInfo.buy.map(
                            provider => `${provider.provider_name} (Buy)`
                        )
                    );
                }

                providersCell.innerText = providerDetails.length > 0 ? providerDetails.join(', ') : 'N/A';
                for (const cell of row.cells) {
                    cell.style.backgroundColor = '#f9f9f9';
                    cell.style.color = '#000000';
                }
            }

            container.appendChild(table);
            document.body.appendChild(container);
        } else {
            console.log('No streaming provider information available for this title.');
        }
    }

    (async () => {
        // fetch tvdb token if we are not on tvdb.com
        tvdbToken = await getTVDBToken(TVDB_API_KEY);
        imdbId = await getIMDbID();
        tvdbSlug = await getTVDBSlug();
        tmdbId = await getTMDbID();
        let contentType = null;

        // IMDb
        if (window.location.hostname === 'www.imdb.com') {
            if (imdbId) {
                const titleElement = document.querySelector('h1[data-testid="hero__pageTitle"]') || document.querySelector('h1');
                if (titleElement) {
                    const episodeElement = document.querySelector('h3.ipc-title__text');
                    if (episodeElement) {
                        contentType = episodeElement.textContent.toLowerCase().includes("episodes") ? "tv" : "movie";
                        tmdbButton.onclick = () => window.open(`https://www.themoviedb.org/${contentType}/${tmdbId}`, '_blank');
                        tvdbButton.onclick = () => window.open(`https://www.thetvdb.com/${tvdbSlug}`, '_blank');

                        const wrapper = document.createElement('div');
                        wrapper.style.display = 'flex';
                        wrapper.style.alignItems = 'center';

                        const parent = titleElement.parentNode;
                        parent.insertBefore(wrapper, titleElement);
                        wrapper.appendChild(titleElement);
                        wrapper.appendChild(tmdbButton);
                        wrapper.appendChild(tvdbButton);
                    }
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
                titleElement.parentNode.insertBefore(tvdbButton, titleElement.nextSibling);
                titleElement.parentNode.insertBefore(imdbButton, titleElement.nextSibling);
                applyTallButtons(window.getComputedStyle(titleElement).lineHeight);
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
                wrapper.appendChild(imdbButton);
                wrapper.appendChild(tmdbButton);
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
