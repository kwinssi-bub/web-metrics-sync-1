const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
const path = require('path');

puppeteer.use(StealthPlugin());

const LINKS_FILE = path.join(__dirname, 'automation', 'data', 'links.json');
const PINGED_FILE = path.join(__dirname, 'automation', 'data', 'pinged.json');
const WAIT_TIME = 5000;

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

function main() {
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

  (async () => {
    const browser = await puppeteer.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    let pinged = 0;
    let failed = 0;

    for (const url of newLinks) {
      try {
        const page = await browser.newPage();
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
        await new Promise(r => setTimeout(r, WAIT_TIME));
        await page.close();

        pingedLinks.push(url);
        pinged++;

        if (pinged % 50 === 0) {
          saveJson(PINGED_FILE, pingedLinks);
          console.log(`Progress: ${pinged}/${newLinks.length} new links pinged`);
        }

        console.log(`[OK] ${url}`);
      } catch (err) {
        failed++;
        console.log(`[FAIL] ${url} - ${err.message.split('\n')[0]}`);
        pingedLinks.push(url);
      }
    }

    saveJson(PINGED_FILE, pingedLinks);
    await browser.close();

    console.log(`\nDone. Pinged: ${pinged}, Failed: ${failed}, Total tracked: ${pingedLinks.length}`);
    process.exit(0);
  })();
}
