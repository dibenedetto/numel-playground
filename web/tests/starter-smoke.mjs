import { chromium } from 'playwright';

const baseUrl = process.argv[2] || process.env.NUMEL_TEST_BASE_URL || 'http://127.0.0.1:18777';
const username = process.env.NUMEL_TEST_USERNAME || 'starter';
const email = process.env.NUMEL_TEST_EMAIL || `${username}@local`;
const password = process.env.NUMEL_TEST_PASSWORD || 'pass1234';

function assert(condition, message) {
	if (!condition) {
		throw new Error(message);
	}
}

async function waitForEnabled(page, selector, timeout = 30000) {
	await page.waitForFunction((target) => {
		const el = document.querySelector(target);
		return !!el && !el.disabled;
	}, selector, { timeout });
}

async function main() {
	const browser = await chromium.launch({
		channel: 'msedge',
		headless: true,
	});
	const page = await browser.newPage();
	page.setDefaultTimeout(90000);

	const pageErrors = [];
	const consoleMessages = [];
	const requestEvents = [];
	globalThis.__numelPageErrors = pageErrors;
	globalThis.__numelConsoleMessages = consoleMessages;
	page.on('pageerror', (error) => pageErrors.push(String(error?.message || error)));
	page.on('console', (message) => {
		consoleMessages.push(`${message.type()}: ${message.text()}`);
	});
	page.on('request', (request) => {
		const url = request.url();
		if (url.startsWith(baseUrl)) requestEvents.push(`request:${request.resourceType()}:${url}`);
	});
	page.on('requestfinished', (request) => {
		const url = request.url();
		if (url.startsWith(baseUrl)) requestEvents.push(`finished:${request.resourceType()}:${url}`);
	});
	page.on('requestfailed', (request) => {
		const url = request.url();
		if (url.startsWith(baseUrl)) requestEvents.push(`failed:${request.resourceType()}:${url}:${request.failure()?.errorText || 'unknown'}`);
	});
	const stubPaths = new Set([
		'/dist/agui-client.bundle.js',
		'/dist/codemirror-bundle.js',
		'/dist/threejs-bundle.js',
		'/schemagraph/schemagraph-media-ext.js',
		'/schemagraph/schemagraph-ml-ext.js',
		'/schemagraph/schemagraph-3d-ext.js',
	]);
	await page.route('**/*', async (route) => {
		const requestUrl = new URL(route.request().url());
		if (requestUrl.origin === baseUrl && stubPaths.has(requestUrl.pathname)) {
			requestEvents.push(`stub:${requestUrl.pathname}`);
			await route.fulfill({
				status: 200,
				contentType: 'application/javascript',
				body: '',
			});
			return;
		}
		await route.continue();
	});

	try {
		await page.goto(baseUrl, { waitUntil: 'commit' });

		await page.waitForSelector('#authModal', { state: 'visible' });
		await page.fill('#authRegUsername', username);
		await page.fill('#authRegEmail', email);
		await page.fill('#authRegPassword', password);
		await page.fill('#authRegPasswordConfirm', password);
		await page.click('#authRegisterBtn');

		await page.waitForSelector('#authModal', { state: 'hidden' });
		await page.waitForSelector('#spaceStarterPanel', { state: 'visible' });

		const starterTitle = await page.textContent('#spaceStarterPanel .nw-starter-panel-title');
		assert((starterTitle || '').includes('Start This Space'), 'Starter panel title did not appear');

		const workbenchHint = await page.textContent('.nw-field-hint');
		assert((workbenchHint || '').includes('project workbenches'), 'Space workbench hint missing');

		let usedStarterModal = false;
		try {
			await page.waitForSelector('#nwStarterModal', { state: 'visible', timeout: 5000 });
			usedStarterModal = true;
		} catch {}
		if (usedStarterModal) {
			await page.click('#nwStarterModal [data-starter-action="hello"]');
			await page.waitForSelector('#nwStarterModal', { state: 'detached' });
		} else {
			await page.click('#starterHelloBtn');
		}

		await page.waitForFunction(() => {
			const el = document.getElementById('singleWorkflowName');
			return !!el && /Hello Workflow/.test(el.textContent || '');
		});

		await page.waitForFunction(() => {
			const panel = document.getElementById('spaceStarterPanel');
			return !!panel && getComputedStyle(panel).display === 'none';
		});

		assert(pageErrors.length === 0, `Page errors detected: ${pageErrors.join(' | ')}`);
		console.log(`Starter smoke passed for ${baseUrl}`);
	} catch (error) {
		let snapshot = null;
		try {
			snapshot = await page.evaluate(() => {
				const authModal = document.getElementById('authModal');
				const starterPanel = document.getElementById('spaceStarterPanel');
				const hero = document.querySelector('.nw-canvas-hero');
				const stagebar = document.querySelector('.nw-canvas-stagebar');
				const spacesList = document.getElementById('workbenchSpacesList');
				return {
					readyState: document.readyState,
					bodyClass: document.body?.className || '',
					authModalDisplay: authModal ? getComputedStyle(authModal).display : null,
					authModalHtml: authModal?.outerHTML?.slice(0, 300) || null,
					starterDisplay: starterPanel ? getComputedStyle(starterPanel).display : null,
					starterHiddenAttr: starterPanel?.hidden ?? null,
					heroClass: hero?.className || null,
					heroDisplay: hero ? getComputedStyle(hero).display : null,
					stagebarClass: stagebar?.className || null,
					stagebarDisplay: stagebar ? getComputedStyle(stagebar).display : null,
					spacesCount: spacesList?.children?.length ?? null,
					spacesHtml: spacesList?.innerHTML?.slice(0, 500) || null,
					singleWorkflowName: document.getElementById('singleWorkflowName')?.textContent || null,
					hasNumelUser: typeof window._numelUser !== 'undefined' ? !!window._numelUser : null,
					hasSchemaGraphApp: typeof window.SchemaGraphApp,
					location: window.location.href,
				};
			});
		} catch {}
		const details = [];
		if (error?.stack || error) details.push(error?.stack || String(error));
		if (snapshot) details.push(`Snapshot: ${JSON.stringify(snapshot)}`);
		if (pageErrors.length) details.push(`Page errors: ${pageErrors.join(' | ')}`);
		if (consoleMessages.length) details.push(`Console: ${consoleMessages.join(' | ')}`);
		if (requestEvents.length) details.push(`Requests: ${requestEvents.slice(-40).join(' | ')}`);
		throw new Error(details.join('\n'));
	} finally {
		await page.close();
		await browser.close();
	}
}

main().catch((error) => {
	console.error(error?.stack || String(error));
	process.exit(1);
});
