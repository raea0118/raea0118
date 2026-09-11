from pathlib import Path
from datetime import date,timedelta
import os,xml.etree.ElementTree as ET
import numpy as np,pandas as pd,geopandas as gpd,pydeck as pdk,requests,streamlit as st
from dbfread import DBF
from shapely.geometry import box,shape

st.set_page_config(page_title="강남구 포트홀 위험지도",page_icon="🛣️",layout="wide")
LOCAL=Path("/Users/gimgayeon/Desktop/결초보은/브이월드공모전");DEFAULT=LOCAL if LOCAL.exists() else Path("data")
try:SEC=dict(st.secrets)
except Exception:SEC={}
ROOT=Path(os.getenv("POTHOLE_DATA_DIR",SEC.get("DATA_DIR",str(DEFAULT))));CRS="EPSG:5186";BBOX=(127.00,37.45,127.13,37.56)
V2X_URL=SEC.get("V2X_ENDPOINT","https://t-data.seoul.go.kr/apig/apiman-gateway/tapi/v2xPotholeInformation/1.0")
COLORS=[[46,125,50,210],[139,195,74,210],[255,193,7,220],[255,112,67,220],[198,40,40,230]]
LEVELS=["매우 낮음","낮음","보통","높음","매우 높음"]

@st.cache_data(show_spinner=False)
def boundary(root_text):
    local=Path(root_text)/"gangnam.geojson"
    if local.exists():return gpd.read_file(local).to_crs(4326)
    try:
        r=requests.get("https://nominatim.openstreetmap.org/search",params={"q":"강남구, 서울특별시, 대한민국","format":"jsonv2","polygon_geojson":1,"limit":1},headers={"User-Agent":"gangnam-pothole-mvp/1.0"},timeout=15);r.raise_for_status()
        return gpd.GeoDataFrame(geometry=[shape(r.json()[0]["geojson"])],crs=4326)
    except Exception:return gpd.GeoDataFrame(geometry=[box(*BBOX)],crs=4326)

@st.cache_data(show_spinner="강남구 도로망을 불러오는 중입니다")
def network(root_text):
    root=Path(root_text);b=boundary(root_text);out={};gpkg=root/"gangnam_network.gpkg"
    if gpkg.exists():
        out["links"]=gpd.read_file(gpkg,layer="links").to_crs(4326);out["nodes"]=gpd.read_file(gpkg,layer="nodes").to_crs(4326)
    for key,name in {"links":"MOCT_LINK.shp","nodes":"MOCT_NODE.shp"}.items():
        if key in out or not (root/name).exists():continue
        g=gpd.read_file(root/name,bbox=tuple(b.to_crs(CRS).total_bounds))
        if g.crs is None:g=g.set_crs(CRS)
        out[key]=gpd.clip(g.to_crs(4326),b)
    if "links" in out:
        ids=set(out["links"].LINK_ID.astype(str));nids=set(out.get("nodes",pd.DataFrame()).get("NODE_ID",pd.Series(dtype=str)).astype(str))
        for key,name,col,valid in [("multilink","MULTILINK.dbf","LINK_ID",ids),("turninfo","TURNINFO.dbf","NODE_ID",nids)]:
            p=root/name
            if p.exists():
                d=pd.DataFrame(iter(DBF(p,encoding="cp949",char_decode_errors="ignore")));out[key]=d[d[col].astype(str).isin(valid)]
        for key,name in [("multilink","gangnam_multilink.csv"),("turninfo","gangnam_turninfo.csv")]:
            if key not in out and (root/name).exists():out[key]=pd.read_csv(root/name,dtype=str)
    return out

