// ==UserScript==
// @name           Disney+ Subtitle Downloader
// @description    Download subtitles from Disney+
// @version        1.7
// @author         squasher
// @license        MIT; https://opensource.org/licenses/MIT
// @match          https://www.disneyplus.com/*
// @grant          unsafeWindow
// @require        https://cdn.jsdelivr.net/npm/jszip@3.5.0/dist/jszip.min.js
// @require        https://cdn.jsdelivr.net/npm/file-saver@2.0.2/dist/FileSaver.min.js
// @run-at         document-start
// ==/UserScript==

(function(open, send) {
    'use strict';
    const DEBUG = false;
    const log = (msg) => { console.log(`[DSNP Subtitle Downloader] ${msg}`); }
    const debug = (msg) => { if (DEBUG) console.log(`[DSNP DEBUG] ${msg}`); }

    function init() {
        debug("Init document state: " + document.readyState);
        if (document.readyState == "complete" || document.readyState == "loaded") {
            start();
            debug("Document already loaded");
        } else {
            if (window.addEventListener) {
                window.addEventListener("load", start, false);
                debug("Onload method: addEventListener");
            } else if (window.attachEvent) {
                window.attachEvent("onload", start);
                debug("Onload method: attachEvent");
            } else {
                window.onload = start;
                debug("Onload method: onload");
            }
        }
        document.listen = true;
    }

    function stripURL(url) {
        if (!url) return url;
        // remove fragment
        url = url.split('#')[0];
        // remove query params
        url = url.split('?')[0];
        // remove disney signed token prefix
        url = url.replace(/https:\/\/[^\/]+\/dvt\d+=.*?\//, '');
        return url;
    }

    function start() {
        debug("start");
        if (typeof document.initaudio !== "undefined") document.initaudio();
        if (typeof document.initsub !== "undefined") document.initsub();
        listensend();
        document.handleinterval = setInterval(buttonhandle,100);
        if (typeof window._dsnpFetchPatched === 'undefined') {
            window._dsnpFetchPatched = true;
            const origFetch = window.fetch.bind(window);
            window.fetch = function(resource, init) {
                // resolve resource to string URL
                let url;
                try { url = (typeof resource === 'string') ? resource : resource.url; } catch(e) { url = '';}
                return origFetch(resource, init).then(function(response) {
                    try {
                        if (response && response.ok && url) {
                            let norm = stripURL(url);
                            if (norm.match(/\.m3u8(\?.*)?$/i) || norm.match(/\.vtt(\?.*)?$/i)) {
                                // clone & read text asynchronously, cache it
                                response.clone().text().then(function(text) {
                                    window._dsnpCache[norm] = text;
                                    debug("Cached fetch response for: " + norm);
                                }).catch(function(err){ debug("fetch clone text err: " + err); });
                            }
                        }
                    } catch (ex) { debug("fetch patch error: " + ex); }
                    return response;
                });
            };
        }
    }

    if (!document.listen) init();

    document.initsub = function() {
        debug("initsub");
        if (typeof window._dsnpCache === 'undefined') window._dsnpCache = {};
        document.disneyAuthToken = "";
        document.langs = [];
        document.segments = "";
        document.wait = false;
        document.m3u8found = false;
        document.fetchingyear = false;
        document.url = null;
        document.oldlocation = null;
        document.dmcContentId = "";
        document.filename = "";
        document.releaseyear = "";
        document.episode = "";
        document.downloadall = false;
        document.downloadid = 0;
        document.waitsub = false;
        document.segid = 0;
        document.vttlist = [];

        // Inject a floating "DL Subs" button in the top-right corner
        if (!document.getElementById('dsnp-dl-btn')) {
            var btn = document.createElement('button');
            btn.id = 'dsnp-dl-btn';
            btn.textContent = 'DL Subs';
            btn.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999;' +
                'background:#0063e5;color:#fff;border:none;border-radius:6px;' +
                'padding:8px 14px;font-size:13px;font-weight:bold;cursor:pointer;opacity:0.85;';
            btn.addEventListener('mouseenter', function() { this.style.opacity = '1'; });
            btn.addEventListener('mouseleave', function() { this.style.opacity = '0.85'; });
            btn.addEventListener('click', function() {
                if (!document.langs || document.langs.length === 0) {
                    alert('No subtitles found yet. Start playing the video first.');
                    return;
                }
                document.zip = new JSZip();
                document.downloadall = true;
                downloadnext();
            });
            document.body.appendChild(btn);
        }

        // prepare retry map for 403 retries
        if (typeof window._dsnpRetries === 'undefined') window._dsnpRetries = {};
    };

    // catch M3U8 files
    function listensend() {
        debug("listensend");
        var newOpen = function(...args) {
            this._dsnpUrl = (args.length >= 2) ? args[1] : "";
            if (!document.m3u8found && args.length >= 2) {
                if (args[1].indexOf(".m3u8") > 0 && document.url != args[1]) {
                    // m3u8 url
                    debug("m3u8 found: " + args[1]);
                    document.url = args[1];
                    document.langs = [];
                    document.baseurl = document.url.substring(0, document.url.lastIndexOf('/') + 1);
                    document.m3u8found = true;
                    getpagecontent(m3u8loaded, document.url);
                }
            }
            // hook setRequestHeader on this instance
            // captures disney auth token for metadata api request
            var origSetReqHeader = this.setRequestHeader.bind(this);
            this.setRequestHeader = function(header, value) {
                if (header.toLowerCase() === 'authorization'
                    && value != null
                    && value.indexOf('Bearer ') === 0
                    && args.length >= 2
                    && args[1].indexOf('disney.api.edge.bamgrid.com') > -1
                    && document.disneyAuthToken !== value) {
                    document.disneyAuthToken = value;
                    if (document.disneyAuthToken.length > 500) {
                        log(`Disney auth token captured: ${value.slice(0, 50)}`);
                        fetchMetadataFromAPI();
                    }
                }
                origSetReqHeader(header, value);
            };
            open.call(this,...args);
        }

        var newSend = function(...args) {
            var xhrUrl = this._dsnpUrl || "";
            // capture auth token from Disney API requests
            if (xhrUrl.indexOf("disney.api.edge.bamgrid.com") > -1) {
                var headerValue = this.getRequestHeader && this.getRequestHeader("authorization");
                // getRequestHeader may not exist on all browsers, so also try the
                // getAllResponseHeaders fallback after the request completes.
                // instead, we hook setRequestHeader on this instance
            }
            if (args[0] && args[0].match && args[0].match(/globalization/)) {
                this.addEventListener('readystatechange', function(e) {
                    try {
                        document.globalization = JSON.parse(e.target.response).data.globalization;
                    } catch(e) {}
                }, false);
            }
            // check for SPA navigation changes to fetch metadata as a fallback
            this.addEventListener('readystatechange', function(e) {
                parseMetadata(e);
            }, false);
            send.call(this,...args);

            this.addEventListener('load', function(e) {
                try {
                    var url = this._dsnpUrl || "";
                    if (!url) return;
                    // normalize to remove fragment
                    var norm = stripURL(url);
                    if (norm.match(/\.m3u8(\?.*)?$/i) || norm.match(/\.vtt(\?.*)?$/i)) {
                        // only cache successful responses
                        if (this.status === 200 && typeof this.responseText === 'string') {
                            window._dsnpCache[norm] = this.responseText;
                            debug("Cached response for: " + norm);
                        }
                    }
                } catch (ex) { debug("Cache save failed: " + ex); }
            }, false);
        }

        if (typeof unsafeWindow !== "undefined") {
            debug("Window state: unsafe");
            var define = Object.defineProperty;
            define(unsafeWindow.XMLHttpRequest.prototype, "open", {value: exportFunction(newOpen, window)});
            define(unsafeWindow.XMLHttpRequest.prototype, "send", {value: exportFunction(newSend, window)});
        } else {
            debug("Window state: safe");
            XMLHttpRequest.prototype.open = newOpen;
            XMLHttpRequest.prototype.send = newSend;
        }
    }

    // parse the title/year metadata from SPA navigation events
    function parseMetadata(e) {
        if (e.target.readyState === 4 && e.target.status === 200) {
            try {
                var text = e.target.responseText;
                if (text && text.indexOf('releaseYearRange') > -1) {
                    window.__last_release_api_response = text;
                    var resp = JSON.parse(text);
                    var contentTitle = resp?.data?.page?.visuals?.title;
                    var year = resp?.data?.page?.visuals?.metastringParts?.releaseYearRange?.startYear;
                    if (contentTitle) {
                        contentTitle = contentTitle.replaceAll(" Of ", " of ");
                        contentTitle = contentTitle.replaceAll(" The ", " the ");
                        document.filename = contentTitle;
                        log("Parsed content title from SPA nav: " + contentTitle);
                    }
                    if (year) {
                        document.releaseyear = year;
                        log("Parsed release year from SPA nav: " + year);
                    }
                }
            } catch(ex) { debug("Metadata parsing failed: " + ex) }
        }
    }

    // fetch the content metadata from the disney api if we have a valid token
    function fetchMetadataFromAPI() {
        if (document.releaseyear && document.filename) return;

        // extract entity ID from /play/UUID
        var match = window.location.pathname.match(/\/(?:play|browse)\/(?:entity-)?([a-f0-9-]+)/i);
        if (!match) {
            debug("Could not find match in window location: " + window.location.pathname);
            return;
        }

        if (!document.disneyAuthToken) {
            debug("fetchMetadataFromAPI() called with no auth token, skipping request attempt");
            return;
        }

        // the real Disney auth token is ~4000+ chars
        // short tokens (< 500 chars) are pre-flight tokens and should be filtered
        if (document.disneyAuthToken.length < 500) {
            debug("Waiting for full auth token (current length: "
                  + (document.disneyAuthToken ? document.disneyAuthToken.length : 0) + ")");
            return;
        }

        var entityId = match[1];
        var url = "https://disney.api.edge.bamgrid.com/explore/v1.13/page/entity-" + entityId + "?disableSmartFocus=true&enhancedContainersLimit=15&limit=15";

        console.log("Fetching content details from API: " + url);

        // set http request headers
        var http = new XMLHttpRequest();
        http.open("GET", url, true);
        http.setRequestHeader("accept", "application/json");
        http.setRequestHeader("authorization", document.disneyAuthToken);
        http.setRequestHeader("x-bamsdk-client-id", "disney-svod-3d9324fc");
        http.setRequestHeader("x-bamsdk-platform", "javascript/windows/chrome");
        http.setRequestHeader("x-dss-edge-accept", "vnd.dss.edge+json; version=2");

        // parse json response
        http.onloadend = function() {
            if (http.readyState == 4 && http.status == 200) {
                try {
                    var resp = JSON.parse(http.responseText);
                    //console.log(resp);
                    var contentTitle = resp?.data?.page?.visuals?.title;
                    var year = resp?.data?.page?.visuals?.metastringParts?.releaseYearRange?.startYear;
                    if (contentTitle) {
                        contentTitle = contentTitle.replaceAll(" Of ", " of ");
                        contentTitle = contentTitle.replaceAll(" The ", " the ");
                        document.filename = contentTitle;
                        log("Parsed content title from API: " + contentTitle);
                    }
                    if (year) {
                        document.releaseyear = year;
                        log("Parsed release year from API: " + year);
                    }
                } catch(e) {
                    console.log("Failed to parse API response: " + e);
                }
            } else {
                console.log("API request failed: " + http.status);
            }
        };
        http.send();
    }

    function m3u8loaded(response) {
        debug("m3u8loaded");
        if (typeof document.m3u8sub !== "undefined") document.m3u8sub(response);
        if (typeof document.m3u8audio !== "undefined") document.m3u8audio(response);
    }

    document.m3u8sub = function(response) {
        var regexpm3u8 =/^#.{0,}GROUP-ID="sub-main".{0,}\.m3u8"$/gm;
        var regexpvtt = /^[\w-_\/]{0,}MAIN[\w-_\/]{0,}.vtt(?:\?.*)?$/gm;
        var regexpvtt2 = /^[\w-_\/]{0,}.vtt(?:\?.*)?$/gm;

        if (response.indexOf('#EXT-X-INDEPENDENT-SEGMENTS') > 0) {
            // sub infos
            var lines = response.match(regexpm3u8);
            lines.forEach(function(line) {
                var lang = linetoarray(line);
                lang.LOCALIZED = document.globalization.timedText.find(t => t.language == lang.LANGUAGE);
                document.langs.push(lang);
                debug("Sub found : "+lang.NAME);
            });
        } else if (response.indexOf('.vtt') > 0) {
            debug("vtt found");
            var lines = response.match(regexpvtt);
            if (!lines) lines = response.match(regexpvtt2);
            if (lines) {
                lines.forEach(function(line) {
                    var lineTrim = line.trim();

                    // build full URL for vtt
                    // use the line as-is if it's absolute otherwise resolve relative to the playlist's URI
                    var vttUrl = "";
                    try {
                        if (/^https?:\/\//i.test(lineTrim)) {
                            vttUrl = lineTrim;
                        } else {
                            // determine base folder for language URIs (preserve any querystring/tokens that were part of the m3u8 language URI)
                            var uri = document.langs[document.langid].URI || "";
                            var uriBase = document.baseurl;
                            if (uri.indexOf('/') > -1) {
                                uriBase = document.baseurl + uri.substring(0, uri.lastIndexOf('/') + 1);
                            }
                            // use URL() to resolve relative paths properly and keep query strings
                            vttUrl = new URL(lineTrim, uriBase).toString();
                        }
                    } catch (ex) {
                        debug("Failed to resolve VTT URL, fallback to naive concatenation");
                        var url = document.baseurl;
                        var uri = document.langs[document.langid].URI;
                        url += uri.substring(0, 2);
                        if (line.indexOf("/") < 0) url += uri.substring(2, uri.lastIndexOf("/") + 1);
                        url += line;
                        vttUrl = url;
                    }

                    document.vttlist.push(vttUrl);
                });
            } else {
                alert("Unable to parse the m3u8 file, please report a bug for this video.");
            }

            if (document.vttlist.length > 0) {
                getSegments();
            } else {
                alert("Unknown error, please report a bug for this video.");
            }
        }
    }

    function vttloaded(response) {
        debug("vttloaded");
        // save segment
        document.segments += response.substring(response.indexOf("-->") - 13);
        document.segid++;
        if (document.segid < document.vttlist.length) {
            getSegments();
        } else if (document.segments.length > 0) {
            // export segments
            exportfile(document.segments);
            document.segments = "";
            document.vttlist = [];
            document.segid = 0;
        } else {
            alert("Unknown error, please report a bug for this video.");
        }
    }

    function linetoarray(line) {
        var result = [];
        var values = line.split(',');
        values.forEach(function(value) {
            var data = value.replace(/\r\n|\r|\n/g,'').split('=');
            if (data.length > 1) {
                var key = data[0];
                var content = data[1].replace(/"/g,'');
                result[key] = content;
            }
        });
        return result;
    }

    function buttonhandle() {
        var buttons = document.getElementsByClassName("control-icon-btn");
        if (buttons.length > 0) {
            // movie
            var titleElem = document.getElementsByClassName("title-field")[0];
            if (titleElem && titleElem.innerText && titleElem.innerText.trim().length > 0) {
                console.log(titleElem.innerText.trim());
                document.filename = titleElem.innerText.trim();
            }
            // episode
            var epElem = document.getElementsByClassName("subtitle-field")[0];
            if (epElem && epElem.innerText && epElem.innerText.trim().length > 0) document.episode = epElem.innerText.trim();
        }

        // show button only on /play/ pages
        var dlBtn = document.getElementById('dsnp-dl-btn');
        if (dlBtn) {
            dlBtn.style.display = /\/play\//.test(window.location.pathname) ? 'block' : 'none';
            if (!document.langs || document.langs.length === 0) {
                dlBtn.textContent = 'Waiting for subtitles to load...';
                dlBtn.disabled = true;
                dlBtn.style.background = '#555';
                dlBtn.style.cursor = 'not-allowed';
            } else {
                if (document.downloadid < 1) {
                    dlBtn.textContent = 'DL Subs';
                    dlBtn.disabled = false;
                    dlBtn.style.background = '#3EB489';
                    dlBtn.style.cursor = 'pointer';
                }
            }
        }

        if (document.oldlocation != window.location.href && document.oldlocation != null) {
            // location changed
            document.m3u8found = false;
            document.langs = [];
            document.audios = [];
        }

        document.oldlocation = window.location.href;
    }

    function downloadnext() {
        document.downloadid++;
        const button = document.getElementById('dsnp-dl-btn');
        if (document.downloadid < document.langs.length) {
            if (button) button.textContent = `${document.downloadid}/${document.langs.length}`;
            debug("Downloading " + Math.round((document.downloadid / document.langs.length) * 100) + "%");
            download(document.langs[document.downloadid].NAME, false, false);
        } else {
            debug("Subs downloaded");
            clearInterval(document.downloadinterval);
            if (button) button.textContent = "Saving zip";
            debug("Save zip");
            document.zip.generateAsync({type:"blob"}).then(function(content) {
                var output = document.filename;
                if (document.releaseyear) output += "." + document.releaseyear;
                if (document.episode != "") output+= "." + document.episode.replace(':','');
                output += ".DSNP.WEB"
                saveAs(content, output + ".zip");
            });
            if (button) button.textContent = "DL Subs";
            document.downloadid = 0;
        }
    }

    function download(langname, withForced = true, localized = true) {
        if (!document.wait) {
            debug("Download sub : " + langname);
            var language;
            var count = 0;
            document.forced = false;
            document.langs.forEach(function(lang) {
                if (lang.NAME == langname || (localized && lang.LOCALIZED && Object.values(lang.LOCALIZED.renditions).includes(langname) && lang.FORCED == "NO")) {
                    language = lang.LANGUAGE;
                    document.langid = count;
                    getpagecontent(m3u8loaded,document.baseurl + lang.URI);
                    document.wait = true;
                }
                count++;
            });
            if (withForced) {
                count = 0;
                var subid;
                document.langs.forEach(function(lang) {
                    if (lang.LANGUAGE == language && lang.NAME != langname && lang.FORCED == "YES") {
                        subid=count;
                        document.waitsub = true;
                        document.waitInterval = setInterval(function () {
                            if (!document.wait) {
                                debug("Download forced : " + langname);
                                clearInterval(document.waitInterval);
                                document.langid = subid;
                                getpagecontent(m3u8loaded,document.baseurl + lang.URI);
                                document.wait = true;
                            }
                        }, 10);
                    }
                    count++;
                });
            }

            if (count == 0) alert("An error has occurred, please reload the page.");
        }
    }

    function getSegments() {
        debug("Downloading all " + document.vttlist.length + " segments in parallel");

        var total = document.vttlist.length;
        var segments = new Array(total);
        var completed = 0;

        document.vttlist.forEach(function(url, index) {
            getpagecontent(function(response) {
                debug("Segment " + index + "/" + (total - 1) + " downloaded");
                segments[index] = response.substring(response.indexOf("-->") - 13);
                completed++;

                if (completed === total) {
                    debug("All segments downloaded");
                    var merged = segments.join('');
                    if (merged.length > 0) {
                        merged = merged.replace(/WEBVTT\s*STYLE\s*::cue\(\)\s*\{[\s\S]*?\}\s*/g, '');
                        exportfile(merged);
                    } else {
                        alert("Unknown error, please report this on github for this video");
                    }
                    document.segments = "";
                    document.vttlist = [];
                    document.segid = 0;
                }
            }, url);
        });
    }

    function sanitizeString(input) {
        if (input == null) return '';
        const s = String(input);
        // remove commas and Windows-invalid characters
        let out = s.replace(/[:\\?\/\*"<>\|,]/g, '');
        // replace white space with '.' characters
        out = out.replace(/[ _]+/g, '.');
        // collapse multiple '.' characters into one
        out = out.replace(/\.{2,}/g, '.');
        out = out.replace(".-.", ".");
        out = out.replace(",.", ".");
        return out;
    }

    function exportfile(text) {
        debug("exportfile");
        var output = document.filename;
        if (document.releaseyear) output += "." + document.releaseyear;
        if (document.episode != "") output += "." + document.episode.replace(':','');
        output += ".DSNP.WEB"

        let lang = document.langs[document.langid].LANGUAGE;
        if (lang == "en") lang = "en-US";
        if (lang == "zh-HK") lang = "zh-Hant-HK";
        output += "." + lang;
        console.log(document.langs[document.langid]);

        if (document.langs[document.langid].FORCED == "YES") {
            output += "[forced]";
            document.waitsub = false;
        }
        if (document.langs[document.langid].NAME.includes("[CC]")) output += "[sdh]";

        output += ".vtt";
        output = sanitizeString(output);

        if (document.downloadall) {
            debug("Add to zip");
            document.zip.file(output, text);
            document.downloadinterval = setTimeout(function () {
                document.wait = false;
                if (!document.waitsub) downloadnext();
            }, 10);
        } else {
            debug("Save sub");
            var hiddenElement = document.createElement('a');

            hiddenElement.href = 'data:attachment/text,' + encodeURI(text).replace(/#/g, '%23');
            hiddenElement.target = '_blank';
            hiddenElement.download = output;
            hiddenElement.click();
            setTimeout(function () { document.wait = false; }, 50);
        }
    }

    function getpagecontent(callback, url) {
        debug("getpagecontent requested: " + url);
        var norm = stripURL(url);

        // try cache first
        // returns true and fires callback if found
        function checkCache() {
            try {
                if (window._dsnpCache && window._dsnpCache[norm]) {
                    debug("Returning cached content for: " + norm);
                    callback(window._dsnpCache[norm]);
                    return true;
                }
                for (var k in window._dsnpCache) {
                    if (!window._dsnpCache.hasOwnProperty(k)) continue;
                    if (k.indexOf(norm) > -1 || norm.indexOf(k) > -1) {
                        debug("Found near-match cache key: " + k + " for " + norm);
                        callback(window._dsnpCache[k]);
                        return true;
                    }
                }
            } catch (ex) { debug("cache lookup failed: " + ex); }
            return false;
        }

        if (checkCache()) return;

        // not in cache, fetch directly
        fetchViaXHR(callback, url);
    }

    function fetchViaXHR(callback, url) {
        debug("fetchViaXHR: " + url);
        var http = new XMLHttpRequest();
        http.open("GET", url, true);
        //http.withCredentials = true;

        // only attach the Authorization header for Disney API endpoints
        // sending it to CDN URLs (media.dssott.com etc.) triggers a CORS preflight
        // that fails on NA/BR regions, the UK and some other CDN's happen to allow it
        if (document.disneyAuthToken && document.disneyAuthToken.length > 500
            && url.indexOf('disney.api.edge.bamgrid.com') > -1) {
            try { http.setRequestHeader("authorization", document.disneyAuthToken); } catch (ex) { debug("Failed to set Authorization header: " + ex); }
        }

        http.onloadend = function() {
            if (http.readyState == 4 && http.status == 200) {
                try { window._dsnpCache[stripURL(url)] = http.responseText; } catch(e){}
                callback(http.responseText);
            } else if (http.status === 404) {
                debug("Not found (404) for " + url);
                callback("");
            } else if (http.status === 403) {
                debug("Forbidden (403) for " + url);
                callback("");
            } else if (http.status === 0) {
                // status 0 = CORS block or network error, cannot retry
                debug("XHR blocked (CORS or network) for " + url);
                callback("");
            } else {
                debug("Unknown error (" + http.status + "), retrying: " + url);
                setTimeout(function () { fetchViaXHR(callback, url); }, 100);
            }
        };
        http.send();
    }

    String.prototype.lpad = function(padString, length) {
        var str = this;
        while (str.length < length) {
            str = padString + str;
        }
        return str;
    }
})(XMLHttpRequest.prototype.open, XMLHttpRequest.prototype.send);
