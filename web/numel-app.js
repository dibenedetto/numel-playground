/* ========================================================================
   NUMEL APP - Application Logic
   ======================================================================== */

// Constants
const SCHEMA_NAME = "numel";
const START_MESSAGE = "🤖 Hi, I am Numel, an AI playground. Ask me anything you want 🙂";
const END_MESSAGE = "🤖 See you soon 👋";

// Application State
let gApp = null;
let gGraph = null;
let isConnected = false;
let agentPrevIndex = -1;
let agentCurrIndex = -1;
let messagePrevRole = null;
let messagePrevElement = null;

// DOM Elements
let chatContainer;
let messageInput;
let sendButton;
let connectButton;
let statusDiv;
let serverUrlInput;
let sessionIdInput;
let userIdInput;
let loadingDiv;
let systemMsgButton;
let appAgentSelect;
let clearChatButton;

let downloadConfigBtn, uploadConfigBtn, newConfigBtn;
let toolbarToggle, mainToolbar, toolbarContent;

// ========================================================================
// INITIALIZATION
// ========================================================================

function initializeApp() {
	// Get DOM elements
	chatContainer = document.getElementById("chatContainer");
	messageInput = document.getElementById("messageInput");
	sendButton = document.getElementById("sendButton");
	connectButton = document.getElementById("connectButton");
	statusDiv = document.getElementById("status");
	serverUrlInput = document.getElementById("serverUrl");
	sessionIdInput = document.getElementById("sessionId");
	userIdInput = document.getElementById("userId");
	loadingDiv = document.getElementById("loading");
	systemMsgButton = document.getElementById("debugMessage");
	appAgentSelect = document.getElementById("appAgentSelect");
	clearChatButton = document.getElementById("clearChatButton");

	// Config management buttons
	downloadConfigBtn = document.getElementById('downloadConfigBtn');
	uploadConfigBtn = document.getElementById('uploadConfigBtn');
	newConfigBtn = document.getElementById('newConfigBtn');

	// Toolbar elements
	toolbarToggle = document.getElementById('toolbarToggle');
	mainToolbar = document.getElementById('mainToolbar');
	toolbarContent = document.getElementById('toolbarContent');

	// Check if required libraries are loaded
	checkLibrariesLoaded();

	// Initialize SchemaGraph
	gGraph = new SchemaGraphApp("sg-main-canvas");

	// Register workflow node creation callback for SchemaGraph context menu
	gGraph.onAddWorkflowNode = function(nodeType, wx, wy) {
		if (typeof addWorkflowNodeAtPosition === 'function') {
			addWorkflowNodeAtPosition(nodeType, wx, wy);
		} else {
			console.error('addWorkflowNodeAtPosition not defined yet');
		}
	};

	// Setup event listeners
	setupEventListeners();
}

function checkLibrariesLoaded() {
	if (typeof NumelApp !== "undefined") {
		loadingDiv.style.display = "none";
		addMessage("system", "✅ NumelApp loaded successfully");
	} else {
		loadingDiv.style.display = "block";
		loadingDiv.textContent = "❌ Failed to load NumelApp.";
		addMessage("system-error", "❌ Error: NumelApp not found.");
	}
}

function setupEventListeners() {
	// Server URL change
	serverUrlInput.addEventListener("change", () => {
		appAgentSelect.disabled = true;
		appAgentSelect.innerHTML = "<option value='-1'> - None - </option>";
	});

	// Agent selection change
	appAgentSelect.addEventListener("change", (e) => {
		agentCurrIndex = parseInt(e.target.value);
	});

	// Debug message toggle
	systemMsgButton.addEventListener("change", changeSystemVisibility);

	// Message input - Enter key to send
	messageInput.addEventListener("keypress", (e) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	});

	// Connect button
	connectButton.addEventListener("click", toggleConnection);

	// Send button
	sendButton.addEventListener("click", sendMessage);

	// Clear chat button
	clearChatButton.addEventListener("click", clearChat);
	
	// Config management buttons
	downloadConfigBtn.addEventListener('click', downloadConfig);
	uploadConfigBtn.addEventListener('click', uploadConfig);
	newConfigBtn.addEventListener('click', createNewConfig);
	
	// Config file upload handler
	const importConfigFile = document.getElementById('sg-importConfigFile');
	if (importConfigFile) {
		importConfigFile.addEventListener('change', handleConfigFileUpload);
	}
}

// ========================================================================
// UPDATE CONNECT/DISCONNECT FUNCTIONS
// ========================================================================

