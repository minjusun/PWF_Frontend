// The Mapbox token is no longer stored in this file. map_api.py hands it out, but only
// while this month's map loads are under the limit (MAP_LOAD_LIMIT in map_api.py).
const MAP_LOAD_URL = 'api/map-load';

// Cleaned, live Supabase sightings served by map_api.py (same cleaning as the dashboard).
const POINTS_URL = 'api/points.geojson';

// true: visitors press "View the map" first, so bots and quick visits don't use a map load.
// false: the map opens straight away (still counted and capped).
const REQUIRE_CLICK_TO_LOAD = false;

function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('collapsed');
}

function setDimension(mode) {
    if (!map) return; // map not opened yet
    document.getElementById('flat-btn').classList.toggle('active', mode === 'flat');
    document.getElementById('dimensional-btn').classList.toggle('active', mode === 'dimensional');
    map.setProjection(mode === 'flat' ? 'mercator' : 'globe');
    // Spinning only makes sense on the globe.
    if (mode === 'flat') stopGlobeSpin();
}

// Makes user-typed text (notes, boat names) safe to put inside HTML.
function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// ==== Globe spin (Spin / Pause button next to the year dropdown) ====
const SPIN_DEG_PER_SEC = 3;      // how fast the globe turns (~2 min per full turn)
const SPIN_START_MAX_ZOOM = 4;   // zoomed in closer than this? ease out first
const SPIN_START_ZOOM = 2.5;

const SPIN_ICON_PATH = 'M12 5V2L8 6l4 4V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z';
const SPIN_PAUSE_ICON_PATH = 'M6 5h4v14H6zm8 0h4v14h-4z';

let isSpinning = false;
let spinRafId = null;
let spinLastTime = null;

function setSpinButtonState(spinning) {
    const btn = document.getElementById('spin-btn');
    const icon = document.getElementById('spin-icon');
    const label = document.getElementById('spin-label');
    if (!btn || !icon || !label) return;
    btn.classList.toggle('active', spinning);
    btn.setAttribute('aria-label', spinning ? 'Pause globe spin' : 'Spin globe');
    label.textContent = spinning ? 'Pause' : 'Spin';
    icon.innerHTML = `<path fill="currentColor" d="${spinning ? SPIN_PAUSE_ICON_PATH : SPIN_ICON_PATH}" />`;
}

function spinFrame(now) {
    if (!isSpinning) return;
    if (spinLastTime === null) spinLastTime = now;
    const dt = Math.min(now - spinLastTime, 100); // no big jump after a background tab
    spinLastTime = now;


    if (!map.isZooming()) {
        // Turn slower the further in you are
        const zoomFactor = Math.pow(2, Math.max(0, map.getZoom() - SPIN_START_ZOOM));
        const center = map.getCenter();
        center.lng -= (SPIN_DEG_PER_SEC / zoomFactor) * dt / 1000; // west -> east, like the real Earth
        map.jumpTo({ center });
    }

    spinRafId = requestAnimationFrame(spinFrame);
}

function beginSpinLoop() {
    if (!isSpinning) return; // paused while zooming out
    spinLastTime = null;
    spinRafId = requestAnimationFrame(spinFrame);
}

function startGlobeSpin() {
    if (isSpinning) return;
    isSpinning = true;
    setSpinButtonState(true);

    // Spinning needs the globe view.
    if (map.getProjection().name !== 'globe') setDimension('dimensional');

    if (map.getZoom() > SPIN_START_MAX_ZOOM) {
        map.easeTo({ zoom: SPIN_START_ZOOM, duration: 1500 });
        map.once('moveend', beginSpinLoop);
    } else {
        beginSpinLoop();
    }
}

function stopGlobeSpin() {
    if (!isSpinning) return;
    isSpinning = false;
    if (spinRafId !== null) {
        cancelAnimationFrame(spinRafId);
        spinRafId = null;
    }
    setSpinButtonState(false);
}

function toggleGlobeSpin() {
    if (!map) return; // map not opened yet
    if (isSpinning) stopGlobeSpin();
    else startGlobeSpin();
}

// ==== Year dropdown (Flat/Dimensional toggle's neighbor) ====

function closeYearDropdown() {
    const menu = document.getElementById('year-dropdown-menu');
    if (menu) menu.classList.remove('open');
}

(function setupYearDropdownToggle() {
    const btn = document.getElementById('year-dropdown-btn');
    const menu = document.getElementById('year-dropdown-menu');
    const wrapper = document.getElementById('year-dropdown-toggle');

    if (!btn || !menu || !wrapper) {
        console.error('Year dropdown elements missing from the page -- check the IDs year-dropdown-btn / year-dropdown-menu / year-dropdown-toggle in webmap.html.');
        return;
    }

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) {
            closeYearDropdown();
        }
    });
})();

// ==== Shared row/column helpers ====
function normalizeKeys(row) {
    const map = {};
    for (const key in row) {
        map[key.trim().toLowerCase()] = row[key];
    }
    return map;
}

function pickField(map, candidates) {
    for (const c of candidates) {
        const val = map[c];
        if (val !== undefined && val !== null && String(val).trim() !== '') {
            return val;
        }
    }
    return undefined;
}

