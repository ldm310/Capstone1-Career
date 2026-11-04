# 외부 합격자료 기술 키워드 교집합

`GET /api/postings/{postingId}/external-pass-keywords`

공고 필수·우대 기술과 동일 회사 외부 자료의 **기술 키워드 언급**을 비교한다. materialCount는 해당 키워드가 등장한 자료 수이며 사람 수, 검증된 기술 보유, 수행 수준, 합격 원인이 아니다. LV나 확률은 계산하지 않는다.

## 처리 기준

1. 명시적으로 연결된 동일 회사 IT_SW 자료만 읽고 EXCLUDED 관계는 제외한다. 같은 회사라도 미연결 자료는 자동으로 포함하지 않는다. 페이지 제한 없이 전체 연결 자료를 집계한다.
2. 기존 `pass_material.content` TEXT를 JSON으로 읽고 `technologies`의 문자열만 사용한다. projectSignals와 technologySignals는 비교에 사용하지 않으며 원본 content를 변경하지 않는다.
3. 키워드와 사전 이름·alias에 `String.strip()`과 `toLowerCase(Locale.ROOT)`만 적용한다. 내부 공백, 하이픈, 구두점, 전각 문자 등을 바꾸지 않는다.
4. `job.tech.name`의 정규화된 정확 일치를 먼저 찾는다. 정확한 이름이 없을 때만 기존 `job.tech.aliases` 배열을 조회한다. 부모 기술·유사 문자열·번역·퍼지 매칭은 사용하지 않는다.
5. 예를 들어 Spring Boot를 Spring으로 연결하려면 Spring의 aliases에 Spring Boot가 있어야 한다. Spring Boot 자체가 표준 name으로도 있으면 그 tech ID가 먼저 선택된다.
6. 정규화 후 같은 이름 또는 alias가 여러 tech ID에 매칭되면 임의로 선택하지 않고 unmappedKeywords에 남긴다. 이름 충돌 시 alias로 재시도하지 않는다. 하나의 tech에 같은 alias가 반복된 것은 충돌이 아니다.
7. 한 자료 안에서 name·alias·중복 키워드가 같은 tech ID로 연결되면 그 자료에서는 한 번만 센다. 자료가 다르면 각각 한 건이다.
8. 공고는 **현재 extraction_run**의 requirement_tech.tech_id만 읽는다. written_name이나 문장을 다시 분석해 기술 ID를 만들지 않는다. 필수와 우대에 같은 ID가 있으면 필수에만 배치한다. 업무·기타 기술을 필수/우대에 승격하지 않는다.
9. externalOnly는 현재 공고의 필수·우대 tech ID에 없는 외부 키워드다. 업무·기타에만 있는 기술도 여기에 해당할 수 있다.

각 결과 배열은 tech ID 오름차순이다. unmappedKeywords는 앞뒤 공백을 제거한 원래 표기를 반환하며, 대소문자를 무시한 키로 중복 제거한다. 여러 표기가 있으면 사전식으로 가장 작은 표기를 고르고 정규화 키 순서로 반환한다. 미등록 키워드를 사전에 INSERT하지 않는다.

## 응답 예시

```json
{
  "postingId": 1,
  "sourceMaterialCount": 5,
  "requiredOverlap": [{"techId": 10, "name": "Spring", "materialCount": 3}],
  "preferredOverlap": [{"techId": 15, "name": "Docker", "materialCount": 2}],
  "externalOnly": [{"techId": 21, "name": "Kubernetes", "materialCount": 2}],
  "unmappedKeywords": ["기존 사전에 없는 표현"]
}
```

sourceMaterialCount는 비교 대상에 연결된 고유 자료 수다. 과거 일반 텍스트, 잘못된 JSON, technologies 누락·잘못된 타입도 자료 수에는 포함하지만 키워드로 재분석하지 않는다. technologies 배열의 null·숫자·객체·빈 문자열은 무시한다. 자료가 없으면 count=0과 네 개의 빈 배열을 반환한다. 공고가 없으면 404, 양수가 아닌 공고 ID는 400이다.

## 파일과 검증

- `domain/job/Tech.java`: 이미 존재하는 aliases 컬럼의 읽기 전용 매핑 추가. SQL·DB 컬럼 변경 없음.
- `domain/job/TechRepository.java`: 기존 기술 사전 조회.
- `domain/job/RequirementTechRepository.java`: 현재 공고의 필수·우대 tech ID 조회.
- `domain/external/ExternalPassMaterialRepository.java`: 비교 가능한 전체 연결 자료 조회.
- `domain/external/TechKeywordMapper.java`: name 우선·alias 후순위 매핑과 충돌 처리.
- `domain/external/ExternalPassKeywordService.java`, `ExternalPassKeywordResponse.java`: 자료별 ID 중복 제거·언급 수 집계·DTO.
- `api/posting/ExternalPassKeywordController.java`: 신규 GET API.
- `domain/external/TechKeywordMapperTest.java`와 `api/posting/ExternalPassKeywordControllerTest.java` (test): 정규화·alias·정확명 우선·충돌·중복·필수 우선·EXCLUDED/타사 제외·현재 실행·원본 불변·빈 응답·자료 전체 집계 검증.

기존 외부 자료 API, 크롤러의 JSON 저장 형식, 추출 로직, DB SQL은 유지한다. 서비스는 read-only 트랜잭션으로 조회하며 운영 DB에 마이그레이션이나 수집을 실행할 필요가 없다.

```powershell
cd backend
.\gradlew.bat test
```
