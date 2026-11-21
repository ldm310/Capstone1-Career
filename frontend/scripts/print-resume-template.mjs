import { chromium } from "@playwright/test";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const browser = await chromium.launch({ channel: "msedge", headless: true });
try {
  const page = await browser.newPage();
  await page.goto(
    pathToFileURL(
      path.join(root, "public/downloads/career-resume-template.html"),
    ).href,
  );
  await page.pdf({
    path: path.join(root, "public/downloads/career-resume-template.pdf"),
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    tagged: true,
  });
  await page.screenshot({
    path: path.join(root, "work/resume-template-preview.png"),
    fullPage: true,
  });
  console.log("Created Career resume PDF");
} finally {
  await browser.close();
}
