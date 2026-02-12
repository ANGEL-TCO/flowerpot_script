# Rhino 8 - Faceted Argyle Bucket (polygonal outer wall)
import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import math

def clamp(v,a,b): return max(a,min(b,v))
def smoothstep(t):
    t = clamp(float(t),0.0,1.0)
    return t*t*(3.0-2.0*t)

def edge_fade(z01, fade_zone):
    s = float(fade_zone)
    if s <= 0.0: return 1.0
    if z01 < s: return smoothstep(z01/s)
    if z01 > 1.0 - s: return smoothstep((1.0-z01)/s)
    return 1.0

def build_faceted_bucket(
    base_pt,
    height,
    inner_radius,
    wall_thickness,
    base_thickness,
    diamonds_around=5,
    diamonds_vertical=3,
    facet_depth=3.0,
    fade_zone=0.12,
    bevel_height=6.0,     # top/bottom straight "bevel band" height
    bevel_inset=2.0       # how much to pull-in radius in bevel band
):
    """
    Outer wall = rhombus quad grid:
      around segments = 2*diamonds_around
      vertical rings  = 2*diamonds_vertical
    Rings alternate a half-step angular offset => quads become rhombi.
    Relief is binary (+/-) => crisp planar-ish facets + polygonal silhouette.
    """

    H  = float(height)
    Rin = float(inner_radius)
    T  = float(wall_thickness)
    B  = float(base_thickness)

    Rout = Rin + T
    B = clamp(B, 0.5, H*0.9)

    # --- topology that matches argyle ---
    seg_u = max(6, int(2 * diamonds_around))         # corners around
    seg_v = max(2, int(2 * diamonds_vertical))       # rings up
    cols = seg_u + 1                                 # seam dup
    rows = seg_v + 1

    outer = Rhino.Geometry.Mesh()
    inner = Rhino.Geometry.Mesh()

    # ---- vertices ----
    for j in range(rows):
        v01 = float(j) / float(seg_v)    # 0..1 along height
        z = H * v01

        # alternate ring offset: makes rhombi
        theta_off = (math.pi / seg_u) if (j % 2 == 1) else 0.0

        # fade facet depth near top/bottom
        fade = edge_fade(v01, fade_zone)

        # bevel bands to imitate the "straight-ish" rim/base edge you marked in red
        bevel = 0.0
        if bevel_height > 0.0:
            if z < bevel_height:
                # bottom bevel: inset strongest at z=0
                t = 1.0 - (z / bevel_height)
                bevel = -bevel_inset * smoothstep(t)
            elif z > (H - bevel_height):
                # top bevel: inset strongest at z=H
                t = 1.0 - ((H - z) / bevel_height)
                bevel = -bevel_inset * smoothstep(t)

        for i in range(cols):
            u01 = float(i) / float(seg_u)
            theta = 2.0 * math.pi * u01 + theta_off

            # Binary facet pattern (checkerboard in the diamond grid).
            # This is what creates the "polygon from rhombus union" feel.
            s = 1.0 if ((i + j) % 2 == 0) else -1.0

            relief = facet_depth * fade * s
            r_out = Rout + relief + bevel

            # OUTER point
            x_out = base_pt.X + r_out * math.cos(theta)
            y_out = base_pt.Y + r_out * math.sin(theta)
            z_out = base_pt.Z + z
            outer.Vertices.Add(x_out, y_out, z_out)

            # INNER wall = perfect cylinder (starts at base floor)
            # inner side goes from z=B..H (we'll build with same rows for simplicity)
            z_in = base_pt.Z + max(B, z)
            x_in = base_pt.X + Rin * math.cos(theta)
            y_in = base_pt.Y + Rin * math.sin(theta)
            inner.Vertices.Add(x_in, y_in, z_in)

    def vid(ii, jj):
        return jj * cols + ii

    # ---- faces (rhombus quads) ----
    for j in range(seg_v):
        for i in range(seg_u):
            a = vid(i, j)
            b = vid(i+1, j)
            c = vid(i+1, j+1)
            d = vid(i, j+1)

            outer.Faces.AddFace(a, b, c, d)
            # inner is reversed (we'll flip later)
            inner.Faces.AddFace(a, d, c, b)

    outer.Normals.ComputeNormals()
    inner.Normals.ComputeNormals()

    # ---- close bottoms ----
    # Outer bottom cap (z=0)
    outer_center = outer.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z)
    for i in range(seg_u):
        outer.Faces.AddFace(outer_center, vid(i+1, 0), vid(i, 0))

    # Inner floor cap at z=B (so the bucket isn't bottomless)
    # We added inner vertices clamped to z>=B, so row 0 is already at z=B.
    inner_floor_center = inner.Vertices.Add(base_pt.X, base_pt.Y, base_pt.Z + B)
    for i in range(seg_u):
        inner.Faces.AddFace(inner_floor_center, vid(i, 0), vid(i+1, 0))

    # ---- shell: outer + flipped inner ----
    inner2 = inner.DuplicateMesh()
    inner2.Flip(True, True, True)

    shell = Rhino.Geometry.Mesh()
    shell.Append(outer)
    outer_count = outer.Vertices.Count
    shell.Append(inner2)

    # ---- top rim bridge (outer top ring to inner top ring) ----
    top_j = seg_v
    def o(ii, jj): return vid(ii, jj)
    def inn(ii, jj): return outer_count + vid(ii, jj)

    for i in range(seg_u):
        i2 = i + 1
        shell.Faces.AddFace(o(i, top_j), o(i2, top_j), inn(i2, top_j), inn(i, top_j))

    shell.UnifyNormals()
    shell.Normals.ComputeNormals()
    shell.Compact()

    return shell

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
        bevel_inset=bevel_in
    )

    if mesh:
        # make facets read sharper
        mesh.Unweld(math.radians(35.0), True)
        sc.doc.Objects.AddMesh(mesh)
        sc.doc.Views.Redraw()

    rs.EnableRedraw(True)

if __name__ == "__main__":
    main()
