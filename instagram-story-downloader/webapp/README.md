# 📱 Instagram 스토리 다운로더

Instagram 닉네임만 입력하면 현재 스토리를 확인하고 다운로드할 수 있는 웹 애플리케이션입니다.

## ✨ 주요 기능

- ✅ Instagram 닉네임 검색으로 스토리 조회
- ✅ 이미지/동영상 구분하여 표시
- ✅ 개별 스토리 다운로드 기능
- ✅ 모바일 최적화 반응형 디자인
- ✅ 무료 오픈소스 라이브러리 사용 (instaloader)

## 🛠️ 기술 스택

**백엔드:**
- Python 3.11
- Flask (웹 프레임워크)
- instaloader (Instagram 스토리 수집)
- Flask-CORS (CORS 처리)

**프론트엔드:**
- HTML5
- TailwindCSS (스타일링)
- Vanilla JavaScript
- Font Awesome (아이콘)

## 📁 프로젝트 구조

```
webapp/
├── app.py                 # Flask 백엔드 메인 파일
├── static/
│   └── index.html         # 프론트엔드 UI
├── requirements.txt       # Python 의존성
├── Procfile              # 배포 설정 (Render/Heroku)
├── runtime.txt           # Python 버전 지정
├── .env.example          # 환경 변수 예시
└── README.md             # 이 파일
```

## 🚀 Render.com 무료 배포 가이드

### 1️⃣ 사전 준비

1. **GitHub 계정 생성** (없는 경우)
   - https://github.com 접속
   - Sign up 클릭

2. **Render 계정 생성**
   - https://render.com 접속
   - GitHub 계정으로 로그인

3. **Instagram 더미 계정 준비**
   - 테스트용 Instagram 계정 생성
   - 공개 계정으로 설정
   - 닉네임과 비밀번호 메모

### 2️⃣ 코드를 GitHub에 업로드

#### 방법 A: GitHub 웹 인터페이스 사용 (초보자 권장)

1. **GitHub에서 새 저장소 생성**
   ```
   - GitHub 로그인 → 우측 상단 "+" → "New repository"
   - Repository name: instagram-story-downloader
   - Public 선택
   - "Create repository" 클릭
   ```

2. **파일 업로드**
   ```
   - "uploading an existing file" 클릭
   - 모든 프로젝트 파일 드래그앤드롭
   - Commit changes 클릭
   ```

#### 방법 B: Git 명령어 사용 (개발자용)

```bash
# 프로젝트 폴더에서 실행
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/instagram-story-downloader.git
git push -u origin main
```

### 3️⃣ Render.com에서 배포

1. **Render 대시보드 접속**
   - https://dashboard.render.com 접속

2. **새 Web Service 생성**
   ```
   - "New +" 버튼 클릭
   - "Web Service" 선택
   - GitHub 저장소 연결
   - "instagram-story-downloader" 선택
   ```

3. **배포 설정**
   ```
   Name: instagram-story-downloader
   Region: Singapore (가장 가까운 지역 선택)
   Branch: main
   Runtime: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app
   Instance Type: Free
   ```

4. **환경 변수 설정 (매우 중요!)**
   ```
   - "Advanced" 섹션으로 스크롤
   - "Add Environment Variable" 클릭
   
   Key: INSTAGRAM_USERNAME
   Value: your_instagram_account
   
   Key: INSTAGRAM_PASSWORD
   Value: your_instagram_password
   
   Key: PYTHON_VERSION
   Value: 3.11.0
   ```

5. **배포 시작**
   ```
   - "Create Web Service" 클릭
   - 약 5-10분 대기 (빌드 및 배포)
   - 상태가 "Live"로 변경되면 완료
   ```

### 4️⃣ 배포 확인

1. **URL 확인**
   ```
   - Render 대시보드에서 URL 복사
   - 예: https://instagram-story-downloader-xxxx.onrender.com
   ```

2. **테스트**
   ```
   - 브라우저에서 URL 접속
   - Instagram 닉네임 입력 (예: instagram)
   - 스토리 로딩 확인
   ```

## 🔧 Railway.app 배포 (대안)

### 장점
- 더 빠른 배포 속도
- 더 많은 무료 시간 제공 (월 500시간)

