import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import math

# -------------------------
# Helpers
# -------------------------
def clamp(v,a,b): return max(a,min(b,v))

def smoothstep(t):
    t = clamp(float(t), 0.0, 1.0)
    return t*t*(3.0-2.0*t)

def edge_fade(z01, fade_zone):
    s = float(fade_zone)
    if s <= 0.0: return 1.0
    if z01 < s: return smoothstep(z01/s)
    if z01 > 1.0 - s: return smoothstep((1.0-z01)/s)
    return 1.0

def stitch_rings_tri(mesh, ringA, ringB):
    """
    Stitch two closed rings (lists of vertex indices) with triangles.
    Works even if len(ringA) != len(ringB).

    Assumption: both rings are ordered CCW when seen from outside,
    and correspond roughly by angle (same orientation).
    """
    nA = len(ringA)
    nB = len(ringB)
    if nA < 3 or nB < 3:
        return

    i = 0
    j = 0
    # Use normalized progress around each ring to decide next triangle
    while i < nA and j < nB:
        i2 = (i + 1) % nA
        j2 = (j + 1) % nB

        # progress ratios (0..1)
        a_next = float(i + 1) / float(nA)
        b_next = float(j + 1) / float(nB)

        a0 = ringA[i]
        a1 = ringA[i2]
        b0 = ringB[j]
        b1 = ringB[j2]

        if a_next < b_next:
            # advance A: triangle (a0, a1, b0)
            mesh.Faces.AddFace(a0, a1, b0)
            i += 1
            if i == nA: break
        elif b_next < a_next:
            # advance B: triangle (a0, b1, b0)
            mesh.Faces.AddFace(a0, b1, b0)
            j += 1
            if j == nB: break
        else:
            # advance both: quad split into 2 tris
            mesh.Faces.AddFace(a0, a1, b1)
            mesh.Faces.AddFace(a0, b1, b0)
            i += 1
            j += 1
            if i == nA or j == nB: break