// Splits a status string like "Least Concern (Critically Endangered: Yangtze
// River, China)" into its main status
function splitStatus(status) {
    const str = String(status);
    const match = str.match(/^([^(]*)(\(.*\))?\s*$/);
    return {
        main: match ? match[1].trim() : str,
        paren: match && match[2] ? match[2] : ''
    };
}

// ==== Species images ====
// Images live in Frontend/imgs, named exactly as <SPECIES_CODE>.png (e.g. FKW.png
// for false killer whale)
const IMAGES_BASE_PATH = 'imgs/';

function getSpeciesImagePath(code) {
    if (!code) return null;
    return `${IMAGES_BASE_PATH}${code}.png`;
}

// ==== Species list, taxonomy grouping, and per-species color assignment ====
let speciesRows = [];
let speciesColorMap = {};
let speciesTaxonomyMap = {};
let speciesNameMap = {};
let taxonomyShapeMap = {};
let speciesRecordCountMap = {};

const GRAY_FALLBACK = '#999999';

const COLOR_PALETTE = [
    '#51bbd6', '#e07a5f', '#81b29a', '#f2cc8f', '#9c89b8',
    '#f4845f', '#3d5a80', '#98c1d9', '#e56b6f', '#6d597a',
    '#b56576', '#84a59d'
];

const SHAPE_CYCLE = ['circle', 'triangle', 'square'];

const TAXONOMY_PRIORITY = ['whale', 'dolphin', 'porpoise'];

const SMALL_GROUP_RECORD_THRESHOLD = 8;

function taxonomyPriority(taxonomy) {
    const lower = String(taxonomy).toLowerCase();
    for (let i = 0; i < TAXONOMY_PRIORITY.length; i++) {
        if (lower.includes(TAXONOMY_PRIORITY[i])) return i;
    }
    return TAXONOMY_PRIORITY.length;
}

function sortTaxonomies(taxonomies) {
    return Array.from(taxonomies).sort((a, b) => {
        const pa = taxonomyPriority(a);
        const pb = taxonomyPriority(b);
        if (pa !== pb) return pa - pb;
        return a.localeCompare(b);
    });
}

function getSpeciesCode(row) {
    const map = normalizeKeys(row);
    return pickField(map, ['code', 'species_code', 'sp_code', 'abbreviation', 'abbr']);
}

function getSpeciesTaxonomy(row) {
    const map = normalizeKeys(row);
    return pickField(map, ['taxonomy', 'group', 'class', 'family', 'order', 'category', 'type']) ?? 'Unclassified';
}

function buildSpeciesTaxonomyMap(rows) {
    const map = {};
    for (const row of rows) {
        const code = getSpeciesCode(row);
        if (code) map[code] = getSpeciesTaxonomy(row);
    }
    return map;
}

function buildSpeciesNameMap(rows) {
    const map = {};
    for (const row of rows) {
        const code = getSpeciesCode(row);
        if (!code) continue;
        const normalized = normalizeKeys(row);
        const name = pickField(normalized, [
            'species_name', 'species', 'name', 'common_name', 'common name', 'species name'
        ]);
        if (name) map[code] = name;
    }
    return map;
}

// Shapes are pinned directly to taxonomy category: dolphin=triangle,
// porpoise=square, and everything else (whale sub-groups, plus the
// catch-all "other" bucket) is circle.
const FIXED_SHAPE_BY_PRIORITY = ['circle', 'triangle', 'square']; // matches TAXONOMY_PRIORITY: whale, dolphin, porpoise

function buildTaxonomyShapeMap(rows) {
    const taxonomies = sortTaxonomies(new Set(rows.map(getSpeciesTaxonomy)));
    const map = {};
    for (const taxonomy of taxonomies) {
        const priority = taxonomyPriority(taxonomy);
        map[taxonomy] = FIXED_SHAPE_BY_PRIORITY[priority] ?? 'circle';
    }
    return map;
}

function buildSpeciesColorMap(rows, recordCountMap) {
    const map = {};
    let paletteIndex = 0;

    const groups = new Map();
    for (const row of rows) {
        const code = getSpeciesCode(row);
        if (!code) continue;
        const taxonomy = getSpeciesTaxonomy(row);
        if (!groups.has(taxonomy)) groups.set(taxonomy, []);
        groups.get(taxonomy).push(code);
    }

    for (const [, codes] of groups.entries()) {
        const sorted = codes.slice().sort(
            (a, b) => (recordCountMap[b] ?? 0) - (recordCountMap[a] ?? 0)
        );

        const totalRecordsInGroup = sorted.reduce((sum, c) => sum + (recordCountMap[c] ?? 0), 0);

        const coloredSet = new Set(
            totalRecordsInGroup < SMALL_GROUP_RECORD_THRESHOLD
                ? sorted
                : sorted.slice(0, Math.ceil(sorted.length / 2))
        );

        for (const code of sorted) {
            if (coloredSet.has(code)) {
                map[code] = COLOR_PALETTE[paletteIndex % COLOR_PALETTE.length];
                paletteIndex++;
            } else {
                map[code] = GRAY_FALLBACK;
            }
        }
    }

    return map;
}

function hexToRgb(hex) {
    const bigint = parseInt(hex.replace('#', ''), 16);
    return { r: (bigint >> 16) & 255, g: (bigint >> 8) & 255, b: bigint & 255 };
}

function drawSpeciesGlowCanvas(shape, colorHex, size) {
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');

    const cx = size / 2;
    const cy = size / 2;
    const { r, g, b } = hexToRgb(colorHex);
    const haloRadius = size * 0.5;

//color of dot
    ctx.save();
    ctx.beginPath();
    if (shape === 'square') {
        const half = size * 0.42;
        ctx.rect(cx - half, cy - half, half * 2, half * 2);
    } else if (shape === 'triangle') {
        const R = haloRadius;
        for (let i = 0; i < 3; i++) {
            const angle = -Math.PI / 2 + i * (2 * Math.PI / 3);
            const px = cx + R * Math.cos(angle);
            const py = cy + R * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.closePath();
    } else {
        ctx.arc(cx, cy, haloRadius, 0, Math.PI * 2);
    }
    ctx.clip();

    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, haloRadius);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.15, `rgba(${r},${g},${b},1)`);
    gradient.addColorStop(0.5, `rgba(${r},${g},${b},0.55)`);
    gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    ctx.restore();

    // ---- Small hot-white core on top, echoing the same shape ----
    const coreR = size * 0.08;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    if (shape === 'circle') {
        ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
    } else if (shape === 'square') {
        const s = coreR * 1.7;
        ctx.rect(cx - s / 2, cy - s / 2, s, s);
    } else if (shape === 'triangle') {
        ctx.moveTo(cx, cy - coreR);
        ctx.lineTo(cx - coreR, cy + coreR * 0.8);
        ctx.lineTo(cx + coreR, cy + coreR * 0.8);
        ctx.closePath();
    }
    ctx.fill();

    return canvas;
}

// Used for Mapbox's addImage(), which needs raw pixel data.
function createSpeciesGlowImageData(shape, colorHex, size = 128) {
    const canvas = drawSpeciesGlowCanvas(shape, colorHex, size);
    return canvas.getContext('2d').getImageData(0, 0, size, size);
}

// Used for the sidebar's <img> dots -- same drawing routine as the map
// icons (via drawSpeciesGlowCanvas), just exported as a PNG data URL
// instead of raw ImageData, and cached per species code since the
// sidebar list re-renders on every search keystroke / taxonomy toggle.
const speciesGlowDataUrlCache = {};
function getSpeciesGlowDataUrl(code) {
    if (speciesGlowDataUrlCache[code]) return speciesGlowDataUrlCache[code];

    const taxonomy = speciesTaxonomyMap[code] ?? 'Unclassified';
    const shape = taxonomyShapeMap[taxonomy] ?? 'circle';
    const color = speciesColorMap[code] ?? GRAY_FALLBACK;

    const url = drawSpeciesGlowCanvas(shape, color, 48).toDataURL('image/png');
    speciesGlowDataUrlCache[code] = url;
    return url;
}

function registerSpeciesIcons() {
    for (const code in speciesColorMap) {
        const name = `species-icon-${code}`;
        const taxonomy = speciesTaxonomyMap[code] ?? 'Unclassified';
        const shape = taxonomyShapeMap[taxonomy] ?? 'circle';
        const color = speciesColorMap[code] ?? GRAY_FALLBACK;
        if (!map.hasImage(name)) {
            map.addImage(name, createSpeciesGlowImageData(shape, color));
        }
    }
    if (!map.hasImage('species-icon-fallback')) {
        map.addImage('species-icon-fallback', createSpeciesGlowImageData('circle', GRAY_FALLBACK));
    }
}

function buildIconImageExpression() {
    const expr = ['match', ['get', 'species_code']];
    for (const code in speciesColorMap) {
        expr.push(code, `species-icon-${code}`);
    }
    expr.push('species-icon-fallback');
    return expr;
}

let allSpeciesCodes = new Set();
let activeSpeciesCodes = new Set();
let expandedTaxonomies = new Set();

