from pathlib import Path

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

shp_path = "/Users/gimgayeon/Desktop/결초보은/예비/LSMD_ADM_SECT_UMD_27_202607.shp"

gdf = gpd.read_file(shp_path)

print(gdf.head())
print(gdf.columns)
print(gdf.crs)

gdf.plot(
    figsize=(10, 8),
    color="skyblue",
    edgecolor="black"
)

plt.title("대구 침수 지도")
plt.axis("equal")
plt.show()

download_folder = Path.home() / "Downloads"

file_paths = {
    "격자_고도": download_folder / "래아 구역~.csv",
    "하천": download_folder / "김래아2.csv",
    "행정동": download_folder / "래아 지방~.csv",
}


def read_korean_csv(file_path):
    """UTF-8 또는 CP949 방식의 CSV를 자동으로 불러옵니다."""

    for encoding in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            df = pd.read_csv(file_path, encoding=encoding)

            print(
                f"{file_path.name} 불러오기 완료 "
                f"({len(df):,}행, {len(df.columns)}열, {encoding})"
            )

            return df

        except UnicodeDecodeError:
            continue

    raise ValueError(f"파일 인코딩을 확인할 수 없습니다: {file_path}")


# 각각의 데이터 불러오기
elevation_df = read_korean_csv(file_paths["격자_고도"])
river_df = read_korean_csv(file_paths["하천"])
district_df = read_korean_csv(file_paths["행정동"])


print("\n[격자·고도 데이터]")
print(elevation_df.head())
print(elevation_df.columns.tolist())

print("\n[하천 데이터]")
print(river_df.head())
print(river_df.columns.tolist())

print("\n[행정동 데이터]")
print(district_df.head())
print(district_df.columns.tolist())

# 격자 중심 좌표 계산
elevation_df["x"] = (
    elevation_df["left"] + elevation_df["right"]
) / 2

elevation_df["y"] = (
    elevation_df["top"] + elevation_df["bottom"]
) / 2


plt.figure(figsize=(12, 10))

scatter = plt.scatter(
    elevation_df["x"],
    elevation_df["y"],
    c=elevation_df["_mean"],
    cmap="terrain",
    s=2
)

plt.colorbar(scatter, label="평균 고도")
plt.title("격자별 평균 고도")
plt.xlabel("X 좌표")
plt.ylabel("Y 좌표")
plt.axis("equal")
plt.tight_layout()
plt.show()

result_df = elevation_df[
    [
        "id",
        "left",
        "top",
        "right",
        "bottom",
        "x",
        "y",
        "_mean",
        "_median",
        "_min",
        "_max",
    ]
].copy()

result_df = result_df.rename(
    columns={
        "_mean": "평균고도",
        "_median": "중앙고도",
        "_min": "최저고도",
        "_max": "최고고도",
    }
)

output_path = download_folder / "통합_고도데이터.csv"

result_df.to_csv(
    output_path,
    index=False,
    encoding="utf-8-sig",
)

print(f"저장 완료: {output_path}")

