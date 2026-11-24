package com.career.backend.domain.profile;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.UUID;

// 프로젝트 설명 PDF를 서버 디스크에 저장한다. DB에는 경로만 남긴다.
@Component
public class ProjectFileStorage {

    public static final String PDF = "PDF";

    private static final byte[] PDF_SIGNATURE =
            "%PDF-".getBytes(StandardCharsets.US_ASCII);

    private final Path baseDir;

    public ProjectFileStorage(
            @Value("${app.storage.project-file-dir:uploads/projects}")
            String baseDir
    ) {
        this.baseDir = Path.of(baseDir).toAbsolutePath().normalize();
    }

    public String storePdf(MultipartFile file) {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("빈 파일은 올릴 수 없습니다.");
        }

        if (!isPdf(file)) {
            throw new IllegalArgumentException("PDF 파일만 올릴 수 있습니다.");
        }

        Path target = baseDir.resolve(UUID.randomUUID() + ".pdf");

        try {
            Files.createDirectories(baseDir);
            file.transferTo(target);
        } catch (IOException e) {
            throw new UncheckedIOException("파일을 저장하지 못했습니다.", e);
        }

        return target.toString();
    }

    public Resource load(String path) {
        Path file = Path.of(path).toAbsolutePath().normalize();

        if (!file.startsWith(baseDir) || !Files.isReadable(file)) {
            throw new IllegalStateException("설명 파일을 읽을 수 없습니다.");
        }

        return new FileSystemResource(file);
    }

    // 확장자나 Content-Type은 속일 수 있으니 파일 앞부분의 PDF 서명을 확인한다.
    private static boolean isPdf(MultipartFile file) {
        try (InputStream in = file.getInputStream()) {
            byte[] head = in.readNBytes(PDF_SIGNATURE.length);
            return Arrays.equals(head, PDF_SIGNATURE);
        } catch (IOException e) {
            return false;
        }
    }
}
