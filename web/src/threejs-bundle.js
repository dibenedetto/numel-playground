// Three.js r182 bundle for SchemaGraph 3D model preview
// Exports are exposed as window.ThreeViewer by webpack

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PLYLoader } from 'three/addons/loaders/PLYLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';

export {
	THREE,
	OrbitControls,
	GLTFLoader,
	PLYLoader,
	OBJLoader,
	STLLoader,
	FBXLoader
};