function shapeClassFor(taxonomy) {
    const shape = taxonomyShapeMap[taxonomy] ?? 'circle';
    return `shape-${shape}`;
}

function renderSpeciesCard(row) {
    const map = normalizeKeys(row);

    const name = pickField(map, [
        'species_name', 'species', 'name', 'common_name', 'common name', 'species name'
    ]) ?? 'Unknown species';

    const code = getSpeciesCode(row);
    const taxonomy = getSpeciesTaxonomy(row);

    const summary = pickField(map, [
        'species_description', 'summary', 'short_description', 'short description'
    ]) ?? '';

    const detail = pickField(map, [
        'description', 'detail', 'details', 'long_description', 'long description',
        'full_description', 'full description', 'notes', 'info', 'information'
    ]) ?? '';

    const imagePath = getSpeciesImagePath(code);

    const population = pickField(map, ['population', 'pop', 'population_estimate']) ?? 'Unknown';
    const length = pickField(map, ['length', 'body_length', 'size']) ?? 'Unknown';
    const status = pickField(map, ['status', 'conservation_status', 'iucn_status']) ?? 'Unknown';

    // Split off any trailing parenthetical regional note (e.g.
    // "(Critically Endangered: Yangtze River, China)") so it can be
    // colored independently of the main status.
    const { main: statusMain, paren: statusParen } = splitStatus(status);
    const isEndangered = statusMain.toLowerCase().includes('endangered');
    const isParenEndangered = statusParen.toLowerCase().includes('endangered');
    const statusDisplayHtml = statusParen
        ? `${statusMain} <span class="${isParenEndangered ? 'status-paren-endangered' : ''}">${statusParen}</span>`
        : statusMain;

    const color = speciesColorMap[code] ?? GRAY_FALLBACK;

    const card = document.createElement('div');
    card.className = 'info-card';
    card.style.setProperty('--species-color', color);
    if (code && activeSpeciesCodes.has(code)) {
        card.classList.add('active-filter');
    }

    card.innerHTML = `
        <h4>
            <span class="species-name" data-role="filter-trigger">
                <img class="species-color-dot" src="${code ? getSpeciesGlowDataUrl(code) : ''}" alt="">
                ${name}
            </span>
            <span class="cli--arrow-menu expand-icon" data-role="expand-trigger"></span>
        </h4>
        <p class="summary" data-role="filter-trigger">${summary}</p>
        <div class="detail">
            ${imagePath ? `<div class="species-detail-image-wrap"><img class="species-detail-image" src="${imagePath}" alt="${name}" loading="lazy" onerror="console.error('Species image failed to load:', this.src)"></div>` : ''}
            <div class="detail-info-box">
                ${detail || '<em>No description available for this row.</em>'}
                <div class="species-stats">
                    <div class="species-stat"><span class="species-stat-label">Population:</span> ${population}</div>
                    <div class="species-stat"><span class="species-stat-label">Length:</span> ${length}</div>
                    <div class="species-stat species-stat-status${isEndangered ? ' status-endangered' : ''}"><span class="species-stat-label">Status:</span> ${statusDisplayHtml}</div>
                </div>
            </div>
        </div>
    `;

    card.querySelectorAll('[data-role="filter-trigger"]').forEach(el => {
        el.addEventListener('click', () => {
            if (code) toggleSpeciesActive(code);
        });
    });
    card.querySelector('[data-role="expand-trigger"]').addEventListener('click', (e) => {
        e.stopPropagation();
        card.classList.toggle('expanded');
    });

    return card;
}

function renderList(rows) {
    const container = document.getElementById('speciesList');
    container.innerHTML = '';

    if (rows.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'no-results';
        empty.textContent = 'No species match your search.';
        container.appendChild(empty);
        return;
    }

    for (const row of rows) {
        container.appendChild(renderSpeciesCard(row));
    }
}

function renderGroupedList(rows) {
    const container = document.getElementById('speciesList');
    container.innerHTML = '';

    if (rows.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'no-results';
        empty.textContent = 'No species loaded.';
        container.appendChild(empty);
        return;
    }

    const groups = new Map();
    for (const row of rows) {
        const taxonomy = getSpeciesTaxonomy(row);
        if (!groups.has(taxonomy)) groups.set(taxonomy, []);
        groups.get(taxonomy).push(row);
    }

    for (const rowsInGroup of groups.values()) {
        rowsInGroup.sort((a, b) => {
            const countA = speciesRecordCountMap[getSpeciesCode(a)] ?? 0;
            const countB = speciesRecordCountMap[getSpeciesCode(b)] ?? 0;
            return countB - countA;
        });
    }

    const sortedTaxonomies = sortTaxonomies(groups.keys());

    for (const taxonomy of sortedTaxonomies) {
        const rowsInGroup = groups.get(taxonomy);
        const isExpanded = expandedTaxonomies.has(taxonomy);

        const group = document.createElement('div');
        group.className = 'taxonomy-group' + (isExpanded ? '' : ' collapsed');

        const header = document.createElement('div');
        header.className = 'taxonomy-header';
        header.innerHTML = `
            <span class="akar-icons--triangle-right-fill"></span>
            <span class="taxonomy-name" style="flex-grow:1">${taxonomy}</span>
        `;
        header.addEventListener('click', () => {
            if (expandedTaxonomies.has(taxonomy)) {
                expandedTaxonomies.delete(taxonomy);
            } else {
                expandedTaxonomies.add(taxonomy);
            }
            populateList();
        });

        const content = document.createElement('div');
        content.className = 'taxonomy-content';
        for (const row of rowsInGroup) {
            content.appendChild(renderSpeciesCard(row));
        }

        group.appendChild(header);
        group.appendChild(content);
        container.appendChild(group);
    }
}

function populateList() {
    const input = document.getElementById('speciesSearch');
    const query = input ? input.value.trim().toLowerCase() : '';

    if (query) {
        const filtered = speciesRows.filter(row => {
            const map = normalizeKeys(row);
            const name = pickField(map, ['species_name', 'species', 'name', 'common_name']) ?? '';
            return String(name).toLowerCase().includes(query);
        });
        renderList(filtered);
    } else {
        renderGroupedList(speciesRows);
    }
}

async function loadSpeciesCSV() {
    return new Promise((resolve, reject) => {
        // Cache-bust with the current timestamp so a browser (or dev server)
        // never serves a stale cached copy of this file after it's edited.
        Papa.parse(`species_description.csv?t=${Date.now()}`, {
            download: true,
            header: true,
            skipEmptyLines: true,
            complete: (results) => {
                speciesRows = results.data;
                speciesTaxonomyMap = buildSpeciesTaxonomyMap(speciesRows);
                speciesNameMap = buildSpeciesNameMap(speciesRows);
                taxonomyShapeMap = buildTaxonomyShapeMap(speciesRows);

                console.log('species_description.csv headers found:', results.meta.fields);
                console.log('First row parsed:', results.data[0]);
                console.log('Species taxonomy map:', speciesTaxonomyMap);
                console.log('Taxonomy shape map:', taxonomyShapeMap);
                resolve();
            },
            error: (err) => {
                console.error('Failed to load species_description.csv:', err);
                reject(err);
            }
        });
    });
}

