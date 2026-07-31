#!/usr/bin/env node

import { spawn, execSync } from "node:child_process";
import puppeteer from "puppeteer-core";

const args = process.argv.slice(2);
const useProfile = args.includes("--profile");
const headless = args.includes("--headless");

const unknown = args.filter((a) => a !== "--profile" && a !== "--headless");
if (unknown.length) {
	console.log("Usage: browser-start.js [--profile] [--headless]");
	console.log("\nOptions:");
	console.log("  --profile   Copy your default Chrome profile (cookies, logins)");
	console.log("  --headless  Run Chrome without a visible window");
	process.exit(1);
}

const SCRAPING_DIR = `${process.env.HOME}/.cache/browser-tools`;

// Check if already running on :9222
try {
	const browser = await puppeteer.connect({
		browserURL: "http://localhost:9222",
		defaultViewport: null,
	});
	await browser.disconnect();
	console.log("✓ Chrome already running on :9222");
	process.exit(0);
} catch {}

// Setup profile directory
execSync(`mkdir -p "${SCRAPING_DIR}"`, { stdio: "ignore" });

// Remove SingletonLock to allow new instance
try {
	execSync(`rm -f "${SCRAPING_DIR}/SingletonLock" "${SCRAPING_DIR}/SingletonSocket" "${SCRAPING_DIR}/SingletonCookie"`, { stdio: "ignore" });
} catch {}

if (useProfile) {
	console.log("Syncing profile...");
	execSync(
		`rsync -a --delete \
			--exclude='SingletonLock' \
			--exclude='SingletonSocket' \
			--exclude='SingletonCookie' \
			--exclude='*/Sessions/*' \
			--exclude='*/Current Session' \
			--exclude='*/Current Tabs' \
			--exclude='*/Last Session' \
			--exclude='*/Last Tabs' \
			"${process.env.HOME}/Library/Application Support/Google/Chrome/" "${SCRAPING_DIR}/"`,
		{ stdio: "pipe" },
	);
}

null
// Headless Chrome advertises "HeadlessChrome" in its UA, which some sites
// (e.g. Snapchat Web) reject. Spoof the normal Chrome UA when headless.
let headlessUA = null;
if (headless) {
	try {
		const ver = execSync(
			'"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version',
			{ encoding: "utf8" },
		).match(/[\d.]+/)[0];
		headlessUA = `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${ver} Safari/537.36`;
	} catch {}
}

spawn(
	"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
	[
		"--remote-debugging-port=9222",
		`--user-data-dir=${SCRAPING_DIR}`,
		"--no-first-run",
		"--no-default-browser-check",
		...(headless ? ["--headless=new", "--window-size=1440,900"] : []),
		...(headlessUA ? [`--user-agent=${headlessUA}`] : []),
	],
	{ detached: true, stdio: "ignore" },
).unref();

// Wait for Chrome to be ready
let connected = false;
for (let i = 0; i < 30; i++) {
	try {
		const browser = await puppeteer.connect({
			browserURL: "http://localhost:9222",
			defaultViewport: null,
		});
		await browser.disconnect();
		connected = true;
		break;
	} catch {
		await new Promise((r) => setTimeout(r, 500));
	}
}

if (!connected) {
	console.error("✗ Failed to connect to Chrome");
	process.exit(1);
}

console.log(`✓ Chrome started on :9222${useProfile ? " with your profile" : ""}${headless ? " (headless)" : ""}`);
