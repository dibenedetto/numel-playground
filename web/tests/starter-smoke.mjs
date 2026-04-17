import { chromium } from 'playwright';

const baseUrl = process.argv[2] || process.env.NUMEL_TEST_BASE_URL || 'http://127.0.0.1:18777';
const username = process.env.NUMEL_TEST_USERNAME || 'starter';
const email = process.env.NUMEL_TEST_EMAIL || `${username}@local`;
const password = process.env.NUMEL_TEST_PASSWORD || 'pass1234';
const authMode = process.env.NUMEL_TEST_AUTH_MODE || 'register';

function assert(condition, message) {
	if (!condition) {
		throw new Error(message);
	}
}

function step(message) {
	console.log(`[starter-smoke] ${message}`);
}

async function waitForEnabled(page, selector, timeout = 30000) {
	await page.waitForFunction((target) => {
		const el = document.querySelector(target);
		return !!el && !el.disabled;
	}, selector, { timeout });
}

async function launchBrowser() {
	const attempts = [
		{ label: 'playwright-chromium', options: { headless: true } },
		{ label: 'system-edge', options: { channel: 'msedge', headless: true } },
	];
	const errors = [];
	for (const attempt of attempts) {
		try {
			return await chromium.launch(attempt.options);
		} catch (error) {
			errors.push(`${attempt.label}: ${error?.message || error}`);
		}
	}
	throw new Error(`Unable to launch browser. ${errors.join(' | ')}`);
}

