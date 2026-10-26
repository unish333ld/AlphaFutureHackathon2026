# QA продуктового процесса, PDF, подписи и выдачи

Актуальный результат повторной проверки перед жюри — [независимая итоговая проверка](#независимая-итоговая-проверка-26102026) в конце документа. Первый раздел ниже сохранён как история реализации PDF; он не является доказательством повторной проверки.

Дата: 26.10.2026. Исходное рабочее дерево было незакоммиченным: предыдущие продуктовые изменения сохранены; неизвестный `.coverage 2` не изменялся. Commit/push не выполнялись. Разрушительные проверки и кредитные тестовые операции — отдельный `alfa-pdf-qa` / PostgreSQL volume, не основная БД.

## Исходное состояние и изменения

До задачи были принятый Offer, неизменяемый terms_snapshot/document_hash, условная подпись через hash-only sign, транзакционная выдача с назначением/Idempotency-Key. PDF, кодовой попытки, неизменяемых PDF-байтов, отдельной копии и анимации результата не было. Идемпотентность выдачи не заменялась новым механизмом.

Текущие файлы: `agreements/models.py`, `documents.py`, `pdf_worker.py`, `demo_codes.py`, Django-шаблоны; `api/agreement_documents.py`, serializers/схема; frontend `AgreementDocuments`, `AgreementSigning`, `CompletionFeedback`, общий Dialog; `test_pdf_signing.py`, `pdf-signing.spec.ts`. Архитектура/контракты/хранение — [agreements.md](agreements.md).

## Дефекты и регрессии

| ID / серьёзность | Воспроизведение и ожидание → фактическое поведение | Причина → исправление → проверка |
|---|---|---|
| D01 / high, функциональный пробел | Принять предложение, попытаться скачать договор: нужен динамический зафиксированный PDF; раньше существовал только JSON | Не было артефакта/генератора → HTML/CSS/WeasyPrint, private DB bytes, отдельный SHA-256 → реальные PDF, повтор байт-в-байт, роли/чужая компания, гонка генерации |
| D02 / high, усиление протокола | Старый sign с хешем и checkbox сразу подписывал; новая задача требует конкретный PDF и кодовую попытку | Прежний упрощённый sign → тот же endpoint требует document/attempt/code/оба хеша; без них 400 → неверный/истёкший/чужой/повторный код, stale_version, две вкладки |
| D03 / medium | Открыть PDF с графиком 60 месяцев: итог должен быть один; первый рендер повторял «Итого» на каждой странице | Печатный tfoot автоматически повторялся → table-row-group для итога, thead остаётся повторяемым → text.count("Итого")==1 и просмотр всех страниц |
| D04 / medium | Переход просмотр → код → успех: фокус должен оставаться в новом диалоге; возврат из закрывающегося окна мог вмешиваться и останавливать автозакрытие | Несогласованные FocusLock/ручной restore → общий Dialog не возвращает фокус за активное окно, info получает autofocus; переходы/клавиатура/автозакрытие проверяются браузером |
| D05 / medium | Заполнить 3 поля: это не значит «проверено»; прежний checklist сообщал только наличие | Не было отдельной стадии проверки → verification_state/checked_at, missing/invalid отличаются от ready; привязка к текущей revision/attempt → отдельная проверка draft/checked/outdated и существующие уточнения |
| D06 / medium, accessibility | Открыть «Просмотр договора» на 360 px: декоративная иконка закрытия должна быть скрыта от скринридера; Axe находил svg-img-alt у Core closer | Иконка библиотечного Header имела самостоятельный role=img без имени → именованная кнопка Core сохранена, её декоративный символ скрыт aria-hidden; Header также не показывает closer во время запроса → мобильный сценарий с Axe в трёх движках |
| D07 / medium | Сформировать PDF через «Подписать», затем отменить просмотр: карточка должна сохранить ссылку; она могла писать «PDF ещё не сформирован» | Генерация обновляла только локальный state диалога → после генерации перечитывается карточка, не кредитное действие → мобильный тест после отмены проверяет рабочую ссылку и неизменный accepted |
| D08 / medium, измерение тестов | Запустить обычный pytest-cov после выделения PDF-worker: код реально исполняется, но отчёт не учитывал отдельный Python-процесс; порог 95% не проходил (93,32%), хотя 550 тестов прошли | pytest-cov 7 требует явной настройки subprocess → включён штатный coverage patch, без снижения порога/новых исключений; тестовые зависимости устанавливаются в отдельный временный venv, чтобы startup hook работал и у worker → повтор полного замера ниже |

Промежуточные ошибки тестового стенда отдельно: фикстура передавала ORM-объект вместо UUID; тест сравнивал UUID со строкой; замороженные часы блокировали batched notifications/exit transition/скриншот; recovery-кнопка имела не тот же заголовок, что диалог. Два новых теста сначала использовали response вместо response.json() и number вместо revision_no; исправлены именно предусловия, не сервер. Тайм-ауты не увеличены ради прохождения, автоматические повторы Playwright — 0.

Отдельно WebKit r2370 сообщал access-control pageerror при повторной замене документа, пока список запускал detail-запросы. Событий window.error/unhandledrejection при диагностике не было. Это соответствует [известной классификации отмены запросов в WebKit](https://github.com/microsoft/playwright/issues/43120), а не доказанной ошибке CORS приложения. Тест уходит со страницы до кода полной навигацией, а возвращается штатной SPA-ссылкой. pageerror не подавляются; повторная hard-навигация с незавершённой загрузкой списка в WebKit остаётся ограничением среды. В ветке подписи дополнительно обработано отклонение follow-up чтения при уходе со страницы, без повторного POST.

## Независимые деньги и происхождение

Оракул `independent_schedule` не вызывает продуктовый расчётчик: аннуитет считается через сумму дисконтированных периодов при Decimal precision=50, затем независимо моделируется остаток/проценты/последний платёж. Сравнивается **каждая строка** с рабочим сервером: 4 суммы (включая копейки и 30 млн), ставки 0/27/100%, сроки 12/24/60 — 36 комбинаций.

Контроль 1100000 ₽, 27%, 24: 59818,25 ₽ регулярно; последний 59818,30 ₽; проценты 335638,05 ₽; возврат 1435638,05 ₽. Основной долг сходится, последний остаток ноль. Проверены цена каталога → калькулятор → рассмотренная revision → Offer → паспорт → снимок → PDF/график; изменение живого продукта на 99%/другое имя не меняет PDF. Неизвестная стоимость не становится нулём. Итоговые условия через payload клиента не назначаются.

Встречное предложение берётся из decision.assessment.revision и фактического Offer, не случайной последней версии. Существующие серверные политика/low-medium-high/причины сохранены; данные не объявляются внутренней моделью банка. 23,5% «от» остаётся публичным ориентиром, 27% — учебной ставкой. Прогноз денег и юридическая ПСК не реализованы.

## Выполненные команды и состояние проверки

- PostgreSQL/Linux arm64, финальный полный замер: **562 passed**, **95,63% строк+ветвей**, 100,42 с, exit 0; порог 95% сохранён. 340 DeprecationWarning drf-spectacular/Python 3.14 не скрывались. До дополнительных защитных тестов также пройден полный набор 550 тестов. Проверены реальные рендеры, session/CSRF, изоляция компаний и гонки с независимыми соединениями; SQLite для гонок не использовался.
- Дополнительные регрессии: HTTP-отмена/повторное открытие/запрет отмены USED, signed-copy endpoint и соответствие его ответа OpenAPI, неверные PDF query-параметры, старая ревизия, сроки/состояние/оба хеша, несовпадение с Offer, отсутствие реквизитов/неполная цена и лимиты входа. Отрицательные проверки подтверждают, что рендерер вообще не запускается при непригодном источнике.
- PDF-worker теперь учитывается настоящим coverage subprocess hook; список исключённых файлов не расширялся, пути прежних manage.py/wsgi.py сделаны независимыми от cwd дочернего процесса. Промежуточный замер после включения hook был 94,41%, до добавления недостающих проверок. Основание настройки — [официальная документация pytest-cov](https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html). JSON финального замера: `.deps/pdf-qa-coverage.json`, не tracked-артефакт. Непокрытые ветви остаются; процент не означает отсутствие ошибок.
- `ruff check backend scripts`, `ruff format --check`, `makemigrations --check --dry-run` выполнены; модели соответствуют миграциям.
- `spectacular --file docs/openapi.yaml --validate --fail-on-warn` выполнен; сгенерированный временный YAML сравнен с опубликованным через cmp. `npm run api:generate` обновляет TS-контракт.
- `npm run typecheck`, `npm run test`, `npm run build`: успешно, **31 Vitest passed**. Production build также выполнен Dockerfile frontend; предупреждение о chunk >500 kB сохраняется.
- Чистый `alfa-pdf-qa`: миграции/seeds, backend 18003 / frontend 18081, health через Nginx. Pango/HarfBuzz/DejaVu и WeasyPrint работают в non-root backend. Backend `AI_ENABLED=false`, SMS-провайдера нет.
- Четыре PDF в [samples](samples/), 15 страниц суммарно; все страницы отрендерены PDFium и просмотрены, не только извлечён текст. Проверены кириллица/встраивание шрифта, A4, длинная компания, 12/24/60 месяцев, повтор thead, единственный итог, сохранение оригинала и отдельная отметка. Предоставленных PDF-референсов в текущем сообщении не было.

| Финальный браузерный набор | Результат |
|---|---|
| Chromium/macOS: workflow, safety, product-research, pdf-signing | **17 passed**, 43,8 с |
| WebKit/macOS: все 4 PDF-сценария, 2 продуктовых, UI happy path | **7 passed**, 34,7 с |
| Firefox/Linux, официальный Playwright Docker image 1.64.1 | **7 passed**, 37,3 с |

Проверено: создание/уточнение/решение/встречные условия/отказ, назначение/фильтры/права, 409 с сохранением формы, потеря ответа/осознанный повтор выдачи с прежним ключом, новая подпись с отменой/повторным открытием/двойным кликом/уходом/перемонтированием/потерей ответа/503, отсутствие signed и issued при ошибке, отсутствие выдачи непосредственно после подписи. Модальные результаты различаются, автозакрытие/приостановка фокусом и отсутствие повторной анимации проверены. Ширины 360/768/1280/1440, клавиатура/Axe, отключение ИИ, реальное скачивание PDF; дополнительно 360 px/reduced-motion с искусственно недоступным **только встроенным viewer** и рабочим авторизованным скачиванием. Fault injection применяется лишь в тестах ошибок, итоговое приложение использует настоящий API. Кодовые сценарии — trace=off, коды в network trace не сохраняются.

Основное демо обновлено командой `docker compose -p alfa-credit-demo up --build -d --wait --wait-timeout 180`: frontend 8080 / backend 18000, все контейнеры healthy. `agreements.0002` применена. До обновления сделан приватный backup `.deps/backups/alfa-credit-before-pdf-20261026.dump`; после обновления UUID/document_hash всех **трёх** прежних договоров напрямую сравнены с записями pg_restore из архива — совпадают. Канонический хеш каждого текущего terms_snapshot также совпадает с сохранённым. Проверены health/БД, Swagger/OpenAPI 1.3.0, CSRF login/HttpOnly cookie/me/products/logout через Nginx без создания кредитных записей в основной БД. Настройки существующего ИИ не менялись.

### Воспроизведение команд

Из корня, с заполненным локальным `.env`; QA project использует собственный volume:

```sh
WEB_PORT=18003 FRONTEND_PORT=18081 AI_ENABLED=false VITE_AI_ASSISTANT_ENABLED=true \
  docker compose -p alfa-pdf-qa up --build -d --wait --wait-timeout 180
docker compose -p alfa-pdf-qa run --rm --no-deps -e AI_ENABLED=false \
  -v "$PWD:/work" -w /work web sh -c \
  'python -m pip install --quiet --target /tmp/qa-deps -r backend/requirements-test.lock && PYTHONPATH=/tmp/qa-deps python -m pytest'
# Отдельный полный замер, включая реальный subprocess PDF. Данные — в /tmp.
docker compose -p alfa-pdf-qa run --rm --no-deps -e AI_ENABLED=false \
  -v "$PWD:/work" -w /work web sh -c \
  'python -m venv --system-site-packages /tmp/qa-venv && /tmp/qa-venv/bin/pip install --quiet -r backend/requirements-test.lock && COVERAGE_FILE=/tmp/pdf-qa.coverage /tmp/qa-venv/bin/python -m pytest --cov --cov-report=term-missing --cov-report=json:.deps/pdf-qa-coverage.json -o addopts=""'
docker compose -p alfa-pdf-qa exec -T web python manage.py makemigrations --check --dry-run
docker compose -p alfa-pdf-qa exec -T web python manage.py spectacular \
  --file /tmp/pdf-final-openapi.yaml --validate --fail-on-warn
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
git diff --check
cd frontend
npm run typecheck && npm run test && npm run build
E2E_BASE_URL=http://127.0.0.1:18081 npx playwright test \
  tests/e2e/pdf-signing.spec.ts tests/e2e/workflow.spec.ts \
  tests/e2e/product-research.spec.ts tests/e2e/safety.spec.ts \
  --project=chromium --trace=off
E2E_BASE_URL=http://127.0.0.1:18081 npx playwright test \
  tests/e2e/pdf-signing.spec.ts tests/e2e/workflow.spec.ts tests/e2e/product-research.spec.ts \
  --project=webkit --grep '@pdf|@product-research|real UI: create' --trace=off
```

Firefox запускался последовательно после других браузеров в `mcr.microsoft.com/playwright:v1.64.1-noble`, с Linux node_modules, сетью контейнера QA frontend, `E2E_BASE_URL=http://127.0.0.1` и тем же последним набором/grep, `--project=firefox`. Перед E2E отдельному синтетическому `e2e-specialist` в QA назначены staff-права и локальный DEMO_PASSWORD; основная БД не изменяется ради фикстур. После завершения QA-контейнеры остановлены без `-v`; volume и образцы сохранены.

Repowise: индекс рабочего дерева обновлён без LLM/агентов; просмотрены change-risk и per-file impact. Общая оценка review_required/health_delta=partial **не объявляется чистым аудитом**. Проверены shared Dialog/agreements services/API и их потребители, старый Admin не раздаёт новые PDF. Сигналы сложности в существующих ApplicationForm/ApplicationActions и новом sign остаются задачами сопровождения, а не доказанными runtime-дефектами. Per-test coverage map не загружалась: рекомендации тестов от графа были inferred; выполнен полный набор, не только рекомендованные файлы.

## Ограничения и показ жюри

Это не юридически готовый банковский договор: нет реального кредитора/счёта/полномочий/ЭП/перевода. Шаблон v1 — RUB, месячный аннуитет, без услуг/комиссий/залоговой модели; календарные даты не выдумываются. Нет перевыпуска документа того же Agreement на другого подписанта; новые условия — новый допустимый Offer/Agreement. У старых подписей без кодовой попытки нет фальшивой отметки задним числом. БД/backup требуют защиты оператора; append-only на уровне приложения не равен WORM против DBA.

Реальные Safari/iOS и Chrome/Android, production-нагрузка/pen-test, юридическая экспертиза и пользовательское исследование не выполнялись. WebKit не равен реальному iPhone. Неизвестные реквизиты не заполняются автоматически. Прогноз денежных потоков/стресс-сценарий — следующий отдельный этап. Основное демо не зависит от ИИ, оплаты, телефона или SMS.

В проверенном демонстрационном пути просмотр → код → signed → выдача назначенным специалистом блокирующих проблем для показа не обнаружено. Это не утверждение об отсутствии всех возможных багов. PDF-референсы пользователя, реальные телефоны/банковские интеграции и реальные мобильные устройства не проверены.

## Независимая итоговая проверка 26.10.2026

Предыдущие результаты выше не использовались как доказательство. Повторно исследованы код, модели, сервисы, тесты, действующий API, AGENTS.md, актуальные alfa-build/guardrails/frontend/product-research, Django/Playwright-инструкции и риски Repowise. Фактический контракт: **OpenAPI 1.3.0, 41 путь**; сохранённый в frontend-навыке 1.1 — исторический снимок. В этой проверке endpoints, схема и миграции не изменялись.

### Среда и сохранность

macOS host; Docker Linux arm64, Python 3.14.9, Django 5.2.18, DRF 3.18.3, PostgreSQL 18.6, WeasyPrint 70.0. Chromium/WebKit — Playwright на macOS; Firefox и отдельный Chromium для настоящего clipboard — официальный `mcr.microsoft.com/playwright:v1.64.1-noble`. Версии из реально запущенных процессов, не только lock-файлов.

Стенд **alfa-jury-qa-20261026**, frontend 18082 / API 18004, новый volume `alfa-jury-qa-20261026_postgres_data`. Он отсутствовал до старта. Основные сценарии выполнялись при `AI_ENABLED=false VITE_AI_ASSISTANT_ENABLED=false`: без LLM, SMS, оплаты и реального телефона. Второй специалист `e2e-specialist` создан только в этой БД. Pytest использовал отдельную тестовую БД PostgreSQL; SQLite для гонок не применялся. Существующие рабочие БД не использовались для кредитных тестовых операций. Другие проекты Docker не останавливались.

До изменений сохранён архив исходного dirty worktree `.deps/jury-qa-20261026.qrbd7e/worktree-before.tgz` (600, без игнорируемых `.env`/cookies/skills). Сравнение с ним отделяет эти точечные исправления от ранее незакоммиченной работы. Неизвестный `.coverage 2` сохранён: SHA-256 до/после `307f6fec530085024cbe240782ccab1b7887bf0b6d7cc639dfc80314027f8538`. Commit/push не выполнялись.

### Найденные дефекты и исправления

| ID / серьёзность | Воспроизведение; ожидалось → фактически | Причина → исправление → регрессия |
|---|---|---|
| J01 / medium | Дважды активировать «Подтвердить» выдачи в одном цикле событий. Ожидался один POST → отправлялись два, хотя идемпотентность сохраняла одну запись | React loading/isPending обновлялся после обоих обработчиков → синхронный ref-guard в ApplicationActions, общий для мутаций → jury-verification, approved/counteroffer: удержанный настоящий POST, одна отправка, одна выдача и событие; Chromium/Firefox/WebKit |
| J02 / medium | Реальный sign успешно сохранён, последующие GET карточки возвращают 503; закрыть подтверждение. Ожидалось устойчивое известное состояние → снова показывалось «Подписать договор» | Успех жил в кратком модальном окне, кеш карточки оставался accepted → отдельное подтверждённое сервером состояние, постоянная подсказка, скрытие повторной кнопки без выдумывания lock_version → настоящий sign + инъекция отказа только последующих GET; восстановление чтения, один sign во всех трёх движках |
| J03 / low | Открыть карточку специалиста после issued/expired. Ожидалось отсутствие предложения назначить исполнителя → текст «Свободную заявку может взять в работу специалист» | Отсутствие исполнителя ошибочно трактовалось как доступность claim → подсказка зависит от серверного available_actions → оба UI-пути выдачи в трёх движках, обе реальные expiry-проверки |
| J04 / medium | После ошибки signed-document дважды активировать восстановление копии. Ожидался один запрос → два POST и лишний рендеринг | busy имел ту же отложенную React-семантику → синхронный ref-guard AgreementDocuments с освобождением в finally → усиленный copy-failure тест сначала воспроизвёл 2 вместо 1, затем прошёл Chromium/Firefox/WebKit; исходные байты/аудит неизменны, sign не повторяется |
| J05 / medium, документация | Выполнить шаг 5 README. Ожидался работающий протокол 1.3 → инструкция предлагала hash-only sign, который сервер правильно отклоняет 400 | Необновлённый краткий пример → README описывает generate-document → просмотр → signature-attempt → sign со всеми обязательными полями и ссылкой на demo.http → сопоставлено с актуальной схемой, HTTP-тестом и рабочим UI |

Дополнительно закрыт устаревший общий путь TS-клиента: `api.action(sign_agreement)` теперь отклоняется **до fetch**, убраны необязательные hash-only поля. Рабочий UI использует только `api.sign` с обязательным типом SignRequest. Новая Vitest-регрессия проверяет отсутствие отправки; серверный тест подтверждает 400 старого payload без изменения состояния. Это не был обход серверной авторизации.

Улучшены проверки, а не ослаблены assertions:

- В старом reload-тесте отсутствие кнопки могло проверяться ещё на loading-экране, затем закрытие контекста обрывало фоновую PDF-копию и давало WebKit fetch error. Добавлено ожидание именно загруженной карточки и сохранённого signed-статуса. Усиленный сценарий прошёл во всех движках; ошибки JavaScript не фильтровались ради зелёного результата.
- Responsive-тест раньше всегда требовал кнопку ИИ. Теперь явный `E2E_ASSISTANT_ENABLED=false` проверяет отсутствие кнопки **и панели**; ветка включённого помощника сохранена.
- Миграционная регрессия каталога дополнена настоящим PDF: двойное применение data migration не меняет сохранённые байты/хеш/идентификатор артефакта, старую ставку 18% в Offer и снимке, несмотря на новый каталог 27%.

Repowise отметил большую сложность ApplicationActions/ApplicationContent/ApplicationForm и отсутствие per-test coverage map: его рекомендации были **inferred**, не доказательством покрытия. Проверены затронутые auth/query/document потребители; изменения ограничены guards/подсказками/контрактом, без рискованного рефакторинга этих крупных компонентов перед показом. Исторические co-change связи с .gitignore/AGENTS не послужили поводом менять их без необходимости.

### Фактически выполненные проверки

Backend: **572 passed**, 340 DeprecationWarning от drf-spectacular/Python 3.14, покрытие 95,63% при неизменном пороге 95%. Отдельный предварительный прогон новых HTTP/арифметических проверок и свежих PDF-образцов — 14 passed. Новый `test_jury_verification.py` добавил 6 HTTP/конкурентных cases и 4 независимых рациональных расчёта. Fixtures могут готовить исходное состояние сервисом, но сами конкурирующие изменения идут настоящим HTTP с cookie/CSRF, отдельными сессиями и barrier, не force_authenticate.

Проверены гонки: два claim разных специалистов; два sign одной попытки; две выдачи одного/разных ключей; принятие против чтения с истёкшим Offer. Проверены одиночные аудит/история/выдача, запрет действий проигравшего назначения и обхода через retry-checks, клиент/неназначенный специалист, чужая компания/договор/PDF/попытка, can_sign, CSRF/ротация/logout, stale lock после изменения назначения. «Потеря ответа» выдачи моделировалась отбрасыванием успешного результата и последующим чтением/осознанным повтором того же ключа; браузер отдельно обрывал ответ после реальной серверной записи. Физический TCP-разрыв после COMMIT отдельным сетевым прокси не воспроизводился.

Независимый новый oracle использует точные Fraction и целые копейки, а не проверяемый Decimal-калькулятор. Проверены 1 100 000/27%/24, 300 000,37/27%/12, 30 000 000/27%/60 и 300 000,01/0%/60 по **каждой строке**. Контроль: 59 818,25 / последний 59 818,30 / проценты 335 638,05 / возврат 1 435 638,05 ₽. Основной долг сходится, последний остаток ноль. Существующий независимый Decimal-oracle и проверки API/Offer/стоимости/договора/PDF также реально выполнены в полном наборе. Неизвестные/неподдерживаемые комиссии не превращаются в ноль: стоимость помечается неполной. В поддерживаемом продукте комиссии/услуги подтверждённо исключены; смешения публичной «от» и учебной ставки не обнаружено.

Frontend: **32 Vitest passed**, typecheck, production build, Prettier — успешно. `openapi-typescript` заново сгенерирован во временный файл, отформатирован и побайтово совпал с `src/shared/api/schema.d.ts`. `spectacular --validate --fail-on-warn` прошёл; YAML генератора совпал с `docs/openapi.yaml`. Backend `check`, `makemigrations --check --dry-run`, Ruff lint/format, `git diff --check` — успешно. Новых миграций нет; agreements.0002 реально применена и проверена.

Одна составная проверочная shell-команда после успешных 572 тестов завершилась 127: `/tmp/jury-venv/bin/ruff` не имел console entrypoint. Это не объявлялось зелёным общим пайплайном: Ruff отдельно реально выполнен из `.venv/bin/ruff`, а Django/schema-проверки — отдельной успешной командой.

### Самостоятельные сценарии и браузерные запуски

Не суммируем повторные попытки как новые сценарии. **34 самостоятельных E2E-сценария**, **70 успешных сочетаний «сценарий × движок»** в завершённых проверках; это не число всех исторических попыток запуска.

| Набор | Уникальных cases | Chromium | Firefox | WebKit |
|---|---:|---:|---:|---:|
| workflow (8), pdf-signing (4), product-research (2), jury-verification (4) | 18 | 18 | 18 | 18 |
| queue (1), resilience (3), safety (3), session-race (1) | 8 | 8 | — | — |
| auth-inputs, включая настоящий clipboard и password-manager ввод | 6 | 6 Linux | — | — |
| Реальные сроки предложения и подписи, host Docker opt-in | 2 | 2 | — | — |
| Итого | **34** | **34** | **18** | **18** |

Одинаковый критический путь всех трёх движков включает настоящее UI-принятие, скачивание PDF с проверкой SHA-256, явное ознакомление, код, удержание запроса до серверного подтверждения, ожидание без выдачи, выдачу через **UI назначенного специалиста**, сумму/операцию/историю и reload без повтора анимации. Approved и counteroffer отдельно. Подготовка части вариантов выполнялась API, не выдавалась за UI-создание; отдельный workflow действительно создаёт форму, проходит claim → уточнение → новую revision → решение через интерфейс. Отказ/техническая ошибка/недостаток данных также проверены и не подменяют друг друга. Здоровые новые UI-пути собирают console.error и требуют пустого списка; pageerror не игнорируется. Намеренно внесённые сетевые/HTTP-сбои отмечены как fault injection, не как отсутствие ошибок консоли.

Фактические responsive ширины 360/600/768/1024/1280/1440 CSS px; проверены отсутствие общего overflow, фокус/клавиатура/Escape, Axe, fallback без PDF-viewer, выключенный ИИ, reduced-motion. Новая expiry-регрессия переводит серверный deadline только у свежего синтетического Offer в изолированной БД, а не подменяет ответ API или локальный таймер статуса.

Прозрачность неудачных запусков: первый Chromium-прогон получил 17 pass/1 fail — штатный user throttle 300/min исчерпан серией общего аккаунта, logout получил 429; самостоятельный повтор auth дал pass. Первый Firefox запущен раньше готовности перезапущенного QA web: Nginx зафиксировал 502 CSRF, 9 fixture failures; после health-preflight те же cases прошли. Один WebKit-тест выявил описанное преждевременное завершение reload-проверки, после усиления прошёл. Ошибки двойной выдачи/PDF и stale UI сначала воспроизведены красными тестами, исправленные регрессии пройдены. В промежуточном QA restart команда без переопределений попыталась занять основной порт 18000 и была отклонена Docker; восстановлена корректная QA-конфигурация 18004/18082, основной контейнер не останавливался. Ни throttle, ни assertions, ни тайм-ауты ради зелёного результата не ослаблялись.

### Docker, миграции и PDF

Сборка и старт Compose на новом пустом volume прошли с миграциями/синтетическими данными. Дополнительно **build --no-cache web** и **build --no-cache frontend** успешно заново установили apt/pip/npm зависимости, не только использовали готовые слои. Отдельная копия `.deps/backups/alfa-credit-before-pdf-20261026.dump` восстановлена в `jury_upgrade` нового QA-кластера; до migrate agreements.0002 отсутствовала, после — применена OK. Сохранены 3 договора, digest `(id, document_hash, terms_snapshot)` до/после одинаков: `37abba4282acdd5a125f80c22110473a03fc4783c4bb55b97db78489c603c0f5`. Это старая БД **до PDF**, не выдуманная проверка уже существовавших в ней PDF-байтов.

При реальной остановке **только QA PostgreSQL** авторизованный PDF-запрос вернул `503 dependency_unavailable`; после start — 200 и те же байты/SHA-256. Анонимный PDF — 403; публичный media-путь не отдаёт PDF (Nginx может вернуть HTML SPA, это не приватный документ). Swagger/ReDoc/schema доступны; их JS действительно получены из локального /static, а не CDN. Локальные шрифты/библиотеки реально участвовали в генерации.

Свежие договоры `.deps/jury-qa-20261026.qrbd7e/contracts/`: 1 100 000/24 исходник (3 страницы) и подписанная копия (4); 300 000,37/12 (3); 30 000 000/60 (5). Все **15 страниц** отрендерены PDFium в PNG и визуально просмотрены через 4 контактных листа. Проверены длинное кириллическое название, A4, поля, разделы, встроенные шрифты, повторяемый table header, один итог, отсутствие наложений/обрезаний/пустых лишних страниц. У 60-месячного графика последняя страница содержит последний платёж и итог, а не пустой лист. Старые `docs/samples` не перезаписывались. Оформление не доказывает юридическую готовность.

### Команды и артефакты повторения

Ниже фактически использованные команды; `$PWD` заменяет локальный абсолютный путь репозитория. Все операции run/exec относятся к **QA**, не основной среде.

```sh
AI_ENABLED=false VITE_AI_ASSISTANT_ENABLED=false WEB_PORT=18004 FRONTEND_PORT=18082 \
  docker compose -p alfa-jury-qa-20261026 up --build -d --wait --wait-timeout 180
AI_ENABLED=false VITE_AI_ASSISTANT_ENABLED=false WEB_PORT=18004 FRONTEND_PORT=18082 \
  docker compose -p alfa-jury-qa-20261026 build --no-cache web
AI_ENABLED=false VITE_AI_ASSISTANT_ENABLED=false WEB_PORT=18004 FRONTEND_PORT=18082 \
  docker compose -p alfa-jury-qa-20261026 build --no-cache frontend

docker compose -p alfa-jury-qa-20261026 run --rm --no-deps -e AI_ENABLED=false \
  -v "$PWD:/work" -w /work web sh -c \
  'python -m venv --system-site-packages /tmp/jury-venv && /tmp/jury-venv/bin/pip install --quiet -r backend/requirements-test.lock && COVERAGE_FILE=/tmp/jury.coverage /tmp/jury-venv/bin/python -m pytest --cov --cov-report=term -o addopts=""'
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
docker compose -p alfa-jury-qa-20261026 run --rm --no-deps -e AI_ENABLED=false \
  -v "$PWD:/work" -w /work web sh -c \
  'python backend/manage.py check && python backend/manage.py makemigrations --check --dry-run && python backend/manage.py spectacular --validate --fail-on-warn --file /tmp/jury-openapi.yaml && cmp /tmp/jury-openapi.yaml docs/openapi.yaml'
```

В `frontend/` выполнены `npm run typecheck`, `npm run test`, `npm run build`, `npm run format:check`, `npx openapi-typescript ../docs/openapi.yaml -o /tmp/alfa-jury-schema.d.ts`, Prettier временного файла и `cmp`. Основной браузерный набор:

```sh
E2E_BASE_URL=http://127.0.0.1:18082 E2E_ASSISTANT_ENABLED=false \
  PLAYWRIGHT_HTML_OUTPUT_DIR=playwright-report-jury-chromium \
  npx playwright test tests/e2e/jury-verification.spec.ts tests/e2e/pdf-signing.spec.ts \
  tests/e2e/workflow.spec.ts tests/e2e/product-research.spec.ts \
  --project=chromium --output=test-results-jury-chromium --trace=off
```

WebKit — та же команда с `--project=webkit`, собственными report/output. Firefox — тот же набор в официальном Linux-образе с `--network container:alfa-jury-qa-20261026-frontend-1`, `E2E_BASE_URL=http://127.0.0.1`, read-only mount корневого `.env`, отдельным Linux node_modules volume `alfa-ai-review-pw-node-modules`, report/output `*-jury-firefox`. Затем адресно повторены упавшие/усиленные/затронутые cases; финальные `*-jury-*-final` и `*-jury-copy-*-fixed` сохраняют результаты. Дополнительные 9 safety/resilience/queue/session/auth cases — `playwright-report-jury-safety`, 6 Linux auth-inputs — `playwright-report-jury-auth-linux`. Для expiry нужны параметры из [frontend.md](frontend.md).

PDF-образцы получены запуском `test_dynamic_pdf_samples_use_offer_not_live_catalogue` с `PDF_SAMPLE_DIR=/work/.deps/jury-qa-20261026.qrbd7e/contracts`; затем:

```sh
.venv/bin/python scripts/render_contract_samples.py \
  --input .deps/jury-qa-20261026.qrbd7e/contracts \
  --output .deps/jury-qa-20261026.qrbd7e/pdf-renders
```

Reports, cookies, dumps и вспомогательные рендеры игнорируются Git; trace отключён в кодовых/парольных сценариях. Коды не пишутся в аудит; в event.details только идентификаторы версии/подтверждения. Полные request body, cookies и demo_code в отчёт не включены.

### Изменённые файлы этого QA-прохода

Production UI: `frontend/src/features/ApplicationActions.tsx`, `AgreementSigning.tsx`, `AgreementDocuments.tsx`, `frontend/src/pages/ApplicationPage.tsx`, `frontend/src/shared/api/client.ts`. Tests: `contracts.test.ts`, новые `tests/e2e/jury-verification.spec.ts`, `jury-expiry.spec.ts`, усиленные `pdf-signing.spec.ts`/`workflow.spec.ts`, новый `backend/tests/test_jury_verification.py`, усиленный `test_product_research.py`. Документация: README, `docs/frontend.md`, `docs/verification.md`, этот отчёт. Остальные dirty-файлы существовали до проверки и сохранены.

### Остаточные ограничения и репетиция

Блокирующих дефектов **проверенного основного пути** после исправлений не обнаружено; это не обещание отсутствия всех ошибок и не production/юридическая аттестация. Сохраняются ограничения симуляции, месячных периодов/нулевых услуг, одного подписанта первой PDF-версии и отсутствия административного переназначения деактивированного специалиста.

Не выполнены реальные Safari/iOS/Chrome Android, проверка на Windows/amd64 Docker, нагрузка/pen-test/внешний аудит зависимостей, live LLM/OpenRouter и реальный SMS/перевод (они не нужны основному пути). Источники публичных ставок заново не исследовались: проверялась согласованность сохранённого учебного каталога и неизменяемых документов, не актуальная банковская оферта. Остались неблокирующие build warnings: общий chunk ~563 kB, старый peer-range react-virtual внутри Core Components select, deprecation транзитивных библиотек; проверенные формы/Select/клавиатура работают в трёх движках. Крупные UI-компоненты — технический долг, не повод для большого рефакторинга перед жюри. Прогноз денежных потоков/стресс-сценарий остаётся следующим отдельным этапом.

Репетиция: открыть два независимых browser-профиля/обычное и приватное окно на одном origin. `client`: создать заявку с полными синтетическими показателями и отправить. `specialist`: найти её номер, взять в работу, запустить серверное решение. `client`: обновить карточку, сравнить условия, принять, открыть/скачать PDF, отметить ознакомление, начать демо-подпись, дождаться серверного результата **signed**. `specialist`: обновить, выполнить моделируемую выдачу с подтверждением. `client`: обновить/дождаться polling, проверить **issued**, сумму/ID, исходный PDF и копию; reload не повторяет успех. Пароль брать из собственного DEMO_PASSWORD, не из отчёта.

Для передачи результата собран и обновлён **только frontend** существующего `alfa-credit-demo` командой `FRONTEND_PORT=8080 docker compose -p alfa-credit-demo up --build --no-deps -d --wait --wait-timeout 180 frontend`, с сохранением существующего флага ИИ. Backend/основная БД не пересоздавались и не использовались для кредитных QA-сценариев. После обновления выполнены только read-only проверки HTTP frontend/health/docs/schema и состояния контейнеров. При уже открытой старой вкладке обновите страницу `http://localhost:8080`.

QA-контейнеры после проверок остановлены через `docker compose -p alfa-jury-qa-20261026 stop`. Их volume, копия jury_upgrade, images и локальные артефакты сохранены; `down -v`/удаление БД/пользовательских файлов не выполнялись. Основной `alfa-credit-demo` оставлен работающим: frontend/health/docs/schema — HTTP 200, фактическая схема 1.3.0/41 путь, web/db healthy.
