# KISA 공지 포맷터 확장

이 저장소는 [KISA-Bohonara-Alert](https://github.com/doraemyon/KISA-Bohonara-Alert)의 추가 익스펜션 기능을 제공하는 프로젝트입니다. 기존 프로젝트가 KISA 보안공지를 빠르게 감지해 Telegram으로 알리는 기본 기능을 담당하고, 이 프로젝트는 운영 담당자가 공지를 업무에 활용하기 쉬운 국문·영문 형식으로 확인하고 전달할 수 있도록 후처리 기능을 추가합니다.

이 익스펜션은 선택 사항입니다. `KISA-Bohonara-Alert`는 이 저장소를 연결하지 않아도 기존 공지 알리미로 독립적으로 동작합니다. 두 프로젝트를 연결하면 새 공지가 생겼을 때 이 저장소가 실행되어 기존 Telegram 메시지에 다음 버튼을 추가합니다.

```text
공지 열기
국문 공지 | 영문 공지
```

국문·영문 문서는 UTF-8 GitHub Pages로 제공되며 줄번호, `전체 내용 복사`와 텍스트 파일 저장 기능을 지원합니다. 저장된 공지는 사이트 첫 화면의 목록에서도 다시 열 수 있습니다.

## 동작 방식

1. 기존 알리미가 Telegram 공지를 먼저 즉시 전송합니다.
2. 확장이 설정된 경우에만 이 저장소의 Action을 호출합니다.
3. Action이 KISA 원문을 다시 읽고 도메인·게시판·공지 번호를 검증합니다.
4. 제목에 `업데이트`가 있고 본문에 CVE, 영향 버전, 해결 버전 또는 조치 방안이 있으면 업데이트 권고용 요약을 사용합니다. 그 외 공지는 일반 요약을 사용합니다.
5. Gemini API 무료 티어로 공지 전체 문맥을 영문으로 번역하고, URL·CVE·버전 정보가 보존됐는지 검증합니다.
6. Gemini를 사용할 수 없을 때만 무료 MyMemory Translation API로 자동 대체합니다.
7. 국문·영문 페이지를 이 저장소에 저장하고 GitHub Pages에 배포합니다.
8. 배포 성공 후 이미 전송된 Telegram 메시지의 버튼을 3개로 갱신합니다.

확장 처리나 번역이 실패해도 최초 Telegram 알림과 `공지 열기` 버튼은 그대로 남습니다.

## 공개 범위와 비용

- 이 저장소와 생성된 국문·영문 문서는 **Public**입니다. 공개하면 안 되는 내용을 템플릿이나 생성 문서에 추가하지 마세요.
- Public 저장소의 표준 GitHub-hosted runner와 GitHub Pages는 무료입니다.
- 이 Action은 매분 실행되지 않고 새로운 공지가 있을 때만 실행됩니다.
- 권장 번역기는 결제 계정 연결 없이 사용할 수 있는 [Gemini API 무료 티어](https://ai.google.dev/gemini-api/docs/pricing)입니다. 무료 티어의 요청 한도 안에서는 요금이 발생하지 않습니다.
- Gemini API 키가 없거나 일시적으로 실패하면 [MyMemory Translation API](https://mymemory.translated.net/doc/spec.php)로 대체합니다. MyMemory는 익명 기준 하루 5,000자이며, 연락용 이메일을 전달하면 하루 50,000자입니다.
- Gemini 무료 티어에 보낸 데이터는 Google 제품 개선에 사용될 수 있습니다. 이 프로젝트는 인터넷에 이미 공개된 KISA 공지만 번역 대상으로 사용합니다.
- 무료 티어의 실제 요청 한도는 모델과 프로젝트에 따라 달라질 수 있으며 Google AI Studio에서 확인할 수 있습니다. 한도에 도달하면 MyMemory 대체 번역을 시도합니다.
- 번역 결과가 국문과 같거나 한글 비율이 비정상적으로 높으면 성공으로 처리하지 않습니다. 세 번 재시도해도 실패하면 기본 Telegram 알림만 유지됩니다.

## 1. Public 저장소 준비

이 코드는 기존 알리미와 별도의 Public 저장소 `KISA-Bohonara-Support`에서 운영합니다.

저장소를 만든 뒤 다음 설정을 합니다.

1. 저장소 **Settings → Pages**로 이동합니다.
2. **Build and deployment → Source**를 `GitHub Actions`로 선택합니다.
3. 저장소 **Settings → Actions → General → Workflow permissions**에서 `Read and write permissions`를 선택합니다.

별도 Pages workflow를 직접 추가할 필요는 없습니다. 저장소에 포함된 workflow가 문서 생성과 Pages 배포를 처리합니다.

## 2. 무료 번역 설정

권장 방식은 Google AI Studio에서 Gemini API 무료 키를 발급하는 것입니다. Google Cloud Translation API와 달리 결제 계정을 연결하지 않아도 무료 티어를 사용할 수 있습니다.

1. [Google AI Studio API Keys](https://aistudio.google.com/app/apikey)를 엽니다.
2. **Create API key**를 눌러 키를 발급합니다.
3. 다음 단계에서 확장 저장소의 `GEMINI_API_KEY` Secret으로 등록합니다.

번역은 공지 전체를 문맥 단위로 처리합니다. 특정 공지의 문장이나 제품명을 코드에 고정해 두지 않으며, 번역 뒤에는 원문의 URL, CVE 번호와 버전 값이 빠지지 않았는지 검사합니다. Gemini가 실패할 때만 MyMemory가 문장과 표 셀을 동적으로 번역합니다.

Google Cloud Translation도 기본 NMT 번역은 월 500,000자까지 무료 크레딧이 적용되지만, 사용하려면 Google Cloud 결제 계정을 연결해야 합니다. 이 프로젝트는 예상치 못한 과금을 피하기 위해 사용하지 않습니다.

## 3. 확장 저장소의 Secrets 등록

이 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 등록합니다.

| 이름 | 값 |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | 기존 알리미가 사용하는 동일한 봇 token |
| `TELEGRAM_CHAT_ID` | 기존 알리미가 사용하는 동일한 chat ID |
| `GEMINI_API_KEY` | 권장. Google AI Studio에서 발급한 무료 티어 API key |
| `MYMEMORY_CONTACT_EMAIL` | 선택 사항. MyMemory 무료 한도를 하루 50,000자로 늘릴 연락용 이메일 |

모델을 직접 지정해야 하는 경우에만 저장소 **Settings → Secrets and variables → Actions → Variables**에 `GEMINI_MODEL`을 추가합니다. 설정하지 않으면 `gemini-2.5-flash`를 사용합니다.

## 4. KISA-Bohonara-Alert에서 확장 호출 허용

Fine-grained PAT를 하나 만듭니다.

1. GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens**로 이동합니다.
2. Repository access에서 **이 확장 저장소 한 개만** 선택합니다.
3. Repository permissions는 **Actions → Read and write**만 허용합니다.
4. 가능한 짧은 만료일로 발급합니다. (유출 됐을 때 피해 확산 방지, 개인 용도라면 Never로 해도 무방)

그다음 [KISA-Bohonara-Alert 저장소](https://github.com/doraemyon/KISA-Bohonara-Alert)의 **Settings → Secrets and variables → Actions**에 두 Secret을 등록합니다.

| 이름 | 값 |
| --- | --- |
| `NOTICE_EXTENSION_REPOSITORY` | `소유자/확장저장소이름` |
| `NOTICE_EXTENSION_TOKEN` | 위에서 만든 Fine-grained PAT |

PAT가 만료되거나 확장이 실패해도 기본 Telegram 공지는 계속 전송됩니다.

## 5. 연결 테스트

1. 기존 알리미 저장소의 **Actions → KISA security notices to Telegram → Run workflow**를 엽니다.
2. `Send an optional notice-extension test`만 체크하고 실행합니다.
3. Telegram에 테스트 알림이 먼저 오는지 확인합니다.
4. 확장 저장소의 Action과 Pages 배포가 끝나면 같은 메시지에 `국문 공지`, `영문 공지` 버튼이 추가됩니다.
5. 두 버튼을 눌러 UTF-8 표시, 전체 내용 복사와 텍스트 저장을 확인합니다.

## 보안 체크리스트

- 생성 문서는 인터넷에 공개되므로 민감정보나 비공개 문구를 추가하지 않습니다.
- Telegram·GitHub token은 GitHub Secret에만 저장합니다.
- Gemini API key는 코드나 Repository variable이 아닌 `GEMINI_API_KEY` Secret에만 저장합니다.
- Gemini 무료 티어는 입력 데이터가 Google 제품 개선에 사용될 수 있으므로 공개 KISA 공지 외의 내용은 보내지 않습니다.
- `MYMEMORY_CONTACT_EMAIL`을 등록하면 번역 요청마다 MyMemory에 연락용 이메일로 전달됩니다. 원하지 않으면 등록하지 않습니다.
- Fine-grained PAT는 확장 저장소 한 개의 Actions write 권한만 허용합니다.
- PAT에 Contents, Administration, Secrets 등의 추가 권한을 주지 않습니다.
- Secret 값은 Action 입력값, 커밋, Issue, 스크린샷에 넣지 않습니다.

## 로컬 테스트

외부 API를 호출하지 않는 단위 테스트입니다.

```powershell
python -m unittest discover -s tests -v
```

## 문제 해결

- `Could not find the KISA notice title or body`: KISA 페이지 구조가 바뀌었을 수 있습니다.
- `Gemini translation failed`: API key, 무료 티어 한도 또는 모델 이름을 확인합니다. 이 오류 뒤에는 MyMemory로 자동 대체를 시도합니다.
- `MyMemory translation failed after three attempts`: 대체 번역기의 무료 사용량 또는 서비스 상태를 확인하고 잠시 후 Action을 다시 실행합니다.
- `Translation result validation failed`: 번역 서비스가 국문 원문을 그대로 반환해 실패 처리된 것입니다.
- `Get Pages site failed`: **Settings → Pages → Source**가 `GitHub Actions`인지 확인합니다.
- Pages 배포 권한 오류: Workflow permissions와 `pages: write`, `id-token: write` 설정을 확인합니다.
- Telegram 버튼 갱신 실패: 두 저장소의 봇 token과 chat ID가 같은지 확인합니다.
- 확장 Action이 시작되지 않음: Fine-grained PAT의 대상 저장소, Actions write 권한과 만료일을 확인합니다.