function setupSpeciesSearch() {
    const input = document.getElementById('speciesSearch');
    input.addEventListener('input', populateList);
}

// ==== Map setup ====
// Created by startMap() once map_api.py says this month's map loads are under the limit.
let map = null;

let pointsGeojson = null;
const MS_PER_DAY = 1000 * 60 * 60 * 24;

const EXCLUDE_SEASON_YEARS = new Set([2011, 2019, 2026]);

const HEATMAP_MAX_ZOOM = 9;

function getFeatureDate(feature) {
    const raw = feature.properties.date || feature.properties.sighting_date_and_time_utc;
    return raw ? new Date(raw) : null;
}

function formatDate(d) {
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function getSeasonYear(d) {
    const month = d.getUTCMonth() + 1;
    return month === 12 ? d.getUTCFullYear() : d.getUTCFullYear() - 1;
}

function toDayMs(d) {
    return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];

function formatMonthYear(bucket) {
    return `${MONTH_NAMES[bucket.month - 1]} ${bucket.year}`;
}

function buildMonthBuckets(minD, maxD) {
    const buckets = [];
    let y = minD.getUTCFullYear();
    let m = minD.getUTCMonth();
    const endY = maxD.getUTCFullYear();
    const endM = maxD.getUTCMonth();

    while (y < endY || (y === endY && m <= endM)) {
        buckets.push({ year: y, month: m + 1 });
        m++;
        if (m > 11) {
            m = 0;
            y++;
        }
    }
    return buckets;
}

let minDate = null;
let maxDate = null;
let totalDays = 0;
let allYearsList = [];
let monthBuckets = [];

let currentYearFilter = 'All';

let sliderMode = 'month';
const yearDayRangeCache = {};

function computeYearDayRange(year) {
    if (yearDayRangeCache[year]) return yearDayRangeCache[year];

    let minMs = null;
    let maxMs = null;
    for (const feature of pointsGeojson.features) {
        if (feature.properties._year !== year) continue;
        const dayMs = feature.properties._day_ms;
        if (dayMs === null || dayMs === undefined) continue;
        if (minMs === null || dayMs < minMs) minMs = dayMs;
        if (maxMs === null || dayMs > maxMs) maxMs = dayMs;
    }

    const range = {
        minMs,
        maxMs,
        totalDays: (minMs !== null) ? Math.round((maxMs - minMs) / MS_PER_DAY) : 0
    };
    yearDayRangeCache[year] = range;
    return range;
}

async function loadPointsAndComputeDateRange() {
    const res = await fetch(POINTS_URL);
    if (!res.ok) {
        const msg = await res.text();
        throw new Error(`Could not load sightings (${res.status}): ${msg}`);
    }
    pointsGeojson = await res.json();

    let minMs = null;
    let maxMs = null;
    const yearsSet = new Set();

    for (const feature of pointsGeojson.features) {
        feature.properties._taxonomy = speciesTaxonomyMap[feature.properties.species_code] ?? 'Unclassified';

        const code = feature.properties.species_code;
        if (code) {
            speciesRecordCountMap[code] = (speciesRecordCountMap[code] ?? 0) + 1;
        }

        const d = getFeatureDate(feature);
        if (!d || isNaN(d)) {
            feature.properties._day_ms = null;
            feature.properties._ts_ms = null;
            feature.properties._year = null;
            feature.properties._month = null;
            continue;
        }

        if (EXCLUDE_SEASON_YEARS.has(getSeasonYear(d))) {
            feature.properties._day_ms = null;
            feature.properties._ts_ms = null;
            feature.properties._year = null;
            feature.properties._month = null;
            continue;
        }

        const dayMs = toDayMs(d);
        feature.properties._day_ms = dayMs;
        feature.properties._ts_ms = d.getTime(); // exact sighting time, used by the timelapse
        feature.properties._year = d.getUTCFullYear();
        feature.properties._month = d.getUTCMonth() + 1;
        yearsSet.add(feature.properties._year);

        if (minMs === null || dayMs < minMs) minMs = dayMs;
        if (maxMs === null || dayMs > maxMs) maxMs = dayMs;
    }

    allYearsList = Array.from(yearsSet).sort((a, b) => a - b);

    if (minMs !== null) {
        minDate = new Date(minMs);
        maxDate = new Date(maxMs);
        totalDays = Math.round((maxMs - minMs) / MS_PER_DAY);
        monthBuckets = buildMonthBuckets(minDate, maxDate);

        for (const feature of pointsGeojson.features) {
            feature.properties._day_index = (feature.properties._day_ms !== null && feature.properties._day_ms !== undefined)
                ? Math.round((feature.properties._day_ms - minMs) / MS_PER_DAY)
                : null;
        }
    }
}

function buildCombinedFilter() {
    const slider = document.getElementById('timeSlider');
    const index = parseInt(slider.value, 10);

    let baseFilter;
    if (sliderMode === 'month') {
        const bucket = monthBuckets[index];
        baseFilter = bucket
            ? ['all', ['==', ['get', '_year'], bucket.year], ['==', ['get', '_month'], bucket.month]]
            : ['==', ['get', '_year'], -1];
    } else {
        const range = computeYearDayRange(currentYearFilter);
        baseFilter = (range.minMs !== null)
            ? ['==', ['get', '_day_ms'], range.minMs + index * MS_PER_DAY]
            : ['==', ['get', '_year'], -1];
    }

    const speciesPart = buildSpeciesFilterPart();
    return speciesPart ? ['all', baseFilter, speciesPart] : baseFilter;
}

// Returns the species part of the filter, or null when every species is shown.
function buildSpeciesFilterPart() {
    if (activeSpeciesCodes.size >= allSpeciesCodes.size) return null;
    return ['in', ['get', 'species_code'], ['literal', Array.from(activeSpeciesCodes)]];
}

function updateMapFilter() {
    if (!map) return;

    if (timelapseActive) {
        renderTimelapseFrame();
        return;
    }
    const filter = buildCombinedFilter();
    if (map.getLayer('point-layer')) {
        map.setFilter('point-layer', filter);
    }
    if (map.getLayer('heatmap-layer')) {
        map.setFilter('heatmap-layer', filter);
    }
}

function toggleSpeciesActive(code) {
    if (activeSpeciesCodes.has(code)) {
        activeSpeciesCodes.delete(code);
    } else {
        activeSpeciesCodes.add(code);
    }

    populateList();

    document.getElementById('clearSpeciesFilter').style.display =
        (activeSpeciesCodes.size < allSpeciesCodes.size) ? 'inline-block' : 'none';

    updateMapFilter();
}

function clearSpeciesFilter() {
    activeSpeciesCodes = new Set(allSpeciesCodes);
    populateList();
    document.getElementById('clearSpeciesFilter').style.display = 'none';
    updateMapFilter();
}

const GRID_MIN_ZOOM = 10;
const GRID_CELL_KM = 1;
const KM_PER_DEGREE_LAT = 111.32;

function buildGridGeoJSON() {
    const bounds = map.getBounds();
    const south = bounds.getSouth();
    const north = bounds.getNorth();
    const west = bounds.getWest();
    const east = bounds.getEast();

    const centerLat = (south + north) / 2;
    const kmPerDegreeLon = KM_PER_DEGREE_LAT * Math.cos(centerLat * Math.PI / 180);

    const latStepDeg = GRID_CELL_KM / KM_PER_DEGREE_LAT;
    const lonStepDeg = GRID_CELL_KM / Math.max(kmPerDegreeLon, 0.0001);

    const features = [];

    for (let lat = Math.floor(south / latStepDeg) * latStepDeg; lat <= north; lat += latStepDeg) {
        features.push({
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: [[west, lat], [east, lat]] },
            properties: {}
        });
    }

    for (let lon = Math.floor(west / lonStepDeg) * lonStepDeg; lon <= east; lon += lonStepDeg) {
        features.push({
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: [[lon, south], [lon, north]] },
            properties: {}
        });
    }

    return { type: 'FeatureCollection', features };
}

