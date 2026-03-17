"""Generates Gradle build files for the generated Spring Boot project."""
from __future__ import annotations
from typing import Any


class GradleScaffold:
    """Generates build.gradle, settings.gradle, application.yml."""

    def generate(self, arch_plan: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {"path": "build.gradle",        "content": self._build_gradle(), "type": "GRADLE"},
            {"path": "settings.gradle",     "content": self._settings_gradle(), "type": "GRADLE"},
            {"path": "src/main/resources/application.yml", "content": self._app_yml(), "type": "CONFIG"},
        ]

    @staticmethod
    def _build_gradle() -> str:
        return (
            "plugins {\n"
            "    id 'org.springframework.boot' version '3.3.2'\n"
            "    id 'io.spring.dependency-management' version '1.1.5'\n"
            "    id 'java'\n"
            "}\n\n"
            "group   = 'com.migrated'\n"
            "version = '0.0.1-SNAPSHOT'\n"
            "java { sourceCompatibility = JavaVersion.VERSION_21 }\n\n"
            "repositories { mavenCentral() }\n\n"
            "dependencies {\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-web'\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-security'\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-validation'\n"
            "    implementation 'org.springframework.boot:spring-boot-starter-actuator'\n"
            "    implementation 'org.springframework.ws:spring-ws-core'\n"
            "    implementation 'org.springframework.cloud:spring-cloud-starter-openfeign'\n"
            "    implementation 'io.jsonwebtoken:jjwt-api:0.12.5'\n"
            "    runtimeOnly    'org.postgresql:postgresql'\n"
            "    runtimeOnly    'com.h2database:h2'\n"
            "    runtimeOnly    'io.jsonwebtoken:jjwt-impl:0.12.5'\n"
            "    compileOnly    'org.projectlombok:lombok'\n"
            "    annotationProcessor 'org.projectlombok:lombok'\n"
            "    testImplementation 'org.springframework.boot:spring-boot-starter-test'\n"
            "    testImplementation 'org.springframework.security:spring-security-test'\n"
            "}\n\n"
            "tasks.named('test') { useJUnitPlatform() }\n"
        )

    @staticmethod
    def _settings_gradle() -> str:
        return "rootProject.name = 'migrated-app'\n"

    @staticmethod
    def _app_yml() -> str:
        return (
            "spring:\n"
            "  application:\n"
            "    name: migrated-app\n"
            "  datasource:\n"
            "    url: jdbc:h2:mem:testdb\n"
            "    driver-class-name: org.h2.Driver\n"
            "  jpa:\n"
            "    hibernate:\n"
            "      ddl-auto: update\n"
            "    show-sql: false\n"
            "server:\n"
            "  port: 8080\n"
        )