@st.cache_data(show_spinner=False,ttl=21600)
def asos(key,start,end):
    if not key:return pd.DataFrame(columns=["date","rain","tmin","tmax"])
    q={"serviceKey":key,"pageNo":1,"numOfRows":100,"dataType":"JSON","dataCd":"ASOS","dateCd":"DAY","startDt":start.strftime("%Y%m%d"),"endDt":end.strftime("%Y%m%d"),"stnIds":"108"}
    r=requests.get("https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList",params=q,timeout=25);r.raise_for_status()
    d=pd.DataFrame(r.json()["response"]["body"]["items"]["item"]).rename(columns={"tm":"date","sumRn":"rain","minTa":"tmin","maxTa":"tmax"})
    d["date"]=pd.to_datetime(d.date);d[["rain","tmin","tmax"]]=d[["rain","tmin","tmax"]].apply(pd.to_numeric,errors="coerce");d["rain"]=d.rain.fillna(0)
    return d[["date","rain","tmin","tmax"]]

@st.cache_data(show_spinner=False,ttl=3600)
def forecast():
    q={"latitude":37.5172,"longitude":127.0473,"daily":"temperature_2m_min,temperature_2m_max,precipitation_sum","timezone":"Asia/Seoul","forecast_days":6}
    x=requests.get("https://api.open-meteo.com/v1/forecast",params=q,timeout=20).json()["daily"]
    return pd.DataFrame({"date":pd.to_datetime(x["time"]),"rain":x["precipitation_sum"],"tmin":x["temperature_2m_min"],"tmax":x["temperature_2m_max"]})