function updateGrid() {
    const source = map.getSource('grid-source');
    if (!source) return;

    if (map.getZoom() < GRID_MIN_ZOOM) {
        // Skip redundant updates (the spin moves the map every frame).
        if (!gridIsEmpty) {
            source.setData({ type: 'FeatureCollection', features: [] });
            gridIsEmpty = true;
        }
        return;
    }

    source.setData(buildGridGeoJSON());
    gridIsEmpty = false;
}

let gridIsEmpty = false;

let gridMoveListenerAttached = false;

function setupGrid() {
    if (!map.getSource('grid-source')) {
        map.addSource('grid-source', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] }
        });
    }
    if (!map.getLayer('grid-layer')) {
        map.addLayer({
            id: 'grid-layer',
            type: 'line',
            source: 'grid-source',
            paint: {
                'line-color': 'rgba(255, 255, 255, 0.25)',
                'line-width': 1
            }
        });
    }

    if (!gridMoveListenerAttached) {
        map.on('moveend', updateGrid);
        gridMoveListenerAttached = true;
    }

    updateGrid();
}

function updateSiteStats() {
    if (!pointsGeojson) return;

    const totalToDateEl = document.getElementById('totalSightingsToDate');
    const animalsTotalEl = document.getElementById('animalsTotal');
    const todayEl = document.getElementById('sightingsToday');
    if (!totalToDateEl || !todayEl) return;

    const validFeatures = pointsGeojson.features.filter(
        f => f.properties._day_index !== null && f.properties._day_index !== undefined
    );

    const totalValid = validFeatures.length;

    const animalsTotalSum = validFeatures.reduce((sum, f) => {
        const val = Number(f.properties.animals_total);
        return sum + (Number.isFinite(val) ? val : 0);
    }, 0);

    const latestDayIndex = totalDays;
    const todayCount = pointsGeojson.features.filter(
        f => f.properties._day_index === latestDayIndex
    ).length;

    totalToDateEl.textContent = totalValid;
    if (animalsTotalEl) animalsTotalEl.textContent = animalsTotalSum;
    todayEl.textContent = todayCount;
}

function populateYearDropdown() {
    const menu = document.getElementById('year-dropdown-menu');
    menu.innerHTML = '';

    const allOption = document.createElement('div');
    allOption.className = 'year-option' + (currentYearFilter === 'All' ? ' active' : '');
    allOption.dataset.year = 'All';
    allOption.textContent = 'All';
    allOption.addEventListener('click', () => selectYear('All'));
    menu.appendChild(allOption);

    for (const year of allYearsList) {
        const opt = document.createElement('div');
        opt.className = 'year-option' + (currentYearFilter === year ? ' active' : '');
        opt.dataset.year = String(year);
        opt.textContent = String(year);
        opt.addEventListener('click', () => selectYear(year));
        menu.appendChild(opt);
    }
}

function selectYear(year) {

    exitTimelapse();

    currentYearFilter = year;

    document.getElementById('year-dropdown-label').textContent = (year === 'All') ? 'All' : String(year);
    document.getElementById('year-dropdown-btn').classList.toggle('active', year !== 'All');
    document.querySelectorAll('.year-option').forEach(el => {
        el.classList.toggle('active', el.dataset.year === String(year));
    });
    closeYearDropdown();

    configureSlider();
}

function configureSlider() {
    const slider = document.getElementById('timeSlider');
    const granularityLabel = document.getElementById('timesliderGranularity');
    const minLabel = document.getElementById('minDateLabel');
    const maxLabel = document.getElementById('maxDateLabel');

    if (currentYearFilter === 'All') {
        sliderMode = 'month';
        granularityLabel.textContent = 'Month-Year';

        slider.min = 0;
        slider.max = Math.max(0, monthBuckets.length - 1);

        if (monthBuckets.length === 0) {
            minLabel.textContent = '--';
            maxLabel.textContent = '--';
            slider.value = 0;
        } else {
            minLabel.textContent = formatMonthYear(monthBuckets[0]);
            maxLabel.textContent = formatMonthYear(monthBuckets[monthBuckets.length - 1]);

            const today = new Date();
            let defaultIndex = monthBuckets.findIndex(
                b => b.year === today.getUTCFullYear() && b.month === today.getUTCMonth() + 1
            );
            if (defaultIndex === -1) defaultIndex = monthBuckets.length - 1;
            slider.value = defaultIndex;
        }
    } else {
        sliderMode = 'day';
        granularityLabel.textContent = 'Daily';

        const range = computeYearDayRange(currentYearFilter);
        slider.min = 0;
        slider.max = range.totalDays;

        if (range.minMs === null) {
            minLabel.textContent = '--';
            maxLabel.textContent = '--';
            slider.value = 0;
        } else {
            minLabel.textContent = formatDate(new Date(range.minMs));
            maxLabel.textContent = formatDate(new Date(range.maxMs));

            const today = new Date();
            let defaultIndex;
            if (today.getUTCFullYear() === currentYearFilter) {
                const todayMs = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
                defaultIndex = Math.round((todayMs - range.minMs) / MS_PER_DAY);
                defaultIndex = Math.max(0, Math.min(range.totalDays, defaultIndex));
            } else {
                defaultIndex = range.totalDays;
            }
            slider.value = defaultIndex;
        }
    }

    updateSelectedDateLabel();
    updateMapFilter();
}

function updateSelectedDateLabel() {
    const slider = document.getElementById('timeSlider');
    const index = parseInt(slider.value, 10);
    const label = document.getElementById('selectedTime');

    if (sliderMode === 'month') {
        const bucket = monthBuckets[index];
        label.textContent = bucket ? formatMonthYear(bucket) : '--';
    } else {
        const range = computeYearDayRange(currentYearFilter);
        label.textContent = (range.minMs !== null)
            ? formatDate(new Date(range.minMs + index * MS_PER_DAY))
            : '--';
    }
}


// Real-time milliseconds the timelapse spends on one slider step.
const MONTHLY_PLAYBACK_MS = 6000; // real ms per month of data in "All" mode
const SINGLE_YEAR_SLOWDOWN = 6;   // single-year mode runs this many times slower than "All"
const PLAYBACK_MS_PER_STEP = {
    month: MONTHLY_PLAYBACK_MS,
    // Single-year mode steps by day: one average month's worth of days takes

    day: MONTHLY_PLAYBACK_MS * SINGLE_YEAR_SLOWDOWN * 12 / 365.25
};

