# Argyle Bucket Generator (Rhino 8)
# Inner wall: perfect cylinder
# Outer wall: ring-based points with rhombus (argyle) pattern
# Solid: has base thickness and closed mesh

import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import math

# -------------------------
# Helpers
# -------------------------
def clamp(v, a, b):
    return max(a, min(b, v))

def smoothstep(t):
    t = clamp(float(t), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def edge_fade(z01, fade_zone):
    """Fade pattern near bottom/top so the rim/base look cleaner."""
    s = float(fade_zone)
    if s <= 0.0:
        return 1.0
    if z01 < s:
        return smoothstep(z01 / s)
    if z01 > 1.0 - s:
        return smoothstep((1.0 - z01) / s)
    return 1.0

def diamond_value(u, v, diamonds_around, diamonds_vertical):
    """
    UV diamond (argyle) using Manhattan distance to cell center.
    Returns roughly [-1..+1], where +1 is cell center, -1 near edges.
    """
    su = u * float(diamonds_around)
    sv = v * float(diamonds_vertical)

    fu = su - math.floor(su)  # 0..1
    fv = sv - math.floor(sv)  # 0..1

    d = abs(fu - 0.5) + abs(fv - 0.5)   # 0..1
    h = 1.0 - 2.0 * d                   # +1 center, -1 edges
    return clamp(h, -1.0, 1.0)

def hard_facet(x, softness=0.15):
    """
    Turn a smooth [-1..1] into flatter facets.
    softness -> 0 = very hard two-level; higher = softer transitions.
    """
    s = clamp(softness, 0.0, 1.0)
    # Map to 0..1, apply smoothstep for controllable transition, map back
    t = (x + 1.0) * 0.5
    t = smoothstep(clamp((t - 0.5) / max(1e-6, s) + 0.5, 0.0, 1.0)) if s > 0 else (1.0 if t >= 0.5 else 0.0)
    return (t * 2.0) - 1.0

# -------------------------
# Core build
# -------------------------
def build_bucket_mesh(
    base_pt,
    height,
    inner_radius,
    wall_thickness,
    base_thickness,
    seg_u=120,
    seg_v=48,
    diamonds_around=5,
    diamonds_vertical=3,
    facet_depth=3.0,
    fade_zone=0.12,
    facet_softness=0.18,
    waist_amp=0.0,
    waist_cycles=1.0
):
    """
    Creates a closed mesh solid bucket:
      - Outer surface: modulated radius (argyle facets)
      - Outer bottom: sealed at z=0
      - Inner surface: perfect cylinder (no pattern), starts at z=base_thickness
      - Inner floor: sealed at z=base_thickness
      - Top rim: bridged between inner and outer at z=height
    """

    # --- normalize / safety ---
    H = float(height)
    Rin = float(inner_radius)
    T = float(wall_thickness)
    B = float(base_thickness)

    seg_u = max(24, int(seg_u))
    seg_v = max(10, int(seg_v))
    diamonds_around = max(2, int(diamonds_around))
    diamonds_vertical = max(1, int(diamonds_vertical))

    # derive outer radius from inner + thickness
    Rout_base = Rin + T

    # clamp base thickness and thickness sanity
    B = clamp(B, 0.5, H * 0.9)
    T = clamp(T, 0.5, max(1.0, Rin * 2.0))

    cols = seg_u + 1  # duplicate seam for clean wrap

    # --------------------------------
    # 1) OUTER MESH (side + bottom cap)
    # --------------------------------
    outer = Rhino.Geometry.Mesh()

    # Outer side vertices from z=0..H
    for j in range(seg_v + 1):
        v01 = float(j) / float(seg_v)
        z = H * v01
        fade = edge_fade(v01, fade_zone)

        for i in range(cols):
            u01 = float(i) / float(seg_u)
            theta = 2.0 * math.pi * u01

            # Diamond pattern (argyle)
            d = diamond_value(u01, v01, diamonds_around, diamonds_vertical)
            d = hard_facet(d, facet_softness)  # flatten to read as facets

            # Optional waist (subtle “soft wavy” body like the photo)
            waist = 0.0
            if abs(waist_amp) > 1e-9:
                waist = float(waist_amp) * math.sin(2.0 * math.pi * (waist_cycles * v01))

            relief = float(facet_depth) * fade * d
            r_out = Rout_base + relief + waist

            x = base_pt.X + r_out * math.cos(theta)
            y = base_pt.Y + r_out * math.sin(theta)
            zz = base_pt.Z + z
            outer.Vertices.Add(x, y, zz)

    def o_vid(ii, jj):
        return jj * cols + ii

    # Outer side faces (quads)
    for j in range(seg_v):
        for i in range(seg_u):
            a = o_vid(i, j)
            b = o_vid(i + 1, j)
            c = o_vid(i + 1, j + 1)
            d = o_vid(i, j + 1)
            outer.Faces.AddFace(a, b, c, d)

    # Outer bottom cap (fan)
    # Add center vertex at z=0
    outer_center_idx = outer.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z)

    # bottom ring is j=0
    for i in range(seg_u):
        a = outer_center_idx
        b = o_vid(i + 1, 0)
        c = o_vid(i, 0)
        outer.Faces.AddFace(a, b, c)  # orientation for outward normals

    outer.Normals.ComputeNormals()
    outer.Compact()

    # --------------------------------
    # 2) INNER MESH (side + inner floor)
    # --------------------------------
    inner = Rhino.Geometry.Mesh()

    # Inner side starts at z=B .. H (perfect cylinder)
    for j in range(seg_v + 1):
        v01 = float(j) / float(seg_v)
        z = B + (H - B) * v01  # maps 0..1 -> B..H

        for i in range(cols):
            u01 = float(i) / float(seg_u)
            theta = 2.0 * math.pi * u01

            x = base_pt.X + Rin * math.cos(theta)
            y = base_pt.Y + Rin * math.sin(theta)
            zz = base_pt.Z + z
            inner.Vertices.Add(x, y, zz)

    def i_vid(ii, jj):
        return jj * cols + ii

    # Inner side faces (quads)
    for j in range(seg_v):
        for i in range(seg_u):
            a = i_vid(i, j)
            b = i_vid(i + 1, j)
            c = i_vid(i + 1, j + 1)
            d = i_vid(i, j + 1)
            inner.Faces.AddFace(a, b, c, d)

    # Inner floor cap at z=B (fan)
    inner_floor_center_idx = inner.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z + B)

    # floor ring is j=0 in inner mesh
    for i in range(seg_u):
        a = inner_floor_center_idx
        b = i_vid(i, 0)
        c = i_vid(i + 1, 0)
        inner.Faces.AddFace(a, b, c)  # orientation for inward normals (we'll flip later)

    inner.Normals.ComputeNormals()
    inner.Compact()

    # --------------------------------
    # 3) SHELL: outer + flipped inner + top rim bridge
    # --------------------------------
    inner2 = inner.DuplicateMesh()
    inner2.Flip(True, True, True)  # boundary must face outward for solid

    shell = Rhino.Geometry.Mesh()
    shell.Append(outer)

    outer_count = outer.Vertices.Count
    shell.Append(inner2)

    # Indices mapping for inner2 inside shell:
    # shell inner2 vertex k corresponds to (outer_count + k)
    def shell_o(ii, jj):
        return o_vid(ii, jj)

    def shell_i(ii, jj):
        return outer_count + i_vid(ii, jj)

    # Top rim bridge: connect outer top ring (j=seg_v) to inner top ring (j=seg_v)
    top_j = seg_v
    for i in range(seg_u):
        i2 = i + 1
        shell.Faces.AddFace(
            shell_o(i, top_j),
            shell_o(i2, top_j),
            shell_i(i2, top_j),
            shell_i(i, top_j)
        )

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
        rs.EnableRedraw(True)
        return
    base_pt = Rhino.Geometry.Point3d(base.X, base.Y, base.Z)

    H = rs.GetReal("Height (mm)", 90.0, 10.0, 2000.0)
    if H is None:
        rs.EnableRedraw(True); return

    Rin = rs.GetReal("Inner radius (mm)", 55.0, 5.0, 2000.0)
    if Rin is None:
        rs.EnableRedraw(True); return

    T = rs.GetReal("Wall thickness (mm)", 4.0, 0.5, 200.0)
    if T is None:
        rs.EnableRedraw(True); return

    B = rs.GetReal("Base thickness (mm)", 5.0, 0.5, H * 0.9)
    if B is None:
        rs.EnableRedraw(True); return

    # mesh resolution
    seg_u = rs.GetInteger("Segments around (80-180)", 120, 24, 500)
    if seg_u is None:
        rs.EnableRedraw(True); return

    seg_v = rs.GetInteger("Segments height (30-80)", 48, 10, 300)
    if seg_v is None:
        rs.EnableRedraw(True); return

    # pattern controls
    diamonds_around = rs.GetInteger("Diamonds around (4-8)", 5, 2, 30)
    if diamonds_around is None:
        rs.EnableRedraw(True); return

    diamonds_vertical = rs.GetInteger("Diamonds vertical (2-6)", 3, 1, 30)
    if diamonds_vertical is None:
        rs.EnableRedraw(True); return

    facet_depth = rs.GetReal("Facet depth (mm) (1-6)", 3.0, 0.0, 30.0)
    if facet_depth is None:
        rs.EnableRedraw(True); return

    # optional: subtle waist like the photo
    waist_amp = rs.GetReal("Waist amplitude (mm) (0 for none)", 1.5, 0.0, 30.0)
    if waist_amp is None:
        rs.EnableRedraw(True); return

    mesh = build_bucket_mesh(
        base_pt=base_pt,
        height=H,
        inner_radius=Rin,
        wall_thickness=T,
        base_thickness=B,
        seg_u=seg_u,
        seg_v=seg_v,
        diamonds_around=diamonds_around,
        diamonds_vertical=diamonds_vertical,
        facet_depth=facet_depth,
        fade_zone=0.12,
        facet_softness=0.18,  # lower = harder facets
        waist_amp=waist_amp,
        waist_cycles=1.0
    )

    if mesh:
        # Hard edges so facets read better (adjust angle if needed)
        mesh.Unweld(math.radians(30.0), True)
        sc.doc.Objects.AddMesh(mesh)
        sc.doc.Views.Redraw()

    rs.EnableRedraw(True)

if __name__ == "__main__":
    main()

