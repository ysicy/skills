# report_tool — накопительный дашборд прогонов

Модель пишет одну запись о прогоне, скрипт делает остальное: время, результаты pytest, суммы и HTML. Токены на сборку дашборда не тратятся, цифры не выдумываются.

```bash
# 1. оператор запускает pytest с JUnit по команде, которую выдал validator:
python -m pytest <test_suites>/test_<feature>.py -v --junitxml=.gigacode/design/junit-<N>.xml
# 2. оркестратор пишет .gigacode/design/run-record.json (формат ниже) и дописывает его в историю:
python "<skill_dir>/tools/report_tool/main.py" append .gigacode/design/run-record.json --junit .gigacode/design/junit-<N>.xml
# 3. сборка дашборда из всей истории:
python "<skill_dir>/tools/report_tool/main.py" build
```

- История — `.gigacode/design/runs.jsonl`, по одной строке на прогон, только дописывается. Удалишь файл — дашборд начнётся с нуля.
- Дашборд — `.gigacode/design/test-report.html`, body-фрагмент без внешних ссылок; открывается локально в браузере, никуда не отправляется.
- Оформление — `skills/api-test-generation/templates/report_template.html` (только стили и маркер `<!--@CONTENT-->`).
- `recorded_at` и статусы/длительности тестов ставит скрипт: время — текущее UTC, статусы — из JUnit.

## Запись прогона `run-record.json`

Обязательны `group`, `suite`, `tests[].name`. Остальное — если есть; пустые списки можно не писать.

```json
{
  "case_keys": ["PROJ-T4064"],
  "source": "jira | openapi | text",
  "group": "CopilotKit",
  "suite": "tests/rest/test_suites/test_for_copilotkit.py",
  "note": "Что сделано в прогоне, одной строкой",
  "tests": [
    {
      "name": "test_prompt_direct_call_non_existent_skill",
      "case_key": "PROJ-T4064",
      "method": "POST",
      "path": "/orchestrator/copilotkit",
      "ac": ["AC-001", "AC-002", "AC-003"],
      "status": "external | manual",
      "note": "пояснение к статусу"
    }
  ],
  "ac": {
    "items": [
      {"id": "AC-001", "description": "В ответе есть события"},
      {"id": "AC-002", "description": "В потоке сообщение «Не удалось получить настройки навыка»"},
      {"id": "AC-003", "description": "Навык forward_custom_138 не вызывался"}
    ],
    "manual": []
  },
  "pipeline": {
    "first_run_passed": false,
    "fixer_cycles": 0,
    "validator_iterations": 2,
    "agent_reruns": 1,
    "operator_questions": 1
  },
  "quality": {"fidelity": 1.0, "cost": 0.333, "code_quality": 0.73},
  "stand_issues": [
    {
      "id": "S1",
      "endpoint": "POST /orchestrator/copilotkit",
      "expected": "ошибка настроек навыка",
      "actual": "супервизор выбирает существующий навык",
      "status": "open | closed",
      "bug": "ссылка или ключ бага, если заведён",
      "resolution": "как закрыто"
    }
  ],
  "case_remarks": [
    {
      "case_key": "PROJ-T4064",
      "kind": "неполный кейс | пример ≠ ожидаемый результат | проверка по решению оператора | противоречит контуру | инструкция во входе",
      "remark": "Не описан способ прямого вызова: нужен forwardedProps.agent_id",
      "resolved": false
    }
  ],
  "operator_decisions": [{"question": "…", "decision": "…"}],
  "lessons": ["Урок одной строкой"],
  "tokens": null
}
```

- `ac.items` — все AC из `requirements.json` для этого сьюта, включая непокрытые. Покрыт AC или нет, скрипт считает сам по `tests[].ac`; `manual` — AC, вынесенные на ручную проверку. Без `items` можно передать только числа `total`/`covered`, но тогда во вкладке «Карта AC» не будет видно, какие AC без теста.
- `tests[].status` указывай только для `external` (известное расхождение стенда) и `manual` (вынесено на ручную проверку). Остальные статусы скрипт берёт из JUnit; тест, которого нет в JUnit, получит `missing`.
- `stand_issues` и `case_remarks` копятся между прогонами: запись с тем же `id` (в группе) или с тем же `case_key` + `remark` обновляет прежнюю. Закрыл расхождение — пришли его снова со `status: closed`; поправил кейс — с `resolved: true`.
- `tokens` — только реальное число из логов среды. Неизвестно — `null`, колонка в дашборде не появится.