const POINT_VISIBLE_DATA_MS = MS_PER_DAY;           // total time on screen
const POINT_FADE_IN_FRACTION = 0.1;                 // first 10%: fade in
const POINT_FADE_OUT_FRACTION = 0.3;                // last 30%: fade out

// "All" (monthly) playback: points accumulate through the month instead.
const MONTHLY_FADE_IN_FRACTION = 0.05;       // each point fades in over ~1.5 days of the month
const MONTHLY_PREV_FADE_OUT_FRACTION = 0.25; // last month's points fade out over the first quarter of the next

const PLAY_ICON_PATH = 'M8 5v14l11-7z';
const PAUSE_ICON_PATH = 'M6 5h4v14H6zm8 0h4v14h-4z';

let isPlaying = false;        // animation loop currently running
let timelapseActive = false;  // playing OR paused mid-timelapse
let playbackPos = 0;          // fractional slider position
let playbackRafId = null;
let lastFrameTime = null;
let timelapseCursorMs = null; // current moment in data time

// All dated sightings, sorted by exact time -- built once, lazily.
let timelapseFeatures = null;
function getTimelapseFeatures() {
    if (timelapseFeatures) return timelapseFeatures;
    timelapseFeatures = pointsGeojson.features
        .filter(f => f.properties._ts_ms !== null && f.properties._ts_ms !== undefined)
        .sort((a, b) => a.properties._ts_ms - b.properties._ts_ms);
    return timelapseFeatures;
}

// First index whose timestamp is >= ms (binary search).
function lowerBoundByTime(features, ms) {
    let lo = 0, hi = features.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (features[mid].properties._ts_ms < ms) lo = mid + 1; else hi = mid;
    }
    return lo;
}

// Start of slider step i in UTC ms. i may equal the step count (end of range).
function stepStartMs(i) {
    if (sliderMode === 'month') {
        const first = monthBuckets[0];
        return Date.UTC(first.year, first.month - 1 + i, 1);
    }
    const range = computeYearDayRange(currentYearFilter);
    return range.minMs + i * MS_PER_DAY;
}

// Fractional slider position -> exact moment in data time.
function positionToMs(pos) {
    const i = Math.floor(pos);
    const start = stepStartMs(i);
    return start + (pos - i) * (stepStartMs(i + 1) - start);
}

function formatCursorDate(ms) {
    return new Date(ms).toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC'
    });
}

// Shows the timelapse layers and hides the normal ones (or the reverse).
// Only visibility changes here, so nothing has to be re-tiled.
function setTimelapseLayersVisible(on) {
    const show = (id, visible) => {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    };
    show('point-layer', !on);
    show('heatmap-layer', !on);
    show('timelapse-point-layer', on);
    show('timelapse-heatmap-layer', on);
}

// Builds the set of currently-visible sightings, each with its own
// fade value (_alpha), and pushes it into the small timelapse source.
function renderTimelapseFrame() {
    const index = Math.floor(playbackPos);
    const cursor = positionToMs(playbackPos);
    timelapseCursorMs = cursor;

    const visible = (sliderMode === 'month')
        ? collectMonthlyTimelapsePoints(index, cursor)
        : collectDailyTimelapsePoints(cursor);

    const source = map.getSource('timelapse_points');
    if (source) source.setData({ type: 'FeatureCollection', features: visible });

    const slider = document.getElementById('timeSlider');
    slider.value = Math.min(playbackPos, parseFloat(slider.max));

    // "All" plays month by month, so label it by month; single years stay daily.
    const bucket = monthBuckets[Math.min(index, monthBuckets.length - 1)];
    document.getElementById('selectedTime').textContent = (sliderMode === 'month' && bucket)
        ? formatMonthYear(bucket)
        : formatCursorDate(cursor);
}

function speciesPasses(f) {
    return activeSpeciesCodes.size >= allSpeciesCodes.size
        || activeSpeciesCodes.has(f.properties.species_code);
}

function withAlpha(f, alpha) {
    return {
        type: 'Feature',
        geometry: f.geometry,
        properties: { ...f.properties, _alpha: Math.max(0, Math.min(1, alpha)) }
    };
}

// "All" mode: the map builds up the current month's sightings one by one
// (in date/time order) as the month plays, so by the end of the month you
// see that month's full picture. When the next month starts, last month's
// sightings fade away gradually while the new month begins filling in.
function collectMonthlyTimelapsePoints(index, cursor) {
    const monthStart = stepStartMs(index);
    const monthLength = stepStartMs(index + 1) - monthStart;
    const prevStart = stepStartMs(index - 1);

    const fadeIn = monthLength * MONTHLY_FADE_IN_FRACTION;
    const prevFadeSpan = monthLength * MONTHLY_PREV_FADE_OUT_FRACTION;
    const prevAlpha = 1 - (cursor - monthStart) / prevFadeSpan;

    const all = getTimelapseFeatures();
    const visible = [];
    const from = (prevAlpha > 0) ? prevStart : monthStart;

    for (let i = lowerBoundByTime(all, from); i < all.length; i++) {
        const f = all[i];
        const ts = f.properties._ts_ms;
        if (ts > cursor) break;
        if (!speciesPasses(f)) continue;

        if (ts < monthStart) {
            // Previous month: fading out as the new month gets going.
            visible.push(withAlpha(f, prevAlpha));
        } else {
            // Current month: fades in once its date/time is reached, then stays.
            visible.push(withAlpha(f, (cursor - ts) / fadeIn));
        }
    }
    return visible;
}

// Single-year mode: each sighting is on screen for about one day of data
// time, so what you see is roughly that day's sightings.
function collectDailyTimelapsePoints(cursor) {
    const lifetime = POINT_VISIBLE_DATA_MS;
    const fadeIn = lifetime * POINT_FADE_IN_FRACTION;
    const fadeOut = lifetime * POINT_FADE_OUT_FRACTION;
    const fadeOutStart = lifetime - fadeOut;

    const all = getTimelapseFeatures();
    const visible = [];
    for (let i = lowerBoundByTime(all, cursor - lifetime); i < all.length; i++) {
        const f = all[i];
        const ts = f.properties._ts_ms;
        if (ts > cursor) break;
        if (f.properties._year !== currentYearFilter) continue;
        if (!speciesPasses(f)) continue;

        const age = cursor - ts;
        let alpha;
        if (age < fadeIn) alpha = age / fadeIn;                 // fading in
        else if (age < fadeOutStart) alpha = 1;                 // fully shown
        else alpha = 1 - (age - fadeOutStart) / fadeOut;        // fading out
        visible.push(withAlpha(f, alpha));
    }
    return visible;
}

