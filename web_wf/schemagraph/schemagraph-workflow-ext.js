/* ========================================================================
   SCHEMAGRAPH WORKFLOW EXTENSION
   Parses Python schemas with FieldRole annotations and creates node types
   Compatible with SchemaGraph API
   ======================================================================== */

(function() {
	'use strict';

	// ====================================================================
	// WorkflowSchemaParser - Parse Python schema with FieldRole
	// ====================================================================

	class WorkflowSchemaParser {
		constructor() {
			this.classes = new Map();
			this.constants = new Map();
			this.typeAliases = new Map();
			this.inheritance = new Map();
		}

		parse(schemaCode) {
			this.classes.clear();
			this.constants.clear();
			this.typeAliases.clear();
			this.inheritance.clear();

			const lines = schemaCode.split('\n');
			this._extractConstants(lines);
			this._extractTypeAliases(lines);
			this._extractClasses(lines);
			this._resolveInheritance();

			return this.classes;
		}

		_extractConstants(lines) {
			for (const line of lines) {
				// Module-level constants: starts at column 0, uppercase name
				if (/^[A-Z][A-Z0-9_]*\s*[:=]/.test(line)) {
					const match = line.match(/^([A-Z][A-Z0-9_]*)\s*(?::\s*[^=]+)?\s*=\s*(.+)$/);
					if (match) {
						let value = match[2].trim();
						if (value === 'True') value = true;
						else if (value === 'False') value = false;
						else if (value === 'None') value = null;
						else if (/^-?\d+$/.test(value)) value = parseInt(value);
						else if (/^-?\d+\.\d+$/.test(value)) value = parseFloat(value);
						else if (/^["']/.test(value)) value = value.slice(1, -1);
						this.constants.set(match[1], value);
					}
				}
			}
		}

		_extractTypeAliases(lines) {
			for (const line of lines) {
				// Type aliases at module level
				if (line.search(/\S/) !== 0) continue;
				const match = line.match(/^([A-Z][a-zA-Z0-9_]*)\s*=\s*(Union\[.+\]|List\[.+\]|Dict\[.+\]|Optional\[.+\])$/);
				if (match) {
					this.typeAliases.set(match[1], match[2]);
				}
			}
		}

		_extractClasses(lines) {
			let currentClass = null;
			let classBodyIndent = null;

			for (let i = 0; i < lines.length; i++) {
				const line = lines[i];
				const trimmed = line.trimStart();
				const indent = line.length - trimmed.length;

				// Skip empty lines and comments
				if (!trimmed || trimmed.startsWith('#')) continue;

				// Module-level content (indent 0) that's not a class ends current class
				if (indent === 0) {
					// Check for class definition
					const classMatch = trimmed.match(/^class\s+(\w+)\s*\(([^)]+)\)\s*:/);
					if (classMatch) {
						const className = classMatch[1];
						const parents = classMatch[2].split(',').map(p => p.trim());

						currentClass = {
							name: className,
							parents: parents,
							fields: new Map(),
							typeValue: null
						};
						this.classes.set(className, currentClass);

						for (const parent of parents) {
							if (!this.inheritance.has(className)) {
								this.inheritance.set(className, []);
							}
							this.inheritance.get(className).push(parent);
						}

						classBodyIndent = null; // Will be set on first body line
						continue;
					}

					// Any other indent-0 content ends the class
					currentClass = null;
					classBodyIndent = null;
					continue;
				}

				// Inside a class - determine body indent from first indented line
				if (currentClass) {
					if (classBodyIndent === null) {
						classBodyIndent = indent;
					}

					// Only process lines at class body level (not nested deeper like method bodies)
					if (indent !== classBodyIndent) continue;

					// Property getter with FieldRole annotation (for outputs)
					if (trimmed === '@property') {
						// Look ahead for the def line
						const nextLine = lines[i + 1];
						if (nextLine) {
							const nextTrimmed = nextLine.trim();
							const defMatch = nextTrimmed.match(/^def\s+(\w+)\s*\(self\)\s*->\s*Annotated\[([^,]+),\s*FieldRole\.(\w+)\s*\]/);
							if (defMatch) {
								const [, methodName, returnType, role] = defMatch;
								currentClass.fields.set(methodName, {
									name: methodName,
									type: this._parseType(returnType.trim()),
									role: role.toLowerCase(),
									default: undefined,
									isProperty: true
								});
								i++; // Skip the def line
								continue;
							}
						}
						continue;
					}

					// Skip decorators and method definitions
					if (trimmed.startsWith('@') || trimmed.startsWith('def ')) continue;

					// Field definition with Annotated
					const fieldMatch = trimmed.match(/^(\w+)\s*:\s*Annotated\[(.+),\s*FieldRole\.(\w+)\s*\]\s*(?:=\s*(.+))?$/);
					if (fieldMatch) {
						const [, fieldName, fieldType, role, defaultVal] = fieldMatch;

						const field = {
							name: fieldName,
							type: this._parseType(fieldType),
							role: role.toLowerCase(),
							default: this._parseDefault(defaultVal)
						};

						// Extract type discriminator value
						if (fieldName === 'type' && role === 'CONSTANT') {
							const literalMatch = fieldType.match(/Literal\["([^"]+)"\]/);
							if (literalMatch) {
								currentClass.typeValue = literalMatch[1];
							}
						}

						currentClass.fields.set(fieldName, field);
						continue;
					}

					// Simple field (no Annotated) - only if not already defined
					const simpleMatch = trimmed.match(/^(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$/);
					if (simpleMatch) {
						const [, fieldName, fieldType, defaultVal] = simpleMatch;
						if (!currentClass.fields.has(fieldName)) {
							currentClass.fields.set(fieldName, {
								name: fieldName,
								type: this._parseType(fieldType.trim()),
								role: 'input',
								default: this._parseDefault(defaultVal)
							});
						}
					}
				}
			}
		}

		_parseType(typeStr) {
			typeStr = typeStr.trim();

			if (typeStr.startsWith('Literal[')) {
				const match = typeStr.match(/Literal\["([^"]+)"\]/);
				return { kind: 'literal', value: match ? match[1] : '' };
			}

			if (typeStr.startsWith('Optional[')) {
				const inner = this._extractBracketContent(typeStr, 'Optional[');
				return { kind: 'optional', inner: this._parseType(inner) };
			}

			if (typeStr.startsWith('Union[')) {
				const inner = this._extractBracketContent(typeStr, 'Union[');
				const types = this._splitTopLevel(inner, ',');
				return { kind: 'union', types: types.map(t => this._parseType(t.trim())) };
			}

			if (typeStr.startsWith('List[')) {
				const inner = this._extractBracketContent(typeStr, 'List[');
				return { kind: 'list', inner: this._parseType(inner) };
			}

			if (typeStr.startsWith('Dict[')) {
				const inner = this._extractBracketContent(typeStr, 'Dict[');
				const parts = this._splitTopLevel(inner, ',');
				return { kind: 'dict', key: this._parseType(parts[0]?.trim() || 'str'), value: this._parseType(parts[1]?.trim() || 'Any') };
			}

			if (this.typeAliases.has(typeStr)) {
				return this._parseType(this.typeAliases.get(typeStr));
			}

			return { kind: 'basic', name: typeStr };
		}

		_extractBracketContent(str, prefix) {
			const start = prefix.length;
			let depth = 1;
			let i = start;
			while (i < str.length && depth > 0) {
				if (str[i] === '[') depth++;
				else if (str[i] === ']') depth--;
				i++;
			}
			return str.substring(start, i - 1);
		}

		_splitTopLevel(str, delimiter) {
			const result = [];
			let depth = 0;
			let current = '';
			for (const char of str) {
				if (char === '[' || char === '(') depth++;
				else if (char === ']' || char === ')') depth--;
				else if (char === delimiter && depth === 0) {
					result.push(current);
					current = '';
					continue;
				}
				current += char;
			}
			if (current) result.push(current);
			return result;
		}

		_parseDefault(defaultStr) {
			if (!defaultStr) return undefined;
			defaultStr = defaultStr.trim();

			if (defaultStr === 'None') return null;
			if (defaultStr === 'True') return true;
			if (defaultStr === 'False') return false;
			if (/^-?\d+$/.test(defaultStr)) return parseInt(defaultStr);
			if (/^-?\d+\.\d+$/.test(defaultStr)) return parseFloat(defaultStr);
			if (/^["']/.test(defaultStr)) return defaultStr.slice(1, -1);

			if (this.constants.has(defaultStr)) {
				return this.constants.get(defaultStr);
			}

			return defaultStr;
		}

		_resolveInheritance() {
			for (const [className, classInfo] of this.classes) {
				const allFields = new Map();

				const visited = new Set();
				const collectParentFields = (name) => {
					if (visited.has(name)) return;
					visited.add(name);

					const parents = this.inheritance.get(name) || [];
					for (const parent of parents) {
						collectParentFields(parent);
						const parentClass = this.classes.get(parent);
						if (parentClass) {
							for (const [fieldName, field] of parentClass.fields) {
								if (!allFields.has(fieldName)) {
									allFields.set(fieldName, { ...field });
								}
							}
						}
					}
				};

				collectParentFields(className);

				for (const [fieldName, field] of classInfo.fields) {
					allFields.set(fieldName, field);
				}

				classInfo.fields = allFields;
			}
		}

		// Extract base type name, stripping Optional/Union/Annotated wrappers
		_getBaseType(typeInfo) {
			if (!typeInfo) return 'Any';

			switch (typeInfo.kind) {
				case 'basic':
					return typeInfo.name;

				case 'optional':
					return this._getBaseType(typeInfo.inner);

				case 'union': {
					const types = typeInfo.types
						.map(t => this._getBaseType(t))
						.filter(t => t !== 'None' && t !== 'NoneType');
					// Return single type or joined types
					return types.length === 1 ? types[0] : types.join('|');
				}

				case 'list':
					return `List[${this._getBaseType(typeInfo.inner)}]`;

				case 'dict':
					return 'Dict';

				case 'literal':
					return typeInfo.value;

				default:
					return 'Any';
			}
		}

		// Check if two types are compatible for edge connections
		_typesCompatible(outputType, inputType) {
			const outBase = this._getBaseType(outputType);
			const inBase = this._getBaseType(inputType);

			// Any matches anything
			if (outBase === 'Any' || inBase === 'Any') return true;

			// Direct match
			if (outBase === inBase) return true;

			// Check if output is one of input's union types
			if (inBase.includes('|')) {
				const inTypes = inBase.split('|').map(t => t.trim());
				if (inTypes.includes(outBase)) return true;
			}

			// Check if output union contains input type
			if (outBase.includes('|')) {
				const outTypes = outBase.split('|').map(t => t.trim());
				if (outTypes.includes(inBase)) return true;
			}

			// int can connect to Union[int, ...] style inputs
			if (/^int$/.test(outBase) && inBase.includes('int')) return true;

			return false;
		}

		// Get node configurations for SchemaGraph
		getNodeConfigs() {
			const configs = new Map();

			for (const [className, classInfo] of this.classes) {
				if (!classInfo.typeValue) continue;

				const inputs = [];
				const outputs = [];
				const properties = {};

				for (const [fieldName, field] of classInfo.fields) {
					if (fieldName === 'type') continue;

					// Skip property getters from input slots (they're outputs)
					if (field.isProperty) {
						outputs.push({
							name: fieldName,
							type: this._getBaseType(field.type),
							fieldType: field.type,
							isMulti: false
						});
						continue;
					}

					const slotInfo = {
						name: fieldName,
						type: this._getBaseType(field.type),
						fieldType: field.type,
						isMulti: false
					};

					switch (field.role) {
						case 'input':
							inputs.push(slotInfo);
							if (field.default !== undefined) {
								properties[fieldName] = field.default;
							}
							break;

						case 'output':
							outputs.push(slotInfo);
							break;

						case 'multi_input':
							slotInfo.isMulti = true;
							inputs.push(slotInfo);
							break;

						case 'multi_output':
							slotInfo.isMulti = true;
							outputs.push(slotInfo);
							break;
					}
				}

				configs.set(classInfo.typeValue, {
					className: classInfo.name,
					typeValue: classInfo.typeValue,
					inputs,
					outputs,
					properties
				});
			}

			return configs;
		}

		_typeToString(typeInfo) {
			if (!typeInfo) return 'any';
			switch (typeInfo.kind) {
				case 'basic': return typeInfo.name;
				case 'optional': return `Optional[${this._typeToString(typeInfo.inner)}]`;
				case 'list': return `List[${this._typeToString(typeInfo.inner)}]`;
				case 'union': return typeInfo.types.map(t => this._typeToString(t)).join('|');
				case 'dict': return `Dict`;
				case 'literal': return typeInfo.value;
				default: return 'any';
			}
		}
	}

	// ====================================================================
	// WorkflowExtension - Main extension class
	// ====================================================================

	class WorkflowExtension {
		constructor(schemaGraph) {
			this.schemaGraph = schemaGraph;
			this.parser = new WorkflowSchemaParser();
			this.schemaName = null;
			this.nodeConfigs = null;
			this.parsedClasses = null;
		}

		registerSchema(schemaName, schemaCode) {
			try {
				this.schemaName = schemaName;
				this.parsedClasses = this.parser.parse(schemaCode);
				this.nodeConfigs = this.parser.getNodeConfigs();

				// Register with SchemaGraph's schema system
				if (this.schemaGraph.api && this.schemaGraph.api.schema) {
					try {
						this.schemaGraph.api.schema.register(schemaName, schemaCode, 'int', 'Workflow');
					} catch (e) {
						console.warn('Standard schema registration failed, using custom handling:', e.message);
					}
				}

				console.log(`✅ Workflow schema "${schemaName}" parsed: ${this.nodeConfigs.size} node types`);
				return true;

			} catch (e) {
				console.error('Failed to register workflow schema:', e);
				return false;
			}
		}

		import(workflow) {
			if (!this.schemaName || !this.nodeConfigs) {
				console.error('Schema not registered');
				return null;
			}

			const nodes = workflow.nodes || [];
			const edges = workflow.edges || [];
			const graphNodes = [];

			// Create nodes
			nodes.forEach((workflowNode, index) => {
				const typeName = workflowNode.type;
				const config = this.nodeConfigs.get(typeName);

				if (!config) {
					console.warn(`Unknown node type: ${typeName}`);
					graphNodes[index] = null;
					return;
				}

				// Calculate position
				const pos = workflowNode.position || workflowNode.extra?.position || this._calcPosition(index);
				const x = pos.x ?? pos[0] ?? 0;
				const y = pos.y ?? pos[1] ?? 0;

				// Try to create node via SchemaGraph API
				const fullTypeName = `${this.schemaName}.${config.className}`;
				let graphNode = null;

				if (this.schemaGraph.api?.node?.create) {
					graphNode = this.schemaGraph.api.node.create(fullTypeName, x, y);
				}

				// If SchemaGraph couldn't create it, create a custom node
				if (!graphNode) {
					graphNode = this._createCustomNode(config, workflowNode, index, x, y);
				}

				if (graphNode) {
					// Ensure slots are properly set up (SchemaGraph may create different structure)
					this._ensureSlots(graphNode, config);

					// Expand multi-slots
					this._expandMultiSlots(graphNode, config, workflowNode);

					// Apply metadata
					graphNode.workflowIndex = index;
					graphNode.workflowType = typeName;
					graphNode.isWorkflowNode = true;
					graphNode.schemaName = this.schemaName;

					if (workflowNode.extra) {
						const extra = typeof workflowNode.extra === 'string'
							? JSON.parse(workflowNode.extra)
							: workflowNode.extra;
						if (extra.name) graphNode.title = extra.name;
						if (extra.color) graphNode.color = extra.color;
					}

					graphNodes[index] = graphNode;
				}
			});

			// Create edges with type validation
			edges.forEach(edge => {
				const sourceNode = graphNodes[edge.source];
				const targetNode = graphNodes[edge.target];

				if (!sourceNode || !targetNode) return;

				const sourceSlotIdx = this._findSlot(sourceNode.outputs, edge.source_slot);
				const targetSlotIdx = this._findSlot(targetNode.inputs, edge.target_slot);

				if (sourceSlotIdx === -1 || targetSlotIdx === -1) {
					console.warn(`Slot not found: ${edge.source_slot} -> ${edge.target_slot}`);
					return;
				}

				// Validate type compatibility
				const sourceSlot = sourceNode.outputs[sourceSlotIdx];
				const targetSlot = targetNode.inputs[targetSlotIdx];

				if (!this._slotsCompatible(sourceSlot, targetSlot)) {
					console.warn(`Type mismatch: ${sourceSlot.type} -> ${targetSlot.type} (${edge.source_slot} -> ${edge.target_slot})`);
					// Still create the edge, but warn
				}

				if (this.schemaGraph.api?.link?.create) {
					this.schemaGraph.api.link.create(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx);
				} else if (sourceNode.connect) {
					sourceNode.connect(sourceSlotIdx, targetNode, targetSlotIdx);
				}
			});

			return graphNodes;
		}

		_slotsCompatible(sourceSlot, targetSlot) {
			if (!sourceSlot || !targetSlot) return true;

			// Use fieldType if available, otherwise parse type string
			const sourceType = sourceSlot.fieldType || { kind: 'basic', name: sourceSlot.type };
			const targetType = targetSlot.fieldType || { kind: 'basic', name: targetSlot.type };

			return this.parser._typesCompatible(sourceType, targetType);
		}

		_createCustomNode(config, workflowNode, index, x, y) {
			const node = {
				id: Date.now() + index,
				type: `${this.schemaName}.${config.typeValue}`,
				title: this._formatTitle(config.typeValue),
				pos: [x, y],
				size: [220, 80],
				color: this._getColor(config.typeValue),
				inputs: [],
				outputs: [],
				properties: { ...config.properties },
				isWorkflowNode: true,
				modelName: config.typeValue,
				schemaName: this.schemaName
			};

			// Add inputs with type info
			config.inputs.forEach(input => {
				node.inputs.push({
					name: input.name,
					type: input.type,
					fieldType: input.fieldType,
					link: null
				});
			});

			// Add outputs with type info
			config.outputs.forEach(output => {
				node.outputs.push({
					name: output.name,
					type: output.type,
					fieldType: output.fieldType,
					links: []
				});
			});

			// Add to graph
			if (this.schemaGraph.graph?.add) {
				this.schemaGraph.graph.add(node);
			}

			return node;
		}

		_ensureSlots(node, config) {
			// Ensure inputs array exists and has all required slots
			if (!node.inputs) node.inputs = [];
			for (const input of config.inputs) {
				const exists = node.inputs.some(s => s && s.name === input.name);
				if (!exists) {
					if (node.addInput) {
						node.addInput(input.name, input.type);
					} else {
						node.inputs.push({
							name: input.name,
							type: input.type,
							fieldType: input.fieldType,
							link: null
						});
					}
				}
			}

			// Ensure outputs array exists and has all required slots
			if (!node.outputs) node.outputs = [];
			for (const output of config.outputs) {
				const exists = node.outputs.some(s => s && s.name === output.name);
				if (!exists) {
					if (node.addOutput) {
						node.addOutput(output.name, output.type);
					} else {
						node.outputs.push({
							name: output.name,
							type: output.type,
							fieldType: output.fieldType,
							links: []
						});
					}
				}
			}
		}

		_expandMultiSlots(node, config, workflowNode) {
			// Expand multi-inputs
			for (const input of config.inputs) {
				if (!input.isMulti) continue;

				const data = workflowNode[input.name];
				if (Array.isArray(data)) {
					const baseIdx = this._findSlot(node.inputs, input.name);
					if (baseIdx !== -1 && node.removeInput) {
						node.removeInput(baseIdx);
					} else if (baseIdx !== -1 && node.inputs) {
						node.inputs.splice(baseIdx, 1);
					}

					data.forEach(key => {
						const slotName = `${input.name}.${key}`;
						if (node.addInput) {
							node.addInput(slotName, input.type);
						} else if (node.inputs) {
							node.inputs.push({
								name: slotName,
								type: input.type,
								fieldType: input.fieldType,
								link: null
							});
						}
					});
				}
			}

			// Expand multi-outputs
			for (const output of config.outputs) {
				if (!output.isMulti) continue;

				const data = workflowNode[output.name];
				if (Array.isArray(data)) {
					const baseIdx = this._findSlot(node.outputs, output.name);
					if (baseIdx !== -1 && node.removeOutput) {
						node.removeOutput(baseIdx);
					} else if (baseIdx !== -1 && node.outputs) {
						node.outputs.splice(baseIdx, 1);
					}

					data.forEach(key => {
						const slotName = `${output.name}.${key}`;
						if (node.addOutput) {
							node.addOutput(slotName, output.type);
						} else if (node.outputs) {
							node.outputs.push({
								name: slotName,
								type: output.type,
								fieldType: output.fieldType,
								links: []
							});
						}
					});
				}
			}
		}

		export(baseWorkflow = {}) {
			if (!this.schemaName) {
				console.error('Schema not registered');
				return null;
			}

			const nodes = [];
			const edges = [];
			const nodeIndexMap = new Map();

			const graphNodes = this.schemaGraph.graph?.nodes ||
				(this.schemaGraph.api?.node?.list ? this.schemaGraph.api.node.list() : []);

			// Export nodes
			graphNodes.forEach((graphNode) => {
				if (!this._isWorkflowNode(graphNode)) return;

				const newIndex = nodes.length;
				nodeIndexMap.set(graphNode.id, newIndex);

				const node = {
					type: graphNode.modelName || graphNode.workflowType || this._extractTypeName(graphNode.type),
					extra: {
						name: graphNode.title,
						color: graphNode.color
					},
					position: {
						x: Math.round(graphNode.pos?.[0] || 0),
						y: Math.round(graphNode.pos?.[1] || 0)
					}
				};

				if (graphNode.properties) {
					Object.assign(node, graphNode.properties);
				}

				nodes.push(node);
			});

			// Export edges
			const links = this.schemaGraph.graph?.links || {};
			const linksArray = Array.isArray(links) ? links : Object.values(links);

			linksArray.forEach(link => {
				if (!link) return;

				const sourceNode = this._getNodeById(graphNodes, link.origin_id);
				const targetNode = this._getNodeById(graphNodes, link.target_id);

				if (!sourceNode || !targetNode) return;
				if (!this._isWorkflowNode(sourceNode) || !this._isWorkflowNode(targetNode)) return;

				const sourceIndex = nodeIndexMap.get(link.origin_id);
				const targetIndex = nodeIndexMap.get(link.target_id);

				if (sourceIndex === undefined || targetIndex === undefined) return;

				const sourceSlot = sourceNode.outputs?.[link.origin_slot]?.name || 'output';
				const targetSlot = targetNode.inputs?.[link.target_slot]?.name || 'input';

				edges.push({
					type: 'edge',
					source: sourceIndex,
					target: targetIndex,
					source_slot: sourceSlot,
					target_slot: targetSlot
				});
			});

			return {
				type: baseWorkflow.type || 'workflow',
				info: baseWorkflow.info,
				options: baseWorkflow.options,
				nodes,
				edges
			};
		}

		_isWorkflowNode(node) {
			if (!node) return false;
			if (node.isWorkflowNode) return true;
			if (node.schemaName === this.schemaName) return true;
			if (node.type?.startsWith(this.schemaName + '.')) return true;
			return false;
		}

		_extractTypeName(fullType) {
			if (!fullType) return 'unknown';
			const parts = fullType.split('.');
			return parts[parts.length - 1];
		}

		_getNodeById(nodes, id) {
			for (const node of nodes) {
				if (node.id === id) return node;
			}
			return null;
		}

		_findSlot(slots, name) {
			if (!slots || !name) return 0;

			for (let i = 0; i < slots.length; i++) {
				if (slots[i].name === name) return i;
			}

			const baseName = name.split('.')[0];
			for (let i = 0; i < slots.length; i++) {
				if (slots[i].name === baseName || slots[i].name.startsWith(baseName + '.')) {
					return i;
				}
			}

			return -1; // Changed from 0 to -1 for proper "not found" handling
		}

		_calcPosition(index) {
			const col = index % 5;
			const row = Math.floor(index / 5);
			return { x: 100 + col * 250, y: 100 + row * 150 };
		}

		_formatTitle(type) {
			return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
		}

		_getColor(type) {
			if (type.endsWith('_config')) return '#2d5a87';
			if (type.includes('node')) return '#5a7d2d';
			return '#5a5a5a';
		}

		getNodeConfig(typeName) {
			return this.nodeConfigs?.get(typeName);
		}

		getNodeTypes() {
			if (!this.nodeConfigs) return [];
			return Array.from(this.nodeConfigs.keys());
		}

		// Debug helper: list all parsed classes and their fields
		debug() {
			console.group('Workflow Schema Debug');
			console.log('Constants:', Object.fromEntries(this.parser.constants));
			console.log('Type Aliases:', Object.fromEntries(this.parser.typeAliases));

			for (const [name, cls] of this.parsedClasses) {
				console.group(`Class: ${name} (type=${cls.typeValue})`);
				for (const [fname, field] of cls.fields) {
					const inherited = cls.fields.get(fname) !== field ? ' [inherited]' : '';
					console.log(`  ${fname}: ${this.parser._typeToString(field.type)} [${field.role}]${inherited}`);
				}
				console.groupEnd();
			}
			console.groupEnd();

			// Also show node configs
			console.group('Node Configs');
			for (const [typeName, config] of this.nodeConfigs) {
				console.log(`${typeName}: inputs=[${config.inputs.map(i => i.name).join(', ')}] outputs=[${config.outputs.map(o => o.name).join(', ')}]`);
			}
			console.groupEnd();
		}
	}

	// ====================================================================
	// Register extension with SchemaGraph
	// ====================================================================

	function registerWorkflowExtension(schemaGraphApp) {
		const extension = new WorkflowExtension(schemaGraphApp);

		schemaGraphApp.api = schemaGraphApp.api || {};
		schemaGraphApp.api.workflow = {
			registerSchema: (name, code) => extension.registerSchema(name, code),
			import: (workflow, schemaName) => extension.import(workflow),
			export: (schemaName, baseWorkflow) => extension.export(baseWorkflow),
			getNodeConfig: (typeName) => extension.getNodeConfig(typeName),
			getNodeTypes: () => extension.getNodeTypes(),
			debug: () => extension.debug()
		};

		console.log('✅ Workflow extension registered');
		return extension;
	}

	// Export
	window.registerWorkflowExtension = registerWorkflowExtension;
	window.WorkflowSchemaParser = WorkflowSchemaParser;
	window.WorkflowExtension = WorkflowExtension;

})();
