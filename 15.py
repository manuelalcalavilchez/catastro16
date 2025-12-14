import os
import csv
import xml.etree.ElementTree as ET
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from PIL import Image
from io import BytesIO
from datetime import date, datetime
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point

# -----------------------------
# Leer polígonos del KML (con huecos)
# -----------------------------
def parse_kml_polygons(kml_file):
    tree = ET.parse(kml_file)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    polygons = []
    for placemark in root.findall(".//kml:Placemark", ns):
        for polygon in placemark.findall(".//kml:Polygon", ns):
            rings = []
            for ring_tag in ["outerBoundaryIs", "innerBoundaryIs"]:
                for ring in polygon.findall(f".//kml:{ring_tag}/kml:LinearRing/kml:coordinates", ns):
                    coords = []
                    for c in ring.text.strip().split():
                        lon, lat, *_ = map(float, c.split(","))
                        coords.append((lon, lat))
                    rings.append(coords)
            polygons.append(rings)
    return polygons

# -----------------------------
# Calcular BBOX y ampliar zoom
# -----------------------------
def get_bbox_from_polygons(polygons):
    all_coords = [pt for poly in polygons for ring in poly for pt in ring]
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)

    zoom_factor = 3
    lat_center = (lat_min + lat_max) / 2
    lon_center = (lon_min + lon_max) / 2
    lat_half = (lat_max - lat_min) / 2
    lon_half = (lon_max - lon_min) / 2

    lat_min_zoom = lat_center - lat_half * zoom_factor
    lat_max_zoom = lat_center + lat_half * zoom_factor
    lon_min_zoom = lon_center - lon_half * zoom_factor
    lon_max_zoom = lon_center + lon_half * zoom_factor

    return (lat_min_zoom, lon_min_zoom, lat_max_zoom, lon_max_zoom)

# -----------------------------
# Descargar imagen WMS
# -----------------------------
def download_wms_image(base_url, layer, style, bbox, format="image/png"):
    lat_min, lon_min, lat_max, lon_max = bbox
    url = (
        f"{base_url}SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&"
        f"LAYERS={layer}&STYLES={style}&CRS=EPSG:4326&"
        f"BBOX={lat_min},{lon_min},{lat_max},{lon_max}&WIDTH=800&HEIGHT=600&FORMAT={format}"
    )
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        return Image.open(BytesIO(r.content))
    else:
        raise Exception(f"Error {r.status_code} al descargar WMS\nURL: {url}")

# -----------------------------
# Dibujar polígonos con huecos
# -----------------------------
def draw_kml_polygons(ax, polygons):
    for rings in polygons:
        vertices = []
        codes = []
        for ring in rings:
            codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
            vertices += ring + [(0, 0)]
        path = Path(vertices, codes)
        patch = PathPatch(path, edgecolor='red', facecolor='none', linewidth=2)
        ax.add_patch(patch)

# -----------------------------
# Cargar leyenda desde CSV
# -----------------------------
def cargar_leyenda_csv(csv_path):
    leyenda = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            leyenda.append({
                "capa": row["capa"],
                "tipo": row["tipo"],
                "color": row["color"],
                "etiqueta": row["etiqueta"]
            })
    return leyenda

# -----------------------------
# Descargar leyenda oficial WMS
# -----------------------------
def download_wms_legend(base_url, layer, format="image/png"):
    url = (
        f"{base_url}SERVICE=WMS&REQUEST=GetLegendGraphic&VERSION=1.3.0&"
        f"FORMAT={format}&LAYER={layer}"
    )
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        return Image.open(BytesIO(r.content))
    else:
        raise Exception(f"Error {r.status_code} al descargar leyenda\nURL: {url}")

# -----------------------------
# Componer imagen con leyenda oficial (fallback CSV para Montes Públicos)
# -----------------------------
def compose_image_with_legend(layer_key, bbox, polygons, carpeta_salida):
    capa_urls = {
        "MontesPublicos": ("https://wms.mapama.gob.es/sig/Biodiversidad/IEPF_CMUP?", "AM.ForestManagementArea", ""),
        "RedNatura2000": ("https://wms.mapama.gob.es/sig/Biodiversidad/RedNatura/wms.aspx?", "PS.ProtectedSite", ""),
        "ViasPecuarias": ("https://wms.mapama.gob.es/sig/Biodiversidad/ViasPecuarias/wms.aspx?", "Red General de Vías Pecuarias", "default")
    }

    titulos_amables = {
        "MontesPublicos": "Parcela sobre ortofoto y Montes Públicos",
        "RedNatura2000": "Parcela sobre ortofoto y Red Natura 2000",
        "ViasPecuarias": "Parcela sobre ortofoto y Vías Pecuarias"
    }

    fondo_url = "https://www.ign.es/wms-inspire/pnoa-ma?"
    fondo_layer = "OI.OrthoimageCoverage"

    fondo_img = download_wms_image(fondo_url, fondo_layer, "", bbox, format="image/jpeg")
    capa_base, capa_layer, capa_style = capa_urls[layer_key]
    capa_img = download_wms_image(capa_base, capa_layer, capa_style, bbox, format="image/png")

    # Crear figura
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(fondo_img, extent=[bbox[1], bbox[3], bbox[0], bbox[2]])
    ax.imshow(capa_img, extent=[bbox[1], bbox[3], bbox[0], bbox[2]], alpha=0.6)
    draw_kml_polygons(ax, polygons)

    fecha = date.today().strftime("%d-%m-%Y")
    ax.set_title(f"{titulos_amables[layer_key]} ({fecha})", fontsize=13)
    ax.axis("off")

    # Intentar leyenda oficial, fallback CSV si falla en Montes Públicos
    try:
        legend_img = download_wms_legend(capa_base, capa_layer)
        legend_ax = fig.add_axes([0.75, 0.05, 0.2, 0.2])
        legend_ax.imshow(legend_img)
        legend_ax.axis("off")
    except Exception:
        if layer_key == "MontesPublicos":
            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leyenda_montespublicos.csv")
            leyenda = cargar_leyenda_csv(csv_path)
            handles = []
            for item in leyenda:
                patch = plt.Line2D([], [], color=item["color"], linewidth=6, alpha=0.6, label=item["etiqueta"])
                handles.append(patch)
            ax.legend(handles=handles, loc='upper left', fontsize=7.5, ncol=2,
                      handlelength=1.5, columnspacing=0.8, borderpad=0.5, labelspacing=0.4)

    plt.tight_layout()
    filename = os.path.join(carpeta_salida, f"vista_parcela_{layer_key.lower()}_leyenda.png")
    plt.savefig(filename, dpi=150)
    plt.close()
    print(f"Imagen con leyenda guardada: {filename}")

