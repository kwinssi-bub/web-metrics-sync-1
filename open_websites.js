const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const LINKS_FILE = path.join(__dirname, 'automation', 'data', 'links.json');
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

function ping(url) {
  return new Promise((resolve) => {
    const isHttps = url.startsWith('https://');
    const client = isHttps ? https : http;

    const req = client.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
    }, (res) => {
      resolve({ url, ok: res.statusCode >= 200 && res.statusCode < 400, status: res.statusCode });
      res.destroy();
    });

    req.on('error', () => resolve({ url, ok: true, status: -1 }));
    req.setTimeout(TIMEOUT, () => {
      req.destroy();
      resolve({ url, ok: true, status: 0 });
    });
  });
}

async function main() {
  const allLinks = loadJson(LINKS_FILE, []);

  console.log(`Total links to ping: ${allLinks.length}`);

  if (allLinks.length === 0) {
    console.log('No links to ping. Exiting.');
    process.exit(0);
  }

  let done = 0;
  let ok = 0;
  let fail = 0;
  const total = allLinks.length;

  for (let i = 0; i < allLinks.length; i += PARALLEL) {
    const chunk = allLinks.slice(i, i + PARALLEL);
    const results = await Promise.all(chunk.map(url => ping(url)));

    for (const r of results) {
      if (r.ok) {
        ok++;
        console.log(`[OK] ${r.status} ${r.url}`);
      } else {
        fail++;
        console.log(`[FAIL] ${r.status} ${r.url}`);
      }
      done++;
    }

    const pct = Math.round((done / total) * 100);
    console.log(`Progress: ${done}/${total} (${pct}%) | OK: ${ok} | Fail: ${fail}`);
  }

  console.log(`\nDone. OK: ${ok} | Failed: ${fail} | Total: ${total}`);
  process.exit(0);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
