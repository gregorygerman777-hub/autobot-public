#!/usr/bin/env node

import puppeteer from "puppeteer-core";
import { resolve } from "path";

const selector = process.argv[2];
const filePaths = process.argv.slice(3);

if (!selector || filePaths.length === 0) {
	console.log("Usage: browser-upload.js 'selector' file1 [file2 ...]");
	process.exit(1);
}

const b = await Promise.race([
	puppeteer.connect({
		browserURL: "http://localhost:9222",
		defaultViewport: null,
	}),
	new Promise((_, reject) =>
		setTimeout(() => reject(new Error("timeout")), 5000)
	),
]).catch((e) => {
	console.error("✗ Could not connect to browser:", e.message);
	process.exit(1);
});

const p = (await b.pages()).at(-1);
if (!p) {
	console.error("✗ No active tab found");
	process.exit(1);
}

const el = await p.$(selector);
if (!el) {
	console.error(`✗ No element found for selector: ${selector}`);
	process.exit(1);
}

const resolved = filePaths.map((f) => resolve(f));
await el.uploadFile(...resolved);
console.log(`✓ Uploaded ${resolved.length} file(s) to ${selector}`);

await b.disconnect();