# -----------------------------
# Cálculo por píxel con varios umbrales
# -----------------------------
def polygons_to_shapely(polygons):
    geoms = []
    for rings in polygons:
        if not rings:
            continue
        exterior = rings[0]
        interiors = rings[1:] if len(rings) > 1 else []
        poly = Polygon(exterior, interiors)
        geoms.append(poly)
    return MultiPolygon(geoms)

def calcular_porcentaje_pixeles(parcela_polygons, capa_img, bbox, umbral=250):
    parcela_geom = polygons_to_shapely(parcela_polygons)

    width, height = capa_img.size
    xs = np.linspace(bbox[1], bbox[3], width)
    ys = np.linspace(bbox[0], bbox[2], height)

    mask = np.zeros((height, width), dtype=bool)
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            if parcela_geom.contains(Point(x, y)):
                mask[i, j] = True

    arr = np.array(capa_img.convert("L"))
    arr_masked = arr[mask]

    afectados = np.sum(arr_masked < umbral)
    total = arr_masked.size

    porcentaje = (afectados / total) * 100 if total > 0 else 0
    return porcentaje

# -----------------------------
# Ejecución principal (batch desde carpeta KMLs)
# -----------------------------
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    kml_dir = os.path.join(script_dir, "KMLs")
    resultados_dir = os.path.join(script_dir, "RESULTADOS-BUSQUEDA")

    os.makedirs(kml_dir, exist_ok=True)
    os.makedirs(resultados_dir, exist_ok=True)

    kml_files = [f for f in os.listdir(kml_dir) if f.lower().endswith(".kml")]

    if not kml_files:
        print("No se encontraron archivos KML en la carpeta 'KMLs'.")
        exit()

    capa_urls = {
        "MontesPublicos": ("https://wms.mapama.gob.es/sig/Biodiversidad/IEPF_CMUP?", "AM.ForestManagementArea", ""),
        "RedNatura2000": ("https://wms.mapama.gob.es/sig/Biodiversidad/RedNatura/wms.aspx?", "PS.ProtectedSite", ""),
        "ViasPecuarias": ("https://wms.mapama.gob.es/sig/Biodiversidad/ViasPecuarias/wms.aspx?", "Red General de Vías Pecuarias", "default")
    }

    umbrales = [250, 200, 150]
    resumen_general = []

    for kml_name in kml_files:
        kml_path = os.path.join(kml_dir, kml_name)
        nombre_base = os.path.splitext(kml_name)[0]
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        carpeta_salida = os.path.join(resultados_dir, f"{nombre_base}_{timestamp}")
        os.makedirs(carpeta_salida, exist_ok=True)

        print(f"\nProcesando: {kml_name}")
        try:
            polygons = parse_kml_polygons(kml_path)
            bbox = get_bbox_from_polygons(polygons)
        except Exception as e:
            print(f"Error al leer {kml_name}: {e}")
            continue

        resultados = []

        for capa, (base_url, layer, style) in capa_urls.items():
            try:
                # Generar PNG con leyenda oficial o CSV
                compose_image_with_legend(capa, bbox, polygons, carpeta_salida)

                # Calcular porcentajes por píxel
                capa_img = download_wms_image(base_url, layer, style, bbox, format="image/png")
                for u in umbrales:
                    porcentaje = calcular_porcentaje_pixeles(polygons, capa_img, bbox, umbral=u)
                    resultados.append(f"{capa} (umbral {u}): {porcentaje:.2f}%")
            except Exception as e:
                resultados.append(f"{capa}: Error en cálculo ({e})")

        # Guardar TXT de resultados individuales
        txt_path = os.path.join(carpeta_salida, "porcentajes_afeccion.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"Resultados para {kml_name} ({timestamp}):\n")
            f.write("\n".join(resultados))

        print(f"Resultados guardados en: {carpeta_salida}")

        # Añadir al resumen general
        resumen_general.append(f"--- {kml_name} ({timestamp}) ---")
        resumen_general.extend(resultados)
        resumen_general.append("")

    # Guardar resumen maestro
    resumen_path = os.path.join(resultados_dir, "resumen_general.txt")
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write("Resumen general de porcentajes de afección:\n\n")
        f.write("\n".join(resumen_general))

    print(f"\nResumen maestro guardado en: {resumen_path}")