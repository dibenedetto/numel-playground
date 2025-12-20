class NumelApp {

	static EventType = AGUI.EventType;

	static _randomId() {
		// https://gist.github.com/jed/982883?permalink_comment_id=852670#gistcomment-852670
		return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,a=>(a^Math.random()*16>>a/4).toString(16));
	}

	static _randomMessageId() {
		const id = `numel-message-${NumelApp._randomId()}`;
		return id;
	}

	static async _post(url, body) {
		const res = await fetch(url, {
			method  : "POST",
			headers : {
				"Access-Control-Allow-Origin": "*",
				"Content-Type": "application/json"
			},
			body    : body ? JSON.stringify(body) : null,
		}).then(async response => {
			if (!response.ok) {
				throw new Error(response.statusText);
			}
			const result = await response.json();
			if (!("error" in result)) {
				result["error"] = null;
			}
			return result;
		})
		.catch(error => {
			console.error("Error fetching:", error);
			const result = {
				"error" : error,
			}
			return result;
		});
		return res;
	}

	static async _ping(url) {
		return NumelApp._post(url + "/ping");
	}

	static async _getSchema(url) {
		return NumelApp._post(url + "/schema");
	}

	static async _getConfig(url) {
		return NumelApp._post(url + "/export");
	}

	static async _putConfig(url, config) {
		return NumelApp._post(url + "/import", config);
	}

	static async _start(url) {
		return NumelApp._post(url + "/start");
	}

	static async _stop(url) {
		return NumelApp._post(url + "/stop");
	}

	static async _restart(url) {
		return NumelApp._post(url + "/restart");
	}

	static async _getStatus(url) {
		return NumelApp._post(url + "/status");
	}

	static async _shutdown(url) {
		return NumelApp._post(url + "/shutdown");
	}

	static async connect(url, options = {}) {
		if (!url || (url.length == 0)) {
			console.error("Invalid URL");
			return null;
		}
		if (!options) {
			options = {};
		}

		const userId     = options["userId"    ];
		const sessionId  = options["sessionId" ];
		const subscriber = options["subscriber"];

		try {
			await NumelApp._stop(url);

			let status = await NumelApp._start(url);
			if (!status || status.error) {
				return null;
			}

			const schemaDict = await NumelApp._getSchema(url);
			const schemaCode = schemaDict["schema"];

			const app = new NumelApp(url, schemaCode, userId, sessionId, subscriber);
			status = await app._update();
			if (!status || status.error) {
				return null;
			}

			if (!app.isValid()) {
				await NumelApp._stop(url);
				return null;
			}

			return app;
		}
		catch (error) {
			console.error("Error connecting to Numel app:", error);
			return null;
		}
	}

	constructor(url, schema, userId, sessionId, subscriber) {
		this.url        = url;
		this.schema     = schema;
		this.userId     = userId;
		this.sessionId  = sessionId;
		this.subscriber = subscriber;
		this.status     = null;
		this.valid      = false;
		this.agents     = null;
		this.agentIndex = -1;
	}

	async _update() {
		try {
			const status    = await NumelApp._getStatus(this.url);
			this.valid      = true;
			this.status     = status;
			this.agents     = (("config" in status) && ("agents" in status["config"])) ? new Array(status["config"]["agents"].length) : [];
			this.agentIndex = (this.agents.lenght > 0) ? 0 : -1;
		}
		catch (error) {
			console.error("Error fetching status:", error);
			this.valid      = false;
			this.status     = null;
			this.agents     = null;
			this.agentIndex = -1;
		}
		return this.isValid();
	}

	_getAgent(index) {
		if ((index == null) || (index < 0)) {
			index = this.agentIdx;
			if (index < 0) {
				return null;
			}
		}

		let agent = this.agents[index];
		if (agent) {
			return agent;
		}

		const configs = this.status["config"]["agents"] ?? null;
		if (!configs || (index >= configs.length)) {
			return null;
		}

		const config = configs[index];
		if (!config) {
			return null;
		}

		const baseUrl = this.url.substr(0, this.url.lastIndexOf(":"));
		const port    = config["port"];
		const url     = `${baseUrl}:${port}/agui`;

		agent = new AGUI.HttpAgent({
			name : config["info"]["name"],
			url  : url,
		});

		if (this.subscriber) {
			agent.subscribe(this.subscriber);
		}

		this.agents[index] = agent;

		return agent;
	}

	async disconnect() {
		await this.stop();
		this.valid  = false;
		this.status = null;
		this.agents = null;
	}

	isValid() {
		return this.valid;
	}

	getDefaultAgentIndex() {
		return this.agentIdx;
	}

	setDefaultAgentIndex(index) {
		if (!this.isValid() || (index < 0) || (index >= this.status["config"]["agents"].length)) {
			return false;
		}
		this.agentIdx = index;
		return true;
	}

	async ping() {
		return NumelApp._ping(this.url);
	}

	async getStatus() {
		return NumelApp._getStatus(this.url);
	}

	async getSchema() {
		return NumelApp._getSchema(this.url);
	}

	async getConfig() {
		return NumelApp._getConfig(this.url);
	}

	async putConfig(config) {
		return NumelApp._putConfig(this.url, config);
	}

	async start() {
		return NumelApp._start(this.url);
	}

	async stop() {
		return NumelApp._stop(this.url);
	}

	async restart() {
		return NumelApp._restart(this.url);
	}

	async shutdown() {
		return NumelApp._shutdown(this.url);
	}

	async send(message, index = -1) {
		if (!this.isValid()) {
			return false;
		}
		const agent = this._getAgent(index);
		if (!agent) {
			return null;
		}
		const messageId   = `${NumelApp._randomMessageId()}`;
		const userMessage = {
			id      : messageId,
			role    : "user",
			content : message,
		};
		agent.setMessages([userMessage]);
		return await agent.runAgent({});
	}
};
