#! python3
import rhinoscriptsyntax as rs
import math

# ========= PARAMETERS =========
radius = 10.0  # Overall radius of the cylinder
height = 10.0  # Height of the cylinder
num_facets = 16  # Number of facets around the perimeter
wall_thickness = 1.0  # Thickness of the wall

# Inner pattern parameters
num_radial_lines = 120  # Number of radial lines in the inner pattern
inner_depth = 0.5  # How deep the inner pattern goes
num_horizontal_rings = 40  # Number of horizontal divisions for inner pattern

# Outer shell parameters
num_vertical_rings = 8  # Number of horizontal rings for the outer shell

# ========= HELPER FUNCTIONS =========
def create_ring(n, r, z, phase=0.0):
    """Create a ring of points at given radius and height"""
    pts = []
    step = 2.0 * math.pi / n
    for i in range(n):
        angle = phase + i * step
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        pts.append([x, y, z])
    return pts

# ========= BUILD GEOMETRY =========
V = []  # Vertices
F = []  # Faces

# ========= OUTER FACETED SHELL WITH ALTERNATING RINGS =========
outer_rings = []
half_step = math.pi / num_facets  # Half a facet rotation

# Create rings at different heights with alternating rotation
for level in range(num_vertical_rings + 1):
    z = (level / num_vertical_rings) * height
    # Alternate rotation: even rings = no offset, odd rings = half-step offset
    theta_offset = half_step if (level % 2 == 1) else 0.0
    ring = create_ring(num_facets, radius, z, theta_offset)
    base_idx = len(V)
    V.extend(ring)
    outer_rings.append((base_idx, num_facets))

# Create triangular faces with alternating diagonal direction
for level in range(num_vertical_rings):
    base_lower, n_lower = outer_rings[level]
    base_upper, n_upper = outer_rings[level + 1]
    
    flip_diag = (level % 2 == 0)  # Alternate diagonal direction per band
    
    for i in range(num_facets):
        i_next = (i + 1) % num_facets
        
        v1 = base_lower + i
        v2 = base_lower + i_next
        v3 = base_upper + i_next
        v4 = base_upper + i
        
        if not flip_diag:
            # Diagonal v1-v3
            F.append([v1, v2, v3])
            F.append([v1, v3, v4])
        else:
            # Diagonal v2-v4
            F.append([v1, v2, v4])
            F.append([v2, v3, v4])

# Create top cap
top_center_idx = len(V)
V.append([0, 0, height])

base_top, n_top = outer_rings[-1]
for i in range(num_facets):
    i_next = (i + 1) % num_facets
    F.append([top_center_idx, base_top + i, base_top + i_next])

# Create bottom cap
bottom_center_idx = len(V)
V.append([0, 0, 0])

base_bottom, n_bottom = outer_rings[0]
for i in range(num_facets):
    i_next = (i + 1) % num_facets
    F.append([bottom_center_idx, base_bottom + i_next, base_bottom + i])

# ========= INNER RADIAL PATTERN =========
inner_rings = []
inner_radius = radius - wall_thickness

for ring_idx in range(num_horizontal_rings):
    z = (ring_idx / (num_horizontal_rings - 1)) * height
    # Vary the radius slightly to create depth
    r_variation = inner_depth * math.sin(ring_idx * math.pi / num_horizontal_rings)
    r = inner_radius - r_variation
    
    ring = create_ring(num_radial_lines, r, z, 0.0)
    base_idx = len(V)
    V.extend(ring)
    inner_rings.append((base_idx, num_radial_lines))

# Create faces for inner pattern
for ring_idx in range(num_horizontal_rings - 1):
    base_lower, n_lower = inner_rings[ring_idx]
    base_upper, n_upper = inner_rings[ring_idx + 1]
    
    for i in range(num_radial_lines):
        i_next = (i + 1) % num_radial_lines
        
        v1 = base_lower + i
        v2 = base_lower + i_next
        v3 = base_upper + i_next
        v4 = base_upper + i
        
        F.append([v1, v2, v3, v4])

# Connect inner pattern to top center
top_inner_base, n = inner_rings[-1]
for i in range(num_radial_lines):
    i_next = (i + 1) % num_radial_lines
    F.append([top_center_idx, top_inner_base + i, top_inner_base + i_next])

# Connect inner pattern to bottom center
bottom_inner_base, n = inner_rings[0]
for i in range(num_radial_lines):
    i_next = (i + 1) % num_radial_lines
    F.append([bottom_center_idx, bottom_inner_base + i_next, bottom_inner_base + i])

# ========= CREATE MESH =========
mesh = rs.AddMesh(V, F)

print("Faceted cylinder with diagonal crisscross pattern created!")
print(f"Total vertices: {len(V)}")
print(f"Total faces: {len(F)}")