async function connect() {
	const serverUrl = serverUrlInput.value.trim();
	if (!serverUrl) {
		addMessage("system", "⚠️ Please enter a valid server URL");
		return;
	}

	clearChatButton.disabled = true;
	connectButton.disabled = true;
	downloadConfigBtn.disabled = true;
	uploadConfigBtn.disabled = true;
	newConfigBtn.disabled = true;

	addMessage("system", "⌛ Connecting...");

	const userId = userIdInput.value.trim();
	const sessionId = sessionIdInput.value.trim();

	enableAppInput(false);
	updateStatus("connecting", "Connecting...");

	try {
		gApp = await NumelApp.connect(serverUrl, {
			userId: userId,
			sessionId: sessionId,
			subscriber: {
				onEvent(params) {
					handleAGUIEvent(params.event);
				}
			}
		});

		if (!gApp) {
			throw new Error("NumelApp initialization failed");
		}

		// Load schema and config into SchemaGraph
		const config = await gApp.getConfig();
		gGraph.api.schema.register(SCHEMA_NAME, gApp.schema, "Index", "AppConfig");
		gGraph.api.config.import(config, SCHEMA_NAME);
		gGraph.api.layout.apply("circular");
		gGraph.api.view.center();

		agentPrevIndex = -1;
		agentCurrIndex = 0;
		isConnected = true;

		await setAppStatus();

		clearChat();
		updateStatus("connected", "Connected");
		enableInput(true);
		connectButton.textContent = "Disconnect";
		connectButton.classList.remove("numel-btn-accent");
		connectButton.classList.add("numel-btn-accent-red");
		addMessage("system", `✅ Connected to ${serverUrl}`);
		addMessage("ui", START_MESSAGE);

	} catch (error) {
		console.error("Failed to initialize connection:", error);
		addMessage("system-error", `❌ Connection failed: ${error.message}`);
		updateStatus("disconnected", "Connection failed");
		enableAppInput(true);
	} finally {
		clearChatButton.disabled = false;
		connectButton.disabled = false;
		downloadConfigBtn.disabled = !isConnected;
		uploadConfigBtn.disabled = false; // Can upload when disconnected
		newConfigBtn.disabled = false;
	}
}

async function disconnect() {
	clearChatButton.disabled = true;
	connectButton.disabled = true;
	downloadConfigBtn.disabled = true;
	uploadConfigBtn.disabled = true;
	newConfigBtn.disabled = true;

	enableInput(false);

	gGraph.api.schema.remove(SCHEMA_NAME);

	if (gApp) {
		addMessage("system", "⌛ Disconnecting...");
		await gApp.disconnect();
		gApp = null;
	}

	isConnected = false;
	agentCurrIndex = -1;
	appAgentSelect.innerHTML = "<option value='-1'> - None - </option>";
	messageInput.value = "";

	updateStatus("disconnected", "Disconnected");
	connectButton.textContent = "Connect";
	connectButton.classList.remove("numel-btn-accent-red");
	connectButton.classList.add("numel-btn-accent");
	addMessage("system", "ℹ️ Disconnected");
	addMessage("ui", END_MESSAGE);
	enableAppInput(true);

	clearChatButton.disabled = false;
	connectButton.disabled = false;
	downloadConfigBtn.disabled = true;
	uploadConfigBtn.disabled = false;
	newConfigBtn.disabled = false;
}

function toggleConnection() {
	if (isConnected) {
		disconnect();
	} else {
		connect();
	}
	chatModeBtn.click();
}

async function setAppStatus() {
	const status = await gApp.getStatus();
	const config = status["config"];
	const agents = config["agents"];
	
	let content = "";
	if (agents.length === 0) {
		agentCurrIndex = -1;
		content = "<option value='-1'> - None - </option>";
	} else {
		agentCurrIndex = 0;
		for (let i = 0; i < agents.length; i++) {
			const selected = (i === agentCurrIndex) ? " selected" : "";
			const info = config["infos"][agents[i]["info"]];
			content += `<option value="${i}"${selected}>${info["name"]}</option>`;
		}
	}
	
	appAgentSelect.innerHTML = content;
	appAgentSelect.disabled = false;
	
	return status;
}

// ========================================================================
// MESSAGE HANDLING
// ========================================================================

