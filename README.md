# 아침 브리핑 (삼성증권 보유 ETF 자동 리포트)

평일 아침 9시쯤 갤럭시로 수익률 알림이 오고, 누르면 계좌별 수익률과 간밤 미국장 데이터를 볼 수 있는 앱입니다.
삼성증권 계좌에 직접 접속하지 않고, 직접 입력한 수량·평단 + 네이버 금융 시세로 계산합니다.
**유료 API를 쓰지 않아서 운영 비용이 0원**이에요.

## 동작 방식

1. 한국 시간 평일 08:45와 14:45, GitHub Actions가 자동으로 실행돼요.
2. 각각 09:01, 15:00에 보유 ETF 현재가를 가져와 계좌별 수익률(전일 종가 대비 등락 포함), 평단, 평가금액을 계산해요.
3. 같은 시각 아래 데이터를 무료로 모아요 (키 필요 없음).
   - 간밤 미국 지수: 나스닥100, 필라델피아 반도체(SOX), S&P500
   - 주요 종목: 엔비디아, 브로드컴, AMD, TSMC(ADR), 애플, 마이크로소프트
   - 원/달러 환율과 전일 대비 변화
   - 구글 뉴스(한국어)에서 "나스닥", "필라델피아 반도체", "엔비디아", "미국 증시", "뉴욕증시" 최근 24시간 기사 최대 15개
4. 결과를 앱 비밀번호로 암호화해서 저장하고(공개 저장소여도 내용은 안 보여요), 휴대폰으로 알림을 보내요.
   알림에는 수익률과 "간밤 나스닥100 / SOX 등락" 한 줄이 들어가요.
5. 알림을 누르면 앱이 열리고 "내 수익률"과 "아침 브리핑" 두 화면을 볼 수 있어요.

### Claude로 분석하기
브리핑 화면의 **Claude로 분석하기** 버튼을 누르면, 오늘 모은 지수·환율·뉴스 제목과 내 보유 ETF 수익률이 담긴
분석 요청문이 클립보드에 복사되고 claude.ai가 열려요. 입력창에 붙여넣기만 하면
간밤 미국장 요약, 환율 영향, 시초가 방향, ETF별 단기 전망, 이번 주 일정, 리스크/기대 요인을 정리해 줘요.
(claude.ai 구독 안에서 쓰는 거라 추가 비용이 없어요. 요청문에는 금액 없이 수익률과 비중만 들어가요.)

## 준비물

- GitHub 계정 (무료)
- 휴대폰에 ntfy 앱 (Play 스토어에서 "ntfy" 검색, 무료)
- PC에 git, GitHub CLI(gh): `winget install Git.Git GitHub.cli`

## 설정 순서

### 1. 저장소 만들기
```bash
gh auth login
gh repo create morning-brief --public --source . --push
```
(GitHub Pages 무료 사용 조건이 Public이에요. 데이터는 암호화돼 있어서 비밀번호 없이는 읽을 수 없어요.)

### 2. 종목코드 확인
네이버 증권에서 보유 ETF를 검색하면 6자리 종목코드가 나와요. 이름이 비슷한 상품(TR, H, 레버리지)이 많으니 꼭 확인하세요.
- KODEX 미국나스닥100: `379810`
- TIGER 미국필라델피아반도체나스닥: `381180`

### 3. ntfy 구독
ntfy 앱에서 "+" 를 누르고 남들이 추측할 수 없는 토픽 이름으로 구독하세요. 예: `mb-k82jq7x3vz`
(ntfy.sh 는 공개 서버라 토픽 이름이 곧 비밀번호 역할이에요.)

### 4. 시크릿 등록
터미널에서 아래 명령을 하나씩 실행하고, 나오는 입력창에 값을 붙여넣으세요(화면과 기록에 남지 않아요).

```bash
gh secret set APP_PASSWORD
gh secret set NTFY_TOPIC
gh secret set HOLDINGS_JSON
```

| 이름 | 값 |
|---|---|
| `APP_PASSWORD` | 앱을 열 때 쓸 비밀번호 (길게) |
| `NTFY_TOPIC` | 3번에서 정한 토픽 이름 |
| `HOLDINGS_JSON` | 보유 종목 (`holdings.example.json` 형식) |

