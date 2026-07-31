#!/usr/bin/env node

/**
 * Submit file(s) to a MyCompass/Blackbaud assignment dropbox.
 * Usage: school-submit.js <assignmentIndexId> <file1> [file2 ...]
 *
 * Requires Chrome running on :9222 and already authenticated to the portal.
 */

import puppeteer from "puppeteer-core";
import { existsSync } from "fs";
import { resolve } from "path";

// Your school's Blackbaud/MyCompass portal, e.g. https://yourschool.myschoolapp.com
const BASE = process.env.SCHOOL_PORTAL_URL;
if (!BASE) {
	console.error("SCHOOL_PORTAL_URL not set in environment");
	process.exit(1);
}

const aiid = process.argv[2];
const filePaths = process.argv.slice(3);

if (!aiid || filePaths.length === 0) {
	console.error(
		"Usage: school-submit.js <assignmentIndexId> <file1> [file2 ...]"
	);
	process.exit(1);
}

const resolved = filePaths.map((f) => resolve(f));
for (const f of resolved) {
	if (!existsSync(f)) {
		console.error(`✗ File not found: ${f}`);
		process.exit(1);
	}
}

function sleep(ms) {
	return new Promise((r) => setTimeout(r, ms));
}

// Connect to Chrome
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
	console.error("  Run: browser-start.js --profile");
	process.exit(1);
});

const p = (await b.pages()).at(-1);
if (!p) {
	console.error("✗ No active tab found");
	process.exit(1);
}

/** Poll for a button whose text includes `text` (case-insensitive), click it. */
async function clickButton(text, { timeout = 10000, poll = 500 } = {}) {
	const lc = text.toLowerCase();
	const deadline = Date.now() + timeout;
	while (Date.now() < deadline) {
		const clicked = await p.evaluate((t) => {
			const btn = Array.from(document.querySelectorAll("button")).find(
				(b) => b.textContent.trim().toLowerCase().includes(t)
			);
			if (btn) { btn.click(); return true; }
			return false;
		}, lc);
		if (clicked) return true;
		await sleep(poll);
	}
	return false;
}

/** Poll for page text to include `text`. */
async function waitForText(text, { timeout = 15000, poll = 500 } = {}) {
	const lc = text.toLowerCase();
	const deadline = Date.now() + timeout;
	while (Date.now() < deadline) {
		const found = await p.evaluate(
			(t) => document.body.innerText.toLowerCase().includes(t), lc
		);
		if (found) return true;
		await sleep(poll);
	}
	return false;
}

try {
	// Navigate to assignment
	const url = `${BASE}/lms-assignment/assignment/assignment-student-view/${aiid}`;
	console.error(`Navigating to assignment ${aiid}...`);
	await p.goto(url, { waitUntil: "networkidle2", timeout: 30000 });

	// Wait for page to fully render (file input lives inside an Angular component)
	console.error("Waiting for dropbox to load...");
	let fileInput;
	for (let attempt = 0; attempt < 20; attempt++) {
		fileInput = await p.$('input[type="file"]');
		if (fileInput) break;
		await p.evaluate(() => window.scrollBy(0, 300));
		await sleep(1000);
	}

	if (!fileInput) {
		console.error("✗ Could not find file input on page");
		process.exit(1);
	}

	// Upload files
	for (const filePath of resolved) {
		const name = filePath.split("/").pop();
		console.error(`Uploading ${name}...`);
		await fileInput.uploadFile(filePath);
		await sleep(3000);
	}

	// Wait for file link to appear in the DOM
	const firstName = resolved[0].split("/").pop();
	console.error("Waiting for file to register...");
	const fileVisible = await waitForText(firstName, { timeout: 15000 });
	if (!fileVisible) {
		console.error("⚠ File may not have registered, attempting submit anyway...");
	}

	// Click Submit
	console.error("Clicking Submit...");
	const submitted = await clickButton("submit", { timeout: 5000 });
	if (!submitted) {
		console.error("✗ Submit button not found");
		process.exit(1);
	}

	// Wait for and click confirmation dialog
	console.error("Confirming submission...");
	const confirmed = await clickButton("yes", { timeout: 10000 });
	if (!confirmed) {
		console.error("⚠ No confirmation dialog found (may have auto-submitted)");
	}

	// Verify completed status
	console.error("Verifying...");
	const ok = await waitForText("completed", { timeout: 10000 })
		|| await waitForText("submitted", { timeout: 3000 });

	if (ok) {
		console.log(`✓ Submitted ${resolved.length} file(s) to assignment ${aiid}`);
	} else {
		console.log(`⚠ Upload done for assignment ${aiid} — verify submission on portal`);
	}
} catch (err) {
	console.error(`✗ Error: ${err.message}`);
	process.exit(1);
} finally {
	await b.disconnect();
}
