package com.career.backend.domain.profile;

import com.career.backend.domain.common.NotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class UserService {

    private final AppUserRepository appUserRepository;

    public UserService(AppUserRepository appUserRepository) {
        this.appUserRepository = appUserRepository;
    }

    @Transactional
    public UserResponse create(String email, String name) {
        if (appUserRepository.existsByEmail(email)) {
            throw new IllegalStateException("이미 가입된 이메일입니다.");
        }

        return UserResponse.from(
                appUserRepository.save(new AppUser(email, name))
        );
    }

    public UserResponse get(Long userId) {
        return UserResponse.from(find(userId));
    }

    AppUser find(Long userId) {
        return appUserRepository.findById(userId)
                .orElseThrow(() ->
                        new NotFoundException("사용자를 찾을 수 없습니다.")
                );
    }
}
