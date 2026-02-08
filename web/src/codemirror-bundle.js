// CodeMirror 6 bundle for SchemaGraph code editor
import { EditorView, basicSetup } from 'codemirror';
import { EditorState } from '@codemirror/state';
import { python } from '@codemirror/lang-python';
import { javascript } from '@codemirror/lang-javascript';
import { oneDark } from '@codemirror/theme-one-dark';
import { keymap } from '@codemirror/view';
import { indentWithTab } from '@codemirror/commands';

window.CodeEditor = {
	EditorView,
	EditorState,
	basicSetup,
	python,
	javascript,
	oneDark,
	keymap,
	indentWithTab
};
