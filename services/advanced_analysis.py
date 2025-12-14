import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
import requests
import numpy as np
from io import BytesIO
from collections import Counter
from datetime import datetime
import json
import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages

class AnalizadorAfeccionesAmbientales:
    """
    Analiza afecciones ambientales desde KML calculando porcentajes
    reales mediante análisis de píxeles de capas WMS con máscara geométrica
    e integración con Catastro
    """
    
    def __init__(self, kml_path, referencia_catastral=None):
        self.kml_path = kml_path
        self.referencia_catastral = referencia_catastral
        self.bbox = None
        self.coordenadas = []
        self.mascara = None
        self.datos_catastro = None
        
        # Capas WMS con múltiples variantes de color
        self.capas = {
            'montes_publicos': {
                'url': 'https://www.ign.es/wms-inspire/cubierta-tierra',
                'layer': 'LC.ForestManagementUnit',
                'colores_posibles': [
                    (34, 139, 34),   # Verde forestal
                    (0, 128, 0),     # Verde oscuro
                    (46, 125, 50),   # Verde material
                    (76, 175, 80),   # Verde claro
                ],
                'tolerancia': 40
            },
            'red_natura': {
                'url': 'https://servicios.idee.es/wms-inspire/protectedsites',
                'layer': 'PS.ProtectedSite',
                'colores_posibles': [
                    (0, 128, 0),     # Verde protegido
                    (34, 139, 34),   # Verde forestal
                    (0, 100, 0),     # Verde oscuro
                    (60, 179, 113),  # Verde medio
                ],
                'tolerancia': 45
            },
            'vias_pecuarias': {
                'url': 'https://www.mapa.gob.es/servicios/wms/vias-pecuarias',
                'layer': 'viaspecuarias',
                'colores_posibles': [
                    (165, 42, 42),   # Marrón
                    (139, 69, 19),   # Marrón silla
                    (160, 82, 45),   # Siena
                    (205, 133, 63),  # Perú
                ],
                'tolerancia': 35
            },
            'patrimonio_geologico': {
                'url': 'https://www.ign.es/wms-inspire/geologia',
                'layer': 'GE.GeologicUnit',
                'colores_posibles': [
                    (128, 128, 128), # Gris
                    (169, 169, 169), # Gris oscuro
                ],
                'tolerancia': 50
            }
        }
        
        self.resultados = {}
    
    def consultar_catastro_por_coordenadas(self, lon, lat):
        """
        Consulta la referencia catastral usando coordenadas (CPMRC)
        Servicio: Consulta de Parcela por Mapa y Referencia Catastral
        """
        url = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC"
        
        params = {
            'SRS': 'EPSG:4326',
            'Coordenada_X': str(lon),
            'Coordenada_Y': str(lat)
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Parsear XML
            root = ET.fromstring(response.content)
            
            # Buscar referencia catastral
            rc_elem = root.find('.//{http://www.catastro.meh.es/}pc1')
            if rc_elem is not None:
                ref_catastral = rc_elem.text
                print(f"✓ Referencia catastral encontrada: {ref_catastral}")
                return ref_catastral
            else:
                print("⚠ No se encontró referencia catastral en esas coordenadas")
                return None
                
        except Exception as e:
            print(f"✗ Error consultando Catastro: {e}")
            return None
    
    def consultar_datos_catastro(self, referencia_catastral):
        """
        Consulta datos completos de una parcela catastral (DNPRC)
        Servicio: Datos No Protegidos por Referencia Catastral
        """
        url = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPRC"
        
        params = {
            'Provincia': '',
            'Municipio': '',
            'RC': referencia_catastral
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            ns = {'cat': 'http://www.catastro.meh.es/'}
            
            # Extraer información relevante
            datos = {
                'referencia_catastral': referencia_catastral,
                'direccion': self._extraer_texto(root, './/cat:ldt', ns),
                'municipio': self._extraer_texto(root, './/cat:nm', ns),
                'provincia': self._extraer_texto(root, './/cat:np', ns),
                'uso_principal': self._extraer_texto(root, './/cat:luso', ns),
                'superficie_catastral': self._extraer_texto(root, './/cat:sfc', ns),
                'superficie_construida': self._extraer_texto(root, './/cat:scc', ns),
                'ano_construccion': self._extraer_texto(root, './/cat:ant', ns),
                'codigo_postal': self._extraer_texto(root, './/cat:dp', ns),
            }
            
            # Buscar coordenadas de la geometría
            coords_elem = root.find('.//cat:coord', ns)
            if coords_elem is not None:
                xcen = coords_elem.find('cat:xcen', ns)
                ycen = coords_elem.find('cat:ycen', ns)
                if xcen is not None and ycen is not None:
                    datos['coord_x'] = xcen.text
                    datos['coord_y'] = ycen.text
            
            print(f"✓ Datos catastrales obtenidos para {referencia_catastral}")
            return datos
            
        except Exception as e:
            print(f"✗ Error obteniendo datos catastrales: {e}")
            return None
    
    def _extraer_texto(self, root, xpath, namespaces):
        """Extrae texto de un elemento XML, retorna None si no existe"""
        elem = root.find(xpath, namespaces)
        return elem.text if elem is not None else None
    
    def obtener_geometria_catastro(self, referencia_catastral):
        """
        Obtiene la geometría de la parcela desde Catastro (WFS)
        """
        url = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
        
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetFeature',
            'typeName': 'cp:CadastralParcel',
            'srsName': 'EPSG:4326',
            'outputFormat': 'application/gml+xml; version=3.2',
            'REFCAT': referencia_catastral
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            # Parsear GML para extraer coordenadas
            root = ET.fromstring(response.content)
            
            # Buscar coordenadas en el GML
            # Esto depende de la estructura del GML de Catastro
            ns = {
                'gml': 'http://www.opengis.net/gml/3.2',
                'cp': 'urn:x-inspire:specification:gmlas:CadastralParcels:3.0'
            }
            
            pos_list = root.find('.//gml:posList', ns)
            if pos_list is not None:
                coords_text = pos_list.text.strip().split()
                coords = []
                for i in range(0, len(coords_text), 2):
                    lat = float(coords_text[i])
                    lon = float(coords_text[i+1])
                    coords.append((lon, lat))
                
                print(f"✓ Geometría catastral obtenida: {len(coords)} puntos")
                return coords
            
        except Exception as e:
            print(f"✗ Error obteniendo geometría de Catastro: {e}")
        
        return None
    
    def validar_con_catastro(self):
        """
        Valida y enriquece la información con datos de Catastro
        """
        print("\n" + "="*70)
        print("VALIDACIÓN CON CATASTRO")
        print("="*70)
        
        # Si no hay referencia catastral, intentar obtenerla por coordenadas
        if not self.referencia_catastral:
            print("\n🔍 Buscando referencia catastral por coordenadas...")
            # Usar el centroide del polígono
            if self.coordenadas:
                lon_centro = sum(c[0] for c in self.coordenadas) / len(self.coordenadas)
                lat_centro = sum(c[1] for c in self.coordenadas) / len(self.coordenadas)
                
                self.referencia_catastral = self.consultar_catastro_por_coordenadas(
                    lon_centro, lat_centro
                )
        
        # Consultar datos completos
        if self.referencia_catastral:
            print(f"\n📋 Consultando datos de: {self.referencia_catastral}")
            self.datos_catastro = self.consultar_datos_catastro(self.referencia_catastral)
            
            if self.datos_catastro:
                print("\n" + "─"*70)
                print("INFORMACIÓN CATASTRAL")
                print("─"*70)
                print(f"Referencia: {self.datos_catastro['referencia_catastral']}")
                if self.datos_catastro['direccion']:
                    print(f"Dirección: {self.datos_catastro['direccion']}")
                if self.datos_catastro['municipio']:
                    print(f"Municipio: {self.datos_catastro['municipio']} ({self.datos_catastro['provincia']})")
                if self.datos_catastro['uso_principal']:
                    print(f"Uso: {self.datos_catastro['uso_principal']}")
                if self.datos_catastro['superficie_catastral']:
                    print(f"Superficie catastral: {self.datos_catastro['superficie_catastral']} m²")
                    sup_ha = float(self.datos_catastro['superficie_catastral']) / 10000
                    print(f"                       {sup_ha:.4f} ha")
                if self.datos_catastro['superficie_construida']:
                    print(f"Superficie construida: {self.datos_catastro['superficie_construida']} m²")
                
                # Comparar superficies
                sup_kml = self._calcular_superficie_aproximada()
                if self.datos_catastro['superficie_catastral'] and sup_kml:
                    sup_catastro_ha = float(self.datos_catastro['superficie_catastral']) / 10000
                    diferencia = abs(sup_kml - sup_catastro_ha)
                    porc_dif = (diferencia / sup_catastro_ha) * 100
                    print(f"\n📊 Comparación de superficies:")
                    print(f"   KML: {sup_kml:.4f} ha")
                    print(f"   Catastro: {sup_catastro_ha:.4f} ha")
                    print(f"   Diferencia: {diferencia:.4f} ha ({porc_dif:.1f}%)")
                    
                    if porc_dif < 5:
                        print(f"   ✅ Concordancia excelente")
                    elif porc_dif < 15:
                        print(f"   ⚠ Diferencia aceptable")
                    else:
                        print(f"   ❌ Diferencia significativa - verificar delimitación")
            
            # Intentar obtener geometría de Catastro
            print(f"\n🗺️ Obteniendo geometría catastral...")
            coords_catastro = self.obtener_geometria_catastro(self.referencia_catastral)
            
            if coords_catastro:
                print(f"✓ Se puede comparar con geometría oficial")
                # Aquí se podría implementar comparación de geometrías
        else:
            print("\n⚠ No se pudo obtener información catastral")
        
        print("="*70)
    
    def parsear_kml(self):
        """Extrae coordenadas y calcula bbox del KML"""
        tree = ET.parse(self.kml_path)
        root = tree.getroot()
        
        # Namespaces comunes en KML
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        # Buscar coordenadas
        coords_elem = root.find('.//kml:coordinates', ns)
        if coords_elem is None:
            coords_elem = root.find('.//coordinates')
        
        if coords_elem is None:
            print("⚠ No se encontraron coordenadas como texto simple en coordinates, intentando LinearRing...")
            # Intento alternativo para polígonos complejos
            coords_elem = root.find('.//kml:LinearRing/kml:coordinates', ns)
        
        if coords_elem is None:
             raise ValueError("No se encontraron coordenadas en el KML")
        
        coords_text = coords_elem.text.strip()
        self.coordenadas = []
        
        for linea in coords_text.split():
            if linea.strip():
                partes = linea.split(',')
                if len(partes) >= 2:
                    lon, lat = float(partes[0]), float(partes[1])
                    self.coordenadas.append((lon, lat))
        
        if not self.coordenadas:
            raise ValueError("No se pudieron parsear las coordenadas")
        
        # Calcular bbox
        lons = [c[0] for c in self.coordenadas]
        lats = [c[1] for c in self.coordenadas]
        
        self.bbox = {
            'minx': min(lons),
            'miny': min(lats),
            'maxx': max(lons),
            'maxy': max(lats)
        }
        
        print(f"✓ KML parseado: {len(self.coordenadas)} coordenadas")
        print(f"✓ BBox: {self.bbox}")
    
    def crear_mascara_poligono(self, width, height):
        """Crea una máscara binaria del polígono KML"""
        mascara = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mascara)
        
        # Convertir coordenadas geográficas a píxeles
        coords_pixel = []
        for lon, lat in self.coordenadas:
            x = int((lon - self.bbox['minx']) / (self.bbox['maxx'] - self.bbox['minx']) * width)
            y = int((self.bbox['maxy'] - lat) / (self.bbox['maxy'] - self.bbox['miny']) * height)
            coords_pixel.append((x, y))
        
        # Dibujar polígono relleno
        draw.polygon(coords_pixel, fill=255)
        
        self.mascara = np.array(mascara) > 0
        pixels_poligono = np.sum(self.mascara)
        
        print(f"✓ Máscara creada: {pixels_poligono:,} píxeles dentro del polígono")
        return self.mascara
    
    def descargar_capa_wms(self, nombre_capa, width=1200, height=1200):
        """Descarga una imagen WMS de la capa especificada"""
        config = self.capas[nombre_capa]
        
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetMap',
            'LAYERS': config['layer'],
            'BBOX': f"{self.bbox['miny']},{self.bbox['minx']},{self.bbox['maxy']},{self.bbox['maxx']}",
            'CRS': 'EPSG:4326',
            'WIDTH': width,
            'HEIGHT': height,
            'FORMAT': 'image/png',
            'TRANSPARENT': 'TRUE',
            'STYLES': ''
        }
        
        try:
            response = requests.get(config['url'], params=params, timeout=30)
            response.raise_for_status()
            
            img = Image.open(BytesIO(response.content))
            print(f"✓ Descargada capa: {nombre_capa} ({img.size[0]}x{img.size[1]})")
            return img
        
        except Exception as e:
            print(f"✗ Error descargando {nombre_capa}: {e}")
            return None
    
    def detectar_color_multiple(self, pixels, colores_posibles, tolerancia):
        """
        Detecta píxeles que coincidan con cualquiera de los colores posibles
        """
        mask_total = np.zeros(pixels.shape[:2], dtype=bool)
        
        for color in colores_posibles:
            diferencias = np.abs(pixels - color)
            mask_color = np.all(diferencias <= tolerancia, axis=2)
            mask_total = mask_total | mask_color
        
        return mask_total
    
    def analizar_pixeles(self, imagen, nombre_capa):
        """
        Analiza los píxeles de la imagen usando máscara geométrica
        y detectando múltiples variantes de color
        """
        if imagen is None:
            return {'error': 'Imagen no disponible'}
        
        config = self.capas[nombre_capa]
        
        # Convertir a RGB
        if imagen.mode != 'RGB':
            imagen = imagen.convert('RGB')
        
        # Obtener array de píxeles
        pixels = np.array(imagen)
        
        # Aplicar máscara del polígono
        if self.mascara is not None:
            pixels_dentro = pixels[self.mascara]
            total_pixels_poligono = len(pixels_dentro)
        else:
            pixels_dentro = pixels.reshape(-1, 3)
            total_pixels_poligono = len(pixels_dentro)
        
        # Detectar píxeles blancos/transparentes
        blancos = np.all(pixels_dentro > 240, axis=0)
        pixels_blancos = np.sum(blancos)
        
        # Área útil (dentro del polígono, sin blancos)
        area_util = total_pixels_poligono - pixels_blancos
        
        # Detectar píxeles afectados (con múltiples colores)
        if self.mascara is not None:
            # Crear una versión completa para análisis
            pixels_full_masked = pixels.copy()
            pixels_full_masked[~self.mascara] = [255, 255, 255]  # Blanquear fuera
            pixels_afectados_mask = self.detectar_color_multiple(
                pixels_full_masked, 
                config['colores_posibles'], 
                config['tolerancia']
            )
            pixels_afectados_mask = pixels_afectados_mask & self.mascara
            num_afectados = np.sum(pixels_afectados_mask)
        else:
            pixels_reshaped = pixels_dentro.reshape(pixels.shape[0], pixels.shape[1], 3)
            pixels_afectados_mask = self.detectar_color_multiple(
                pixels_reshaped,
                config['colores_posibles'],
                config['tolerancia']
            )
            num_afectados = np.sum(pixels_afectados_mask)
        
        # Calcular porcentajes
        if area_util == 0:
            porcentaje_afectacion = 0
            porcentaje_sobre_total = 0
        else:
            porcentaje_afectacion = (num_afectados / area_util) * 100
            porcentaje_sobre_total = (num_afectados / total_pixels_poligono) * 100
        
        # Analizar colores únicos dentro del polígono
        pixels_tuple = [tuple(p) for p in pixels_dentro]
        color_counts = Counter(pixels_tuple)
        top_colores = color_counts.most_common(10)
        
        # Calcular superficie aproximada (si se conocen las dimensiones reales)
        superficie_ha = self._calcular_superficie_aproximada()
        superficie_afectada = (superficie_ha * porcentaje_afectacion / 100) if superficie_ha else None
        
        return {
            'total_pixels_poligono': int(total_pixels_poligono),
            'pixels_blancos': int(pixels_blancos),
            'area_util': int(area_util),
            'pixels_afectados': int(num_afectados),
            'porcentaje_afectacion': round(porcentaje_afectacion, 2),
            'porcentaje_sobre_total': round(porcentaje_sobre_total, 2),
            'colores_detectados': len(color_counts),
            'top_colores': [(color, count) for color, count in top_colores],
            'colores_buscados': config['colores_posibles'],
            'tolerancia_usada': config['tolerancia'],
            'superficie_ha': superficie_ha,
            'superficie_afectada_ha': round(superficie_afectada, 4) if superficie_afectada else None
        }
    
    def _calcular_superficie_aproximada(self):
        """Calcula superficie aproximada en hectáreas usando lat/lon"""
        if not self.bbox:
            return None
        
        # Aproximación simple (solo válida para áreas pequeñas)
        lat_medio = (self.bbox['miny'] + self.bbox['maxy']) / 2
        
        # Metros por grado a esta latitud
        m_por_grado_lon = 111320 * np.cos(np.radians(lat_medio))
        m_por_grado_lat = 110540
        
        ancho_m = (self.bbox['maxx'] - self.bbox['minx']) * m_por_grado_lon
        alto_m = (self.bbox['maxy'] - self.bbox['miny']) * m_por_grado_lat
        
        area_m2 = ancho_m * alto_m
        area_ha = area_m2 / 10000
        
        return round(area_ha, 2)
    
    def analizar_todas_capas(self, width=1200, height=1200):
        """Analiza todas las capas ambientales disponibles"""
        if not self.bbox:
            self.parsear_kml()
        
        # Crear máscara del polígono
        self.crear_mascara_poligono(width, height)
        
        print("\n" + "="*70)
        print("INICIANDO ANÁLISIS DE AFECCIONES AMBIENTALES")
        print("="*70)
        
        for nombre_capa in self.capas.keys():
            print(f"\n{'─'*70}")
            print(f"📡 {nombre_capa.replace('_', ' ').upper()}")
            print(f"{'─'*70}")
            
            # Descargar imagen
            imagen = self.descargar_capa_wms(nombre_capa, width, height)
            
            # Analizar píxeles
            analisis = self.analizar_pixeles(imagen, nombre_capa)
            
            # Guardar resultados
            self.resultados[nombre_capa] = {
                'imagen': imagen,
                'analisis': analisis
            }
            
            # Mostrar resultados
            if 'error' not in analisis:
                print(f"  Píxeles en polígono: {analisis['total_pixels_poligono']:,}")
                print(f"  Área útil analizada: {analisis['area_util']:,} píxeles")
                print(f"  Píxeles afectados: {analisis['pixels_afectados']:,}")
                print(f"  🎯 AFECTACIÓN: {analisis['porcentaje_afectacion']}% (del área útil)")
                print(f"  📊 Sobre total: {analisis['porcentaje_sobre_total']}%")
                if analisis['superficie_afectada_ha']:
                    print(f"  📐 Superficie afectada: ~{analisis['superficie_afectada_ha']} ha")
                print(f"  Colores detectados: {analisis['colores_detectados']}")
                print(f"  Tolerancia: ±{analisis['tolerancia_usada']} RGB")
            else:
                print(f"  ✗ {analisis['error']}")
    
    def clasificar_afectacion(self, porcentaje):
        """Clasifica el nivel de afectación"""
        if porcentaje == 0:
            return "SIN AFECTACIÓN", "✅"
        elif porcentaje < 5:
            return "MUY BAJA", "🟢"
        elif porcentaje < 15:
            return "BAJA", "🟡"
        elif porcentaje < 35:
            return "MODERADA", "🟠"
        elif porcentaje < 60:
            return "ALTA", "🔴"
        else:
            return "MUY ALTA", "🔴"
    
    def generar_informe(self):
        """Genera un informe detallado de todas las afectaciones"""
        print("\n" + "="*70)
        print(" "*20 + "INFORME DE AFECTACIONES")
        print("="*70)
        print(f"\n📄 Archivo: {self.kml_path}")
        print(f"📍 Coordenadas: {len(self.coordenadas)} vértices")
        print(f"📐 Superficie aproximada: {self._calcular_superficie_aproximada()} ha")
        print(f"🗺️  BBox: ({self.bbox['minx']:.6f}, {self.bbox['miny']:.6f}) → "
              f"({self.bbox['maxx']:.6f}, {self.bbox['maxy']:.6f})")
        print(f"📅 Fecha análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n" + "─"*70)
        print("RESULTADOS POR CAPA")
        print("─"*70)
        
        for nombre_capa, datos in self.resultados.items():
            analisis = datos['analisis']
            titulo = nombre_capa.replace('_', ' ').title()
            
            print(f"\n🗂️  {titulo}")
            print("   " + "─"*65)
            
            if 'error' not in analisis:
                nivel, emoji = self.clasificar_afectacion(analisis['porcentaje_afectacion'])
                
                print(f"   {emoji} Nivel: {nivel}")
                print(f"   📊 Afectación: {analisis['porcentaje_afectacion']}% del área útil")
                print(f"   📈 Sobre total: {analisis['porcentaje_sobre_total']}%")
                print(f"   🎨 Píxeles afectados: {analisis['pixels_afectados']:,} / {analisis['area_util']:,}")
                
                if analisis['superficie_afectada_ha']:
                    print(f"   📐 Superficie: ~{analisis['superficie_afectada_ha']} ha afectadas")
                
                print(f"   🔍 Colores detectados: {analisis['colores_detectados']} únicos")
                print(f"   ⚙️  Tolerancia aplicada: ±{analisis['tolerancia_usada']} RGB")
                
                # Mostrar colores más frecuentes
                print(f"   🎨 Top 3 colores:")
                for i, (color, count) in enumerate(analisis['top_colores'][:3], 1):
                    porc = (count / analisis['area_util']) * 100
                    print(f"      {i}. RGB{color}: {count:,} píxeles ({porc:.1f}%)")
            else:
                print(f"   ✗ No disponible: {analisis['error']}")
        
        # Resumen ejecutivo
        print("\n" + "="*70)
        print("RESUMEN EJECUTIVO")
        print("="*70)
        
        afectaciones = []
        for nombre, datos in self.resultados.items():
            if 'error' not in datos['analisis']:
                afectaciones.append((
                    nombre.replace('_', ' ').title(),
                    datos['analisis']['porcentaje_afectacion']
                ))
        
        afectaciones.sort(key=lambda x: x[1], reverse=True)
        
        if afectaciones:
            print("\n🏆 Ranking de afectaciones:")
            for i, (nombre, porc) in enumerate(afectaciones, 1):
                nivel, emoji = self.clasificar_afectacion(porc)
                print(f"   {i}. {emoji} {nombre}: {porc}% ({nivel})")
        
        print("\n" + "="*70)
    
    def guardar_imagenes(self, directorio='output_afecciones'):
        """Guarda las imágenes descargadas y máscaras"""
        os.makedirs(directorio, exist_ok=True)
        
        # Guardar máscara
        if self.mascara is not None:
            mascara_img = Image.fromarray((self.mascara * 255).astype(np.uint8))
            ruta_mascara = os.path.join(directorio, "mascara_poligono.png")
            mascara_img.save(ruta_mascara)
            print(f"✓ Máscara guardada: {ruta_mascara}")
        
        # Guardar imágenes de capas
        for nombre_capa, datos in self.resultados.items():
            if datos['imagen']:
                ruta = os.path.join(directorio, f"{nombre_capa}.png")
                datos['imagen'].save(ruta)
                print(f"✓ Guardada: {ruta}")
                
                # Guardar versión con máscara aplicada
                if self.mascara is not None:
                    img_masked = datos['imagen'].copy()
                    pixels = np.array(img_masked)
                    pixels[~self.mascara] = [255, 255, 255, 0]
                    img_masked = Image.fromarray(pixels)
                    ruta_masked = os.path.join(directorio, f"{nombre_capa}_masked.png")
                    img_masked.save(ruta_masked)
                    print(f"✓ Con máscara: {ruta_masked}")
    
    def exportar_json(self, archivo='informe_afecciones.json'):
        """Exporta resultados a JSON incluyendo datos catastrales"""
        datos_export = {
            'archivo_kml': self.kml_path,
            'fecha_analisis': datetime.now().isoformat(),
            'bbox': self.bbox,
            'superficie_ha': self._calcular_superficie_aproximada(),
            'coordenadas': [[lon, lat] for lon, lat in self.coordenadas],
            'catastro': self.datos_catastro if self.datos_catastro else None,
            'afecciones': {}
        }
        
        for nombre, datos in self.resultados.items():
            if 'error' not in datos['analisis']:
                analisis = datos['analisis'].copy()
                analisis.pop('top_colores', None)  # Simplificar
                datos_export['afecciones'][nombre] = analisis
        
        with open(archivo, 'w', encoding='utf-8') as f:
            json.dump(datos_export, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Datos exportados a: {archivo}")
    
    def generar_pdf(self, archivo='informe_afecciones.pdf'):
        """Genera un informe completo en PDF con gráficos"""
        print(f"\n📄 Generando informe PDF...")
        
        # Configurar matplotlib para español
        plt.rcParams['font.family'] = 'DejaVu Sans'
        
        with PdfPages(archivo) as pdf:
            # PÁGINA 1: Portada
            self._generar_portada(pdf)
            
            # PÁGINA 2: Resumen ejecutivo con gráficos
            self._generar_resumen_grafico(pdf)
            
            # PÁGINAS 3+: Detalles por capa
            for nombre_capa, datos in self.resultados.items():
                if 'error' not in datos['analisis']:
                    self._generar_pagina_capa(pdf, nombre_capa, datos)
            
            # ÚLTIMA PÁGINA: Mapa de calor
            self._generar_mapa_comparativo(pdf)
        
        print(f"✅ PDF generado: {archivo}")
    
    def _generar_portada(self, pdf):
        """Genera la portada del informe"""
        fig = plt.figure(figsize=(8.27, 11.69))  # A4
        fig.patch.set_facecolor('white')
        ax = fig.add_subplot(111)
        ax.axis('off')
        
        # Título principal
        ax.text(0.5, 0.75, 'INFORME DE AFECCIONES\nAMBIENTALES',
                ha='center', va='center', fontsize=28, fontweight='bold',
                color='#2C3E50')
        
        # Subtítulo
        ax.text(0.5, 0.65, 'Análisis Detallado por Píxel',
                ha='center', va='center', fontsize=16, color='#7F8C8D')
        
        # Información del proyecto
        info_y = 0.55
        
        # Información catastral si está disponible
        if self.datos_catastro:
            ax.text(0.5, info_y, 'DATOS CATASTRALES', ha='center',
                    fontsize=13, fontweight='bold', color='#E74C3C')
            info_y -= 0.04
            
            ax.text(0.15, info_y, '🏛️ Ref. Catastral:', fontsize=10, fontweight='bold')
            ax.text(0.40, info_y, self.datos_catastro['referencia_catastral'], fontsize=10)
            info_y -= 0.03
            
            if self.datos_catastro['direccion']:
                ax.text(0.15, info_y, '📍 Dirección:', fontsize=10, fontweight='bold')
                direccion = self.datos_catastro['direccion'][:40]
                ax.text(0.40, info_y, direccion, fontsize=9)
                info_y -= 0.03
            
            if self.datos_catastro['municipio']:
                ax.text(0.15, info_y, '🏘️ Municipio:', fontsize=10, fontweight='bold')
                municipio = f"{self.datos_catastro['municipio']} ({self.datos_catastro['provincia']})"
                ax.text(0.40, info_y, municipio, fontsize=9)
                info_y -= 0.03
            
            if self.datos_catastro['uso_principal']:
                ax.text(0.15, info_y, '🏗️ Uso:', fontsize=10, fontweight='bold')
                ax.text(0.40, info_y, self.datos_catastro['uso_principal'], fontsize=9)
                info_y -= 0.03
            
            if self.datos_catastro['superficie_catastral']:
                sup_ha = float(self.datos_catastro['superficie_catastral']) / 10000
                ax.text(0.15, info_y, '📐 Sup. Catastro:', fontsize=10, fontweight='bold')
                ax.text(0.40, info_y, f"{sup_ha:.4f} ha ({self.datos_catastro['superficie_catastral']} m²)", fontsize=9)
                info_y -= 0.05
        
        # Separador
        ax.text(0.5, info_y, '─' * 40, ha='center', fontsize=10, color='#BDC3C7')
        info_y -= 0.03
        
        ax.text(0.5, info_y, 'DATOS DEL ANÁLISIS', ha='center',
                fontsize=13, fontweight='bold', color='#3498DB')
        info_y -= 0.04
        
        ax.text(0.15, info_y, '📄 Archivo KML:', fontsize=10, fontweight='bold')
        ax.text(0.40, info_y, os.path.basename(self.kml_path), fontsize=9)
        info_y -= 0.03
        
        ax.text(0.15, info_y, '📐 Superficie KML:', fontsize=10, fontweight='bold')
        superficie = self._calcular_superficie_aproximada()
        ax.text(0.40, info_y, f'{superficie} ha', fontsize=9)
        info_y -= 0.03
        
        ax.text(0.15, info_y, '📍 Coordenadas:', fontsize=10, fontweight='bold')
        ax.text(0.40, info_y, f'{len(self.coordenadas)} vértices', fontsize=9)
        info_y -= 0.03
        
        ax.text(0.15, info_y, '📅 Fecha análisis:', fontsize=10, fontweight='bold')
        ax.text(0.40, info_y, datetime.now().strftime('%d/%m/%Y %H:%M'), fontsize=9)
        info_y -= 0.03
        
        ax.text(0.15, info_y, '🗺️ BBox:', fontsize=10, fontweight='bold')
        bbox_text = f"({self.bbox['minx']:.4f}, {self.bbox['miny']:.4f})\n→ ({self.bbox['maxx']:.4f}, {self.bbox['maxy']:.4f})"
        ax.text(0.40, info_y-0.015, bbox_text, fontsize=8, family='monospace')
        info_y -= 0.08
        
        # Capas analizadas
        ax.text(0.5, info_y, 'CAPAS AMBIENTALES ANALIZADAS', ha='center',
                fontsize=12, fontweight='bold', color='#27AE60')
        info_y -= 0.04
        
        for i, nombre in enumerate(self.capas.keys(), 1):
            titulo = nombre.replace('_', ' ').title()
            ax.text(0.25, info_y, f'{i}. {titulo}', fontsize=9)
            info_y -= 0.03
        
        # Footer
        ax.text(0.5, 0.05, 'Generado por Analizador de Afecciones Ambientales v2.1\ncon integración Catastro',
                ha='center', fontsize=8, color='#95A5A6', style='italic')
        
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _generar_resumen_grafico(self, pdf):
        """Genera página con resumen y gráficos"""
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle('RESUMEN EJECUTIVO', fontsize=18, fontweight='bold', y=0.98)
        
        # Preparar datos
        nombres = []
        porcentajes = []
        colores_barras = []
        
        for nombre, datos in self.resultados.items():
            if 'error' not in datos['analisis']:
                nombres.append(nombre.replace('_', ' ').title())
                porcentajes.append(datos['analisis']['porcentaje_afectacion'])
                
                # Color según nivel
                porc = datos['analisis']['porcentaje_afectacion']
                if porc == 0:
                    colores_barras.append('#27AE60')
                elif porc < 15:
                    colores_barras.append('#F39C12')
                elif porc < 35:
                    colores_barras.append('#E67E22')
                else:
                    colores_barras.append('#E74C3C')
        
        # Gráfico de barras horizontal
        ax1 = plt.subplot(3, 1, 1)
        y_pos = np.arange(len(nombres))
        bars = ax1.barh(y_pos, porcentajes, color=colores_barras, alpha=0.8)
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(nombres)
        ax1.set_xlabel('Porcentaje de Afectación (%)', fontsize=10)
        ax1.set_title('Afectaciones por Capa', fontsize=12, fontweight='bold', pad=10)
        ax1.set_xlim(0, max(porcentajes) * 1.1 if porcentajes else 100)
        ax1.grid(axis='x', alpha=0.3)
        
        # Añadir valores en las barras
        for i, (bar, val) in enumerate(zip(bars, porcentajes)):
            ax1.text(val + 1, i, f'{val}%', va='center', fontsize=9, fontweight='bold')
        
        # Gráfico de pastel
        ax2 = plt.subplot(3, 2, 3)
        if porcentajes:
            wedges, texts, autotexts = ax2.pie(porcentajes, labels=nombres, autopct='%1.1f%%',
                                                colors=colores_barras, startangle=90)
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(8)
            ax2.set_title('Distribución de Afectaciones', fontsize=11, fontweight='bold')
        
        # Tabla de resumen
        ax3 = plt.subplot(3, 2, 4)
        ax3.axis('off')
        
        tabla_datos = [['Capa', 'Afectación', 'Nivel']]
        for nombre, datos in self.resultados.items():
            if 'error' not in datos['analisis']:
                porc = datos['analisis']['porcentaje_afectacion']
                nivel, _ = self.clasificar_afectacion(porc)
                nombre_corto = nombre.replace('_', ' ').title()[:20]
                tabla_datos.append([nombre_corto, f'{porc}%', nivel])
        
        tabla = ax3.table(cellText=tabla_datos, cellLoc='left',
                         colWidths=[0.5, 0.25, 0.25],
                         loc='center', bbox=[0, 0, 1, 1])
        tabla.auto_set_font_size(False)
        tabla.set_fontsize(9)
        tabla.scale(1, 2)
        
        # Estilo de la tabla
        for i in range(len(tabla_datos)):
            for j in range(3):
                cell = tabla[(i, j)]
                if i == 0:
                    cell.set_facecolor('#34495E')
                    cell.set_text_props(weight='bold', color='white')
                else:
                    cell.set_facecolor('#ECF0F1' if i % 2 == 0 else 'white')
        
        # Estadísticas generales
        ax4 = plt.subplot(3, 1, 3)
        ax4.axis('off')
        
        stats_text = "ESTADÍSTICAS GENERALES\n\n"
        superficie_total = self._calcular_superficie_aproximada()
        stats_text += f"• Superficie total analizada: {superficie_total} ha\n"
        
        if porcentajes:
            stats_text += f"• Afectación promedio: {np.mean(porcentajes):.1f}%\n"
            stats_text += f"• Afectación máxima: {max(porcentajes):.1f}%\n"
            stats_text += f"• Afectación mínima: {min(porcentajes):.1f}%\n"
            
            # Calcular superficie afectada total (evitando doble conteo)
            max_afectacion = max(porcentajes)
            superficie_afectada = (superficie_total * max_afectacion / 100)
            stats_text += f"• Superficie máxima afectada: ~{superficie_afectada:.2f} ha\n"
        
        stats_text += f"\n• Total de capas analizadas: {len(self.resultados)}\n"
        stats_text += f"• Píxeles en polígono: {list(self.resultados.values())[0]['analisis']['total_pixels_poligono']:,}\n"
        
        ax4.text(0.1, 0.5, stats_text, fontsize=10, verticalalignment='center',
                family='monospace', bbox=dict(boxstyle='round', facecolor='#F8F9FA', alpha=0.8))
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _generar_pagina_capa(self, pdf, nombre_capa, datos):
        """Genera una página detallada para cada capa"""
        analisis = datos['analisis']
        imagen = datos['imagen']
        
        fig = plt.figure(figsize=(8.27, 11.69))
        titulo_capa = nombre_capa.replace('_', ' ').upper()
        fig.suptitle(f'ANÁLISIS DETALLADO: {titulo_capa}', 
                    fontsize=16, fontweight='bold', y=0.98)
        
        # Imagen de la capa
        ax1 = plt.subplot(3, 2, (1, 2))
        if imagen:
            ax1.imshow(np.array(imagen))
            ax1.set_title('Capa WMS Descargada', fontsize=11, fontweight='bold')
            ax1.axis('off')
        
        # Información principal
        ax2 = plt.subplot(3, 2, 3)
        ax2.axis('off')
        
        nivel, emoji = self.clasificar_afectacion(analisis['porcentaje_afectacion'])
        
        info_text = f"{emoji} NIVEL DE AFECTACIÓN: {nivel}\n\n"
        info_text += f"Afectación: {analisis['porcentaje_afectacion']}%\n"
        info_text += f"Sobre área útil: {analisis['porcentaje_afectacion']}%\n"
        info_text += f"Sobre total: {analisis['porcentaje_sobre_total']}%\n\n"
        
        if analisis['superficie_afectada_ha']:
            info_text += f"Superficie afectada:\n  ~{analisis['superficie_afectada_ha']} ha\n\n"
        
        info_text += f"Píxeles afectados:\n  {analisis['pixels_afectados']:,}\n"
        info_text += f"Área útil analizada:\n  {analisis['area_util']:,}\n"
        info_text += f"Colores únicos:\n  {analisis['colores_detectados']}\n"
        
        ax2.text(0.1, 0.9, info_text, fontsize=9, verticalalignment='top',
                family='monospace', bbox=dict(boxstyle='round', facecolor='#F0F3F4', alpha=0.9))
        
        # Gráfico de píxeles
        ax3 = plt.subplot(3, 2, 4)
        categorias = ['Afectados', 'No afectados', 'Blancos']
        valores = [
            analisis['pixels_afectados'],
            analisis['area_util'] - analisis['pixels_afectados'],
            analisis['pixels_blancos']
        ]
        colores_pie = ['#E74C3C', '#95A5A6', '#ECF0F1']
        
        wedges, texts, autotexts = ax3.pie(valores, labels=categorias, autopct='%1.1f%%',
                                            colors=colores_pie, startangle=90)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        ax3.set_title('Distribución de Píxeles', fontsize=10, fontweight='bold')
        
        # Parámetros de detección
        ax4 = plt.subplot(3, 1, 3)
        ax4.axis('off')
        
        params_text = "PARÁMETROS DE DETECCIÓN\n\n"
        params_text += f"Tolerancia RGB: ±{analisis['tolerancia_usada']}\n\n"
        params_text += "Colores buscados:\n"
        for i, color in enumerate(analisis['colores_buscados'], 1):
            params_text += f"  {i}. RGB{color}\n"
        
        params_text += f"\nTop 5 colores detectados:\n"
        for i, (color, count) in enumerate(analisis['top_colores'][:5], 1):
            porc = (count / analisis['area_util']) * 100 if analisis['area_util'] > 0 else 0
            params_text += f"  {i}. RGB{color}: {count:,} ({porc:.1f}%)\n"
        
        ax4.text(0.1, 0.9, params_text, fontsize=8, verticalalignment='top',
                family='monospace', bbox=dict(boxstyle='round', facecolor='#FDFEFE', alpha=0.9))
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _generar_mapa_comparativo(self, pdf):
        """Genera mapa de calor comparativo de todas las capas"""
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle('COMPARATIVA VISUAL DE CAPAS', fontsize=16, fontweight='bold', y=0.98)
        
        num_capas = len([d for d in self.resultados.values() if d['imagen']])
        
        if num_capas == 0:
            plt.close()
            return
        
        cols = 2
        rows = (num_capas + 1) // 2
        
        for i, (nombre, datos) in enumerate(self.resultados.items(), 1):
            if datos['imagen']:
                ax = plt.subplot(rows, cols, i)
                ax.imshow(np.array(datos['imagen']))
                
                titulo = nombre.replace('_', ' ').title()
                porc = datos['analisis']['porcentaje_afectacion']
                nivel, emoji = self.clasificar_afectacion(porc)
                
                ax.set_title(f'{emoji} {titulo}\n{porc}% - {nivel}', 
                           fontsize=9, fontweight='bold')
                ax.axis('off')
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()


# Ejemplo de uso
if __name__ == "__main__":
    print("="*70)
    print(" "*15 + "ANALIZADOR DE AFECCIONES AMBIENTALES")
    print(" "*15 + "Versión 2.1 - Con Integración Catastro")
    print("="*70)
    
    # Ruta al archivo KML
    kml_file = "parcela.kml"
    
    # Opción 1: Con referencia catastral conocida
    referencia_catastral = "1234567AB1234B0001AB"  # Ejemplo
    
    # Opción 2: Sin referencia (se buscará automáticamente)
    referencia_catastral = None
    
    try:
        # Crear analizador
        analizador = AnalizadorAfeccionesAmbientales(kml_file, referencia_catastral)
        
        # Parsear KML primero
        analizador.parsear_kml()
        
        # Validar con Catastro
        analizador.validar_con_catastro()
        
        # Analizar todas las capas (mayor resolución)
        analizador.analizar_todas_capas(width=1500, height=1500)
        
        # Generar informe completo
        analizador.generar_informe()
        
        # Guardar imágenes
        analizador.guardar_imagenes()
        
        # Exportar a JSON
        analizador.exportar_json()
        
        # Generar PDF completo
        analizador.generar_pdf()
        
        print("\n✅ Análisis completado con éxito")
        print("📦 Archivos generados:")
        print("   • informe_afecciones.pdf")
        print("   • informe_afecciones.json")
        print("   • output_afecciones/*.png")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
