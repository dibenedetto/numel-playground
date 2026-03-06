# mesh_toolkit

import json
import pymeshlab


from   typing    import Optional


class MeshToolkit:
	"""3D Mesh Processing Toolkit.

You have access to a shared mesh workspace that persists across tool calls.
Use load_mesh to import a 3D model, then apply operations like decimation,
smoothing, repair, and remeshing. Use save_mesh to export the result.

Typical workflow for mobile optimization:
1. load_mesh (import the source model)
2. get_info (check vertex/face counts, topology)
3. repair (fix non-manifold edges, duplicates, degenerate faces)
4. decimate (reduce polygon count, preserving texture if present)
5. smooth (optional light pass to reduce decimation artifacts)
6. recompute_normals (fix normals after geometry changes)
7. remove_small_components (clean up floating fragments)
8. get_info (verify final counts)
9. save_mesh (export the optimized model)

Supported import formats: OBJ, PLY, STL, GLB, GLTF, FBX, DAE, 3DS, OFF, and more.
Supported export formats: OBJ, PLY, STL, DAE, OFF, X3D (note: GLB/GLTF export is not supported)."""

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

	def _mesh_summary(self) -> str:
		if self._ms.mesh_number() == 0:
			return "No meshes loaded."
		m = self._ms.current_mesh()
		bbox = m.bounding_box()
		dims = bbox.max() - bbox.min()
		return f"Current mesh: {m.vertex_number()} vertices, {m.face_number()} faces, bbox size: [{dims[0]:.3f}, {dims[1]:.3f}, {dims[2]:.3f}]"
