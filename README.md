# KISA 공지 포맷터 확장

이 저장소는 [KISA-Bohonara-Alert](https://github.com/doraemyon/KISA-Bohonara-Alert)의 추가 익스펜션 기능을 제공하는 프로젝트입니다. 기존 프로젝트가 KISA 보안공지를 빠르게 감지해 Telegram으로 알리는 기본 기능을 담당하고, 이 프로젝트는 운영 담당자가 공지를 업무에 활용하기 쉬운 국문·영문 형식으로 확인하고 전달할 수 있도록 후처리 기능을 추가합니다.

이 익스펜션은 선택 사항입니다. `KISA-Bohonara-Alert`는 이 저장소를 연결하지 않아도 기존 공지 알리미로 독립적으로 동작합니다. 두 프로젝트를 연결하면 기본 알리미가 첫 Telegram 메시지부터 다음 버튼을 표시하고, 이 저장소는 해당 링크의 문서를 생성합니다.

```text
공지 열기
국문 공지 | 영문 공지
```

국문·영문 문서는 UTF-8 GitHub Pages로 제공되며 발행일, 줄번호, `전체 내용 복사`와 텍스트 파일 저장 기능을 지원합니다. 저장된 공지는 발행일과 함께 사이트 첫 화면의 목록에서도 다시 열 수 있습니다. 알림 직후 아직 문서가 생성되지 않았으면 404 대신 준비 상태를 표시하고, 게시가 끝나는 즉시 같은 주소에서 자동으로 문서를 엽니다.

## 동작 방식

1. 기존 알리미가 `공지 열기`, `국문 공지`, `영문 공지` 버튼을 포함한 Telegram 공지를 즉시 전송합니다.
2. 확장이 설정된 경우에만 이 저장소의 Action을 호출합니다. 국문·영문 링크는 공지 번호로 미리 계산되므로 두 저장소의 Telegram chat ID를 맞출 필요가 없습니다.
3. Action이 KISA 원문을 다시 읽고 도메인·게시판·공지 번호·발행일을 검증합니다.
4. 제목이 `업데이트 권고`이면 본문 표현과 관계없이 업데이트 권고용 요약을 사용합니다. 제목이 `업데이트`, `업그레이드`, `보안 조치 권고` 또는 `보안 패치 권고` 계열인 경우에는 본문에 CVE, 영향 제품·버전, 해결 버전, 패치나 조치 방안이 있는지 추가 확인합니다. 그 외 공지는 일반 요약을 사용합니다.
5. `□`, `o`, `※`, URL, CVE와 버전 정보는 번역기가 변경하지 못하도록 분리·보호하고, 번역 후 원래 위치와 개수를 검증합니다.
6. 번역은 Gemini 무료 티어 → 선택적 Cloudflare Workers AI 번역 모델 → Google Translate 웹 경로 → MyMemory 순서로 시도합니다. 각 경로는 최대 세 번 재시도합니다.
7. 국문과 검증을 통과한 영문이 모두 완성된 경우에만 두 페이지를 한 번에 저장합니다. 번역 대기 문서나 한국어 본문을 넣은 가짜 영문 페이지는 게시하지 않습니다.
8. 공지 처리 성공을 확인한 별도 Pages workflow가 최신 `main`을 배포합니다.
9. 배포가 완료되면 최초 Telegram 메시지에 이미 들어 있던 국문·영문 링크가 정상 문서로 전환됩니다.

업데이트 권고로 판정된 공지는 항상 `영향 버전을 가용중인 각 관계사 담당자 분들께 업데이트 권고` 문구가 포함된 요약을 사용합니다. 거의 동시에 여러 공지가 들어와도 Action을 직렬로 실행하고, 각 실행은 시작 시점의 최신 `main`을 체크아웃해 생성 문서 커밋이 서로 충돌하지 않도록 합니다.

알림 전송과 문서 생성은 분리되어 있어 Telegram 알림은 지연되지 않습니다. 알림 직후 국문·영문 버튼을 누르면 준비 상태가 표시되며, 게시 완료 여부를 5초마다 확인해 실제 문서로 자동 전환합니다. 한 번의 번역기 오류는 같은 실행에서 다음 제공자로 전환합니다. KISA 원문 수집 자체가 실패해도 준비 화면의 원문 링크와 기본 알림의 `공지 열기` 버튼은 그대로 유지됩니다.

30분마다 최근 RSS와 저장된 국문·영문 쌍을 비교하는 복구 workflow도 실행됩니다. 최초 처리 실행이 완전히 실패해 저장소에 흔적을 남기지 못한 공지도 RSS에 남아 있는 동안 자동으로 다시 생성합니다. 복구할 공지가 없거나 외부 서비스가 계속 불안정하면 변경 없이 정상 종료하므로 같은 실패 메일을 반복해서 만들지 않습니다.

## 공개 범위와 비용

- 이 저장소와 생성된 국문·영문 문서는 **Public**입니다. 공개하면 안 되는 내용을 템플릿이나 생성 문서에 추가하지 마세요.
- Public 저장소의 표준 GitHub-hosted runner와 GitHub Pages는 무료입니다.
- 이 Action은 매분 실행되지 않고 새로운 공지가 있을 때만 실행됩니다.
- 권장 번역기는 결제 계정 연결 없이 사용할 수 있는 [Gemini API 무료 티어](https://ai.google.dev/gemini-api/docs/pricing)입니다. 무료 티어의 요청 한도 안에서는 요금이 발생하지 않습니다.
- Cloudflare를 설정하면 [Workers AI의 M2M100 번역 전용 모델](https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/)을 두 번째 경로로 사용합니다. Workers Free는 하루 10,000 Neurons 무료 할당량을 초과하면 추가 과금 대신 호출이 중단됩니다.
- Google Translate 웹 경로는 별도 API key나 결제 계정 없이 사용하는 세 번째 경로입니다. 공식 Cloud Translation API가 아니므로 별도 SLA는 없지만, 구조·보안 식별자 검증을 통과한 결과만 사용합니다.
- MyMemory는 별도 키 없이 사용하는 마지막 경로입니다. 익명 기준 하루 5,000자이며, 연락용 이메일을 전달하면 하루 50,000자입니다.
- Gemini 무료 티어에 보낸 데이터는 Google 제품 개선에 사용될 수 있습니다. 이 프로젝트는 인터넷에 이미 공개된 KISA 공지만 번역 대상으로 사용합니다.
- 무료 티어의 실제 요청 한도는 모델과 프로젝트에 따라 달라질 수 있으며 Google AI Studio에서 확인할 수 있습니다. 한도에 도달하면 다음 제공자로 자동 전환합니다.
- 번역 결과가 국문과 같거나, 한글 비율이 비정상적으로 높거나, 구조 표식·URL·CVE·버전이 하나라도 빠지면 성공으로 처리하지 않습니다.

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

번역은 공지 전체를 문맥 단위로 처리합니다. 특정 공지의 문장이나 제품명을 코드에 고정해 두지 않습니다. 구조 표식과 보안 식별자는 번역기에 보내지 않고 그대로 결합하며, 복원 뒤 원문과 개수를 다시 비교합니다. 안정적인 KISA 표준 섹션명만 `□ Overview`, `□ Description`, `□ Questions and inquiries`처럼 일관되게 정규화합니다.

Google Cloud Translation도 기본 NMT 번역은 월 500,000자까지 무료 크레딧이 적용되지만, 사용하려면 Google Cloud 결제 계정을 연결해야 합니다. 이 프로젝트는 예상치 못한 과금을 피하기 위해 사용하지 않습니다.

## 3. 확장 저장소의 번역 설정

이 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 등록합니다.

| 이름 | 값 |
| --- | --- |
| `GEMINI_API_KEY` | 권장. Google AI Studio에서 발급한 무료 티어 API key |
| `CLOUDFLARE_ACCOUNT_ID` | 선택. Cloudflare Workers AI 계정 ID |
| `CLOUDFLARE_API_TOKEN` | 선택. Workers AI 실행 권한만 가진 API token |
| `MYMEMORY_CONTACT_EMAIL` | 선택 사항. MyMemory 무료 한도를 하루 50,000자로 늘릴 연락용 이메일 |

Telegram bot token과 chat ID는 이 저장소에 등록하지 않습니다. 기존에 등록한 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` Secret은 삭제해도 됩니다. Telegram 발송과 버튼 구성은 `KISA-Bohonara-Alert`가 한 번에 처리하고, 이 저장소는 공개 문서 생성과 Pages 배포만 담당합니다.

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
3. Telegram 테스트 알림에 `공지 열기`, `국문 공지`, `영문 공지` 버튼이 처음부터 모두 보이는지 확인합니다.
4. 확장 저장소의 Action과 Pages 배포가 끝날 때까지 기다립니다.
5. 국문·영문 버튼을 눌러 UTF-8 표시, 전체 내용 복사와 텍스트 저장을 확인합니다.

## 보안 체크리스트

- 생성 문서는 인터넷에 공개되므로 민감정보나 비공개 문구를 추가하지 않습니다.
- GitHub token은 GitHub Secret에만 저장합니다.
- Gemini API key는 코드나 Repository variable이 아닌 `GEMINI_API_KEY` Secret에만 저장합니다.
- Cloudflare를 사용할 경우 Account ID와 API token을 모두 GitHub Secret에만 저장하고 Workers AI 실행 외 권한은 부여하지 않습니다.
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

- `Could not find the KISA notice title, published date, or body`: KISA 페이지 구조가 바뀌었을 수 있습니다.
- `Gemini translation failed`: API key, 무료 티어 한도 또는 모델 이름을 확인합니다. 이 오류 뒤에는 Cloudflare 또는 MyMemory로 자동 전환합니다.
- `MyMemory translation failed after three attempts`: 앞선 Gemini·Cloudflare·Google Translate 경로까지 모두 실패한 뒤 마지막 제공자의 무료 한도 또는 서비스 상태도 사용할 수 없는 경우입니다. workflow 전체가 최대 세 차례 다시 시도합니다.
- KISA 원문 수집의 일시적인 네트워크 오류: workflow가 15초 간격으로 최대 세 번 자동 재시도합니다.
- 번역 서비스 오류 또는 구조·식별자 누락: 해당 제공자 결과를 폐기하고 다음 제공자로 넘어갑니다. 모든 경로가 실패하면 국문만 단독 게시하지 않고, 30분 간격 복구 workflow가 최근 RSS에서 누락 건을 찾아 다시 시도합니다.
- `non-fast-forward` 또는 `fetch first`: 최신 workflow에는 동시 공지를 직렬 처리하고 최신 `main`을 체크아웃하는 설정이 포함되어 있습니다. 이전 실패 실행은 **Re-run jobs** 대신 새 workflow를 실행하세요.
- `Translation result validation failed`: 번역 서비스가 국문 원문을 그대로 반환했거나 구조를 손상한 경우입니다. 해당 결과는 게시하지 않고 다음 제공자를 사용합니다.
- `Get Pages site failed`: **Settings → Pages → Source**가 `GitHub Actions`인지 확인합니다.
- Pages 배포 권한 오류: Workflow permissions와 `pages: write`, `id-token: write` 설정을 확인합니다.
- Telegram에 국문·영문 버튼이 없음: 기본 알리미 저장소가 최신 버전인지 확인하고 `NOTICE_EXTENSION_REPOSITORY`, `NOTICE_EXTENSION_TOKEN` 두 Secret을 확인합니다.
- 버튼을 누르면 404가 표시됨: 문서 생성이나 Pages 배포가 아직 진행 중이거나 실패한 상태입니다. 이 저장소의 Action 실행 결과를 확인하세요.
- 확장 Action이 시작되지 않음: Fine-grained PAT의 대상 저장소, Actions write 권한과 만료일을 확인합니다.
