# 강남구 포트홀 위험지도

## API 키

.streamlit/secrets.toml.example을 복사해 .streamlit/secrets.toml로 이름을 바꾼 뒤 ASOS 키와 V2X 키를 입력합니다. V2X_API_KEY에는 승인 URL 전체가 아니라 apikey= 뒤의 값만 넣습니다. secrets.toml은 GitHub에 올리면 안 됩니다. Streamlit Community Cloud에서는 앱 설정의 Secrets에 같은 내용을 입력합니다.

## 로컬 실행

    python -m pip install -r requirements.txt
    streamlit run app.py

로컬에서는 /Users/gimgayeon/Desktop/결초보은/브이월드공모전을 기본 데이터 폴더로 사용합니다. MOCT 링크와 노드의 shp, shx, dbf가 각각 같은 폴더에 있어야 합니다.

## GitHub 배포 준비

원본 SHP와 DBF는 GitHub의 파일당 100MB 제한을 넘으므로 그대로 올리지 않습니다.

    python prepare_data.py

전처리 후 생성된 data/gangnam_network.gpkg, data/gangnam_multilink.csv, data/gangnam_turninfo.csv와 앱 파일만 GitHub에 올립니다. GitHub 저장소를 Streamlit Community Cloud에 연결하고 실행 파일로 app.py를 선택합니다.

## 파일 설명

- app.py, 지도와 API 호출 및 위험도 화면
- prepare_data.py, 전국 도로망을 강남구로 축소
- requirements.txt, 설치 라이브러리
- .streamlit/secrets.toml, 실제 비밀키이며 GitHub 제외
- .streamlit/secrets.toml.example, 키 입력 예시
- .streamlit/config.toml, 화면 설정
- DSRC_LINK_MAP.csv, DSRC ID와 표준 링크 ID가 다를 때 필요한 선택 파일