### 배포 단계

1. **Railway 가입**
   - https://railway.app 접속
   - GitHub 계정으로 로그인

2. **새 프로젝트 생성**
   ```
   - "New Project" 클릭
   - "Deploy from GitHub repo" 선택
   - 저장소 선택
   ```

3. **환경 변수 설정**
   ```
   - "Variables" 탭 클릭
   - "Add Variable" 클릭
   
   INSTAGRAM_USERNAME=your_account
   INSTAGRAM_PASSWORD=your_password
   PORT=5000
   ```

4. **배포 완료**
   ```
   - 자동으로 빌드 및 배포
   - "Settings" → "Generate Domain" 클릭
   - 생성된 URL로 접속
   ```

## 🐛 문제 해결

### 1. "Instagram 로그인 실패" 오류

**원인:** 환경 변수가 올바르게 설정되지 않았습니다.

**해결방법:**
```
1. Render 대시보드 → Environment 탭
2. INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD 확인
3. 값 수정 후 "Save Changes"
4. Manual Deploy 클릭하여 재배포
```

### 2. "사용자를 찾을 수 없습니다" 오류

**원인:** 입력한 닉네임이 존재하지 않거나 비공개 계정입니다.

**해결방법:**
```
- 공개 계정의 정확한 닉네임 입력
- Instagram 앱에서 닉네임 재확인
```

### 3. "스토리가 없습니다" 메시지

**원인:** 해당 사용자가 현재 스토리를 올리지 않았습니다.

**해결방법:**
```
- 스토리가 있는 다른 계정 검색
- Instagram 앱에서 스토리 존재 확인
```

### 4. 배포 후 503 Service Unavailable

**원인:** 서버가 아직 시작 중이거나 크래시되었습니다.

**해결방법:**
```
1. Render 대시보드 → Logs 확인
2. 에러 메시지 확인
3. 환경 변수 재확인
4. Manual Deploy로 재배포
```

### 5. Instagram 계정 차단 문제

**원인:** 동일 IP에서 과도한 요청

**해결방법:**
```
- 더미 계정 여러 개 준비
- 환경 변수에서 계정 교체
- VPN을 사용한 서버 지역 변경
```

## ⚙️ 로컬 개발 환경 설정

로컬에서 테스트하려면:

```bash
# 1. Python 가상환경 생성
python -m venv venv

# 2. 가상환경 활성화
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경 변수 설정
cp .env.example .env
# .env 파일 수정하여 Instagram 계정 정보 입력

# 5. 서버 실행
python app.py

# 6. 브라우저에서 접속
# http://localhost:5000
```

## 📝 주의사항

1. **Instagram 계정 보안**
   - 실제 개인 계정 사용 금지
   - 테스트 전용 더미 계정 사용 권장

2. **Instagram 이용 약관**
   - 과도한 요청 금지
   - 개인 용도로만 사용
   - 스크래핑 정책 준수

3. **저작권**
   - 다운로드한 콘텐츠는 개인 용도로만 사용
   - 무단 재배포 금지

4. **무료 서버 제약**
   - Render 무료 플랜: 15분 비활성화 시 슬립 모드
   - 첫 요청 시 느린 응답 (콜드 스타트)
   - 월 750시간 제한

## 🔄 업데이트

코드 수정 후 재배포:

```bash
# GitHub에 푸시
git add .
git commit -m "Update features"
git push origin main

# Render는 자동으로 재배포됨
# Railway도 자동으로 재배포됨
```

## 🎯 향후 개선 사항

- [ ] 여러 사용자 스토리 한 번에 조회
- [ ] 스토리 자동 저장 기능
- [ ] 다운로드 히스토리 관리
- [ ] 비공개 계정 지원 (로그인 추가)
- [ ] 스토리 만료 시간 표시
- [ ] 일괄 다운로드 기능

## 📄 라이선스

MIT License - 자유롭게 사용, 수정, 배포 가능

## 🤝 기여

버그 리포트, 기능 제안 환영합니다!

## 📧 문의

프로젝트 관련 문의: GitHub Issues

---

**만든 날짜:** 2024년 1월  
**버전:** 1.0.0  
**상태:** ✅ 프로덕션 준비 완료