async function sendMessage() {
	const message = messageInput.value.trim();
	if (!message || !isConnected || !gApp) return;

	addMessage("user", message);

	// Show which agent we're talking to if changed
	if (agentPrevIndex !== agentCurrIndex) {
		agentPrevIndex = agentCurrIndex;
		const agent = gApp.status["config"]["agents"][agentPrevIndex];
		const agentName = gApp.status["config"]["infos"][agent["info"]]["name"];
		addMessage("ui", `🤖 Talking to Agent "${agentName}"`);
	}

	messageInput.value = "";
	sendButton.textContent = "Messaging...";
	sendButton.disabled = true;
	connectButton.disabled = true;
	clearChatButton.disabled = true;

	try {
		await gApp.send(message, agentPrevIndex);
	} catch (error) {
		console.error("Failed to send message:", error);
		addMessage("system-error", `❌ Failed to send message: ${error.message}`);
	} finally {
		sendButton.textContent = "Send";
		sendButton.disabled = false;
		connectButton.disabled = false;
		clearChatButton.disabled = false;
	}
}

function addMessage(role, content) {
	if (messagePrevRole !== role) {
		const messageDiv = document.createElement("div");
		messageDiv.className = `message ${role}`;
		
		if (role === "system") {
			const display = systemMsgButton.checked ? "block" : "none";
			messageDiv.style.display = display;
		}
		
		messageDiv.innerHTML = "";
		chatContainer.appendChild(messageDiv);
		messagePrevRole = role;
		messagePrevElement = messageDiv;
	} else if (role === "system") {
		content = `<br/>${content}`;
	}
	
	messagePrevElement.innerHTML += content;
	chatContainer.scrollTop = chatContainer.scrollHeight;
}

function clearChat() {
	messagePrevRole = null;
	messagePrevElement = null;
	chatContainer.innerHTML = "";
}

// ========================================================================
// AG-UI EVENT HANDLING
// ========================================================================

function handleAGUIEvent(event) {
	console.log("AG-UI Event:", event);

	if (!event) return;

	switch (event.type) {
		case NumelApp.EventType.TEXT_MESSAGE_CONTENT:
		case NumelApp.EventType.TEXT_MESSAGE_CHUNK:
			const content = event.delta || "No content";
			addMessage("agent", content);
			break;

		case NumelApp.EventType.TEXT_MESSAGE_START:
			addMessage("system", "🤖 Agent is responding...");
			break;

		case NumelApp.EventType.TEXT_MESSAGE_END:
			addMessage("system", "✅ Response complete");
			break;

		case NumelApp.EventType.RUN_STARTED:
			addMessage("system", "🚀 Agent run started");
			break;

		case NumelApp.EventType.RUN_FINISHED:
			addMessage("system", "🏁 Agent run finished");
			break;

		case NumelApp.EventType.RUN_ERROR:
			addMessage("system-error", `❌ Error: ${event.error || "Unknown error"}`);
			break;

		case NumelApp.EventType.TOOL_CALL_START:
			addMessage("system", `🔧 Tool call: ${event.tool_name || "unknown"}`);
			break;

		case NumelApp.EventType.TOOL_CALL_RESULT:
			addMessage("system", `✅ Tool result received`);
			break;

		default:
			addMessage("system", `ℹ️ Event: ${event.type}`);
			console.log("Unhandled event:", event);
	}
}

// ========================================================================
// UI HELPERS
// ========================================================================

function updateStatus(type, message) {
	statusDiv.className = `numel-status numel-status-${type}`;
	statusDiv.textContent = message;
}

function enableInput(enabled) {
	messageInput.disabled = !enabled;
	sendButton.disabled = !enabled;
}

function enableAppInput(enable) {
	serverUrlInput.disabled = !enable;
	sessionIdInput.disabled = !enable;
	userIdInput.disabled = !enable;
	appAgentSelect.disabled = enable;
}

function changeSystemVisibility() {
	const divs = document.getElementsByClassName("message system");
	const display = systemMsgButton.checked ? "block" : "none";
	for (let div of divs) {
		div.style.display = display;
	}
}

// ========================================================================
// CONFIG MANAGEMENT
// ========================================================================