# -------------------------
# Build
# -------------------------
def build_faceted_bucket(
    base_pt,
    height,
    inner_radius,
    wall_thickness,
    base_thickness,
    diamonds_around=5,
    diamonds_vertical=3,
    facet_depth=3.0,
    fade_zone=0.10,
    bevel_height=6.0,
    bevel_inset=2.0,
    inner_seg_u=120  # <- IMPORTANT: independent inner resolution for perfect circle
):
    H   = float(height)
    Rin = float(inner_radius)
    T   = float(wall_thickness)
    B   = float(base_thickness)

    Rout = Rin + T
    B = clamp(B, 0.5, H * 0.9)

    # --- OUTER topology matches rhombus grid ---
    outer_seg_u = max(6, int(2 * diamonds_around))       # corners around
    outer_seg_v = max(2, int(2 * diamonds_vertical))     # rings up
    outer_cols  = outer_seg_u + 1
    outer_rows  = outer_seg_v + 1

    # --- INNER topology: smooth circle, no offsets ---
    inner_seg_u = max(24, int(inner_seg_u))
    inner_seg_v = outer_seg_v  # keep same vertical ring count for consistency
    inner_cols  = inner_seg_u + 1
    inner_rows  = inner_seg_v + 1

    outer = Rhino.Geometry.Mesh()
    inner = Rhino.Geometry.Mesh()

    # -------------------------
    # OUTER vertices (faceted)
    # -------------------------
    for j in range(outer_rows):
        v01 = float(j) / float(outer_seg_v)
        z = H * v01

        theta_off = (math.pi / outer_seg_u) if (j % 2 == 1) else 0.0
        fade = edge_fade(v01, fade_zone)

        # bevel band to keep rim/base cleaner & more "straight"
        bevel = 0.0
        if bevel_height > 0.0:
            if z < bevel_height:
                t = 1.0 - (z / bevel_height)
                bevel = -bevel_inset * smoothstep(t)
            elif z > (H - bevel_height):
                t = 1.0 - ((H - z) / bevel_height)
                bevel = -bevel_inset * smoothstep(t)

        for i in range(outer_cols):
            u01 = float(i) / float(outer_seg_u)
            theta = 2.0 * math.pi * u01 + theta_off

            # checkerboard relief (crisp facets)
            s = 1.0 if ((i + j) % 2 == 0) else -1.0
            relief = facet_depth * fade * s

            r_out = Rout + relief + bevel

            x = base_pt.X + r_out * math.cos(theta)
            y = base_pt.Y + r_out * math.sin(theta)
            zz = base_pt.Z + z
            outer.Vertices.Add(x, y, zz)

    def o_vid(ii, jj):
        return jj * outer_cols + ii

    for j in range(outer_seg_v):
        for i in range(outer_seg_u):
            a = o_vid(i, j)
            b = o_vid(i + 1, j)
            c = o_vid(i + 1, j + 1)
            d = o_vid(i, j + 1)
            outer.Faces.AddFace(a, b, c, d)

    # Outer bottom cap
    outer_center = outer.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z)
    for i in range(outer_seg_u):
        outer.Faces.AddFace(outer_center, o_vid(i + 1, 0), o_vid(i, 0))

    outer.Normals.ComputeNormals()
    outer.Compact()

    # -------------------------
    # INNER vertices (perfect circle)
    # Inner starts at z=B (floor), up to z=H
    # -------------------------
    for j in range(inner_rows):
        v01 = float(j) / float(inner_seg_v)
        z = B + (H - B) * v01

        for i in range(inner_cols):
            u01 = float(i) / float(inner_seg_u)
            theta = 2.0 * math.pi * u01  # <- no offset, uniform circle

            x = base_pt.X + Rin * math.cos(theta)
            y = base_pt.Y + Rin * math.sin(theta)
            zz = base_pt.Z + z
            inner.Vertices.Add(x, y, zz)

    def i_vid(ii, jj):
        return jj * inner_cols + ii

    for j in range(inner_seg_v):
        for i in range(inner_seg_u):
            a = i_vid(i, j)
            b = i_vid(i + 1, j)
            c = i_vid(i + 1, j + 1)
            d = i_vid(i, j + 1)
            inner.Faces.AddFace(a, b, c, d)

    # Inner floor cap at z=B
    inner_center = inner.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z + B)
    for i in range(inner_seg_u):
        inner.Faces.AddFace(inner_center, i_vid(i, 0), i_vid(i + 1, 0))

    inner.Normals.ComputeNormals()
    inner.Compact()

    # -------------------------
    # Combine into closed shell
    # -------------------------
    inner2 = inner.DuplicateMesh()
    inner2.Flip(True, True, True)

    shell = Rhino.Geometry.Mesh()
    shell.Append(outer)
    outer_count = outer.Vertices.Count
    shell.Append(inner2)

    # Top ring indices
    outer_top_ring = [o_vid(i, outer_seg_v) for i in range(outer_seg_u)]  # no seam dup
    inner_top_ring = [outer_count + i_vid(i, inner_seg_v) for i in range(inner_seg_u)]  # no seam dup

    # Stitch top rim between outer and inner (triangles)
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

    B = rs.GetReal("Base thickness (mm)", 5.0, 0.5, H*0.9)
    if B is None: rs.EnableRedraw(True); return

    diamonds_around = rs.GetInteger("Diamonds around (4-8)", 5, 2, 40)
    if diamonds_around is None: rs.EnableRedraw(True); return

    diamonds_vertical = rs.GetInteger("Diamonds vertical (2-6)", 3, 1, 40)
    if diamonds_vertical is None: rs.EnableRedraw(True); return

    facet_depth = rs.GetReal("Facet depth (mm) (1-8)", 3.0, 0.0, 30.0)
    if facet_depth is None: rs.EnableRedraw(True); return

    bevel_h = rs.GetReal("Bevel band height (mm)", 6.0, 0.0, H*0.45)
    if bevel_h is None: rs.EnableRedraw(True); return

    bevel_in = rs.GetReal("Bevel inset (mm)", 2.0, 0.0, 30.0)
    if bevel_in is None: rs.EnableRedraw(True); return

    inner_seg_u = rs.GetInteger("Inner circle segments (80-200)", 140, 24, 400)
    if inner_seg_u is None: rs.EnableRedraw(True); return

    mesh = build_faceted_bucket(
        base_pt=base_pt,
        height=H,
        inner_radius=Rin,
        wall_thickness=T,
        base_thickness=B,
        diamonds_around=diamonds_around,
        diamonds_vertical=diamonds_vertical,
        facet_depth=facet_depth,
        fade_zone=0.10,
        bevel_height=bevel_h,
        bevel_inset=bevel_in,
        inner_seg_u=inner_seg_u
    )

    if mesh:
        # Keep outer facets crisp
        mesh.Unweld(math.radians(35.0), True)
        sc.doc.Objects.AddMesh(mesh)
        sc.doc.Views.Redraw()

    rs.EnableRedraw(True)

if __name__ == "__main__":
    main()
