# flowerpot_script / Version de Fernando (FIXED)
# -*- coding: utf-8 -*-

import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import math

# =========================================================
# MACETERA "ARGYLE" (ROMBOS GRANDES) + ONDULACION SUAVE - Rhino 8
# - pocas celdas -> rombos grandes como la referencia
# - seam perfecto (u=0 y u=1)
# - interior limpio
# - mesh cerrado con tapas
# =========================================================

def clamp(v, a, b):
    return max(a, min(b, v))

def smoothstep(t):
    # classic smoothstep 0..1
    t = clamp(float(t), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def edge_fade(z01, rim_soft):
    """Fade near bottom/top to soften detail at rim and base."""
    s = float(rim_soft)
    if s <= 0.0:
        return 1.0
    if z01 < s:
        return smoothstep(z01 / s)
    if z01 > 1.0 - s:
        return smoothstep((1.0 - z01) / s)
    return 1.0

def diamond_cell(u, v, cells_u, cells_v):
    """
    Rombos GRANDES en UV (tipo argyle).
    Devuelve un valor en [-1, 1] usando distancia Manhattan al centro de la celda.
    """
    su = u * float(cells_u)
    sv = v * float(cells_v)

    fu = su - math.floor(su)  # 0..1
    fv = sv - math.floor(sv)  # 0..1

    dist = abs(fu - 0.5) + abs(fv - 0.5)  # 0..1 aprox
    h = 1.0 - 2.0 * dist                  # +1 centro, -1 bordes

    return clamp(h, -1.0, 1.0)

def build_closed_pot(
    base_pt, H, R, T,
    seg_u=96, seg_v=40,
    diamonds_around=5,
    diamonds_vertical=3,
    facet_depth=3.0,
    wave_amp=6.0,
    wave_cycles=1.0,
    rim_soft=0.18,
    inner_factor=0.15
):
    # --- safety / normalization ---
    seg_u = max(24, int(seg_u))
    seg_v = max(10, int(seg_v))
    diamonds_around = max(2, int(diamonds_around))
    diamonds_vertical = max(1, int(diamonds_vertical))

    H = float(H)
    R = float(R)
    T = float(T)
    T = clamp(T, 1.0, R * 0.8)

    cols = seg_u + 1  # seam duplicated for clean wrap
    rows = seg_v + 1

    outer = Rhino.Geometry.Mesh()
    inner = Rhino.Geometry.Mesh()

    # --- vertices ---
    for j in range(rows):
        v = float(j) / float(seg_v)   # 0..1
        z = H * v
        fade = edge_fade(v, rim_soft)

        for i in range(cols):
            u = float(i) / float(seg_u)  # 0..1
            theta = 2.0 * math.pi * u

            # Ondulación suave (baja frecuencia)
            w = wave_amp * fade * math.sin(
                2.0 * math.pi * (wave_cycles * v) + theta * 0.5
            )

            # Rombos (argyle) grandes
            dia = diamond_cell(u, v, diamonds_around, diamonds_vertical)

            # Facet relief
            relief = facet_depth * fade * dia

            r_out = R + w + relief
            r_in = (R - T) + (inner_factor * relief)  # interior casi liso

            x_out = base_pt.X + r_out * math.cos(theta)
            y_out = base_pt.Y + r_out * math.sin(theta)
            z_out = base_pt.Z + z

            x_in = base_pt.X + r_in * math.cos(theta)
            y_in = base_pt.Y + r_in * math.sin(theta)

            outer.Vertices.Add(x_out, y_out, z_out)
            inner.Vertices.Add(x_in, y_in, z_out)

    # --- faces (quads) ---
    def vid(ii, jj):
        return jj * cols + ii

    for j in range(seg_v):
        for i in range(seg_u):
            a = vid(i, j)
            b = vid(i + 1, j)
            c = vid(i + 1, j + 1)
            d = vid(i, j + 1)

            outer.Faces.AddFace(a, b, c, d)
            # inner reversed so normals point inward on inner mesh (we'll flip later)
            inner.Faces.AddFace(a, d, c, b)

    outer.Normals.ComputeNormals()
    inner.Normals.ComputeNormals()

    # --- shell: outer + flipped inner ---
    inner2 = inner.DuplicateMesh()
    inner2.Flip(True, True, True)

    shell = Rhino.Geometry.Mesh()
    shell.Append(outer)
    shell.Append(inner2)

    # --- caps (top & bottom) ---
    outer_count = outer.Vertices.Count
    inner_off = outer_count

    def o(ii, jj):
        return jj * cols + ii

    def inn(ii, jj):
        return inner_off + jj * cols + ii

    top_j = seg_v
    bot_j = 0

    for i in range(seg_u):
        i2 = i + 1
        # top ring quad between outer and inner
        shell.Faces.AddFace(o(i, top_j), o(i2, top_j), inn(i2, top_j), inn(i, top_j))
        # bottom ring quad between inner and outer
        shell.Faces.AddFace(inn(i, bot_j), inn(i2, bot_j), o(i2, bot_j), o(i, bot_j))

    shell.UnifyNormals()
    shell.Normals.ComputeNormals()
    shell.Compact()

    return shell

def main():
    rs.EnableRedraw(False)

    base = rs.GetPoint("Centro de la maceta")
    if not base:
        rs.EnableRedraw(True)
        return

    H = rs.GetReal("Altura (mm)", 120.0, 30.0, 1000.0)
    if H is None:
        rs.EnableRedraw(True); return

    R = rs.GetReal("Radio exterior (mm)", 70.0, 20.0, 1000.0)
    if R is None:
        rs.EnableRedraw(True); return

    T = rs.GetReal("Espesor pared (mm)", 4.0, 1.0, R * 0.8)
    if T is None:
        rs.EnableRedraw(True); return

    seg_u = rs.GetInteger("Segmentos alrededor (80-140)", 110, 40, 300)
    if seg_u is None:
        rs.EnableRedraw(True); return

    seg_v = rs.GetInteger("Segmentos altura (30-60)", 45, 10, 200)
    if seg_v is None:
        rs.EnableRedraw(True); return

    diamonds_around = rs.GetInteger("Rombos alrededor (4-7)", 5, 2, 20)
    if diamonds_around is None:
        rs.EnableRedraw(True); return

    diamonds_vertical = rs.GetInteger("Rombos en altura (2-4)", 3, 1, 20)
    if diamonds_vertical is None:
        rs.EnableRedraw(True); return

    facet_depth = rs.GetReal("Profundidad faceta (mm) (2-5)", 3.0, 0.0, 20.0)
    if facet_depth is None:
        rs.EnableRedraw(True); return

    wave_amp = rs.GetReal("Ondulación cuerpo (mm) (4-10)", 7.0, 0.0, 30.0)
    if wave_amp is None:
        rs.EnableRedraw(True); return

    wave_cycles = rs.GetReal("Ciclos ondulación en altura (0.8-1.5)", 1.0, 0.1, 5.0)
    if wave_cycles is None:
        rs.EnableRedraw(True); return

    base_pt = Rhino.Geometry.Point3d(base.X, base.Y, base.Z)

    mesh = build_closed_pot(
        base_pt=base_pt,
        H=H, R=R, T=T,
        seg_u=seg_u, seg_v=seg_v,
        diamonds_around=diamonds_around,
        diamonds_vertical=diamonds_vertical,
        facet_depth=facet_depth,
        wave_amp=wave_amp,
        wave_cycles=wave_cycles,
        rim_soft=0.18,
        inner_factor=0.12
    )

    if mesh:
        # Aristas un poco más duras ayuda a leer las "caras" grandes
        mesh.Unweld(math.radians(25.0), True)
        sc.doc.Objects.AddMesh(mesh)
        sc.doc.Views.Redraw()

    rs.EnableRedraw(True)

if __name__ == "__main__":
    main()
