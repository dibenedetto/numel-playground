# mesh_toolkit

import json
import pymeshlab


from   typing    import Optional


class MeshToolkit:
	"""3D Mesh Processing Toolkit — shared workspace that persists across tool calls.

## Quick reference

| Method                   | Purpose                                    | When to use                                    |
|--------------------------|--------------------------------------------|------------------------------------------------|
| load_mesh(path)          | Import a 3D model into the workspace       | Always first — nothing works without a mesh    |
| save_mesh(path)          | Export the current mesh to a file           | When done processing; format from extension    |
| get_info()               | Vertex/face counts, topology, bounding box  | Before and after operations to verify results  |
| repair()                 | Fix duplicates, non-manifold, close holes   | Before decimation — bad topology = bad results |
| decimate(target_percent) | Reduce polygon count (quadric collapse)     | To lower face count; 0.5 = keep 50% of faces  |
| smooth(method, iters)    | Reduce surface noise / jagged edges         | After decimation to soften artifacts           |
| remesh(target_edge_len)  | Create uniform triangulation                | When triangle quality matters (simulation)     |
| recompute_normals()      | Fix face/vertex normals after edits         | After any geometry-modifying operation         |
| remove_small_components()| Delete floating fragments                   | After repair or decimation                     |
| simplify_for_mobile()    | One-step: repair+decimate+smooth+normals    | Quick optimization, less control               |
| list_meshes()            | Show all loaded mesh layers                 | When working with multi-part models            |
| set_current_mesh(index)  | Switch active mesh layer                    | To process a specific part of a multi-mesh     |
| apply_filter(name, ...)  | Run any PyMeshLab filter by name            | Advanced ops not covered by other methods      |
| export_preview()         | Mesh as base64 data URL for inline preview  | For visual inspection in UI preview nodes      |

## Key concepts

- **Workspace**: All operations act on the *current mesh* in the MeshSet. If you load multiple
  meshes, use `list_meshes` and `set_current_mesh` to switch between them.
- **target_percent**: Fraction of faces to *keep*, not remove. 0.3 keeps 30%, removes 70%.
- **Texture-aware decimation**: Automatically used when the mesh has texture coords. Preserves
  UV mapping so textures don't distort.
- **Operation order matters**: Always repair before decimation (bad topology causes artifacts).
  Always recompute normals after geometry changes (lighting/shading depends on correct normals).

## Common workflows

**Optimization (reduce file size / poly count):**
load_mesh → get_info → repair → decimate(0.3) → smooth(taubin, 2) → recompute_normals → remove_small_components → get_info → save_mesh

**Quality inspection:**
load_mesh → get_info (check is_two_manifold, holes, boundary_edges) → repair if needed → get_info

**Format conversion:**
load_mesh("model.glb") → save_mesh("model.obj")

**Visual preview pipeline:**
load_mesh → [any operations] → export_preview → (wire to preview_flow with hint=model3d)

## Supported formats

- **Import**: OBJ, PLY, STL, GLB, GLTF, FBX, DAE, 3DS, OFF, and more
- **Export**: OBJ, PLY, STL, DAE, OFF, X3D (GLB/GLTF export is NOT supported)

## Pitfalls to avoid

- Do NOT decimate below 1% — extreme reduction produces unusable geometry.
- Do NOT smooth more than 5-10 iterations — over-smoothing destroys detail.
- Do NOT skip repair before decimation on meshes from 3D scans — they always have issues.
- Do NOT call save_mesh with a .glb/.gltf extension — it will fail. Use .obj or .ply instead.
- remesh changes face count unpredictably — it creates uniform triangles, not fewer triangles.

## Example workflow

Ask the user the path of mesh to operate on, load the mesh, decimate it to 30% of the original faces, apply light smoothing, preview after each step, and export the final mesh to a file:

{
  "type": "workflow",
  "nodes": [
    { "type": "toolkit_config", "name": "contrib.toolkits.mesh_toolkit" },
    { "type": "user_input_flow", "query": "Enter the path of the mesh to process (e.g. '/data/model.obj'):" },
    { "type": "transform_flow", "lang": "python", "script": "output = { 'path': str(input) }" },
    { "type": "start_flow" },
    { "type": "tool_flow", "method": "load_mesh" },
    { "type": "tool_flow", "method": "export_preview" },
    { "type": "preview_flow", "hint": "model3d" },
    { "type": "tool_flow", "method": "decimate", "args": { "target_percent": 0.7 } },
    { "type": "tool_flow", "method": "export_preview" },
    { "type": "preview_flow", "hint": "model3d" },
    { "type": "tool_flow", "method": "smooth", "args": { "iterations": 5 } },
    { "type": "tool_flow", "method": "export_preview" },
    { "type": "preview_flow", "hint": "model3d" },
    { "type": "tool_flow", "method": "save_mesh", "args": { "path": "docs/mesh_output.ply" } },
    { "type": "end_flow" }
  ],
  "edges": [
    { "source": 0, "target": 4, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 5, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 7, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 8, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 10, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 11, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 13, "source_slot": "config", "target_slot": "config" },
    { "source": 4, "target": 5, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 5, "target": 6, "source_slot": "output", "target_slot": "flow_in" },
    { "source": 6, "target": 7, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 7, "target": 8, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 8, "target": 9, "source_slot": "output", "target_slot": "flow_in" },
    { "source": 9, "target": 10, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 10, "target": 11, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 11, "target": 12, "source_slot": "output", "target_slot": "flow_in" },
    { "source": 12, "target": 13, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 13, "target": 14, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 3, "target": 1, "source_slot": "flow_out","target_slot": "flow_in" },
    { "source": 1, "target": 2, "source_slot": "message", "target_slot": "input" },
    { "source": 2, "target": 4, "source_slot": "output", "target_slot": "args" }
  ]
}
"""

	__toolkit__ = True

	def __init__(self):
		self._ms = pymeshlab.MeshSet()

	def load_mesh(self, path: str) -> str:
		"""Load a 3D mesh file into the workspace. Supports OBJ, PLY, STL, GLB, GLTF, FBX, DAE, and more.

		Args:
			path: File path to the mesh (e.g. '/data/model.obj')

		Returns:
			Summary string with vertex count, face count, and bounding box.
		"""
		self._ms.load_new_mesh(path)
		return self._mesh_summary()

	def save_mesh(self, path: str, save_textures: bool = True) -> str:
		"""Save the current mesh to a file. Supported formats: OBJ, PLY, STL, DAE, OFF, X3D.

		Args:
			path: Output file path (format inferred from extension)
			save_textures: Whether to save texture files alongside the mesh (default: True)

		Returns:
			Confirmation with file path and final mesh stats.
		"""
		self._ms.save_current_mesh(path, save_textures=save_textures)
		m = self._ms.current_mesh()
		return f"Saved to {path} ({m.vertex_number()} vertices, {m.face_number()} faces)"

	def get_info(self) -> str:
		"""Get detailed information about the current mesh: vertex/face/edge counts, bounding box, topology, and texture status.

		Returns:
			JSON string with mesh statistics.
		"""
		m = self._ms.current_mesh()
		geo = self._ms.get_geometric_measures()
		topo = self._ms.get_topological_measures()
		bbox = m.bounding_box()
		info = {
			"vertices"             : m.vertex_number(),
			"faces"                : m.face_number(),
			"edges"                : m.edge_number(),
			"has_vertex_colors"    : m.has_vertex_color(),
			"has_texture_coords"   : m.has_wedge_tex_coord(),
			"texture_count"        : m.texture_number(),
			"is_point_cloud"       : m.is_point_cloud(),
			"bounding_box"         : {"min": bbox.min().tolist(), "max": bbox.max().tolist()},
			"surface_area"         : geo.get("surface_area", None),
			"mesh_volume"          : geo.get("mesh_volume", None),
			"avg_edge_length"      : geo.get("avg_edge_length", None),
			"connected_components" : topo.get("connected_components_number", None),
			"boundary_edges"       : topo.get("boundary_edges", None),
			"holes"                : topo.get("number_holes", None),
			"is_two_manifold"      : topo.get("is_mesh_two_manifold", None),
			"genus"                : topo.get("genus", None),
		}
		return json.dumps(info, indent=2)

	def repair(self, close_holes: bool = True, max_hole_size: int = 30) -> str:
		"""Repair common mesh issues: remove duplicates, fix non-manifold geometry, and optionally close holes.

		Args:
			close_holes: Whether to close holes in the mesh (default: True)
			max_hole_size: Maximum hole size in edges to close (default: 30)

		Returns:
			Summary of repairs performed and resulting mesh stats.
		"""
		m = self._ms.current_mesh()
		before = m.face_number()
		self._ms.meshing_remove_duplicate_faces()
		self._ms.meshing_remove_duplicate_vertices()
		self._ms.meshing_remove_null_faces()
		self._ms.meshing_remove_unreferenced_vertices()
		self._ms.meshing_repair_non_manifold_edges()
		self._ms.meshing_repair_non_manifold_vertices()
		if close_holes:
			self._ms.meshing_close_holes(maxholesize=max_hole_size)
		m = self._ms.current_mesh()
		after = m.face_number()
		return f"Repair complete. Faces: {before} → {after}. {self._mesh_summary()}"

	def decimate(self, target_percent: float = 0.5, preserve_texture: bool = True, preserve_boundary: bool = True, preserve_normals: bool = True, quality_threshold: float = 0.3) -> str:
		"""Reduce polygon count using quadric edge collapse decimation.

		Args:
			target_percent: Target face count as fraction of original (0.5 = keep 50%, 0.25 = keep 25%)
			preserve_texture: Use texture-aware decimation if mesh has texture coords (default: True)
			preserve_boundary: Preserve mesh boundary edges (default: True)
			preserve_normals: Prevent face normal flipping (default: True)
			quality_threshold: Quality threshold for edge collapse, lower = more aggressive (default: 0.3)

		Returns:
			Summary with face count before and after decimation.
		"""
		m = self._ms.current_mesh()
		before = m.face_number()
		has_tex = m.has_wedge_tex_coord()
		if has_tex and preserve_texture:
			self._ms.meshing_decimation_quadric_edge_collapse_with_texture(
				targetperc       = target_percent,
				qualitythr       = quality_threshold,
				preserveboundary = preserve_boundary,
				preservenormal   = preserve_normals,
				optimalplacement = True,
			)
		else:
			self._ms.meshing_decimation_quadric_edge_collapse(
				targetperc       = target_percent,
				qualitythr       = quality_threshold,
				preserveboundary = preserve_boundary,
				preservenormal   = preserve_normals,
				optimalplacement = True,
			)
		m = self._ms.current_mesh()
		after = m.face_number()
		reduction = (1 - after / before) * 100 if before > 0 else 0
		return f"Decimation complete. Faces: {before} → {after} ({reduction:.1f}% reduction). {self._mesh_summary()}"

	def smooth(self, method: str = "taubin", iterations: int = 3) -> str:
		"""Apply smoothing to reduce surface noise and decimation artifacts.

		Args:
			method: Smoothing method - 'taubin' (volume-preserving, recommended), 'laplacian', or 'hc' (default: 'taubin')
			iterations: Number of smoothing iterations (default: 3)

		Returns:
			Confirmation with method used and iteration count.
		"""
		if method == "laplacian":
			self._ms.apply_coord_laplacian_smoothing(stepsmoothnum=iterations)
		elif method == "hc":
			self._ms.apply_coord_hc_laplacian_smoothing()
		else:
			self._ms.apply_coord_taubin_smoothing(stepsmoothnum=iterations)
		return f"Applied {method} smoothing ({iterations} iterations). {self._mesh_summary()}"

	def remesh(self, target_edge_length: Optional[float] = None, iterations: int = 5, adaptive: bool = False) -> str:
		"""Remesh to create uniform triangulation. Useful for cleaning up irregular meshes.

		Args:
			target_edge_length: Target edge length (auto-computed if None)
			iterations: Number of remeshing iterations (default: 5)
			adaptive: Adapt edge length to local curvature (default: False)

		Returns:
			Summary with face count before and after remeshing.
		"""
		m = self._ms.current_mesh()
		before = m.face_number()
		kwargs = dict(iterations=iterations, adaptive=adaptive)
		if target_edge_length is not None:
			kwargs["targetlen"] = pymeshlab.PureValue(target_edge_length)
		self._ms.meshing_isotropic_explicit_remeshing(**kwargs)
		m = self._ms.current_mesh()
		after = m.face_number()
		return f"Remesh complete. Faces: {before} → {after}. {self._mesh_summary()}"

	def recompute_normals(self) -> str:
		"""Recompute vertex and face normals and ensure consistent face orientation.

		Returns:
			Confirmation string.
		"""
		self._ms.meshing_re_orient_faces_coherently()
		self._ms.compute_normal_per_face()
		self._ms.compute_normal_per_vertex()
		return f"Normals recomputed. {self._mesh_summary()}"

	def remove_small_components(self, min_face_count: int = 25) -> str:
		"""Remove small disconnected components (floating fragments) below a face count threshold.

		Args:
			min_face_count: Minimum number of faces a component must have to be kept (default: 25)

		Returns:
			Summary with component removal results.
		"""
		m = self._ms.current_mesh()
		before = m.face_number()
		self._ms.meshing_remove_connected_component_by_face_number(mincomponentsize=min_face_count)
		m = self._ms.current_mesh()
		after = m.face_number()
		removed = before - after
		return f"Removed small components (threshold: {min_face_count} faces). Faces removed: {removed}. {self._mesh_summary()}"

	def simplify_for_mobile(self, target_faces: Optional[int] = None, target_percent: float = 0.25) -> str:
		"""One-step mobile optimization: repair, decimate, smooth, recompute normals, and clean up.

		Args:
			target_faces: Exact target face count (overrides target_percent if set)
			target_percent: Target face count as fraction of original (default: 0.25 = keep 25%)

		Returns:
			Comprehensive summary of all operations performed.
		"""
		steps = []

		# Repair
		self._ms.meshing_remove_duplicate_faces()
		self._ms.meshing_remove_duplicate_vertices()
		self._ms.meshing_remove_null_faces()
		self._ms.meshing_remove_unreferenced_vertices()
		self._ms.meshing_repair_non_manifold_edges()
		self._ms.meshing_repair_non_manifold_vertices()
		steps.append("Repaired mesh geometry")

		m = self._ms.current_mesh()
		before = m.face_number()
		has_tex = m.has_wedge_tex_coord()

		# Decimate
		if target_faces is not None:
			perc = target_faces / before if before > 0 else 0.25
		else:
			perc = target_percent
		if has_tex:
			self._ms.meshing_decimation_quadric_edge_collapse_with_texture(
				targetperc=perc, qualitythr=0.3, preserveboundary=True, preservenormal=True, optimalplacement=True,
			)
		else:
			self._ms.meshing_decimation_quadric_edge_collapse(
				targetperc=perc, qualitythr=0.3, preserveboundary=True, preservenormal=True, optimalplacement=True,
			)
		m = self._ms.current_mesh()
		after_decimate = m.face_number()
		steps.append(f"Decimated: {before} → {after_decimate} faces ({(1 - after_decimate / before) * 100:.1f}% reduction)")

		# Light smooth
		self._ms.apply_coord_taubin_smoothing(stepsmoothnum=2)
		steps.append("Applied Taubin smoothing (2 iterations)")

		# Normals
		self._ms.meshing_re_orient_faces_coherently()
		self._ms.compute_normal_per_face()
		self._ms.compute_normal_per_vertex()
		steps.append("Recomputed normals")

		# Clean small components
		self._ms.meshing_remove_connected_component_by_face_number(mincomponentsize=25)
		m = self._ms.current_mesh()
		final = m.face_number()
		steps.append(f"Removed small components (final: {final} faces)")

		return "Mobile optimization complete:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps)) + f"\n{self._mesh_summary()}"

	def list_meshes(self) -> str:
		"""List all meshes currently loaded in the workspace (MeshSet layers).

		Returns:
			List of mesh names with vertex/face counts.
		"""
		results = []
		for i in range(self._ms.mesh_number()):
			self._ms.set_current_mesh(i)
			m = self._ms.current_mesh()
			results.append(f"  [{i}] vertices={m.vertex_number()}, faces={m.face_number()}")
		if not results:
			return "No meshes loaded."
		return f"{len(results)} mesh(es) in workspace:\n" + "\n".join(results)

	def set_current_mesh(self, index: int) -> str:
		"""Switch the active mesh in the workspace when multiple meshes are loaded.

		Args:
			index: 0-based index of the mesh to make active

		Returns:
			Summary of the newly active mesh.
		"""
		self._ms.set_current_mesh(index)
		return f"Active mesh set to [{index}]. {self._mesh_summary()}"

	def apply_filter(self, filter_name: str, **kwargs) -> str:
		"""Apply any filter by name. Use this for advanced operations not covered by other tools.

		Args:
			filter_name: filter name (e.g. 'meshing_decimation_clustering')
			**kwargs: Filter parameters

		Returns:
			Filter result and updated mesh summary.
		"""
		result = self._ms.apply_filter(filter_name, **kwargs)
		summary = self._mesh_summary()
		if result:
			return f"Filter '{filter_name}' applied. Result: {result}. {summary}"
		return f"Filter '{filter_name}' applied. {summary}"

	def export_preview(self, format: str = "ply") -> str:
		"""Export the current mesh as a base64 data URL for inline preview rendering.

		Args:
			format: Export format - 'ply' (default, lightweight) or 'obj'

		Returns:
			Data URL string (data:model/ply;base64,...) suitable for 3D preview.
		"""
		import base64, tempfile, os
		ext = format.lower()
		if ext not in ("ply", "obj", "stl"):
			ext = "ply"
		mime = {"ply": "model/ply", "obj": "model/obj", "stl": "model/stl"}.get(ext, "application/octet-stream")
		with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
			tmp_path = tmp.name
		try:
			self._ms.save_current_mesh(tmp_path)
			with open(tmp_path, "rb") as f:
				raw = f.read()
			b64 = base64.b64encode(raw).decode("ascii")
			return f"data:{mime};base64,{b64}"
		finally:
			os.unlink(tmp_path)

	def _mesh_summary(self) -> str:
		if self._ms.mesh_number() == 0:
			return "No meshes loaded."
		m = self._ms.current_mesh()
		bbox = m.bounding_box()
		dims = bbox.max() - bbox.min()
		return f"Current mesh: {m.vertex_number()} vertices, {m.face_number()} faces, bbox size: [{dims[0]:.3f}, {dims[1]:.3f}, {dims[2]:.3f}]"
