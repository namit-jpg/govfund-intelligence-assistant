const fs = require("node:fs");

function readPayload() {
  const raw = fs.readFileSync(0, "utf8").trim();
  return raw ? JSON.parse(raw) : {};
}

function parseAmount(value) {
  const cleaned = String(value || "")
    .replace(/\$/g, "")
    .replace(/,/g, "")
    .trim();
  return cleaned ? Number(cleaned) : 0;
}

async function main() {
  const payload = readPayload();
  const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE_PATH || "playwright");
  const timeoutMs = Number(process.env.FEC_BROWSER_TIMEOUT_MS || "90000");
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_CHROME_PATH || undefined,
  });

  const rows = [];
  try {
    const page = await browser.newPage();
    await page.goto(payload.url, { waitUntil: "networkidle", timeout: timeoutMs });
    await page.waitForSelector("#results tbody tr", { timeout: timeoutMs });

    const maxPages = Math.max(1, Number(payload.max_pages || 1));
    const fingerprints = new Set();

    for (let currentPage = 1; currentPage <= maxPages; currentPage += 1) {
      await page.waitForSelector("#results tbody tr", { timeout: timeoutMs });
      const currentRows = await page.$$eval("#results tbody tr", (tableRows, context) =>
        tableRows.map((row) => {
          const cells = Array.from(row.querySelectorAll("td"));
          const recipientLink = cells[1]?.querySelector("a");
          const href = recipientLink?.getAttribute("href") || "";
          const committeeMatch = href.match(/committee\/([^/]+)\//i);
          return {
            contributor_name: cells[0]?.textContent?.trim() || "",
            recipient_name: recipientLink?.textContent?.trim() || cells[1]?.textContent?.trim() || "",
            recipient_committee_id: committeeMatch ? committeeMatch[1] : null,
            contributor_state: cells[2]?.textContent?.trim() || "",
            contributor_employer: cells[3]?.textContent?.trim() || "",
            transaction_date: cells[4]?.textContent?.trim() || "",
            amount: cells[5]?.textContent?.trim() || "",
            source_url: context.pageUrl,
            source_page: context.pageNumber,
          };
        }),
        { pageUrl: page.url(), pageNumber: currentPage }
      );

      const fingerprint = currentRows.map((row) => `${row.contributor_name}|${row.transaction_date}|${row.amount}`).join("::");
      if (!fingerprint || fingerprints.has(fingerprint)) {
        break;
      }
      fingerprints.add(fingerprint);

      currentRows.forEach((row) => {
        rows.push({
          ...row,
          transaction_date: row.transaction_date,
          amount: parseAmount(row.amount),
        });
      });

      if (currentPage >= maxPages) {
        break;
      }

      const nextButton = page.locator("#results_next");
      if ((await nextButton.count()) !== 1) {
        break;
      }

      const isDisabled = (await nextButton.getAttribute("aria-disabled")) === "true";
      if (isDisabled) {
        break;
      }

      const firstRowBefore = currentRows[0]
        ? `${currentRows[0].contributor_name}|${currentRows[0].transaction_date}|${currentRows[0].amount}`
        : "";
      await Promise.all([
        page.waitForFunction(
          (previousFingerprint) => {
            const firstRow = document.querySelector("#results tbody tr");
            if (!firstRow) {
              return false;
            }
            const cells = Array.from(firstRow.querySelectorAll("td"));
            const nextFingerprint = `${cells[0]?.textContent?.trim() || ""}|${cells[4]?.textContent?.trim() || ""}|${cells[5]?.textContent?.trim() || ""}`;
            return nextFingerprint !== previousFingerprint;
          },
          firstRowBefore,
          { timeout: timeoutMs }
        ),
        nextButton.click(),
      ]);
    }
  } finally {
    await browser.close();
  }

  process.stdout.write(JSON.stringify(rows));
}

main().catch((error) => {
  process.stderr.write(error?.stack || String(error));
  process.exit(1);
});
