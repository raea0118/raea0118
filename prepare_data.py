from pathlib import Path
import pandas as pd,geopandas as gpd,requests
from dbfread import DBF
from shapely.geometry import shape

SRC=Path("/Users/gimgayeon/Desktop/결초보은/브이월드공모전");OUT=Path("data");CRS="EPSG:5186"
r=requests.get("https://nominatim.openstreetmap.org/search",params={"q":"강남구, 서울특별시, 대한민국","format":"jsonv2","polygon_geojson":1,"limit":1},headers={"User-Agent":"gangnam-pothole-mvp/1.0"},timeout=20);r.raise_for_status()
b=gpd.GeoDataFrame(geometry=[shape(r.json()[0]["geojson"])],crs=4326);bbox=tuple(b.to_crs(CRS).total_bounds);OUT.mkdir(exist_ok=True)
def clip(name):
    g=gpd.read_file(SRC/f"{name}.shp",bbox=bbox)
    if g.crs is None:g=g.set_crs(CRS)
    return gpd.clip(g.to_crs(4326),b)
links=clip("MOCT_LINK");nodes=clip("MOCT_NODE");gpkg=OUT/"gangnam_network.gpkg"
links.to_file(gpkg,layer="links",driver="GPKG");nodes.to_file(gpkg,layer="nodes",driver="GPKG")
ids=set(links.LINK_ID.astype(str));nids=set(nodes.NODE_ID.astype(str))
multi=pd.DataFrame(iter(DBF(SRC/"MULTILINK.dbf",encoding="cp949",char_decode_errors="ignore")));multi[multi.LINK_ID.astype(str).isin(ids)].to_csv(OUT/"gangnam_multilink.csv",index=False)
turn=pd.DataFrame(iter(DBF(SRC/"TURNINFO.dbf",encoding="cp949",char_decode_errors="ignore")));turn[turn.NODE_ID.astype(str).isin(nids)].to_csv(OUT/"gangnam_turninfo.csv",index=False)
print(f"완료, 링크 {len(links):,}개, 노드 {len(nodes):,}개, {gpkg}")
