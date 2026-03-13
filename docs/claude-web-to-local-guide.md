# Claude 웹 프로젝트 → 로컬 Claude Code 이전 가이드

## 사전 준비

### 1. Claude Code CLI 설치
```bash
npm install -g @anthropic-ai/claude-code
```

### 2. Claude 계정 로그인
```bash
claude login
```
- Claude 웹에서 사용하는 **같은 계정**으로 로그인 필수

### 3. GitHub 레포 설정 확인
- 프로젝트가 GitHub에 push 되어 있어야 함
- 로컬에 해당 레포가 clone 되어 있어야 함
- **clean git state** 필요 (커밋되지 않은 변경사항 없어야 함)

```bash
cd ~/atm-dev
git status  # "working tree clean" 확인
```

---

## Teleport 실행 방법

### 방법 A: 대화형 선택
```bash
claude --teleport
```
- 최근 Claude 웹 세션 목록이 표시됨
- 가져올 세션을 선택

### 방법 B: 세션 ID 직접 지정
```bash
claude --teleport <session-id>
```
- Claude 웹 URL에서 세션 ID 확인: `https://claude.ai/chat/<session-id>`

### 동작 원리
1. Claude 웹 세션의 컨텍스트(대화 이력, 파일 변경사항)를 로컬로 가져옴
2. 로컬에서 해당 세션을 이어서 작업 가능
3. 웹에서 생성/수정한 파일들이 로컬 워킹 디렉토리에 반영됨

---

## Teleport 후 확인 사항

### 1. 파일 구조 확인
```bash
ls -la ats/           # 백엔드 코드가 채워졌는지 확인
ls ats/api/           # API 모듈
ls ats/strategy/      # 전략 모듈
ls ats/infra/         # 인프라 모듈
```

### 2. 테스트 실행
```bash
python3 run_tests.py              # 단위 테스트 43건
cd web && npx tsc --noEmit        # TypeScript 체크
```

### 3. 서버 기동 확인
```bash
python3 main.py api               # FastAPI 서버
cd web && npm run dev              # 프론트엔드 dev 서버
```

---

## 주의사항

- `/teleport`은 **같은 Claude 계정**으로 로그인되어 있어야 동작
- **GitHub 레포**가 연결되어 있어야 함 (로컬과 웹 모두)
- 로컬에 **uncommitted changes**가 있으면 충돌 가능 → 먼저 commit 또는 stash
- 웹 세션에서 생성한 파일이 많은 경우 `git diff`로 변경사항 확인 권장

---

## 대안: Teleport가 안 될 경우

1. **수동 다운로드**: Claude 웹에서 아티팩트 개별 다운로드 (다운로드 버튼 클릭)
2. **브라우저 확장**: "Claude Artifact Downloader" (Chrome) → 일괄 ZIP 다운로드
3. **복사-붙여넣기**: 코드 블록을 직접 로컬 파일로 복사

---

## ats/ 서브모듈 문제 해결

현재 `ats/`가 git submodule인데 코드가 비어있는 상태. teleport 후에도 문제가 남아있다면:

### 옵션 1: 서브모듈 → 인라인 전환 (monorepo)
```bash
git rm ats                           # 서브모듈 참조 제거
mkdir -p ats/api ats/strategy ats/risk ats/order ats/position
# ... 코드 파일 배치
git add ats/
git commit -m "Convert ats submodule to inline directory"
```

### 옵션 2: 서브모듈 URL 설정
```bash
# ats 별도 레포 URL을 알고 있다면:
git submodule add <ats-repo-url> ats
git submodule update --init
```
