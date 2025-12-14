import requests
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET
import json
from io import BytesIO

# Intentar importar PIL, pero continuar si no está disponible
try:
    from PIL import Image, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("⚠ Pillow no disponible - se omitirá la composición de imágenes y contornos")


class CatastroDownloader:
    """
    Descarga documentación del Catastro español a partir de referencias catastrales.
    Incluye generación de mapas, KML, y capas de afecciones urbanísticas/ambientales.
    """

    def __init__(self, output_dir="descargas_catastro"):
        self.output_dir = output_dir
        self.base_url = "https://ovc.catastro.meh.es"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self._municipio_cache = {}

    def limpiar_referencia(self, ref):
        """Limpia la referencia catastral eliminando espacios."""
        return ref.replace(" ", "").strip()

    def extraer_del_mun(self, ref):
        """Extrae el código de delegación (2 dígitos) y municipio (3 dígitos) de la referencia."""
        ref = self.limpiar_referencia(ref)
        if len(ref) >= 5:
            return ref[:2], ref[2:5]
        return "", ""

    def obtener_coordenadas(self, referencia):
        """Obtiene las coordenadas de la parcela desde el servicio del Catastro."""
        ref = self.limpiar_referencia(referencia)

        # Método 1: Servicio REST JSON
        try:
            url_json = (
                "http://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/"
                f"COVCCallejero.svc/json/Geo_RCToWGS84/{ref}"
            )
            response = requests.get(url_json, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if (
                    "geo" in data
                    and "xcen" in data["geo"]
                    and "ycen" in data["geo"]
                ):
                    lon = float(data["geo"]["xcen"])
                    lat = float(data["geo"]["ycen"])
                    print(f"  Coordenadas obtenidas (JSON): Lon={lon}, Lat={lat}")
                    return {"lon": lon, "lat": lat, "srs": "EPSG:4326"}
        except Exception as e:
            pass

        # Método 2: Extraer del GML de parcela
        try:
            url_gml = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
            params = {
                "service": "wfs",
                "version": "2.0.0",
                "request": "GetFeature",
                "STOREDQUERY_ID": "GetParcel",
                "refcat": ref,
                "srsname": "EPSG:4326",
            }

            response = requests.get(url_gml, params=params, timeout=30)
            if response.status_code == 200:
                root = ET.fromstring(response.content)

                namespaces = {
                    "gml": "http://www.opengis.net/gml/3.2",
                    "cp": "http://inspire.ec.europa.eu/schemas/cp/4.0",
                    "gmd": "http://www.isotc211.org/2005/gmd",
                }

                for ns_uri in namespaces.values():
                    pos_list = root.findall(f".//{{{ns_uri}}}pos")
                    if pos_list:
                        coords_text = pos_list[0].text.strip().split()
                        if len(coords_text) >= 2:
                            v1 = float(coords_text[0])
                            v2 = float(coords_text[1])
                            if 36 <= v1 <= 44 and -10 <= v2 <= 5: 
                                lat, lon = v1, v2
                            elif 36 <= v2 <= 44 and -10 <= v1 <= 5:
                                lat, lon = v2, v1
                            else:
                                lat, lon = v1, v2 # Asumir (lat, lon) por defecto o (v1, v2)
                                
                            print(f"  Coordenadas extraídas del GML: Lon={lon}, Lat={lat}")
                            return {"lon": lon, "lat": lat, "srs": "EPSG:4326"}
        except Exception as e:
            pass
        
        # Método 3: Servicio XML original
        try:
            url = (
                "http://ovc.catastro.meh.es/ovcservweb/ovcswlocalizacionrc/"
                "ovccoordenadas.asmx/Consulta_RCCOOR"
            )
            params = {"SRS": "EPSG:4326", "RC": ref}

            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                coords_element = root.find(
                    ".//{http://www.catastro.meh.es/}coord"
                )
                if coords_element is not None:
                    geo = coords_element.find(
                        "{http://www.catastro.meh.es/}geo"
                    )
                    if geo is not None:
                        xcen = geo.find(
                            "{http://www.catastro.meh.es/}xcen"
                        )
                        ycen = geo.find(
                            "{http://www.catastro.meh.es/}ycen"
                        )

                        if xcen is not None and ycen is not None:
                            lon = float(xcen.text)
                            lat = float(ycen.text)
                            print(f"  Coordenadas obtenidas (XML): Lon={lon}, Lat={lat}")
                            return {"lon": lon, "lat": lat, "srs": "EPSG:4326"}
        except Exception as e:
            pass

        print("  ✗ No se pudieron obtener coordenadas por ningún método")
        return None

    def convertir_coordenadas_a_etrs89(self, lon, lat):
        """Convierte coordenadas WGS84 a ETRS89/UTM (aproximación)."""
        if lon < -6:
            zona = 29
            epsg = 25829
        elif lon < 0:
            zona = 30
            epsg = 25830
        else:
            zona = 31
            epsg = 25831

        return {"epsg": epsg, "zona": zona}

    def calcular_bbox(self, lon, lat, buffer_metros=200):
        """Calcula un BBOX (WGS84) alrededor de un punto para WMS."""
        # Aproximaciones: 1 grado de longitud ~ 85km, 1 grado de latitud ~ 111km
        buffer_lon = buffer_metros / 85000
        buffer_lat = buffer_metros / 111000

        minx = lon - buffer_lon
        miny = lat - buffer_lat
        maxx = lon + buffer_lon
        maxy = lat + buffer_lat

        return f"{minx},{miny},{maxx},{maxy}"

    def generar_kml(self, referencia, coords, gml_coords=None):
        """
        Genera archivo KML con el punto central y el polígono de la parcela.
        
        Args:
            referencia: Referencia catastral
            coords: Dict con lon, lat del centro
            gml_coords: Lista de tuplas (lat, lon) del polígono (opcional)
        """
        ref = self.limpiar_referencia(referencia)
        filename = f"{self.output_dir}/{ref}_parcela.kml"
        
        lon = coords["lon"]
        lat = coords["lat"]
        
        kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Parcela Catastral {ref}</name>
    <description>Información catastral de la referencia {ref}</description>
    
    <Style id="parcela_style">
      <LineStyle>
        <color>ff0000ff</color>
        <width>3</width>
      </LineStyle>
      <PolyStyle>
        <color>4d0000ff</color>
      </PolyStyle>
    </Style>
    
    <Style id="punto_style">
      <IconStyle>
        <scale>1.2</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    
    <Placemark>
      <name>Centro Parcela {ref}</name>
      <description>
        <![CDATA[
        <b>Referencia Catastral:</b> {ref}<br/>
        <b>Coordenadas:</b> {lat:.6f}, {lon:.6f}<br/>
        <b>Enlace Catastro:</b> <a href="https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?refcat={ref}">Ver en Catastro</a><br/>
        <b>Google Maps:</b> <a href="https://www.google.com/maps/search/?api=1&query={lat},{lon}">Ver en Google Maps</a>
        ]]>
      </description>
      <styleUrl>#punto_style</styleUrl>
      <Point>
        <coordinates>{lon},{lat},0</coordinates>
      </Point>
    </Placemark>
'''
        
        # Si tenemos coordenadas del polígono, añadir el polígono
        if gml_coords and len(gml_coords) > 2:
            kml_content += '''
    <Placemark>
      <name>Contorno Parcela {}</name>
      <description>Límite de la parcela catastral</description>
      <styleUrl>#parcela_style</styleUrl>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
'''.format(ref)
            
            # Convertir coordenadas a formato KML (lon,lat,alt)
            for coord in gml_coords:
                # gml_coords puede venir como (lat,lon) o (lon,lat), aplicar heurística
                v1, v2 = coord
                if 36 <= v1 <= 44 and -10 <= v2 <= 5:
                    # v1 es lat, v2 es lon
                    kml_content += f"              {v2},{v1},0\n"
                elif 36 <= v2 <= 44 and -10 <= v1 <= 5:
                    # v1 es lon, v2 es lat
                    kml_content += f"              {v1},{v2},0\n"
                else:
                    # Por defecto, asumimos v1=lat, v2=lon
                    kml_content += f"              {v2},{v1},0\n"
            
            # Cerrar el polígono
            first_coord = gml_coords[0]
            v1, v2 = first_coord
            if 36 <= v1 <= 44 and -10 <= v2 <= 5:
                kml_content += f"              {v2},{v1},0\n"
            elif 36 <= v2 <= 44 and -10 <= v1 <= 5:
                kml_content += f"              {v1},{v2},0\n"
            else:
                kml_content += f"              {v2},{v1},0\n"
            
            kml_content += '''            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
'''
        
        kml_content += '''  </Document>
</kml>'''
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(kml_content)
            print(f"  ✓ Archivo KML generado: {filename}")
            return True
        except Exception as e:
            print(f"  ✗ Error generando KML: {e}")
            return False

    def descargar_capas_afecciones(self, referencia, bbox_wgs84, width=1600, height=1600):
        """
        Descarga capas de afecciones territoriales sobre la parcela.
        Incluye planeamiento urbanístico, protecciones ambientales, etc.
        """
        ref = self.limpiar_referencia(referencia)
        print("\n  📋 Descargando capas de afecciones...")
        
        coords_list = bbox_wgs84.split(",")
        bbox_wms13 = f"{coords_list[1]},{coords_list[0]},{coords_list[3]},{coords_list[2]}"
        
        capas_disponibles = {
            # Catastro - Información básica
            "catastro_parcelas": {
                "url": "http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
                "version": "1.1.1",
                "layers": "Catastro",
                "srs_param": "SRS",
                "bbox": bbox_wgs84,
                "descripcion": "Plano catastral con parcelas"
            },
            
            # IDEE - Planeamiento urbanístico
            "planeamiento_urbanistico": {
                "url": "https://www.idee.es/wms/IDEE-Planeamiento/IDEE-Planeamiento",
                "version": "1.3.0",
                "layers": "PlaneamientoGeneral",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Planeamiento urbanístico general"
            },
            
            # Catastro - Zonas de valor
            "catastro_zonas_valor": {
                "url": "http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
                "version": "1.1.1",
                "layers": "ZonasValor",
                "srs_param": "SRS",
                "bbox": bbox_wgs84,
                "descripcion": "Zonas de valor catastral"
            },
            
            # Red Natura 2000
            "red_natura_2000": {
                "url": "https://wms.mapama.gob.es/sig/Biodiversidad/EENNPPZZ/wms.aspx",
                "version": "1.3.0",
                "layers": "RedNatura2000",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Espacios Red Natura 2000"
            },
            
            # Dominio público hidráulico
            "dominio_publico_hidraulico": {
                "url": "https://servicios.idee.es/wms-inspire/hidrografia",
                "version": "1.3.0",
                "layers": "HY.PhysicalWaters.Waterbodies",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Hidrografía y zonas inundables"
            },
            
            # Costas (zona marítimo-terrestre)
            "dominio_maritimo": {
                "url": "https://ideihm.covam.es/wms-c/mapas/Demarcaciones",
                "version": "1.3.0",
                "layers": "Demarcaciones",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Dominio público marítimo-terrestre"
            },
            
            # Montes de Utilidad Pública
            "montes_utilidad_publica": {
                "url": "https://wms.mapama.gob.es/sig/Biodiversidad/MUP/wms.aspx",
                "version": "1.3.0",
                "layers": "MUP",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Montes de Utilidad Pública"
            },
            
            # Vías pecuarias
            "vias_pecuarias": {
                "url": "https://wms.mapama.gob.es/sig/Biodiversidad/ViaPecuaria/wms.aspx",
                "version": "1.3.0",
                "layers": "ViasPecuarias",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Vías pecuarias"
            },
        }
        
        capas_descargadas = []
        
        for nombre_capa, config in capas_disponibles.items():
            try:
                params = {
                    "SERVICE": "WMS",
                    "VERSION": config["version"],
                    "REQUEST": "GetMap",
                    "LAYERS": config["layers"],
                    "STYLES": "",
                    config["srs_param"]: "EPSG:4326",
                    "BBOX": config["bbox"],
                    "WIDTH": str(width),
                    "HEIGHT": str(height),
                    "FORMAT": "image/png",
                    "TRANSPARENT": "TRUE",
                }
                
                response = requests.get(config["url"], params=params, timeout=60)
                
                # Verificar que no sea un error XML
                if response.status_code == 200 and len(response.content) > 1000:
                    # Verificar que sea una imagen válida y no esté vacía
                    if b'PNG' in response.content[:100] or b'JFIF' in response.content[:100]:
                        filename = f"{self.output_dir}/{ref}_afeccion_{nombre_capa}.png"
                        with open(filename, 'wb') as f:
                            f.write(response.content)
                        print(f"    ✓ {config['descripcion']}: {filename}")
                        capas_descargadas.append({
                            "nombre": nombre_capa,
                            "descripcion": config["descripcion"],
                            "archivo": filename
                        })
                    else:
                        print(f"    ⚠ {config['descripcion']}: Sin datos en esta zona")
                else:
                    print(f"    ⚠ {config['descripcion']}: No disponible")
                    
            except Exception as e:
                print(f"    ⚠ {config['descripcion']}: Error - {str(e)[:50]}")
        
        # Guardar informe JSON de capas descargadas
        if capas_descargadas:
            informe_file = f"{self.output_dir}/{ref}_afecciones_info.json"
            with open(informe_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "referencia": ref,
                    "capas_disponibles": capas_descargadas,
                    "total_capas": len(capas_descargadas)
                }, f, indent=2, ensure_ascii=False)
            print(f"\n  ✓ Informe de afecciones guardado: {informe_file}")
        
        return len(capas_descargadas) > 0

    def descargar_consulta_descriptiva_pdf(self, referencia):
        """Descarga el PDF oficial de consulta descriptiva"""
        ref = self.limpiar_referencia(referencia)
        del_code = ref[:2]
        mun_code = ref[2:5]
        
        url = f"https://www1.sedecatastro.gob.es/CYCBienInmueble/SECImprimirCroquisYDatos.aspx?del={del_code}&mun={mun_code}&refcat={ref}"
        
        filename = f"{self.output_dir}/{ref}_consulta_oficial.pdf"
        
        if os.path.exists(filename):
            print(f"  ↩ PDF oficial ya existe")
            return True
        
        try:
            response = requests.get(url, timeout=30)
                
            if response.status_code == 200 and response.headers.get("Content-Type", "").startswith("application/pdf"):
                with open(filename, "wb") as f:
                    f.write(response.content)
                print(f"  ✓ PDF oficial descargado: {filename}")
                return True
            else:
                print(f"  ✗ PDF oficial falló (Status {response.status_code})")
                return False
                    
        except Exception as e:
            print(f"  ✗ Error descargando PDF: {e}")
            return False

    def extraer_coordenadas_gml(self, gml_file):
        """Extrae las coordenadas del polígono desde el archivo GML."""
        try:
            tree = ET.parse(gml_file)
            root = tree.getroot()

            coords = []

            for pos_list in root.findall(
                ".//{http://www.opengis.net/gml/3.2}posList"
            ):
                parts = pos_list.text.strip().split()
                
                for i in range(0, len(parts), 2):
                    if i + 1 < len(parts):
                         coords.append((float(parts[i]), float(parts[i + 1])))

            if not coords:
                for pos in root.findall(
                    ".//{http://www.opengis.net/gml/3.2}pos"
                ):
                    parts = pos.text.strip().split()
                    if len(parts) >= 2:
                        coords.append((float(parts[0]), float(parts[1])))

            if coords:
                print(f"  ✓ Extraídas {len(coords)} coordenadas del GML")
                return coords

            print("  ⚠ No se encontraron coordenadas en el GML")
            return None

        except Exception as e:
            print(f"  ⚠ Error extrayendo coordenadas del GML: {e}")
            return None

    def convertir_coordenadas_a_pixel(self, coords, bbox, width, height):
        """Convierte coordenadas a píxeles de la imagen según BBOX WGS84."""
        try:
            minx, miny, maxx, maxy = [float(x) for x in bbox.split(",")]
            pixels = []

            LAT_RANGE = (36, 44)
            LON_RANGE = (-10, 5)

            for v1, v2 in coords:
                lat, lon = v1, v2
                
                if LAT_RANGE[0] <= v1 <= LAT_RANGE[1] and LON_RANGE[0] <= v2 <= LON_RANGE[1]: 
                     lat, lon = v1, v2
                elif LON_RANGE[0] <= v1 <= LON_RANGE[1] and LAT_RANGE[0] <= v2 <= LAT_RANGE[1]: 
                     lon, lat = v1, v2
                else: 
                     lat, lon = v1, v2

            # Fix indentation error potential above
            
                x_norm = (lon - minx) / (maxx - minx) if maxx != minx else 0.5
                y_norm = (maxy - lat) / (maxy - miny) if maxy != miny else 0.5

                x = max(0, min(width - 1, int(x_norm * width)))
                y = max(0, min(height - 1, int(y_norm * height)))
                pixels.append((x, y))

            return pixels

        except Exception as e:
            print(f"  ⚠ Error convirtiendo coordenadas a píxeles: {e}")
            return None

    def dibujar_contorno_en_imagen(
        self, imagen_path, pixels, output_path, color=(255, 0, 0), width=4
    ):
        """Dibuja el contorno de la parcela sobre una imagen existente."""
        if not PILLOW_AVAILABLE:
            print("  ⚠ Pillow no disponible, no se puede dibujar contorno")
            return False

        try:
            img = Image.open(imagen_path).convert("RGBA")
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            if len(pixels) > 2:
                if pixels[0] != pixels[-1]:
                    pixels = pixels + [pixels[0]]
                draw.line(pixels, fill=color + (255,), width=width)

            result = Image.alpha_composite(img, overlay).convert("RGB")
            result.save(output_path)
            print(f"  ✓ Contorno dibujado en {output_path}")
            return True

        except Exception as e:
            print(f"  ⚠ Error dibujando contorno: {e}")
            return False

    def superponer_contorno_parcela(self, ref, bbox_wgs84):
        """Superpone el contorno de la parcela sobre plano, ortofoto y composición."""
        ref = self.limpiar_referencia(ref)
        gml_file = f"{self.output_dir}/{ref}_parcela.gml"
        if not os.path.exists(gml_file):
            print("  ⚠ No existe GML de parcela, no se puede dibujar contorno")
            return False

        coords = self.extraer_coordenadas_gml(gml_file)
        if not coords:
            return False

        exito = False

        imagenes = [
            (
                f"{self.output_dir}/{ref}_ortofoto_pnoa.jpg",
                f"{self.output_dir}/{ref}_ortofoto_pnoa_contorno.jpg",
            ),
            (
                f"{self.output_dir}/{ref}_plano_catastro.png",
                f"{self.output_dir}/{ref}_plano_catastro_contorno.png",
            ),
            (
                f"{self.output_dir}/{ref}_plano_con_ortofoto.png",
                f"{self.output_dir}/{ref}_plano_con_ortofoto_contorno.png",
            ),
        ]

        for in_path, out_path in imagenes:
            if os.path.exists(in_path):
                try:
                    with Image.open(in_path) as img:
                        w, h = img.size
                    pixels = self.convertir_coordenadas_a_pixel(
                        coords, bbox_wgs84, w, h
                    )
                    if pixels and self.dibujar_contorno_en_imagen(
                        in_path, pixels, out_path
                    ):
                        exito = True
                except Exception as e:
                    print(f"  ⚠ Error procesando imagen {in_path}: {e}")

        return exito

    def descargar_plano_ortofoto(self, referencia):
        """Descarga el plano con ortofoto usando servicios WMS y guarda geolocalización."""
        ref = self.limpiar_referencia(referencia)

        print("  Obteniendo coordenadas...")
        coords = self.obtener_coordenadas(ref)

        if not coords:
            print("  ✗ No se pudieron obtener coordenadas para generar el plano")
            return False

        lon = coords["lon"]
        lat = coords["lat"]

        bbox_wgs84 = self.calcular_bbox(lon, lat, buffer_metros=200)
        coords_list = bbox_wgs84.split(",")
        bbox_wms13 = (
            f"{coords_list[1]},{coords_list[0]},{coords_list[3]},{coords_list[2]}"
        )

        print("  Generando mapa con ortofoto...")

        wms_url = "http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx"

        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": "Catastro",
            "STYLES": "",
            "SRS": "EPSG:4326",
            "BBOX": bbox_wgs84,
            "WIDTH": "1600",
            "HEIGHT": "1600",
            "FORMAT": "image/png",
            "TRANSPARENT": "FALSE",
        }

        try:
            response_catastro = requests.get(
                wms_url, params=params, timeout=60
            )

            plano_descargado = False
            filename_catastro = f"{self.output_dir}/{ref}_plano_catastro.png"

            if (
                response_catastro.status_code == 200
                and len(response_catastro.content) > 1000
            ):
                with open(filename_catastro, "wb") as f:
                    f.write(response_catastro.content)
                print(f"  ✓ Plano catastral descargado: {filename_catastro}")
                plano_descargado = True
            else:
                print("  ✗ Error descargando plano catastral")


            ortofotos_descargadas = False

            # PNOA
            try:
                wms_pnoa_url = "http://www.ign.es/wms-inspire/pnoa-ma"
                params_pnoa = {
                    "SERVICE": "WMS",
                    "VERSION": "1.3.0",
                    "REQUEST": "GetMap",
                    "LAYERS": "OI.OrthoimageCoverage",
                    "STYLES": "",
                    "CRS": "EPSG:4326",
                    "BBOX": bbox_wms13,
                    "WIDTH": "1600",
                    "HEIGHT": "1600",
                    "FORMAT": "image/jpeg",
                }

                response_pnoa = requests.get(
                    wms_pnoa_url, params=params_pnoa, timeout=60
                )

                if (
                    response_pnoa.status_code == 200
                    and len(response_pnoa.content) > 5000
                ):
                    filename_ortofoto = (
                        f"{self.output_dir}/{ref}_ortofoto_pnoa.jpg"
                    )
                    with open(filename_ortofoto, "wb") as f:
                        f.write(response_pnoa.content)
                    print(
                        f"  ✓ Ortofoto PNOA descargada: {filename_ortofoto}"
                    )
                    ortofotos_descargadas = True

                    if PILLOW_AVAILABLE and response_catastro.status_code == 200:
                        try:
                            if os.path.exists(filename_catastro):
                                with open(filename_catastro, "rb") as f:
                                    img_catastro = Image.open(BytesIO(f.read()))
                            else:
                                img_catastro = Image.open(
                                    BytesIO(response_catastro.content)
                                )
                                
                            img_ortofoto = Image.open(
                                BytesIO(response_pnoa.content)
                            )

                            img_ortofoto = img_ortofoto.convert("RGBA")
                            img_catastro = img_catastro.convert("RGBA")

                            resultado = Image.blend(img_ortofoto.convert("RGB"), img_catastro.convert("RGB"), alpha=0.6)

                            filename_composicion = (
                                f"{self.output_dir}/{ref}_plano_con_ortofoto.png"
                            )
                            resultado.save(filename_composicion, "PNG")
                            print(
                                f"  ✓ Composición creada: {filename_composicion}"
                            )
                        except Exception as e:
                            print(
                                f"  ⚠ No se pudo crear composición: {e}"
                            )
                    else:
                        if not PILLOW_AVAILABLE:
                            print(
                                "  ⚠ Composición omitida (Pillow no instalado)"
                            )

            except Exception as e:
                print(f"  ⚠ PNOA no disponible: {e}")

            if not ortofotos_descargadas:
                try:
                    wms_catastro_orto = wms_url
                    params_orto = {
                        "SERVICE": "WMS",
                        "VERSION": "1.1.1",
                        "REQUEST": "GetMap",
                        "LAYERS": "ORTOFOTOS",
                        "STYLES": "",
                        "SRS": "EPSG:4326",
                        "BBOX": bbox_wgs84,
                        "WIDTH": "1600",
                        "HEIGHT": "1600",
                        "FORMAT": "image/jpeg",
                        "TRANSPARENT": "FALSE",
                    }

                    response_orto = requests.get(
                        wms_catastro_orto, params=params_orto, timeout=60
                    )

                    if (
                        response_orto.status_code == 200
                        and len(response_orto.content) > 5000
                    ):
                        filename_ortofoto = (
                            f"{self.output_dir}/{ref}_ortofoto_catastro.jpg"
                        )
                        with open(filename_ortofoto, "wb") as f:
                            f.write(response_orto.content)
                        print(
                            f"  ✓ Ortofoto Catastro descargada: {filename_ortofoto}"
                        )
                        ortofotos_descargadas = True
                except Exception as e:
                    print(f"  ⚠ Ortofoto Catastro no disponible: {e}")

            if not ortofotos_descargadas:
                print("  ⚠ No se pudieron descargar ortofotos automáticamente")
                print(
                    f"  🔍 Google Maps: https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                )

            geo_info = {
                "referencia": ref,
                "coordenadas": coords,
                "bbox": bbox_wgs84,
                "url_visor_catastro": (
                    "https://www1.sedecatastro.gob.es/Cartografia/"
                    f"mapa.aspx?refcat={ref}"
                ),
                "url_google_maps": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                "url_google_earth": (
                    "https://earth.google.com/web/@"
                    f"{lat},{lon},100a,500d,35y,0h,0t,0r"
                ),
            }

            filename_geo = f"{self.output_dir}/{ref}_geolocalizacion.json"
            with open(filename_geo, "w", encoding="utf-8") as f:
                json.dump(geo_info, f, indent=2, ensure_ascii=False)
            print(f"  ✓ Información de geolocalización guardada: {filename_geo}")

            self.superponer_contorno_parcela(ref, bbox_wgs84)

            return plano_descargado

        except Exception as e:
            print(f"  ✗ Error descargando plano con ortofoto: {e}")
            return False

    def descargar_consulta_pdf(self, referencia):
        """Descarga el PDF oficial de consulta descriptiva (versión antigua)"""
        return self.descargar_consulta_descriptiva_pdf(referencia)

    def descargar_parcela_gml(self, referencia):
        """Descarga la geometría de la parcela en formato GML"""
        ref = self.limpiar_referencia(referencia)
        url = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
        
        params = {
            'service': 'wfs',
            'version': '2.0.0',
            'request': 'GetFeature',
            'STOREDQUERY_ID': 'GetParcel',
            'refcat': ref,
            'srsname': 'EPSG:4326'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                filename = f"{self.output_dir}/{ref}_parcela.gml"
                
                if b'ExceptionReport' in response.content or b'Exception' in response.content:
                    print(f"  ⚠ Parcela GML no disponible para {ref} (Exception Report en la respuesta)")
                    return False

                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"  ✓ Parcela GML descargada: {filename}")
                return True
            else:
                print(f"  ✗ Error descargando parcela GML para {ref}: Status {response.status_code}")
                return False
        except Exception as e:
            print(f"  ✗ Error descargando parcela GML para {ref}: {e}")
            return False
    
    def descargar_edificio_gml(self, referencia):
        """Descarga la geometría del edificio en formato GML"""
        ref = self.limpiar_referencia(referencia)
        url = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
        
        params = {
            'service': 'wfs',
            'version': '2.0.0',
            'request': 'GetFeature',
            'STOREDQUERY_ID': 'GetBuilding',
            'refcat': ref,
            'srsname': 'EPSG:4326'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                content = response.content
                if b'ExceptionReport' in content or b'Exception' in content:
                    print(f"  ⚠ Edificio GML no disponible para {ref} (puede ser solo parcela)")
                    return False
                    
                filename = f"{self.output_dir}/{ref}_edificio.gml"
                with open(filename, 'wb') as f:
                    f.write(content)
                print(f"  ✓ Edificio GML descargado: {filename}")
                return True
            else:
                print(f"  ✗ Error descargando edificio GML para {ref}: Status {response.status_code}")
                return False
        except Exception as e:
            print(f"  ✗ Error descargando edificio GML para {ref}: {e}")
            return False

    def descargar_todo(self, referencia, crear_zip=False):
        """Descarga todos los documentos para una referencia catastral."""
        print(f"\n{'='*60}")
        print(f"Procesando referencia: {referencia}")
        print(f"{'='*60}")

        ref = self.limpiar_referencia(referencia)
        ref_dir = Path(self.output_dir) / ref
        ref_dir.mkdir(exist_ok=True)

        old_dir = self.output_dir
        self.output_dir = str(ref_dir)

        # Obtener coordenadas primero para KML
        coords = self.obtener_coordenadas(ref)
        
        # Descargar GML de parcela (necesario para KML con polígono)
        parcela_gml_descargado = self.descargar_parcela_gml(ref)
        
        # Extraer coordenadas del GML si existe
        gml_coords = None
        if parcela_gml_descargado:
            gml_file = f"{self.output_dir}/{ref}_parcela.gml"
            gml_coords = self.extraer_coordenadas_gml(gml_file)
        
        # Generar archivo KML
        kml_generado = False
        if coords:
            kml_generado = self.generar_kml(ref, coords, gml_coords)

        # Descargar planos y ortofotos
        plano_descargado = self.descargar_plano_ortofoto(ref)
        
        # Descargar capas de afecciones
        afecciones_descargadas = False
        if coords:
            bbox_wgs84 = self.calcular_bbox(coords["lon"], coords["lat"], buffer_metros=200)
            afecciones_descargadas = self.descargar_capas_afecciones(ref, bbox_wgs84)

        resultados = {
            'consulta_descriptiva': self.descargar_consulta_pdf(ref),
            'plano_ortofoto': plano_descargado,
            'parcela_gml': parcela_gml_descargado, 
            'edificio_gml': self.descargar_edificio_gml(ref),
            'kml_generado': kml_generado,
            'capas_afecciones': afecciones_descargadas,
        }

        try:
            generador = GeneradorInformeCatastral(ref, self.output_dir)
            generador.cargar_datos()
            output_pdf = f"{self.output_dir}/{ref}_Informe_Analisis_Espacial.pdf"
            generador.generar_pdf(output_pdf)
            resultados['informe_pdf'] = True
        except Exception as e:
            print(f"✗ Error generando informe PDF: {e}")
            resultados['informe_pdf'] = False

        # Crear ZIP si se solicita
        if crear_zip:
            try:
                # Usar old_dir para la ruta de la carpeta base
                zip_path = crear_zip_referencia(ref, old_dir) 
                if zip_path:
                    resultados['zip_path'] = zip_path
                    resultados['zip_generado'] = True
                else:
                    resultados['zip_generado'] = False
            except Exception as e:
                print(f"✗ Error creando ZIP: {e}")
                resultados['zip_generado'] = False
        
        # Restablecer el directorio de salida y retornar
        self.output_dir = old_dir
        time.sleep(2)
        return resultados

    def procesar_lista(self, lista_referencias):
        """Procesa una lista de referencias catastrales"""
        print(f"\nIniciando descarga de {len(lista_referencias)} referencias...")
        print(f"Directorio de salida: {self.output_dir}\n")
        
        resultados_totales = []
        
        for i, ref in enumerate(lista_referencias, 1):
            print(f"\n[{i}/{len(lista_referencias)}]")
            # No se pasa 'crear_zip' aquí, se crea un ZIP de lote al final
            resultados = self.descargar_todo(ref) 
            resultados_totales.append({
                'referencia': ref,
                'resultados': resultados
            })
        
        print(f"\n{'='*60}")
        print("RESUMEN DE DESCARGAS")
        print(f"{'='*60}")
        
        for item in resultados_totales:
            ref = item['referencia']
            res = item['resultados']
            # Filtrar 'zip_path' del conteo si no existe
            exit_keys = [k for k in res if k not in ['zip_path', 'zip_generado']] 
            exitos = sum(1 for k in exit_keys if res.get(k))
            print(f"\n{ref}: {exitos}/{len(exit_keys)} categorías completadas")
            for doc, exitoso in res.items():
                if doc not in ['zip_path']:
                    estado = "✓" if exitoso else "✗"
                    print(f"  {estado} {doc}")


from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import datetime

class GeneradorInformeCatastral:
    def __init__(self, referencia, directorio_datos):
        self.referencia = referencia
        self.directorio = directorio_datos
        self.styles = getSampleStyleSheet()
        self._crear_estilos_personalizados()
    
    def _crear_estilos_personalizados(self):
        self.styles.add(ParagraphStyle(
            name='TituloInforme',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#003366'),
            spaceAfter=12,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='Subtitulo',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=8,
            spaceBefore=12
        ))
        self.styles.add(ParagraphStyle(
            name='TextoNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_JUSTIFY,
            spaceAfter=6
        ))
    
    def cargar_datos(self):
        geo_file = f"{self.directorio}/{self.referencia}_geolocalizacion.json"
        with open(geo_file, 'r', encoding='utf-8') as f:
            self.datos_geo = json.load(f)
        # El nombre del archivo en el código de descarga era 'afecciones_info.json'
        afecciones_file = f"{self.directorio}/{self.referencia}_afecciones_info.json" 
        if os.path.exists(afecciones_file):
            with open(afecciones_file, 'r', encoding='utf-8') as f:
                self.datos_afecciones = json.load(f)
        else:
            self.datos_afecciones = {'capas_disponibles': []}
    
    def generar_pdf(self, output_path):
        doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        elementos = []
        elementos.extend(self._crear_portada())
        elementos.extend(self._crear_datos_descriptivos())
        elementos.extend(self._crear_seccion_mapa())
        elementos.extend(self._crear_analisis_afectaciones())
        elementos.extend(self._crear_leyenda_anotaciones())
        doc.build(elementos)
        print(f"✓ PDF generado: {output_path}")
    
    def _crear_portada(self):
        elementos = []
        titulo = Paragraph(f"INFORME ANÁLISIS ESPACIAL<br/>Referencia Catastral {self.referencia}", self.styles['TituloInforme'])
        elementos.append(titulo)
        elementos.append(Spacer(1, 1*cm))
        fecha = datetime.now().strftime("%d/%m/%Y")
        fecha_texto = Paragraph(f"<b>Fecha de generación:</b> {fecha}", self.styles['TextoNormal'])
        elementos.append(fecha_texto)
        elementos.append(Spacer(1, 2*cm))
        return elementos
    
    def _crear_datos_descriptivos(self):
        elementos = []
        subtitulo = Paragraph("DATOS DESCRIPTIVOS", self.styles['Subtitulo'])
        elementos.append(subtitulo)
        coords = self.datos_geo.get('coordenadas', {})
        lon = coords.get('lon', 'N/A')
        lat = coords.get('lat', 'N/A')
        datos_tabla = [
            ['Referencia Catastral', self.referencia],
            ['Coordenadas (WGS84)', f"Lon: {lon}, Lat: {lat}"],
            ['BBOX', self.datos_geo.get('bbox', 'N/A')],
        ]
        tabla = Table(datos_tabla, colWidths=[6*cm, 10*cm])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e6f2ff')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 1*cm))
        return elementos
    
    def _crear_seccion_mapa(self):
        elementos = []
        subtitulo = Paragraph("REPRESENTACIÓN CARTOGRÁFICA", self.styles['Subtitulo'])
        elementos.append(subtitulo)
        imagen_path = f"{self.directorio}/{self.referencia}_plano_con_ortofoto_contorno.png" # Usar la composición con contorno
        if not os.path.exists(imagen_path):
            imagen_path = f"{self.directorio}/{self.referencia}_plano_catastro_contorno.png"
        if os.path.exists(imagen_path):
            img = RLImage(imagen_path, width=15*cm, height=15*cm)
            elementos.append(img)
        else:
            elementos.append(Paragraph("Imagen no disponible", self.styles['TextoNormal']))
        elementos.append(Spacer(1, 0.5*cm))
        leyenda_texto = Paragraph("<b>LEYENDA:</b> Geometría de Análisis (contorno rojo)", self.styles['TextoNormal'])
        elementos.append(leyenda_texto)
        elementos.append(Spacer(1, 1*cm))
        return elementos
    
    def _crear_analisis_afectaciones(self):
        elementos = []
        subtitulo = Paragraph("ANÁLISIS DE AFECTACIÓN ESPACIAL", self.styles['Subtitulo'])
        elementos.append(subtitulo)
        capas = self.datos_afecciones.get('capas_disponibles', [])
        if capas:
            for capa in capas:
                nombre_capa = capa.get('nombre', 'N/A')
                descripcion = capa.get('descripcion', 'N/A')
                datos_capa = [
                    ['Tipología', nombre_capa.upper()],
                    ['Descripción', descripcion],
                ]
                tabla_capa = Table(datos_capa, colWidths=[4*cm, 12*cm])
                tabla_capa.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#fff3cd')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ]))
                elementos.append(tabla_capa)
                elementos.append(Spacer(1, 0.5*cm))
        else:
            texto_sin_afecciones = Paragraph("No se han detectado afecciones territoriales para esta parcela.", self.styles['TextoNormal'])
            elementos.append(texto_sin_afecciones)
        elementos.append(Spacer(1, 1*cm))
        return elementos
    
    def _crear_leyenda_anotaciones(self):
        elementos = []
        subtitulo = Paragraph("ANOTACIONES DEL INFORME", self.styles['Subtitulo'])
        elementos.append(subtitulo)
        texto_anotaciones = """<b>Normativa aplicable:</b><br/>
        - Directiva 92/43/CEE del Consejo, relativa a la conservación de hábitats naturales.<br/>
        - Ley 42/2007, de 13 de diciembre, del Patrimonio Natural y de la Biodiversidad.<br/>
        - Real Decreto Legislativo 7/2015, Ley de Suelo y Rehabilitación Urbana.<br/><br/>
        <b>Advertencia:</b> El informe puede no ofrecer información exhaustiva, exacta o actualizada."""
        anotaciones = Paragraph(texto_anotaciones, self.styles['TextoNormal'])
        elementos.append(anotaciones)
        return elementos


import zipfile
import shutil

def crear_zip_referencia(referencia, directorio_base):
    """
    Crea un archivo ZIP con todos los documentos generados para una referencia.
    
    Args:
        referencia: Referencia catastral
        directorio_base: Directorio raíz donde están las descargas
    
    Returns:
        Ruta del archivo ZIP generado
    """
    ref_limpia = referencia.replace(" ", "").strip()
    directorio_ref = f"{directorio_base}/{ref_limpia}"
    
    if not os.path.exists(directorio_ref):
        print(f"✗ No existe el directorio {directorio_ref}")
        return None
    
    # Nombre del ZIP
    zip_filename = f"{directorio_base}/{ref_limpia}_completo.zip"
    
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Recorrer todos los archivos del directorio
            for root, dirs, files in os.walk(directorio_ref):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, directorio_base)
                    zipf.write(file_path, arcname)
                    print(f"  Añadido: {file}")
        
        size_mb = os.path.getsize(zip_filename) / (1024 * 1024)
        print(f"✓ ZIP creado: {zip_filename} ({size_mb:.2f} MB)")
        return zip_filename
    
    except Exception as e:
        print(f"✗ Error creando ZIP: {e}")
        return None


def procesar_y_comprimir(referencia, directorio_base="descargas_catastro"):
    """
    Procesa una referencia catastral completa y genera un ZIP con todo.
    
    Args:
        referencia: Referencia catastral
        directorio_base: Directorio de salida
    
    Returns:
        Ruta del archivo ZIP generado, y resultados
    """
    downloader = CatastroDownloader(output_dir=directorio_base)
    
    print(f"Procesando referencia: {referencia}")
    resultados = downloader.descargar_todo(referencia, crear_zip=True)
    
    zip_path = resultados.get('zip_path')
    
    return zip_path, resultados
