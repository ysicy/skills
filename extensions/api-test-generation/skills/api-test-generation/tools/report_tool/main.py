"""Накопительный дашборд прогонов api-test-generation.

Модель пишет одну запись о прогоне (JSON), скрипт делает всё остальное:

    python "<skill_dir>/tools/report_tool/main.py" append .gigacode/design/run-record.json \
        --junit .gigacode/design/junit.xml
    python "<skill_dir>/tools/report_tool/main.py" build

append — проверяет запись, подставляет время и результаты pytest из JUnit XML,
         дописывает одну строку в .gigacode/design/runs.jsonl.
build  — собирает дашборд из всех записей runs.jsonl по шаблону
         templates/report_template.html → .gigacode/design/test-report.html.

Только стандартная библиотека Python 3.8+. Формат записи — README.md рядом.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA_VERSION = "1.0"
DESIGN = Path(".gigacode/design")
DEFAULT_RUNS = DESIGN / "runs.jsonl"
DEFAULT_OUT = DESIGN / "test-report.html"
DEFAULT_TEMPLATE = (
    # <skill_dir>/tools/report_tool/main.py → <skill_dir>/templates/report_template.html
    Path(__file__).resolve().parent.parent.parent / "templates" / "report_template.html"
)
MARKER = "<!--@CONTENT-->"

TEST_STATUSES = {"passed", "failed", "error", "skipped", "external", "manual"}
ISSUE_STATUSES = {"open", "closed"}


# ---------------------------------------------------------------- append


def _fail(msg: str) -> None:
    print(f"report_tool: {msg}", file=sys.stderr)
    sys.exit(2)


MAX_JUNIT_BYTES = 20 * 1024 * 1024


def parse_junit(path: Path) -> dict[str, dict]:
    """Результаты pytest по имени теста: {name: {status, duration, message}}.

    junit.xml — артефакт прогона, имена тестов в нём пишет модель, поэтому файл
    читается с лимитом размера. Внешние сущности ElementTree не раскрывает.
    """
    size = path.stat().st_size
    if size > MAX_JUNIT_BYTES:
        raise ValueError(f"{path}: {size} байт — больше лимита {MAX_JUNIT_BYTES}; это не junit одного прогона")
    root = ET.parse(path).getroot()
    out: dict[str, dict] = {}
    for case in root.iter("testcase"):
        name = case.get("name", "")
        status, message = "passed", ""
        for tag in ("failure", "error", "skipped"):
            node = case.find(tag)
            if node is not None:
                status = {"failure": "failed"}.get(tag, tag)
                message = (node.get("message") or "").strip()
                break
        out[name] = {
            "status": status,
            "duration": round(float(case.get("time") or 0), 2),
            "message": message[:300],
            "classname": case.get("classname", ""),
        }
    return out


def _match_junit(test_name: str, junit: dict[str, dict]) -> list[dict]:
    """Тест с параметризацией даёт несколько записей: test_x[user_1], test_x[user_2]."""
    return [r for n, r in junit.items() if n == test_name or n.startswith(test_name + "[")]


def validate(rec: dict) -> list[str]:
    errors = []
    for key in ("group", "suite", "tests"):
        if not rec.get(key):
            errors.append(f"нет обязательного поля «{key}»")
    for i, t in enumerate(rec.get("tests") or []):
        if not t.get("name"):
            errors.append(f"tests[{i}]: нет «name» (имя тест-функции)")
        st = t.get("status")
        if st and st not in TEST_STATUSES:
            errors.append(f"tests[{i}]: status «{st}» не из {sorted(TEST_STATUSES)}")
    for i, s in enumerate(rec.get("stand_issues") or []):
        if s.get("status", "open") not in ISSUE_STATUSES:
            errors.append(f"stand_issues[{i}]: status должен быть open или closed")
        if not s.get("id"):
            errors.append(f"stand_issues[{i}]: нет «id»")
    for i, r in enumerate(rec.get("case_remarks") or []):
        if not r.get("case_key") or not r.get("remark"):
            errors.append(f"case_remarks[{i}]: нужны «case_key» и «remark»")
    return errors


def cmd_append(args: argparse.Namespace) -> None:
    rec_path = Path(args.record)
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _fail(f"не читается запись {rec_path}: {e}")
    errors = validate(rec)
    if errors:
        _fail("запись не принята:\n  - " + "\n  - ".join(errors))

    rec["schema_version"] = SCHEMA_VERSION
    rec["recorded_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.junit:
        junit_path = Path(args.junit)
        if not junit_path.exists():
            _fail(f"нет файла JUnit {junit_path}")
        junit = parse_junit(junit_path)
        for t in rec["tests"]:
            hits = _match_junit(t["name"], junit)
            if not hits:
                t.setdefault("status", "missing")
                continue
            worst = "passed"
            for h in hits:
                if h["status"] in ("failed", "error"):
                    worst = h["status"]
                elif h["status"] == "skipped" and worst == "passed":
                    worst = "skipped"
            t["pytest_status"] = worst
            t["duration"] = round(sum(h["duration"] for h in hits), 2)
            msg = next((h["message"] for h in hits if h["message"]), "")
            if msg:
                t["message"] = msg
            # external/manual — классификация validator'а поверх pytest
            if t.get("status") not in ("external", "manual"):
                t["status"] = worst
        rec["junit"] = str(junit_path)
    for t in rec["tests"]:
        t.setdefault("status", "missing")

    runs = Path(args.runs)
    runs.parent.mkdir(parents=True, exist_ok=True)
    with runs.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    passed = sum(1 for t in rec["tests"] if t["status"] == "passed")
    print(f"report_tool: запись добавлена в {runs} — {rec['group']}, тестов {len(rec['tests'])}, passed {passed}")


# ---------------------------------------------------------------- build


def load_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    runs = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            runs.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"report_tool: строка {n} в {path} повреждена — пропущена", file=sys.stderr)
    runs.sort(key=lambda r: r.get("recorded_at", ""))
    return runs


def e(v) -> str:
    return html.escape("" if v is None else str(v))


def _fmt_dur(sec: float) -> str:
    if sec < 60:
        return f"{sec:.1f} с"
    return f"{int(sec // 60)} мин {int(sec % 60)} с"


def aggregate(runs: list[dict]) -> dict:
    """Текущее состояние: последняя запись по каждому тесту и по каждой группе."""
    tests: dict[tuple, dict] = {}
    groups: dict[str, dict] = {}
    issues: dict[tuple, dict] = {}
    remarks: dict[tuple, dict] = {}
    lessons: dict[str, str] = {}
    for r in runs:
        date = r.get("recorded_at", "")[:10]
        g = r.get("group", "—")
        grp = groups.setdefault(g, {"suites": set(), "ac": {}, "first": date})
        grp["suites"].add(r.get("suite", ""))
        grp["last"] = date
        # покрытие AC — по последней записи сьюта, где оно указано: частичный перепрогон без «ac» его не обнуляет
        if r.get("ac"):
            grp["ac"][r.get("suite", "")] = r["ac"]
        for t in r.get("tests") or []:
            key = (r.get("suite", ""), t.get("name"))
            tests[key] = {**t, "group": g, "suite": r.get("suite", ""), "date": date,
                          "case_key": t.get("case_key") or ", ".join(r.get("case_keys") or [])}
        for s in r.get("stand_issues") or []:
            key = (g, s.get("id"))
            prev = issues.get(key, {})
            issues[key] = {**prev, **s, "group": g, "first": prev.get("first", date), "last": date}
        for c in r.get("case_remarks") or []:
            key = (c.get("case_key"), c.get("remark"))
            prev = remarks.get(key, {})
            remarks[key] = {**prev, **c, "first": prev.get("first", date)}
        for les in r.get("lessons") or []:
            lessons.setdefault(les, date)
    for name, grp in groups.items():
        grp["acmap"] = _ac_map(name, grp, tests)
    return {"tests": tests, "groups": groups, "issues": issues, "remarks": remarks, "lessons": lessons}


def _ac_map(group: str, grp: dict, tests: dict) -> dict:
    """Покрытие группы по каждому AC.

    Есть список ac.items — статус каждого AC считается по текущим тестам группы:
    covered — его проверяет хотя бы один тест, manual — вынесен на ручную проверку,
    uncovered — не проверяет ничто. Списка нет — берутся числа total/covered из записи.
    """
    items: dict[str, dict] = {}
    manual: set[str] = set()
    tot = cov = 0
    for ac in grp["ac"].values():
        manual |= {str(x) for x in ac.get("manual") or []}
        for it in ac.get("items") or []:
            if it.get("id"):
                items[str(it["id"])] = {"id": str(it["id"]), "description": it.get("description", "")}
        if not ac.get("items"):
            tot += int(ac.get("total") or 0)
            cov += int(ac.get("covered") or 0)
    by_ac: dict[str, list[str]] = {}
    for t in tests.values():
        if t["group"] != group:
            continue
        for a in t.get("ac") or []:
            by_ac.setdefault(str(a), []).append(t.get("name", ""))
    for a, it in items.items():
        it["tests"] = sorted(by_ac.get(a, []))
        it["status"] = "covered" if it["tests"] else ("manual" if a in manual else "uncovered")
    listed = list(items.values())
    tot += len(listed)
    cov += sum(1 for it in listed if it["status"] == "covered")
    return {"items": sorted(listed, key=lambda x: x["id"]), "total": tot, "covered": cov,
            "manual": sorted(manual),
            "uncovered": [it["id"] for it in listed if it["status"] == "uncovered"]}


STATUS_BADGE = {
    "passed": ("pass", "passed"),
    "failed": ("fail", "failed"),
    "error": ("fail", "error"),
    "skipped": ("manual", "skipped"),
    "external": ("ext", "внешнее"),
    "manual": ("manual", "ручная"),
    "missing": ("fail", "нет в pytest"),
}


def badge(status: str) -> str:
    cls, label = STATUS_BADGE.get(status, ("manual", status))
    return f'<span class="badge {cls}">{e(label)}</span>'


def render(runs: list[dict]) -> str:
    agg = aggregate(runs)
    tests = list(agg["tests"].values())
    by_status = {s: sum(1 for t in tests if t["status"] == s) for s in STATUS_BADGE}
    ac_total = sum(g["acmap"]["total"] for g in agg["groups"].values())
    ac_cov = sum(g["acmap"]["covered"] for g in agg["groups"].values())
    manual_ac = [m for g in agg["groups"].values() for m in g["acmap"]["manual"]]
    uncovered_ac = sum(len(g["acmap"]["uncovered"]) for g in agg["groups"].values())
    endpoints = {(t.get("method"), t.get("path")) for t in tests if t.get("path")}
    duration = sum(float(t.get("duration") or 0) for t in tests)
    has_dur = any("duration" in t for t in tests)
    open_issues = [i for i in agg["issues"].values() if i.get("status", "open") == "open"]
    open_remarks = [r for r in agg["remarks"].values() if not r.get("resolved")]

    out: list[str] = []
    w = out.append
    last = runs[-1].get("recorded_at", "")[:16].replace("T", " ") if runs else "—"
    w('<header><h1>Дашборд сгенерированных API-тестов'
      f'<small>{len(agg["groups"])} групп · {len(runs)} прогонов · обновлено {e(last)} UTC</small></h1>'
      '<div class="tag">api-test-generation · собрано скриптом из runs.jsonl</div></header>')

    cov = f"{ac_cov / ac_total:.2f}" if ac_total else "—"
    w('<div class="gates">')
    w(f'<div class="gate"><div class="k">Тесты</div><div class="v">{len(tests)}</div>'
      f'<div class="s">{by_status["passed"]} passed · {by_status["failed"] + by_status["error"]} failed · '
      f'{by_status["external"]} внешних · {by_status["manual"]} ручных</div></div>')
    w(f'<div class="gate"><div class="k">Покрытие AC</div><div class="v">{ac_cov}/{ac_total}</div>'
      f'<div class="s">{cov}{" · ручные: " + e(", ".join(manual_ac)) if manual_ac else ""}'
      f'{" · не покрыто: " + str(uncovered_ac) if uncovered_ac else ""}</div></div>')
    w(f'<div class="gate"><div class="k">Длительность pytest</div><div class="v">'
      f'{_fmt_dur(duration) if has_dur else "—"}</div><div class="s">по JUnit, сумма последних прогонов</div></div>')
    w(f'<div class="gate"><div class="k">Открыто</div><div class="v">{len(open_issues)} / {len(open_remarks)}</div>'
      '<div class="s">расхождений стенда / замечаний к кейсам</div></div>')
    w('</div>')

    panes = [
        ("p-sum", "Сводка", _pane_summary(agg, len(tests), ac_total, ac_cov, manual_ac, uncovered_ac)),
        ("p-tests", f"Тесты ({len(tests)})", _pane_tests(tests)),
        ("p-ac", "Карта AC" + (f" ({uncovered_ac} без теста)" if uncovered_ac else ""), _pane_ac(agg["groups"])),
        ("p-remarks", f"Замечания к кейсам ({len(open_remarks)})", _pane_remarks(agg["remarks"])),
        ("p-stand", f"Расхождения стенда ({len(open_issues)})", _pane_stand(agg["issues"])),
        ("p-quality", "Качество генерации", _pane_quality(runs)),
        ("p-history", "Хронология", _pane_history(runs)),
        ("p-lessons", "Уроки", _pane_lessons(agg["lessons"])),
    ]
    w('<div class="tabs" id="tabs">')
    for i, (pid, title, _) in enumerate(panes):
        w(f'<div class="tab{" active" if i == 0 else ""}" data-pane="{pid}">{e(title)}</div>')
    w('</div>')
    for i, (pid, _, body) in enumerate(panes):
        w(f'<div class="pane{" active" if i == 0 else ""}" id="{pid}">{body}</div>')
    suites = sorted({t["suite"] for t in tests})
    w(f'<div class="foot"><div class="foot-col">Сьюты: {e(", ".join(suites)) or "—"} · '
      f'эндпоинтов: {len(endpoints)}</div><div class="foot-col">Источник: .gigacode/design/runs.jsonl · '
      'цифры считает скрипт, а не модель</div></div>')
    w("<script>(function(){document.querySelectorAll('.tab').forEach(function(t){t.addEventListener('click',"
      "function(){var id=t.getAttribute('data-pane');document.querySelectorAll('.tab').forEach(function(x)"
      "{x.classList.toggle('active',x===t)});document.querySelectorAll('.pane').forEach(function(p)"
      "{p.classList.toggle('active',p.id===id)})})})})();</script>")
    return "\n".join(out)


def _card(title: str, sub: str, body: str) -> str:
    s = f'<div class="sub">{e(sub)}</div>' if sub else ""
    return f'<div class="card"><h3>{e(title)}</h3>{s}{body}</div>'


def _table(head: list[str], rows: list[list[str]], num_cols: tuple = ()) -> str:
    if not rows:
        return '<div class="empty">Пока нет данных.</div>'
    th = "".join(f'<th{" class=num" if i in num_cols else ""}>{e(h)}</th>' for i, h in enumerate(head))
    trs = []
    for row in rows:
        if len(row) == 1:
            trs.append(f'<tr><td colspan="{len(head)}" class="grp">{row[0]}</td></tr>')
            continue
        tds = "".join(f'<td{" class=num" if i in num_cols else ""}>{c}</td>' for i, c in enumerate(row))
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="wrap-x"><table><tr>{th}</tr>{"".join(trs)}</table></div>'


def _pane_summary(agg: dict, n_tests: int, ac_total: int, ac_cov: int,
                  manual_ac: list[str], uncovered_ac: int) -> str:
    rows = []
    for name, grp in sorted(agg["groups"].items()):
        gt = [t for t in agg["tests"].values() if t["group"] == name]
        ok = sum(1 for t in gt if t["status"] == "passed")
        ext = sum(1 for t in gt if t["status"] == "external")
        bad = sum(1 for t in gt if t["status"] in ("failed", "error", "missing"))
        tot, cov = grp["acmap"]["total"], grp["acmap"]["covered"]
        rows.append([e(name), f'<span class="code">{e(", ".join(sorted(grp["suites"])))}</span>',
                     str(len(gt)), str(ok), str(bad), str(ext), f"{cov}/{tot}" if tot else "—",
                     e(grp.get("last", ""))])
    groups = _card("Группы", "Текущее состояние: по каждому тесту берётся последний прогон.",
                   _table(["Группа", "Сьют", "Тестов", "passed", "failed", "внешних", "AC", "Обновлено"],
                          rows, (2, 3, 4, 5)))
    rest = ac_total - ac_cov
    tail = []
    if manual_ac:
        tail.append(f"{len(manual_ac)} вынесено на ручную проверку")
    if uncovered_ac:
        tail.append(f"{uncovered_ac} пока без теста")
    explain = (
        f"<p>Тестов — <b>{n_tests}</b>, критериев приёмки (AC) — <b>{ac_total}</b>, из них проверяются "
        f"автотестами <b>{ac_cov}</b>{' (' + e(', '.join(tail)) + ')' if rest and tail else ''}.</p>"
        "<p>Это разные величины. <b>Тест</b> — сценарий: отправить запрос и убедиться, что ответ такой-то. "
        "<b>AC</b> — одно проверяемое правило из кейса или спецификации: «вернуть 404 на несуществующий id», "
        "«навык вызван». Один тест может закрывать несколько AC, а одно AC — проверяться несколькими тестами. "
        "Число тестов показывает объём работы, покрытие AC — насколько полно проверены требования. "
        "Какие именно AC без теста — во вкладке «Карта AC».</p>")
    return groups + _card("Тесты и критерии приёмки — не одно и то же", "", explain)


def _pane_ac(groups: dict) -> str:
    label = {"covered": ("pass", "покрыт"), "manual": ("manual", "ручная проверка"),
             "uncovered": ("fail", "без теста")}
    rows, numbers_only = [], []
    order = {"uncovered": 0, "manual": 1, "covered": 2}
    for name, grp in sorted(groups.items()):
        m = grp["acmap"]
        if not m["items"]:
            if m["total"]:
                numbers_only.append(f"{name}: {m['covered']}/{m['total']}")
            continue
        rows.append([e(f"{name} — {m['covered']}/{m['total']}")])
        for it in sorted(m["items"], key=lambda x: (order[x["status"]], x["id"])):
            cls, text = label[it["status"]]
            tests = "<br>".join(f'<span class="code">{e(t)}</span>' for t in it["tests"]) or "—"
            rows.append([e(it["id"]), e(it["description"]), tests, f'<span class="badge {cls}">{text}</span>'])
    sub = "Каждый критерий приёмки и тесты, которые его проверяют. Сверху — AC без теста: это дыры в покрытии."
    note = ""
    if numbers_only:
        note = ('<div class="muted" style="margin-top:10px">Без списка AC в записи (только числа): '
                + e("; ".join(numbers_only)) + "</div>")
    return _card("Карта покрытия AC", sub, _table(["AC", "Критерий", "Тесты", "Статус"], rows) + note)


def _pane_tests(tests: list[dict]) -> str:
    rows = []
    for g in sorted({t["group"] for t in tests}):
        rows.append([e(g)])
        for t in sorted((t for t in tests if t["group"] == g), key=lambda x: x.get("name", "")):
            ep = f'{e(t.get("method", ""))} <span class="code">{e(t.get("path", ""))}</span>' if t.get("path") else "—"
            note = e(t.get("note") or t.get("message") or "")
            dur = f'{t["duration"]:.1f} с' if "duration" in t else "—"
            rows.append([f'<span class="code">{e(t.get("name"))}</span>', e(t.get("case_key", "")), ep,
                         e(", ".join(t.get("ac") or [])), badge(t["status"]), dur,
                         f'<span class="muted">{note}</span>'])
    return _card("Тесты", "Статус — из JUnit последнего прогона; «внешнее» и «ручная» — классификация validator'а.",
                 _table(["Тест", "Кейс", "Эндпоинт", "AC", "Статус", "Время", "Примечание"], rows, (5,)))


def _pane_remarks(remarks: dict) -> str:
    rows = []
    for r in sorted(remarks.values(), key=lambda x: (bool(x.get("resolved")), x.get("case_key", ""))):
        st = '<span class="badge closed">исправлено</span>' if r.get("resolved") else '<span class="badge open">открыто</span>'
        rows.append([e(r.get("case_key")), e(r.get("kind", "")), e(r.get("remark")), st, e(r.get("first", ""))])
    return _card("Замечания к кейсам",
                 "Что стоит поправить в тест-кейсах: кейс неполный, пример противоречит ожидаемому результату, "
                 "не описан способ воспроизведения, проверка добавлена по решению оператора.",
                 _table(["Кейс", "Тип", "Замечание", "Статус", "Найдено"], rows))


def _pane_stand(issues: dict) -> str:
    rows = []
    for s in sorted(issues.values(), key=lambda x: (x.get("status", "open") != "open", x.get("group", ""), x.get("id", ""))):
        st = s.get("status", "open")
        bug = e(s.get("bug") or "—")
        rows.append([e(s.get("id")), e(s.get("group")), f'<span class="code">{e(s.get("endpoint", ""))}</span>',
                     e(s.get("expected", "")), e(s.get("actual", "")),
                     f'<span class="badge {st}">{"открыто" if st == "open" else "закрыто"}</span>',
                     bug, e(s.get("resolution", ""))])
    return _card("Расхождения стенда",
                 "Где стенд отвечает не по контракту или кейсу. Тесты при этом не ослаблены.",
                 _table(["ID", "Группа", "Эндпоинт", "Ожидалось", "Фактически", "Статус", "Баг", "Как закрыто"], rows))


def _pane_quality(runs: list[dict]) -> str:
    show_tokens = any(r.get("tokens") for r in runs)
    head = ["Дата", "Группа", "Кейсы", "С первого запуска", "Циклов fixer", "Итераций validator",
            "Перезапусков", "Вопросов оператору", "code_quality"]
    if show_tokens:
        head.append("Токены")
    rows, firsts = [], []
    for r in runs:
        p = r.get("pipeline") or {}
        q = r.get("quality") or {}
        first = p.get("first_run_passed")
        if first is not None:
            firsts.append(bool(first))
        row = [e(r.get("recorded_at", "")[:16].replace("T", " ")), e(r.get("group")),
               e(", ".join(r.get("case_keys") or [])),
               {True: "да", False: "нет", None: "—"}[first],
               e(p.get("fixer_cycles", "—")), e(p.get("validator_iterations", "—")),
               e(p.get("agent_reruns", "—")), e(p.get("operator_questions", "—")),
               e(q.get("code_quality", "—"))]
        if show_tokens:
            row.append(e(r.get("tokens") or "—"))
        rows.append(row)
    share = f"{sum(firsts)}/{len(firsts)}" if firsts else "—"
    sub = (f"Прогонов, где тест прошёл с первого запуска validator: {share}. "
           "Растёт число циклов fixer или вопросов — смотри, какое правило не срабатывает.")
    return _card("Качество генерации по прогонам", sub, _table(head, rows, tuple(range(3, len(head)))))


def _pane_history(runs: list[dict]) -> str:
    rows = []
    for r in reversed(runs):
        ts = r.get("tests") or []
        ok = sum(1 for t in ts if t.get("status") == "passed")
        ext = sum(1 for t in ts if t.get("status") == "external")
        bad = sum(1 for t in ts if t.get("status") in ("failed", "error", "missing"))
        res = f"{ok} passed · {bad} failed · {ext} внешних"
        dec = "; ".join(d.get("decision", "") if isinstance(d, dict) else str(d) for d in r.get("operator_decisions") or [])
        rows.append([e(r.get("recorded_at", "")[:16].replace("T", " ")), e(r.get("group")),
                     e(r.get("note", "")), res, e(dec)])
    return _card("Хронология", "Каждая строка — один прогон, новые сверху.",
                 _table(["Дата", "Группа", "Что сделано", "Результат", "Решения оператора"], rows))


def _pane_lessons(lessons: dict) -> str:
    rows = [[e(d), e(les)] for les, d in sorted(lessons.items(), key=lambda x: x[1], reverse=True)]
    return _card("Уроки", "Повторяющиеся уроки показаны один раз, с датой первого появления.",
                 _table(["Дата", "Урок"], rows))


def cmd_build(args: argparse.Namespace) -> None:
    tpl_path = Path(args.template)
    try:
        tpl = tpl_path.read_text(encoding="utf-8")
    except OSError as err:
        _fail(f"не читается шаблон {tpl_path}: {err}")
    if MARKER not in tpl:
        _fail(f"в шаблоне {tpl_path} нет маркера {MARKER}")
    runs = load_runs(Path(args.runs))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl.replace(MARKER, render(runs)), encoding="utf-8")
    print(f"report_tool: дашборд {out} — прогонов {len(runs)}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="report_tool", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append", help="дописать запись прогона в runs.jsonl")
    a.add_argument("record", help="JSON-файл записи прогона")
    a.add_argument("--junit", help="JUnit XML от pytest (--junitxml)")
    a.add_argument("--runs", default=str(DEFAULT_RUNS))
    a.set_defaults(func=cmd_append)
    b = sub.add_parser("build", help="собрать дашборд из runs.jsonl")
    b.add_argument("--runs", default=str(DEFAULT_RUNS))
    b.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    b.add_argument("--out", default=str(DEFAULT_OUT))
    b.set_defaults(func=cmd_build)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
