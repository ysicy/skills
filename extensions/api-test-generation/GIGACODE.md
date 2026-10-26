---
name: api-test-generation
description: >
  Генерация API-автотестов на Python (pytest, Allure) по тест-кейсу Jira/Zephyr
  или по спецификации OpenAPI/Swagger через пайплайн из 7 субагентов.
---

# Оркестратор API Test Generation

При вызове команды `/api-test-generation`, а также на просьбу сгенерировать или автоматизировать API-автотест по тест-кейсу Jira/Zephyr или по OpenAPI/Swagger, прочитай и полностью выполни skill `api-test-generation`, передав ему запрос пользователя без сокращений.

Внутренний skill является единственным источником логики пайплайна. Не пересказывай, не сокращай и не подменяй его этапы в extension context.