`HOLDINGS_JSON` 은 `holdings.json` 을 채운 뒤 파일째로 넣는 게 편해요. Windows PowerShell 에서
`Get-Content … | gh secret set` 으로 넘기면 한글이 깨지니, 아래처럼 `cmd` 로 넣으세요.

```bash
cmd /c "gh secret set HOLDINGS_JSON < holdings.json"
```

변수(Variables):

```bash
gh variable set APP_URL --body "https://내아이디.github.io/morning-brief/"
```

| 이름 | 값 |
|---|---|
| `APP_URL` | 앱 주소 |
| `NOTIFY_AMOUNTS` | (선택) `false` 로 하면 알림에 금액 없이 수익률만 나와요 |

### 5. GitHub Pages 켜기
Settings > Pages > Source 를 "Deploy from a branch", 브랜치 `main`, 폴더 `/docs` 로 저장하세요.

### 6. 첫 실행 테스트
```bash
gh workflow run morning.yml
```
또는 Actions 탭 > "아침 브리핑" > "Run workflow". 수동 실행은 9시를 기다리지 않고 바로 실행돼요.
2~3분 뒤 휴대폰에 알림이 오면 성공이에요.

### 7. 앱 설치
휴대폰 크롬(또는 삼성 인터넷)으로 `APP_URL` 을 열고 비밀번호를 입력한 뒤,
메뉴에서 "홈 화면에 추가" 또는 "앱 설치"를 누르세요. 이후엔 앱처럼 열려요.

## 로컬에서 실행해 보기

```bash
pip install -r requirements.txt
```
`holdings.example.json` 을 `holdings.json` 으로 복사해서 채운 뒤(이 파일은 저장소에 올라가지 않아요):

```powershell
$env:APP_PASSWORD="테스트비번"; $env:NO_WAIT="1"; python scripts/brief.py
python -m http.server 8000 -d docs
```
브라우저에서 http://localhost:8000 을 열고 같은 비밀번호를 입력하세요.
로컬에서 만든 `docs/data.enc.json` 은 커밋하지 마세요(비밀번호가 다르면 Actions가 새로 시작해요).

## 알아둘 점

- **매매하면** `HOLDINGS_JSON` 시크릿의 수량과 평단을 고쳐주세요. 앱은 그 값을 기준으로 계산해요.
- **시간**: GitHub 예약 실행은 몰리는 시간대에 수 분~수십 분 늦게 시작될 수 있어서 15분 일찍(08:45, 14:45) 시작하도록 해뒀어요. 일찍 시작하면 09:01, 15:00까지 기다렸다가 시세를 가져와요. 알림은 저장·반영 대기 때문에 그로부터 1~2분 뒤에 와요.
- **수익률 기록**은 하루에 한 개만 남아요. 오후 실행이 그날 오전 값을 덮어써요.
- **9시 직후 시세**는 장 시작 직후라 변동이 커요. 앱의 "새로고침"은 그날 아침 데이터를 다시 불러오는 것이고 실시간 시세는 아니에요.
- **휴장일**에도 실행되며, 이 경우 전 거래일 종가 기준이라고 표시돼요.
- **데이터 출처**: 시세·환율은 네이버 금융의 비공식 주소(해외 지수·종목·환율은 실패 시 야후 파이낸스로 재시도), 뉴스는 구글 뉴스 RSS예요.
  항목마다 따로 처리해서 하나가 실패해도 나머지는 표시되고, 실패한 항목은 "가져오지 못했어요"로 나와요. 원인은 Actions 로그의 `[경고]` 줄에서 볼 수 있어요.
- **환율**은 하나은행 고시 기준이라 09시 직후 값이에요.
- **비밀번호를 바꾸면** 이전 수익률 기록은 새로 시작돼요.
- 브리핑과 Claude 분석은 참고 자료이고 투자 권유가 아니에요.

## 파일 구성

```
.github/workflows/morning.yml   매일 아침 자동 실행 설정
scripts/brief.py                시세·뉴스 수집, 수익률 계산, 암호화
scripts/notify.py               휴대폰 알림 전송
docs/                           앱 화면 (GitHub Pages로 배포)
holdings.example.json           보유 종목 입력 예시
```
