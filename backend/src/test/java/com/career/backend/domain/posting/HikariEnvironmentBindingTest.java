package com.career.backend.domain.posting;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.SimpleCommandLinePropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.core.env.SystemEnvironmentPropertySource;

import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class HikariEnvironmentBindingTest {
    private HikariDataSource pool() {
        var pool = new HikariDataSource();
        pool.setJdbcUrl("jdbc:h2:mem:hikari_binding_" + UUID.randomUUID());
        pool.setUsername("sa");
        pool.setPassword("");
        pool.setMaximumPoolSize(1);
        return pool;
    }

    private StandardEnvironment environment() {
        var environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(new SimpleCommandLinePropertySource(
                "--spring.datasource.hikari.read-only=true",
                "--spring.datasource.hikari.connection-init-sql=SELECT 1"));
        return environment;
    }

    @Test void splitEnvironmentNameReproducesPrematurePoolStartup() {
        var environment = environment();
        environment.getPropertySources().addLast(new SystemEnvironmentPropertySource("staging-systemEnvironment",
                Map.of("SPRING_DATASOURCE_HIKARI_CONNECTION_INIT_SQL", "SELECT 1",
                        "SPRING_DATASOURCE_HIKARI_READ_ONLY", "true")));
        try (var pool = pool()) {
            assertThatThrownBy(() -> Binder.get(environment).bind("spring.datasource.hikari", Bindable.ofInstance(pool)))
                    .hasStackTraceContaining("The configuration of the pool is sealed once started");
        }
    }

    @Test void canonicalPropertiesBindBeforeTheFirstConnection() throws Exception {
        try (var pool = pool()) {
            Binder.get(environment()).bind("spring.datasource.hikari", Bindable.ofInstance(pool));
            assertThat(pool.isRunning()).isFalse();
            assertThat(pool.isReadOnly()).isTrue();
            assertThat(pool.getConnectionInitSql()).isEqualTo("SELECT 1");
            try (var connection = pool.getConnection()) {
                assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("H2");
            }
        }
    }
}
