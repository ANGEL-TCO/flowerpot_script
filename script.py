import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import math

# -------------------------
# Helpers
# -------------------------
def clamp(v, a, b): 
    return max(a, min(b, v))

def stitch_rings_tri(mesh, ringA, ringB):
    """
    Stitch two closed rings (lists of vertex indices) with triangles.
    Works even if len(ringA) != len(ringB).
    """
    nA = len(ringA)
    nB = len(ringB)
    if nA < 3 or nB < 3:
        return

    i = 0
    j = 0
    while i < nA and j < nB:
        i2 = (i + 1) % nA
        j2 = (j + 1) % nB

        a_next = float(i + 1) / float(nA)
        b_next = float(j + 1) / float(nB)

        a0 = ringA[i]
        a1 = ringA[i2]
        b0 = ringB[j]
        b1 = ringB[j2]

        if a_next < b_next:
            mesh.Faces.AddFace(a0, a1, b0)
            i += 1
            if i == nA:
                break
        elif b_next < a_next:
            mesh.Faces.AddFace(a0, b1, b0)
            j += 1
            if j == nB:
                break
        else:
            mesh.Faces.AddFace(a0, a1, b1)
            mesh.Faces.AddFace(a0, b1, b0)
            i += 1
            j += 1
            if i == nA or j == nB:
                break

# -------------------------
# Outer wall: ring stack + alternating rotation
# -------------------------
def add_ngon_ring(mesh, base_pt, radius, z, sides, theta_offset=0.0):
    """
    Adds one polygon ring (sides points) to a mesh and returns the list of vertex indices.
    CCW order when viewed from +Z.
    """
    idx = []
    for i in range(sides):
        theta = (2.0 * math.pi * i / float(sides)) + theta_offset
        x = base_pt.X + radius * math.cos(theta)
        y = base_pt.Y + radius * math.sin(theta)
        idx.append(mesh.Vertices.Add(x, y, base_pt.Z + z))
    return idx

def connect_rings_as_tris(mesh, ring0, ring1, flip_diag=False):
    """
    Connect two equal-length rings (same number of sides) using 2 triangles per side.
    flip_diag=False uses diagonal (a-d).
    flip_diag=True  uses diagonal (b-c).
    Alternating this per band prevents the "stretched rows".
    """
    n = len(ring0)
    for i in range(n):
        a = ring0[i]
        b = ring0[(i + 1) % n]
        c = ring1[i]
        d = ring1[(i + 1) % n]

        if not flip_diag:
            # diagonal a-d (your previous version)
            mesh.Faces.AddFace(a, c, d)
            mesh.Faces.AddFace(a, d, b)
        else:
            # diagonal b-c (the alternate split)
            mesh.Faces.AddFace(a, b, c)
            mesh.Faces.AddFace(b, d, c)