async function main() {
	const browser = await launchBrowser();
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
		if (url.startsWith('http://127.0.0.1:') || url.startsWith('https://127.0.0.1:') || url.startsWith(baseUrl)) {
			requestEvents.push(`request:${request.resourceType()}:${url}`);
		}
	});
	page.on('requestfinished', (request) => {
		const url = request.url();
		if (url.startsWith('http://127.0.0.1:') || url.startsWith('https://127.0.0.1:') || url.startsWith(baseUrl)) {
			requestEvents.push(`finished:${request.resourceType()}:${url}`);
		}
	});
	page.on('requestfailed', (request) => {
		const url = request.url();
		if (url.startsWith('http://127.0.0.1:') || url.startsWith('https://127.0.0.1:') || url.startsWith(baseUrl)) {
			requestEvents.push(`failed:${request.resourceType()}:${url}:${request.failure()?.errorText || 'unknown'}`);
		}
	});
	page.on('response', async (response) => {
		const url = response.url();
		if (!(url.startsWith('http://127.0.0.1:') || url.startsWith('https://127.0.0.1:') || url.startsWith(baseUrl))) return;
		if (!/\/(auth|spaces|schema|ping|workflow|channels|assistant-deployments)\b/.test(url)) return;
		requestEvents.push(`response:${response.status()}:${url}`);
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
		step('open app');
		await page.goto(baseUrl, { waitUntil: 'commit' });

		step(authMode === 'login' ? 'login account' : 'register account');
		await page.waitForSelector('#authModal', { state: 'visible' });
		if (authMode === 'login') {
			await page.fill('#authUsername', username);
			await page.fill('#authPassword', password);
			await page.click('#authLoginBtn');
		} else {
			await page.fill('#authRegUsername', username);
			await page.fill('#authRegEmail', email);
			await page.fill('#authRegPassword', password);
			await page.fill('#authRegPasswordConfirm', password);
			await page.click('#authRegisterBtn');
		}

		await page.waitForSelector('#authModal', { state: 'hidden' });
		await page.waitForSelector('#spaceStarterPanel', { state: 'visible' });

		const spacesEmpty = await page.evaluate(() => {
			const list = document.getElementById('workbenchSpacesList');
			return /No spaces yet/i.test(list?.textContent || '');
		});
		assert(!spacesEmpty, 'Starter space missing from seeded smoke environment');

		step('verify starter panel');
		const starterTitle = await page.textContent('#spaceStarterPanel .nw-starter-panel-title');
		assert((starterTitle || '').includes('Start This Space'), 'Starter panel title did not appear');

		const workbenchHint = await page.textContent('.nw-field-hint');
		assert(
			(workbenchHint || '').includes('project containers') && (workbenchHint || '').includes('workbench'),
			'Space workbench hint missing',
		);

		let usedStarterModal = false;
		try {
			await page.waitForSelector('#nwStarterModal', { state: 'visible', timeout: 5000 });
			usedStarterModal = true;
		} catch {}
		if (usedStarterModal) {
			step('launch hello starter from modal');
			await page.click('#nwStarterModal [data-starter-action="hello"]');
			await page.waitForSelector('#nwStarterModal', { state: 'detached' });
		} else {
			step('launch hello starter from panel');
			await page.click('#starterHelloBtn');
		}

		step('wait for hello workflow');
		await page.waitForFunction(() => {
			const el = document.getElementById('singleWorkflowName');
			return !!el && /Hello Workflow/.test(el.textContent || '');
		});

		step('wait for starter panel to close');
		await page.waitForFunction(() => {
			const panel = document.getElementById('spaceStarterPanel');
			return !!panel && getComputedStyle(panel).display === 'none';
		});

		step('open deployment panel');
		await page.click('#assistantDeploymentPanelBtn');
		await page.waitForSelector('#assistantDeploymentPanel.open');
		await page.waitForSelector('#assistantDeploymentList .nw-assist-empty-state');

		const emptyTitle = await page.textContent('#assistantDeploymentList .nw-assist-empty-title');
		assert((emptyTitle || '').includes('No assistant deployments yet'), 'Assistant deployment empty state did not appear');

		step('open deployment status guide');
		await page.click('#assistantDeploymentHelpBtn');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"]');
		const guideTitle = await page.textContent('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"] h3');
		assert((guideTitle || '').includes('Status Guide'), 'Assistant deployment status guide did not open');
		await page.click('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"] [data-role="cancel"]');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"]', { state: 'detached' });

		step('open deployment network inspector');
		await page.click('#assistantDeploymentInspectBtn');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Inspect Live Network"]');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Inspect Live Network"] [data-role="inspect-filter"]');
		const networkTitle = await page.textContent('.nw-assist-dialog[aria-label="Inspect Live Network"] h3');
		assert((networkTitle || '').includes('Inspect Live Network'), 'Assistant deployment network inspector did not open');
		const networkFilterStatus = await page.textContent('.nw-assist-dialog[aria-label="Inspect Live Network"] [data-role="inspect-filter-count"]');
		assert((networkFilterStatus || '').includes('trace row') || (networkFilterStatus || '').includes('No trace rows'), 'Network inspector filter status missing');
		await page.click('.nw-assist-dialog[aria-label="Inspect Live Network"] [data-role="cancel"]');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Inspect Live Network"]', { state: 'detached' });

		step('open status guide from empty state');
		await page.click('#assistantDeploymentList [data-role="status-guide"]');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"]');
		await page.click('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"] [data-role="cancel"]');
		await page.waitForSelector('.nw-assist-dialog[aria-label="Assistant Deployment Status Guide"]', { state: 'detached' });

		step('open channels from empty state');
		await page.click('#assistantDeploymentList [data-role="open-channels"]');
		await page.waitForSelector('#channelPanel.open');
		const deploymentStillOpen = await page.evaluate(() => document.getElementById('assistantDeploymentPanel')?.classList.contains('open'));
		assert(!deploymentStillOpen, 'Assistant deployment panel should close when opening Channels');

		assert(pageErrors.length === 0, `Page errors detected: ${pageErrors.join(' | ')}`);
		step('done');
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
					serverUrl: document.getElementById('serverUrl')?.value || null,
					wsStatusClass: document.getElementById('wsStatus')?.className || null,
					wsStatusText: document.getElementById('wsStatus')?.textContent || null,
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
					eventLogTail: document.getElementById('eventLog')?.textContent?.slice(-500) || null,
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