def features(hist,fc):
    d=pd.concat([hist,fc]).drop_duplicates("date",keep="last").sort_values("date").reset_index(drop=True)
    d["rain_lag3"]=d.rain.rolling(3,min_periods=1).sum();d["rain_lag7"]=d.rain.rolling(7,min_periods=1).sum();d["heavy_rain"]=(d.rain>12.7).astype(int)
    d["ft_day"]=((d.tmin<0)&(d.tmax>0)).astype(int);d["ft_count30"]=d.ft_day.rolling(30,min_periods=1).sum();run=0;runs=[];breaks=[]
    for mx in d.tmax:
        breaks.append(int(run>0 and mx>0));run=run+1 if mx<0 else 0;runs.append(run)
    d["frozen_run"]=runs;d["thaw_break"]=breaks
    d["score"]=(d.rain_lag3/40*30+d.rain_lag7/80*15+d.heavy_rain*15+d.ft_day*15+d.ft_count30/10*10+d.frozen_run.clip(0,5)+d.thaw_break*10).clip(0,100)
    d["level"]=np.minimum((d.score//20).astype(int),4)+1;return d

def records(x):
    found=[]
    def walk(v):
        if isinstance(v,list) and v and isinstance(v[0],dict):found.extend(v)
        elif isinstance(v,dict):
            for z in v.values():walk(z)
        elif isinstance(v,list):
            for z in v:walk(z)
    walk(x);return found

@st.cache_data(show_spinner=False,ttl=1800)
def v2x(endpoint,key):
    if not key:return pd.DataFrame()
    r=requests.get(endpoint,params={"apikey":key},timeout=30);r.raise_for_status()
    try:return pd.DataFrame(records(r.json()))
    except Exception:
        root=ET.fromstring(r.text);return pd.DataFrame([{c.tag:c.text for c in item} for item in root.findall(".//item")])

def match_potholes(d,links):
    if d is None or d.empty:return gpd.GeoDataFrame(columns=["geometry","LINK_ID"],geometry="geometry",crs=4326)
    names={str(c).lower():c for c in d};lat=next((names[x] for x in ["detclat","detc_lat","lat","latitude","위도"] if x in names),None);lon=next((names[x] for x in ["detclot","detc_lot","lon","lng","longitude","경도"] if x in names),None)
    if lat is None or lon is None:st.error("V2X 응답에서 검지 위도와 검지 경도를 찾지 못했습니다.");return gpd.GeoDataFrame(columns=["geometry","LINK_ID"],geometry="geometry",crs=4326)
    d=d.copy();d[lat]=pd.to_numeric(d[lat],errors="coerce");d[lon]=pd.to_numeric(d[lon],errors="coerce");d=d.dropna(subset=[lat,lon])
    p=gpd.GeoDataFrame(d,geometry=gpd.points_from_xy(d[lon],d[lat]),crs=4326)
    return gpd.sjoin_nearest(p.drop(columns=["LINK_ID"],errors="ignore").to_crs(5179),links[["LINK_ID","geometry"]].to_crs(5179),max_distance=80,distance_col="link_distance_m").to_crs(4326)

@st.cache_data(show_spinner=False)
def speeds(root_text):
    root=Path(root_text);ready=root/"gangnam_traffic.csv"
    if ready.exists():return pd.read_csv(ready,dtype={"LINK_ID":str})
    files=list(root.glob("DSRC*"))
    if not files:return pd.DataFrame(columns=["LINK_ID","speed"])
    parts=[]
    for c in pd.read_csv(files[0],encoding="cp949",chunksize=250000):
        idc=next((x for x in c if "ID" in x.upper()),c.columns[1]);spc=next((x for x in c if "속도" in x),c.columns[-2]);parts.append(c.groupby(idc)[spc].mean())
    s=pd.concat(parts).groupby(level=0).mean().rename("speed").reset_index().rename(columns={idc:"SOURCE_ID"});mp=root/"DSRC_LINK_MAP.csv"
    if not mp.exists():return pd.DataFrame(columns=["LINK_ID","speed"])
    return s.merge(pd.read_csv(mp,dtype=str),left_on="SOURCE_ID",right_on="dsrc_id")[["link_id","speed"]].rename(columns={"link_id":"LINK_ID"})

def paths(g):
    d=g.copy();d["path"]=d.geometry.map(lambda x:[[a,b] for a,b in x.coords] if x.geom_type=="LineString" else [[a,b] for z in x.geoms for a,b in z.coords]);return d.drop(columns="geometry")

st.title("강남구 포트홀 위험지도");st.caption("도로망, 통행속도, 기상 위험, V2X 포트홀 탐지를 표준 링크로 연결합니다")
with st.sidebar:
    st.subheader("데이터 설정");root=st.text_input("데이터 폴더",str(ROOT));kma=st.text_input("ASOS API 키",SEC.get("KMA_SERVICE_KEY",""),type="password");vkey=st.text_input("V2X API 키",SEC.get("V2X_API_KEY",""),type="password")
    upload=st.file_uploader("V2X CSV 대체 업로드",type="csv");show_nodes=st.checkbox("노드",True);show_multi=st.checkbox("멀티링크",True);show_turn=st.checkbox("회전정보",False)
try:net=network(root)
except Exception as e:st.error(f"도로망을 읽지 못했습니다. {e}");st.stop()
if "links" not in net:st.error("MOCT_LINK.shp, shx, dbf를 같은 데이터 폴더에 넣어주세요.");st.stop()
links=net["links"].copy();links["LINK_ID"]=links.LINK_ID.astype(str);links=links.merge(speeds(root),on="LINK_ID",how="left")
try:raw=pd.read_csv(upload,encoding_errors="ignore") if upload else v2x(V2X_URL,vkey)
except Exception as e:st.warning(f"V2X API 연결 실패, CSV 업로드를 이용할 수 있습니다. {e}");raw=pd.DataFrame()
pts=match_potholes(raw,links);links["past_count"]=links.LINK_ID.map(pts.LINK_ID.value_counts()).fillna(0);today=date.today()
try:hist=asos(kma,today-timedelta(days=37),today-timedelta(days=1));fc=forecast()
except Exception as e:st.warning(f"기상 API 연결 실패로 예시값을 사용합니다. {e}");hist=pd.DataFrame(columns=["date","rain","tmin","tmax"]);fc=pd.DataFrame({"date":pd.date_range(today,periods=5),"rain":0,"tmin":5,"tmax":15})
wf=features(hist,fc);days=[pd.Timestamp(today+timedelta(days=i)) for i in range(5)];names=["오늘","하루 뒤","이틀 뒤","사흘 뒤","나흘 뒤"]
chosen=st.segmented_control("예측 날짜",days,format_func=lambda x:f"{names[(x-pd.Timestamp(today)).days]}  {x:%m월 %d일}",default=days[0]);w=wf.loc[wf.date.eq(chosen)].iloc[0]
links["risk_score"]=(w.score+np.log1p(links.past_count)*12).clip(0,100);links["risk_level"]=np.minimum((links.risk_score//20).astype(int),4)+1;links["color"]=links.risk_level.map(lambda x:COLORS[x-1])
c1,c2,c3,c4=st.columns(4);c1.metric("강우 위험",LEVELS[int(w.level)-1]);c2.metric("3일 누적 강우",f"{w.rain_lag3:.1f} mm");c3.metric("30일 동결융해",f"{int(w.ft_count30)}일");c4.metric("V2X 포트홀",f"{len(pts):,}건")
layers=[pdk.Layer("PathLayer",paths(links),get_path="path",get_color="color",get_width=2,width_min_pixels=1,pickable=True)]
if show_nodes and "nodes" in net:
    n=net["nodes"].copy();n["lon"]=n.geometry.x;n["lat"]=n.geometry.y;layers.append(pdk.Layer("ScatterplotLayer",n.drop(columns="geometry"),get_position="[lon,lat]",get_radius=10,get_fill_color=[18,45,70,150]))
if show_multi and "multilink" in net:
    mids=set(net["multilink"].LINK_ID.astype(str));layers.append(pdk.Layer("PathLayer",paths(links[links.LINK_ID.isin(mids)]),get_path="path",get_color=[123,44,191,210],get_width=4,width_min_pixels=2))
if show_turn and "turninfo" in net and "nodes" in net:
    ids=set(net["turninfo"].NODE_ID.astype(str));n=net["nodes"][net["nodes"].NODE_ID.astype(str).isin(ids)].copy();n["lon"]=n.geometry.x;n["lat"]=n.geometry.y;layers.append(pdk.Layer("ScatterplotLayer",n.drop(columns="geometry"),get_position="[lon,lat]",get_radius=18,get_fill_color=[0,188,212,220]))
if len(pts):
    pts["lon"]=pts.geometry.x;pts["lat"]=pts.geometry.y;layers.append(pdk.Layer("ScatterplotLayer",pts.drop(columns="geometry"),get_position="[lon,lat]",get_radius=24,get_fill_color=[255,35,35,230],pickable=True))
st.pydeck_chart(pdk.Deck(map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",initial_view_state=pdk.ViewState(latitude=37.5172,longitude=127.0473,zoom=12),layers=layers,tooltip={"html":"<b>링크 {LINK_ID}</b><br/>위험점수 {risk_score}<br/>평균속도 {speed}<br/>과거 파손 {past_count}"}),height=650)
legend=" ".join(f"<span style='display:inline-block;width:12px;height:12px;background:rgb({c[0]},{c[1]},{c[2]});border-radius:3px'></span> {x}" for x,c in zip(LEVELS,COLORS));st.markdown(f"<div style='text-align:right'>{legend}</div>",unsafe_allow_html=True)
with st.expander("선택일 기상 변수"):
    st.dataframe(pd.DataFrame({"변수":["rain_lag3","rain_lag7","heavy_rain","ft_day","ft_count30","frozen_run","thaw_break"],"값":[w.rain_lag3,w.rain_lag7,int(w.heavy_rain),int(w.ft_day),int(w.ft_count30),int(w.frozen_run),int(w.thaw_break)]}),hide_index=True,use_container_width=True)
st.caption("위험도는 공모전 시연용 규칙 기반 지수입니다. ASOS는 과거 관측, 예보 API는 향후 5일, T Data V2X는 과거 포트홀 위치에 사용됩니다.")
