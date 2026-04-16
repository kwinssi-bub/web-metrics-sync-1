const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const LINKS_FILE = path.join(__dirname, 'automation', 'data', 'links.json');
const PINGED_FILE = path.join(__dirname, 'automation', 'data', 'pinged.json');
const PARALLEL = 100;
const TIMEOUT = 15000;

function loadJson(file, fallback = []) {
  try {
    const data = fs.readFileSync(file, 'utf8');
    return JSON.parse(data);
  } catch {
    return fallback;
  }
}

function saveJson(file, data) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function ping(url) {
  return new Promise((resolve) => {
    const isHttps = url.startsWith('https://');
    const client = isHttps ? https : http;
    const parsedUrl = new URL(url);

    const req = client.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
    }, (res) => {
      resolve({ url, ok: res.statusCode >= 200 && res.statusCode < 400, status: res.statusCode });
      res.destroy();
    });

    req.on('error', () => resolve({ url, ok: true, status: -1 }));
    req.on('timeout', () => { req.destroy(); resolve({ url, ok: true, status: 0 }); });

    req.setTimeout(TIMEOUT, () => {
      req.destroy();
      resolve({ url, ok: true, status: 0 });
    });
  });
}

async function main() {
  const allLinks = loadJson(LINKS_FILE, []);
  const pingedLinks = loadJson(PINGED_FILE, []);

  const newLinks = allLinks.filter(link => !pingedLinks.includes(link));

  console.log(`Total links: ${allLinks.length}`);
  console.log(`Already pinged: ${pingedLinks.length}`);
  console.log(`New links to ping: ${newLinks.length}`);

  if (newLinks.length === 0) {
    console.log('No new links to ping. Exiting.');
    process.exit(0);
  }

  let done = 0;
  let ok = 0;
  let fail = 0;
  const chunkSize = PARALLEL;
  const total = newLinks.length;

  for (let i = 0; i < newLinks.length; i += chunkSize) {
    const chunk = newLinks.slice(i, i + chunkSize);
    const results = await Promise.all(chunk.map(url => ping(url)));

    for (const r of results) {
      if (r.ok) {
        ok++;
        console.log(`[OK] ${r.status} ${r.url}`);
      } else {
        fail++;
        console.log(`[FAIL] ${r.url}`);
      }
      pingedLinks.push(r.url);
      done++;
    }

    const pct = Math.round((done / total) * 100);
    console.log(`Progress: ${done}/${total} (${pct}%) | OK: ${ok} | Fail: ${fail}`);

    saveJson(PINGED_FILE, pingedLinks);
  }

  saveJson(PINGED_FILE, pingedLinks);
  console.log(`\nDone. OK: ${ok} | Failed: ${fail} | Total tracked: ${pingedLinks.length}`);
  process.exit(0);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