function playbackFrame(now) {
    if (!isPlaying) return;
    if (lastFrameTime === null) lastFrameTime = now;
    const dt = Math.min(now - lastFrameTime, 100); // don't leap after a background tab
    lastFrameTime = now;

    playbackPos += dt / PLAYBACK_MS_PER_STEP[sliderMode];

    const slider = document.getElementById('timeSlider');
    const endPos = parseFloat(slider.max) + 1; // let the last step play out fully
    if (playbackPos >= endPos) {
        playbackPos = parseFloat(slider.max);
        exitTimelapse();
        return;
    }

    renderTimelapseFrame();
    playbackRafId = requestAnimationFrame(playbackFrame);
}

function setPlayButtonState(playing) {
    const btn = document.getElementById('playBtn');
    const icon = document.getElementById('playIcon');
    if (!btn || !icon) return;
    btn.classList.toggle('playing', playing);
    btn.setAttribute('aria-label', playing ? 'Pause timelapse' : 'Play timelapse');
    icon.innerHTML = `<path fill="currentColor" d="${playing ? PAUSE_ICON_PATH : PLAY_ICON_PATH}" />`;
}

function startPlayback() {
    if (isPlaying) return;
    const slider = document.getElementById('timeSlider');

    if (!timelapseActive) {
        // Fresh start: begin from the slider's position, or rewind if at the end.
        const current = parseInt(slider.value, 10);
        playbackPos = (current >= parseInt(slider.max, 10)) ? 0 : current;
        timelapseActive = true;
        slider.step = 'any'; // lets the thumb glide instead of snapping
        setTimelapseLayersVisible(true);
    }

    isPlaying = true;
    lastFrameTime = null;
    setPlayButtonState(true);
    playbackRafId = requestAnimationFrame(playbackFrame);
}

// Pause: freezes the animation where it is, points and all.
function stopPlayback() {
    isPlaying = false;
    if (playbackRafId !== null) {
        cancelAnimationFrame(playbackRafId);
        playbackRafId = null;
    }
    setPlayButtonState(false);
}

// Leave timelapse mode entirely and go back to the normal slider view.
function exitTimelapse() {
    stopPlayback();
    if (!timelapseActive) return;

    timelapseActive = false;
    timelapseCursorMs = null;

    const slider = document.getElementById('timeSlider');
    slider.step = 1;
    slider.value = Math.min(Math.floor(playbackPos), parseInt(slider.max, 10));

    const source = map.getSource('timelapse_points');
    if (source) source.setData({ type: 'FeatureCollection', features: [] });
    setTimelapseLayersVisible(false);

    updateSelectedDateLabel();
    updateMapFilter();
}

function togglePlayback() {
    if (isPlaying) stopPlayback();
    else startPlayback();
}

function initializeTimeControls() {
    if (!minDate || !maxDate) {
        document.getElementById('selectedTime').textContent = 'No dated sightings returned from Supabase';
        return;
    }

    populateYearDropdown();
    configureSlider();

    const slider = document.getElementById('timeSlider');
    slider.addEventListener('input', () => {
        updateSelectedDateLabel();
        updateMapFilter();
    });

    // Grabbing the slider manually ends the timelapse and returns to
    // normal scrubbing from wherever it was.
    slider.addEventListener('pointerdown', exitTimelapse);

    document.getElementById('playBtn').addEventListener('click', togglePlayback);

    updateSiteStats();
}

// Heatmap styling shared by the normal and timelapse heatmap layers;
// only the per-point weight differs.
function buildHeatmapPaint(weight) {
    return {
        'heatmap-weight': weight,
        'heatmap-intensity': [
            'interpolate', ['linear'], ['zoom'],
            0, 1.4,
            HEATMAP_MAX_ZOOM, 3
        ],
        'heatmap-radius': [
            'interpolate', ['linear'], ['zoom'],
            0, 14,
            HEATMAP_MAX_ZOOM, 42
        ],
        'heatmap-color': [
            'interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(2, 7, 20, 0)',
            0.04, 'rgba(81, 187, 214, 0.25)',
            0.12, 'rgba(81, 187, 214, 0.5)',
            0.25, 'rgba(81, 187, 214, 0.75)',
            0.45, 'rgba(120, 210, 235, 0.9)',
            0.7, 'rgba(190, 235, 250, 0.95)',
            0.9, 'rgba(235, 250, 255, 0.98)',
            1, 'rgba(255, 255, 255, 1)'
        ],
        'heatmap-opacity': [
            'interpolate', ['linear'], ['zoom'],
            HEATMAP_MAX_ZOOM - 1.5, 1,
            HEATMAP_MAX_ZOOM, 0
        ]
    };
}

let dataFetched = false;

