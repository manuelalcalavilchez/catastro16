import os
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import requests
from io import BytesIO
from owslib.wms import WebMapService
from datetime import datetime
import json

class AnalizadorUrbanistico:
    def __init__(self, geojson_path, output_dir):
        self.geojson_path = geojson_path
        self.output_dir = output_dir
        self.encuadre_factor = 4
        self.wfs_url = "https://mapas-gis-inter.carm.es/geoserver/SIT_USU_PLA_URB_CARM/wfs?"
        self.wms_url = "https://mapas-gis-inter.carm.es/geoserver/SIT_USU_PLA_URB_CARM/wms?"
        self.pnoa_wms = "https://www.ign.es/wms-inspire/pnoa-ma"
        self.typename = "SIT_USU_PLA_URB_CARM:clases_plu_ze_37mun"
        
        # Crear directorio de salida si no existe
        os.makedirs(output_dir, exist_ok=True)

    def cargar_parcela(self):
        """Carga la parcela desde el GeoJSON y reproyecta a Web Mercator"""
        gdf = gpd.read_file(self.geojson_path)
        return gdf.to_crs(epsg=3857)

    def descargar_capa_wfs(self):
        """Descarga la capa WFS de urbanismo"""
        params = {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typename": self.typename,
            "outputFormat": "json",
            "srsName": "EPSG:4326"
        }
        r = requests.get(self.wfs_url, params=params, timeout=60)
        if r.status_code == 200:
            gdf = gpd.read_file(BytesIO(r.content))
            gdf.columns = [c.lower() for c in gdf.columns]
            return gdf.to_crs(epsg=25830)  # Reproyectar para cálculo de área (métrico)
        else:
            raise Exception(f"Error {r.status_code} al descargar WFS\nURL: {r.url}")

    def calcular_porcentajes(self, gdf_parcela, gdf_planeamiento):
        """Calcula intersecciones y porcentajes de clasificación"""
        # Asegurar mismo CRS para intersección
        gdf_parcela_local = gdf_parcela.to_crs(epsg=25830)
        
        interseccion = gpd.overlay(gdf_planeamiento, gdf_parcela_local, how="intersection")

        if interseccion.empty:
            return {}, {}

        interseccion["area_m2"] = interseccion.geometry.area

        # Crear campo combinado para diferenciar subtipos
        # Asumiendo que existen columnas 'clasificacion' y 'ambito'
        if "clasificacion" in interseccion.columns:
            interseccion["tipo_suelo"] = interseccion["clasificacion"]
            mask_no_urb = interseccion["clasificacion"].str.contains("No Urbanizable", case=False, na=False)
            if "ambito" in interseccion.columns:
                 interseccion.loc[mask_no_urb, "tipo_suelo"] = (
                    interseccion["clasificacion"] + " - " + interseccion["ambito"].fillna("")
                )
        else:
            # Fallback si no hay columnas específicas, usar la primera disponible interesante o ID
            interseccion["tipo_suelo"] = "Desconocido"

        resumen = interseccion.groupby("tipo_suelo")["area_m2"].sum()
        total_area = resumen.sum()
        porcentajes = (resumen / total_area) * 100
        
        return resumen.to_dict(), porcentajes.to_dict()

    def descargar_ortofoto(self, extent):
        """Descarga ortofoto del PNOA"""
        wms = WebMapService(self.pnoa_wms, version="1.3.0")
        minx, maxx, miny, maxy = extent
        try:
            img = wms.getmap(
                layers=["OI.OrthoimageCoverage"],
                srs="EPSG:3857",
                bbox=(minx, miny, maxx, maxy),
                size=(1000, 1000),
                format="image/jpeg",
                transparent=True
            )
            filepath = os.path.join(self.output_dir, "ortofoto.jpg")
            with open(filepath, "wb") as f:
                f.write(img.read())
            return filepath
        except Exception as e:
            print(f"Error descargando ortofoto: {e}")
            return None

    def descargar_urbanismo(self, extent):
        """Descarga capa de urbanismo (WMS)"""
        wms = WebMapService(self.wms_url, version="1.3.0")
        minx, maxx, miny, maxy = extent
        try:
            img = wms.getmap(
                layers=[self.typename],
                srs="EPSG:3857",
                bbox=(minx, miny, maxx, maxy),
                size=(1000, 1000),
                format="image/png",
                transparent=True
            )
            filepath = os.path.join(self.output_dir, "urbanismo.png")
            with open(filepath, "wb") as f:
                f.write(img.read())
            return filepath
        except Exception as e:
            print(f"Error descargando urbanismo WMS: {e}")
            return None

    def descargar_leyenda(self):
        """Descarga leyenda gráfica del servicio WMS"""
        url = f"{self.wms_url}service=WMS&version=1.1.0&request=GetLegendGraphic&layer={self.typename}&format=image/png"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                filepath = os.path.join(self.output_dir, "leyenda.png")
                with open(filepath, "wb") as f:
                    f.write(r.content)
                return filepath
        except Exception as e:
            print(f"Error descargando leyenda: {e}")
        return None

    def generar_mapa(self, gdf_parcela, ortofoto_path, urbanismo_path, leyenda_path, extent):
        """Genera composición final del mapa"""
        if not ortofoto_path or not urbanismo_path:
            return None
        
        filepath = os.path.join(self.output_dir, "mapa_urbanistico.png")
        
        try:
            fig, ax = plt.subplots(figsize=(10,10))

            # Ortofoto
            if os.path.exists(ortofoto_path):
                ortofoto = plt.imread(ortofoto_path)
                ax.imshow(ortofoto, extent=extent, origin="upper")

            # Urbanismo
            if os.path.exists(urbanismo_path):
                urbanismo_img = plt.imread(urbanismo_path)
                ax.imshow(urbanismo_img, extent=extent, origin="upper", alpha=0.5)

            # Contorno parcela
            gdf_parcela.boundary.plot(ax=ax, color="red", linewidth=2)

            plt.title("Parcela sobre ortofoto + urbanismo")
            plt.axis("off")

            # Leyenda
            if leyenda_path and os.path.exists(leyenda_path):
                leyenda_img = plt.imread(leyenda_path)
                # Ajustar posición leyenda según necesidad
                ax_leyenda = fig.add_axes([0.75, 0.05, 0.2, 0.2])
                ax_leyenda.imshow(leyenda_img)
                ax_leyenda.axis("off")

            plt.savefig(filepath, dpi=200, bbox_inches='tight')
            plt.close()
            return filepath
        except Exception as e:
            print(f"Error generando mapa: {e}")
            return None

    def ejecutar_analisis(self):
        """Flujo principal de ejecución"""
        resultados = {}
        
        # 1. Cargar Parcela
        parcela = self.cargar_parcela()
        
        # 2. Calcular Encuadre
        minx, miny, maxx, maxy = parcela.total_bounds
        ancho = maxx - minx
        alto = maxy - miny
        minx -= (self.encuadre_factor-1) * ancho/2
        maxx += (self.encuadre_factor-1) * ancho/2
        miny -= (self.encuadre_factor-1) * alto/2
        maxy += (self.encuadre_factor-1) * alto/2
        extent = (minx, maxx, miny, maxy)
        
        # 3. Datos Urbanísticos (Intersect)
        planeamiento = self.descargar_capa_wfs()
        areas, porcentajes = self.calcular_porcentajes(parcela, planeamiento)
        
        resultados["areas_m2"] = areas
        resultados["porcentajes"] = porcentajes
        
        # 4. Descarga de Imágenes
        orto_path = self.descargar_ortofoto(extent)
        urb_path = self.descargar_urbanismo(extent)
        leyenda_path = self.descargar_leyenda()
        
        # 5. Generar Mapa
        mapa_path = self.generar_mapa(parcela, orto_path, urb_path, leyenda_path, extent)
        
        files = {
            "mapa": os.path.basename(mapa_path) if mapa_path else None,
            "ortofoto": os.path.basename(orto_path) if orto_path else None,
            "urbanismo": os.path.basename(urb_path) if urb_path else None,
            "leyenda": os.path.basename(leyenda_path) if leyenda_path else None
        }
        
        # Guardar JSON resumen
        json_path = os.path.join(self.output_dir, "resultados_urbanismo.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "resultados": resultados,
                "files": files,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
            
        return {
            "data": resultados,
            "files": files,
            "json_path": json_path,
            "output_dir": self.output_dir
        }
