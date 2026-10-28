package com.career.backend;

import org.springframework.jdbc.core.JdbcTemplate;

// job 스키마는 백엔드가 쓰지 않는 표라서 테스트 데이터는 SQL로 넣는다.
public final class TestFixtures {

    private TestFixtures() {
    }

    // 공고 1건: 서버 개발자 단위 하나, 필수(관계형 DB: MySQL), 우대(컨테이너: Docker)
    public static void insertAnalyzedPosting(JdbcTemplate jdbc) {
        jdbc.update("insert into job.capability (id, name, group_name, is_active) values (1, '관계형 DB', '데이터', true)");
        jdbc.update("insert into job.capability (id, name, group_name, is_active) values (2, '컨테이너', '인프라', true)");
        jdbc.update("insert into job.capability (id, name, group_name, is_active) values (3, '사용안함', '기타', false)");
        jdbc.update("insert into job.tech (id, name) values (1, 'MySQL')");

        jdbc.update("insert into job.company (id, name) values (1, '커리어컴퍼니')");
        jdbc.update("""
                insert into job.posting (id, company_id, site, site_posting_no, title, kind, status,
                                         collected_at, last_checked_at)
                values (1, 1, '사람인', '50001', '백엔드 개발자 채용', '섞임', '진행',
                        current_timestamp, current_timestamp)
                """);
        jdbc.update("""
                insert into job.posting (id, company_id, site, site_posting_no, title, kind, status,
                                         collected_at, last_checked_at)
                values (2, 1, '사람인', '50002', '디자이너 채용', '글', '마감',
                        current_timestamp, current_timestamp)
                """);
        jdbc.update("insert into job.posting_image (id, posting_id, seq, url, kept) values (2, 1, 2, 'https://img.example/2.png', null)");
        jdbc.update("insert into job.posting_image (id, posting_id, seq, url, kept) values (1, 1, 1, 'https://img.example/1.png', true)");

        jdbc.update("""
                insert into job.extraction_run (id, posting_id, model, dict_version, is_current, run_at)
                values (1, 1, 'test-model', '0.1.1', true, current_timestamp)
                """);
        jdbc.update("""
                insert into job.recruit_unit (id, run_id, seq, name, is_it, career, years_text)
                values (1, 1, 1, '서버 개발자', true, '경력', '3년 이상')
                """);
        jdbc.update("""
                insert into job.recruit_unit (id, run_id, seq, name, is_it, career, years_text)
                values (2, 1, 2, '경영지원', false, '신입', '')
                """);
        jdbc.update("insert into job.unit_item (id, unit_id, category, seq, text, quote) values (1, 1, '필수', 1, 'MySQL 사용 경험', 'MySQL 등 RDBMS 경험')");
        jdbc.update("insert into job.unit_item (id, unit_id, category, seq, text, quote) values (2, 1, '필수', 2, 'RDB 설계 경험', 'DB 설계 경험자')");
        jdbc.update("insert into job.unit_item (id, unit_id, category, seq, text, quote) values (3, 1, '우대', 1, 'Docker 사용 경험', 'Docker 경험 우대')");
        jdbc.update("insert into job.requirement (id, item_id, capability_id, other_name, relation) values (1, 1, 1, '', '예시')");
        jdbc.update("insert into job.requirement (id, item_id, capability_id, other_name, relation) values (2, 2, 1, '', '능력만')");
        jdbc.update("insert into job.requirement (id, item_id, capability_id, other_name, relation) values (3, 3, 2, '', '능력만')");
        jdbc.update("insert into job.requirement_tech (id, requirement_id, tech_id, written_name) values (1, 1, 1, 'MySQL')");
        jdbc.update("insert into job.requirement_tech (id, requirement_id, tech_id, written_name) values (2, 3, null, '도커')");
    }
}