async function downloadConfig() {
	if (!gApp || !gApp.isValid()) {
		addMessage("system-error", "⚠️ Not connected to server");
		return;
	}

	try {
		downloadConfigBtn.disabled = true;
		addMessage("system", "📥 Downloading config...");
		
		const config = await gApp.getConfig();
		
		// Create and download JSON file
		const json = JSON.stringify(config, null, 2);
		const blob = new Blob([json], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		
		const a = document.createElement('a');
		a.href = url;
		a.download = `config_${new Date().toISOString().slice(0,10)}.json`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
		
		addMessage("system", "✅ Config downloaded successfully");
	} catch (error) {
		console.error("Failed to download config:", error);
		addMessage("system-error", `❌ Failed to download config: ${error.message}`);
	} finally {
		downloadConfigBtn.disabled = false;
	}
}

async function uploadConfig() {
	if (!gApp || !gApp.isValid()) {
		addMessage("system-error", "⚠️ Not connected to server");
		return;
	}
	
	// Trigger file input
	const fileInput = document.getElementById('sg-importConfigFile');
	fileInput.click();
}

async function handleConfigFileUpload(event) {
	const file = event.target.files[0];
	if (!file) return;

	try {
		uploadConfigBtn.disabled = true;
		addMessage("system", "📤 Uploading config...");
		
		// Read file
		const text = await file.text();
		const config = JSON.parse(text);
		
		// Validate basic structure
		if (!config || typeof config !== 'object') {
			throw new Error("Invalid config file format");
		}
		
		// Confirm before uploading (will require restart)
		const confirmed = confirm(
			"⚠️ Uploading a new config will stop the current application.\n" +
			"You'll need to reconnect after upload. Continue?"
		);
		
		if (!confirmed) {
			addMessage("system", "ℹ️ Config upload cancelled");
			event.target.value = '';
			return;
		}
		
		// Stop the app first
		if (isConnected) {
			await gApp.stop();
			addMessage("system", "⏸️ Application stopped");
		}
		
		// Upload config
		const result = await gApp.putConfig(config);
		
		if (result.error) {
			throw new Error(result.error);
		}
		
		addMessage("system", "✅ Config uploaded successfully");
		addMessage("system", "ℹ️ Click 'Connect' to start with new config");
		
		// Update UI state
		isConnected = false;
		gApp = null;
		enableInput(false);
		connectButton.textContent = "Connect";
		connectButton.classList.remove("numel-btn-accent-red");
		connectButton.classList.add("numel-btn-accent");
		updateStatus("disconnected", "Ready to connect");
		
	} catch (error) {
		console.error("Failed to upload config:", error);
		addMessage("system-error", `❌ Failed to upload config: ${error.message}`);
	} finally {
		uploadConfigBtn.disabled = false;
		event.target.value = '';
	}
}

function createNewConfig() {
	if (!gApp || !gApp.isValid()) {
		addMessage("system-error", "⚠️ Not connected to server");
		return;
	}
	
	const confirmed = confirm(
		"⚠️ Creating a new config will stop the current application.\n" +
		"This will create a minimal default configuration.\n" +
		"Continue?"
	);
	
	if (!confirmed) {
		return;
	}
	
	// Create minimal config
	const newConfig = {
		"port": 8000,
		"info": {
			"version": "1.0.0",
			"name": "Numel Playground",
			"author": "user@numel.app",
			"description": "New Numel AI Configuration"
		},
		"options": {
			"seed": null,
			"reload": true
		},
		"backends": [
			{
				"type": "agno",
				"version": ""
			}
		],
		"models": [
			{
				"type": "openai",
				"id": "gpt-4"
			}
		],
		"embeddings": [
			{
				"type": "openai",
				"id": ""
			}
		],
		"prompts": [
			{
				"model": 0,
				"embedding": 0,
				"description": "Numel AI Assistant",
				"instructions": [
					"Be helpful and informative"
				]
			}
		],
		"content_dbs": [],
		"index_dbs": [],
		"memory_mgrs": [],
		"session_mgrs": [],
		"knowledge_mgrs": [],
		"tools": [],
		"agent_options": [
			{
				"markdown": true
			}
		],
		"agents": [
			{
				"info": {
					"version": "1.0.0",
					"name": "Default Agent",
					"author": "user@numel.app"
				},
				"options": 0,
				"backend": 0,
				"prompt": 0,
				"content_db": null,
				"memory_mgr": null,
				"session_mgr": null,
				"knowledge_mgr": null,
				"tools": []
			}
		]
	};
	
	// Download as template
	const json = JSON.stringify(newConfig, null, 2);
	const blob = new Blob([json], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	
	const a = document.createElement('a');
	a.href = url;
	a.download = `config_new_${new Date().toISOString().slice(0,10)}.json`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
	
	addMessage("system", "📄 New config template downloaded");
	addMessage("system", "ℹ️ Edit the file and upload it to apply");
}

// ========================================================================
// ENTRY POINT
// ========================================================================

if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', initializeApp);
} else {
	initializeApp();
}