# -------------------------
# Full bucket build
# -------------------------
def build_bucket(
    base_pt,
    height,
    inner_radius,
    wall_thickness,
    base_thickness,
    sides=9,
    rings=8,                 # number of polygon rings from bottom to top (>=2)
    inner_circle_segments=180 # smooth inner cylinder resolution
):
    H   = float(height)
    Rin = float(inner_radius)
    T   = float(wall_thickness)
    B   = float(base_thickness)

    B = clamp(B, 0.5, H * 0.9)
    Rout = Rin + T

    sides = max(3, int(sides))
    rings = max(2, int(rings))
    inner_circle_segments = max(24, int(inner_circle_segments))

    # ---- OUTER mesh (polygon rings + triangles) ----
    outer = Rhino.Geometry.Mesh()

    # ring z positions (linear)
    rings_idx = []
    half_step = math.pi / float(sides)   # rotate by half a segment

    for r in range(rings):
        t = float(r) / float(rings - 1)  # 0..1
        z = H * t
        # alternating rotation: even ring = no offset, odd ring = half-step offset
        theta_off = half_step if (r % 2 == 1) else 0.0
        ring = add_ngon_ring(outer, base_pt, Rout, z, sides, theta_off)
        rings_idx.append(ring)

    # connect rings
    for r in range(rings - 1):
        flip = (r % 2 == 0)  # alternate per band
        connect_rings_as_tris(outer, rings_idx[r], rings_idx[r + 1], flip_diag=flip)


    # outer bottom cap (fan)
    outer_center = outer.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z)
    bottom_ring = rings_idx[0]
    for i in range(sides):
        b0 = bottom_ring[i]
        b1 = bottom_ring[(i + 1) % sides]
        outer.Faces.AddFace(outer_center, b1, b0)

    outer.UnifyNormals()
    outer.Normals.ComputeNormals()
    outer.Compact()

    # ---- INNER mesh (perfect circular cylinder) ----
    inner = Rhino.Geometry.Mesh()

    inner_cols = inner_circle_segments
    inner_rows = max(2, rings)  # follow similar vertical density

    inner_rings = []
    for j in range(inner_rows):
        v01 = float(j) / float(inner_rows - 1)
        z = B + (H - B) * v01  # inner starts at floor thickness
        ring = []
        for i in range(inner_cols):
            theta = 2.0 * math.pi * (float(i) / float(inner_cols))
            x = base_pt.X + Rin * math.cos(theta)
            y = base_pt.Y + Rin * math.sin(theta)
            ring.append(inner.Vertices.Add(x, y, base_pt.Z + z))
        inner_rings.append(ring)

    # inner side faces (quads split into tris)
    for j in range(inner_rows - 1):
        r0 = inner_rings[j]
        r1 = inner_rings[j + 1]
        for i in range(inner_cols):
            a = r0[i]
            b = r0[(i + 1) % inner_cols]
            c = r1[i]
            d = r1[(i + 1) % inner_cols]
            inner.Faces.AddFace(a, c, d)
            inner.Faces.AddFace(a, d, b)

    # inner floor cap at z=B
    inner_center = inner.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z + B)
    floor_ring = inner_rings[0]
    for i in range(inner_cols):
        a = floor_ring[i]
        b = floor_ring[(i + 1) % inner_cols]
        inner.Faces.AddFace(inner_center, a, b)

    inner.UnifyNormals()
    inner.Normals.ComputeNormals()
    inner.Compact()

    # ---- Combine: outer + flipped inner + stitched top rim ----
    inner2 = inner.DuplicateMesh()
    inner2.Flip(True, True, True)

    shell = Rhino.Geometry.Mesh()
    shell.Append(outer)
    outer_count = outer.Vertices.Count
    shell.Append(inner2)

    # stitch top rim (outer polygon top ring -> inner circle top ring)
    outer_top_ring = rings_idx[-1]  # polygon ring at z=H
    inner_top_ring = [outer_count + vid for vid in inner_rings[-1]]  # offset into shell

    stitch_rings_tri(shell, outer_top_ring, inner_top_ring)

    shell.UnifyNormals()
    shell.Normals.ComputeNormals()
    shell.Compact()

    return shell

# -------------------------
# UI / Main
# -------------------------
def main():
    rs.EnableRedraw(False)

    base = rs.GetPoint("Bucket center (base)")
    if not base:
        rs.EnableRedraw(True); return
    base_pt = Rhino.Geometry.Point3d(base.X, base.Y, base.Z)

    H = rs.GetReal("Height (mm)", 90.0, 10.0, 2000.0)
    if H is None: rs.EnableRedraw(True); return

    Rin = rs.GetReal("Inner radius (mm)", 55.0, 5.0, 2000.0)
    if Rin is None: rs.EnableRedraw(True); return

    T = rs.GetReal("Wall thickness (mm)", 4.0, 0.5, 200.0)
    if T is None: rs.EnableRedraw(True); return

    B = rs.GetReal("Base thickness (mm)", 5.0, 0.5, H * 0.9)
    if B is None: rs.EnableRedraw(True); return

    sides = rs.GetInteger("Outer polygon sides (e.g., 9)", 9, 3, 64)
    if sides is None: rs.EnableRedraw(True); return

    rings = rs.GetInteger("Number of outer rings (6-20)", 10, 2, 200)
    if rings is None: rs.EnableRedraw(True); return

    inner_segs = rs.GetInteger("Inner circle segments (120-260 recommended)", 200, 24, 800)
    if inner_segs is None: rs.EnableRedraw(True); return

    mesh = build_bucket(
        base_pt=base_pt,
        height=H,
        inner_radius=Rin,
        wall_thickness=T,
        base_thickness=B,
        sides=sides,
        rings=rings,
        inner_circle_segments=inner_segs
    )

    if mesh:
        # Make facets read crisp
        mesh.Unweld(math.radians(35.0), True)
        sc.doc.Objects.AddMesh(mesh)
        sc.doc.Views.Redraw()

    rs.EnableRedraw(True)

if __name__ == "__main__":
    main()
