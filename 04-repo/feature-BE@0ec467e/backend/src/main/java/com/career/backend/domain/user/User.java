package com.career.backend.domain.user;

import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "users") //User는 SQL 예약어와 충돌할 가능성이 있어서 테이블 이름을 users로 지정했어요
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(nullable = false, length = 50)
    private String nickname;

    @Column(nullable = false)
    private boolean studyMatchingEnabled;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected User() {
    }

    public User(String email, String nickname) {
        this.email = email;
        this.nickname = nickname;
        this.studyMatchingEnabled = false;
    }

    @PrePersist
    private void prePersist() {
        this.createdAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getNickname() {
        return nickname;
    }

    public boolean isStudyMatchingEnabled() {
        return studyMatchingEnabled;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void changeStudyMatchingEnabled(boolean enabled) {
        this.studyMatchingEnabled = enabled;
    }
}