// Runs every time the map style finishes loading (the first load, and projection changes).
async function onStyleLoad() {
    map.setPaintProperty('background', 'background-color', '#020714');

    map.setFog({
        'color': 'rgb(20, 40, 70)',
        'high-color': 'rgb(10, 20, 50)',
        'horizon-blend': 0.02,
        'space-color': 'rgb(2, 4, 10)',
        'star-intensity': 0.4
    });

    map.getStyle().layers.forEach(layer => {
        if (
            layer.id.includes('settlement') ||
            layer.id.includes('place-label') ||
            layer.id === 'poi-label' ||
            layer.id.includes('road') ||
            layer.id.includes('bridge') ||
            layer.id.includes('tunnel') ||
            layer.id.includes('building') ||
            layer.id.includes('transit') ||
            layer.id.includes('railway') ||
            layer.id.includes('aeroway') ||
            layer.id.includes('airport') ||
            layer.id.includes('poi')
        ) {
            map.setLayoutProperty(layer.id, 'visibility', 'none');
        }
    });

    if (map.getLayer('water')) {
        map.setPaintProperty('water', 'fill-color', '#041c33');
    }

    if (!dataFetched) {
        document.getElementById('selectedTime').textContent = 'Loading sightings…';
        try {
            await loadSpeciesCSV();
            await loadPointsAndComputeDateRange();
        } catch (err) {
            // Most likely map_api.py isn't running, or Supabase couldn't be reached.
            console.error(err);
            document.getElementById('selectedTime').textContent =
                'Could not load sightings. Is map_api.py running? (see console)';
            return;
        }

        speciesColorMap = buildSpeciesColorMap(speciesRows, speciesRecordCountMap);

        allSpeciesCodes = new Set(speciesRows.map(getSpeciesCode).filter(Boolean));
        activeSpeciesCodes = new Set(allSpeciesCodes);

        dataFetched = true;
    }

    registerSpeciesIcons();

    if (!map.getSource('my_points')) {
        map.addSource('my_points', {
            type: 'geojson',
            data: pointsGeojson
        });
    }

    if (!map.getLayer('point-layer')) {
        map.addLayer({
            id: 'point-layer',
            type: 'symbol',
            source: 'my_points',
            minzoom: HEATMAP_MAX_ZOOM,
            layout: {
                'icon-image': buildIconImageExpression(),
                'icon-size': 0.35,
                'icon-allow-overlap': true
            }
        });
    }

    if (!map.getLayer('heatmap-layer')) {
        map.addLayer({
            id: 'heatmap-layer',
            type: 'heatmap',
            source: 'my_points',
            maxzoom: HEATMAP_MAX_ZOOM,
            paint: buildHeatmapPaint(1)
        }, 'point-layer');
    }

    // ---- Timelapse layers: a small, separate source that playback refills
    //      each frame with only the sightings currently on screen (each
    //      carrying its own fade value). Hidden unless a timelapse is on. ----
    if (!map.getSource('timelapse_points')) {
        map.addSource('timelapse_points', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] }
        });
    }
    if (!map.getLayer('timelapse-point-layer')) {
        map.addLayer({
            id: 'timelapse-point-layer',
            type: 'symbol',
            source: 'timelapse_points',
            minzoom: HEATMAP_MAX_ZOOM,
            layout: {
                'icon-image': buildIconImageExpression(),
                'icon-size': 0.35,
                'icon-allow-overlap': true,
                'visibility': 'none'
            },
            paint: {
                'icon-opacity': ['get', '_alpha']
            }
        });
    }
    if (!map.getLayer('timelapse-heatmap-layer')) {
        map.addLayer({
            id: 'timelapse-heatmap-layer',
            type: 'heatmap',
            source: 'timelapse_points',
            maxzoom: HEATMAP_MAX_ZOOM,
            layout: { 'visibility': 'none' },
            paint: buildHeatmapPaint(['get', '_alpha'])
        }, 'timelapse-point-layer');
    }


    setupGrid();

    // Dragging, rotating or tilting the map stops the spin. Zooming in or
    // out (scroll, pinch, double-click) does NOT -- it keeps spinning.
    if (!window.__spinInteractionAttached) {
        window.__spinInteractionAttached = true;
        ['dragstart', 'rotatestart', 'pitchstart'].forEach(ev => map.on(ev, (e) => {
            if (e.originalEvent) stopGlobeSpin(); // only user gestures, not our own camera moves
        }));
    }

    if (!document.getElementById('timeSlider').dataset.initialized) {
        initializeTimeControls();
        document.getElementById('timeSlider').dataset.initialized = 'true';
        setDimension('flat');
    } else {
        updateMapFilter();
    }

    if (!document.getElementById('speciesList').dataset.initialized) {
        populateList();
        setupSpeciesSearch();
        document.getElementById('speciesList').dataset.initialized = 'true';
    }

    if (!window.__whaleMapPopupAttached) {
        window.__whaleMapPopupAttached = true;

        function buildSightingPopupHtml(props) {
            const speciesDisplay = speciesNameMap[props.species_code] ?? props.species_name ?? props.species_code ?? 'N/A';

            const rawDate = props.date || props.sighting_date_and_time_utc;
            const parsedDate = rawDate ? new Date(rawDate) : null;
            const dateDisplay = (parsedDate && !isNaN(parsedDate)) ? formatDate(parsedDate) : 'N/A';

            return `
                <strong>Date:</strong> ${dateDisplay}<br>
                <strong>Species:</strong> ${escapeHtml(speciesDisplay)}<br>
                <strong>Total animals:</strong> ${escapeHtml(props.animals_total ?? 'N/A')}<br>
                <strong>Boat:</strong> ${escapeHtml(props.boat_name ?? 'N/A')}<br>
                <strong>Notes:</strong> ${escapeHtml(props.general_notes)}
            `;
        }

        const popup = new mapboxgl.Popup({
            closeButton: false,
            closeOnClick: false
        });

        function attachHoverPopup(layerId) {
            map.on('mouseenter', layerId, (e) => {
                map.getCanvas().style.cursor = 'pointer';

                const coordinates = e.features[0].geometry.coordinates.slice();
                const props = e.features[0].properties;

                // During a timelapse, ignore sightings that haven't "happened" yet.
                if (timelapseCursorMs !== null && Number(props._ts_ms) > timelapseCursorMs) return;

                while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
                    coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
                }

                popup.setLngLat(coordinates).setHTML(buildSightingPopupHtml(props)).addTo(map);
            });

            map.on('mouseleave', layerId, () => {
                map.getCanvas().style.cursor = '';
                popup.remove();
            });
        }

        attachHoverPopup('point-layer');
        attachHoverPopup('timelapse-point-layer');
    }
}

// ==== Opening the map (counted against the monthly Mapbox limit) ====
// Every new mapboxgl.Map() is one billed Mapbox map load, so the map is only created
// after map_api.py has counted it and returned the token.
function startMap(token) {
    mapboxgl.accessToken = token;
    map = new mapboxgl.Map({
        container: 'map',
        style: 'mapbox://styles/mapbox/satellite-streets-v12',
        center: [-156.6, 20.8],
        zoom: 9
    });
    map.on('style.load', onStyleLoad);
}

function getMapGate() {
    let gate = document.getElementById('map-gate');
    if (gate) return gate;

    const style = document.createElement('style');
    style.textContent = `
        #map-gate {
            position: fixed; inset: 0; z-index: 20;
            display: flex; align-items: center; justify-content: center;
            background: radial-gradient(circle at 50% 40%, #0b2540 0%, #020714 70%);
            color: #ffffff; padding: 20px; box-sizing: border-box;
        }
        #map-gate.hidden { display: none; }
        .map-gate-card {
            max-width: 420px; text-align: center;
            background: rgba(2, 7, 20, 0.85); border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px; padding: 28px 32px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        }
        .map-gate-text { margin: 0; font-size: 1.05em; line-height: 1.45; }
        .map-gate-btn {
            margin-top: 18px; padding: 10px 22px; border: none; border-radius: 6px;
            background: #a5ddf7; color: #020714; font-weight: bold; font-size: 0.95em; cursor: pointer;
        }
        .map-gate-btn:hover { background: #c0e8f1; }
        .map-gate-btn[hidden] { display: none; }
    `;
    document.head.appendChild(style);

    gate = document.createElement('div');
    gate.id = 'map-gate';
    gate.innerHTML = `
        <div class="map-gate-card">
            <p class="map-gate-text"></p>
            <button class="map-gate-btn" type="button"></button>
        </div>
    `;
    document.body.appendChild(gate);
    return gate;
}

// Shows the cover screen with a message, and a button if a label is given.
function showMapGate(text, buttonLabel, onClick) {
    const gate = getMapGate();
    gate.classList.remove('hidden');
    gate.querySelector('.map-gate-text').textContent = text;
    const btn = gate.querySelector('.map-gate-btn');
    btn.hidden = !buttonLabel;
    btn.textContent = buttonLabel || '';
    btn.onclick = onClick || null;
}

function hideMapGate() {
    const gate = document.getElementById('map-gate');
    if (gate) gate.classList.add('hidden');
}

async function openMap() {
    showMapGate('Loading map…');
    let info;
    try {
        const res = await fetch(MAP_LOAD_URL, { method: 'POST' });
        info = await res.json();
    } catch (err) {
        console.error('Map-load check failed:', err);
        showMapGate('Could not reach the map server. Please try again in a moment.', 'Try again', openMap);
        return;
    }

    if (!info.allowed || !info.token) {
        // Monthly limit reached, too many opens today, or a server setup problem.
        showMapGate(info.message || 'The map is unavailable right now.');
        return;
    }

    hideMapGate();
    startMap(info.token);
}

if (REQUIRE_CLICK_TO_LOAD) {
    showMapGate('Explore whale and dolphin sightings from the Whale & Dolphin Tracker.', 'View the map', openMap);
} else {
    openMap();
}