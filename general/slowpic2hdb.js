// ==UserScript==
// @name        SlowPics → HDBits Rehost
// @namespace   Violentmonkey Scripts
// @match       https://slow.pics/c/*
// @grant       GM.xmlHttpRequest
// @grant       GM.setClipboard
// @connect     img.hdbits.org
// @connect     slow.pics
// @version     1.1
// @author      xzin
// @description Rehost slow.pics comparisons to an HDBits gallery
// ==/UserScript==

(async function () {
    "use strict";

    // ------------------------------------------------------------
    // CONFIG
    // ------------------------------------------------------------

    const HDB_USERNAME = ""; // leave blank if using cookie-login
    const HDB_PASSKEY = ""; // leave blank if using cookie-login
    const DEBUG = false;

    const HDB_UPLOAD_ENDPOINT = "https://img.hdbits.org/upload_api.php";
    const ALLOWED_WIDTHS = [100,150,200,250,300,350];

    // ------------------------------------------------------------
    // Generic Helpers
    // ------------------------------------------------------------

    const log = (...args) => console.log("[HDB REHOST]", ...args);
    const debug = (...args) => DEBUG && console.log("[HDB REHOST]", ...args)

    function http(opts) {
        return new Promise((resolve, reject) => {
            GM.xmlHttpRequest({
                ...opts,
                onload: res => resolve(res),
                onerror: err => reject(err)
            });
        });
    }

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    // ------------------------------------------------------------
    // slowpic stuff
    // ------------------------------------------------------------

    function getSources() {
        let sources = [];
        unsafeWindow.collection.comparisons[0].images.forEach((image) => {
            sources.push(image.name.replace(/^\([BIP]\) /, ''));
        });
        return sources;
    }

    function getImages() {
        let images = [];
        unsafeWindow.collection.comparisons.forEach((comparison) => {
            comparison.images.forEach((image) => {
                images.push(`https://i.slow.pics/${image.publicFileName}`);
            });
        });
        return images;
    }

    async function getBlobs() {
        const images = getImages()
        const blobs = await Promise.all(
            images.map(url => fetchBlob(url))
        );
        return blobs;
    }

    // ------------------------------------------------------------
    // Image Conversion
    // ------------------------------------------------------------

    function convertWebPToPNG(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => {
                const img = new Image();
                img.onload = () => {
                    const canvas = document.createElement("canvas");
                    canvas.width = img.width;
                    canvas.height = img.height;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0);
                    canvas.toBlob(
                        pngBlob => resolve(pngBlob),
                        "image/png"
                    );
                };
                img.onerror = reject;
                img.src = e.target.result;
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    async function fetchBlob(url) {
        debug("Fetching image:", url);

        const res = await http({
            method: "GET",
            url,
            responseType: "blob"
        });

        if (res.status !== 200) throw new Error(`HTTP error ${res.status}`);

        const blob = res.response;

        if (blob.type === "image/webp") {
            debug("Converting WEBP → PNG");
            return await convertWebPToPNG(blob);
        }

        return blob;
    }

    // ------------------------------------------------------------
    // Thumbnail width logic
    // ------------------------------------------------------------

    function chooseThumbsize(sourceCount) {
        const ideal = Math.floor(900 / sourceCount);
        let chosen = 100;

        for (const w of ALLOWED_WIDTHS) {
            if (w <= ideal) chosen = w;
        }

        log(`Ideal width = ${ideal}, chosen = w${chosen}`);
        return `w${chosen}`;
    }

    // ------------------------------------------------------------
    // Upload images into a new gallery
    // ------------------------------------------------------------
    async function uploadAllToHDB(blobs, galleryName, thumbsize) {
        const SOURCES = getSources();
        const BATCH_SIZE = SOURCES.length; // Upload {SOURCES.length} images at a time
        let batches = [];

        // split blobs into batches to avoid 413 payload too large response from HDB
        for (let i = 0; i < blobs.length; i += BATCH_SIZE) {
            batches.push(blobs. slice(i, i + BATCH_SIZE));
        }

        log(`Uploading ${blobs.length} images in ${batches.length} batches`);

        let allBBCode = [];
        let comparisonHeader = "[center]" + getSources().join(" | ") + "[/center]";
        allBBCode.push(comparisonHeader); // comparison header with source names

        for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
            const batch = batches[batchIndex];
            const form = new FormData();

            if (HDB_USERNAME) form.append("username", HDB_USERNAME);
            if (HDB_PASSKEY) form.append("passkey", HDB_PASSKEY);
            let batchGalleryName = galleryName + " comparison " + (batchIndex + 1);
            form.append("galleryoption", "1"); // create new gallery
            form.append("galleryname", batchGalleryName); // set gallery name
            form.append("thumbsize", thumbsize); // set thumbnail image size

            // add blobs from this batch
            batch.forEach((blob, i) => {
                form.append("images_files[]", blob, `image${i}.png`);
            });

            log(`Uploading batch ${batchIndex + 1}/${batches.length} (${batch.length} images)...`);
            btn.textContent = `Uploading comparison ${batchIndex + 1}/${batches.length}... `;

            // send request to HDB
            const res = await http({
                method: "POST",
                url: HDB_UPLOAD_ENDPOINT,
                data: form
            });

            if (res.status === 413) {
                throw new Error(`413 Payload Too Large:  Try reducing BATCH_SIZE (currently ${BATCH_SIZE})`);
            }

            if (res.status === 403) {
                throw new Error("403 Forbidden: Make sure you're logged into HDBits or provide valid credentials");
            }

            if (res.status !== 200) {
                throw new Error(`Upload failed: ${res.status} - ${res.responseText}`);
            }

            const responseText = res.responseText;
            debug(`Batch ${batchIndex + 1} response: `, responseText);
            // add center bbcode to first and last batch
            if (batchIndex == 0) {
                allBBCode.push("[center]" + responseText);
            } else if (batchIndex == batches.length -1) {
                allBBCode.push(responseText + "[/center]");
            } else {
                allBBCode.push(responseText);
            }

            // small delay between batches to be nice to the server
            if (batchIndex < batches.length - 1) {
                await sleep(1000);
            }
        }

        // Return all BBCode combined
        return allBBCode.join("\n");
    }

    // ------------------------------------------------------------
    // UI Button
    // ------------------------------------------------------------

    const btn = document.createElement("button");
    btn.textContent = "HDB Rehost";
    btn.className = "btn btn-success mr-2";
    btn.type = "button";

    const navItems = document.querySelectorAll(".nav-item");
    navItems[navItems.length - 2].append(btn);

    btn.addEventListener("click", run);

    // ------------------------------------------------------------
    // Main Function
    // ------------------------------------------------------------

    async function run() {
        try {
            btn.textContent = "Processing…";
            // check if collection exists
            if (! unsafeWindow.collection || ! unsafeWindow.collection.comparisons) {
                throw new Error("Could not find collection data on page");
            }

            const thumbsize = chooseThumbsize(getSources().length);

            const galleryName = document.title.trim().replace(" | Slowpoke Pics", "");
            log("Gallery name:", galleryName);

            // Parallel download + convert
            const blobs = await getBlobs();

            // Upload all at once
            const reply = await uploadAllToHDB(blobs, galleryName, thumbsize);

            log("BBCode copied to clipboard:", reply);
            GM.setClipboard(reply); // copy bbcode to clipboard

            if (DEBUG) {
                confirm("BBCode generated:\n\n" + reply);
            }

            btn.textContent = "HDB Rehost";

        } catch (err) {
            console.error(err);
            alert("Error: " + err.message);
            btn.textContent = "Error";
        }
    }

})();
