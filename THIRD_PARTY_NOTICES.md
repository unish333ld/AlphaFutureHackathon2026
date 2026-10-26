# Сторонние компоненты

Прототип создан для хакатонного кейса; это не официальный банковский сервис. Синтетические данные, локальные моки и демонстрационная политика описаны в `docs/architecture.md`. Банковские API и реальные финансовые документы не включены. Необязательный помощник вызывает внешний или локальный OpenAI-совместимый endpoint; веса LLM в репозиторий не входят.

Версии Python-пакетов закреплены в `backend/requirements.lock`; дополнительные инструменты покрытия тестов — в `backend/requirements-test.lock`. Лицензии проверены по метаданным установленных дистрибутивов. Полные уведомления/тексты сохраняются в `*.dist-info/licenses`, `METADATA` и исходных пакетах, включая Docker-образ.

| Компонент | Лицензия |
|---|---|
| Python | PSF-2.0 |
| Django, asgiref, sqlparse | BSD-3-Clause |
| Django REST Framework | BSD |
| drf-spectacular, drf-spectacular-sidecar | BSD-3-Clause / BSD |
| Включённые sidecar Swagger UI / ReDoc | Apache-2.0 / MIT |
| PostgreSQL | PostgreSQL License |
| psycopg, psycopg-binary | LGPL-3.0-only; бинарная поставка также сохраняет уведомления включённых библиотек |
| Gunicorn, WhiteNoise | MIT |
| python-dotenv | BSD-3-Clause |
| attrs, inflection, iniconfig, jsonschema, jsonschema-specifications, pluggy, pytest, PyYAML, referencing, rpds-py, Ruff | MIT |
| packaging | Apache-2.0 OR BSD-2-Clause |
| Pygments | BSD-2-Clause |
| pytest-django | BSD-3-Clause |
| pytest-cov (только тестирование) | MIT |
| coverage.py (только тестирование) | Apache-2.0 |
| uritemplate | BSD-3-Clause OR Apache-2.0 |
| Базовые образы python и postgres | Содержат системные компоненты со своими лицензиями и уведомлениями |

Источники: [Django](https://www.djangoproject.com/), [DRF](https://github.com/encode/django-rest-framework), [drf-spectacular](https://github.com/tfranzel/drf-spectacular), [sidecar](https://github.com/tfranzel/drf-spectacular-sidecar), [PostgreSQL](https://www.postgresql.org/), [psycopg](https://www.psycopg.org/), [Gunicorn](https://gunicorn.org/), [WhiteNoise](https://whitenoise.readthedocs.io/), остальные пакеты — соответствующие PyPI-проекты из lock-файла.

Навыки в локальной игнорируемой папке `skills/` используются при разработке и исключены из Docker-контекста; их лицензии остаются в исходных репозиториях. Скоринг, seeds и адаптеры написаны для этого проекта. В runtime не включён код Repowise.

Публичные параметры [разового кредита Альфа-Банка](https://alfabank.ru/sme/profits/businesscredit/) используются как справочный ориентир с указанием источника/даты; HTML страницы, тарифный документ и макеты банка не копировались. Учебная ставка и ограничения отдельно раскрыты в [docs/product-research.md](docs/product-research.md). Это не официальная оферта или воспроизведение закрытой банковской модели.

## Генерация и проверка PDF

WeasyPrint 70.0, pydyf, tinycss2, cssselect2 и webencodings — BSD (точные тексты в дистрибутивах); tinyhtml5/Brotli/fontTools — MIT; CFFI — MIT-0; Pillow — MIT-CMU; pycparser — BSD-3-Clause; Zopfli — Apache-2.0. Pyphen — GPLv2+/LGPLv2+/MPL-1.1 (альтернативные лицензии); словари имеют отдельные уведомления. Уведомления не удаляются из установленных пакетов.

Pango — LGPL-2.1-or-later; HarfBuzz — MIT-style; DejaVu Serif — лицензия Bitstream Vera и условия DejaVu (добавленные глифы public domain). Системные тексты сохраняются в `/usr/share/doc/*/copyright` Docker-образа; шрифт встроен в PDF. Версии системных зависимостей закреплены в backend/Dockerfile. PDF не использует шрифты/CDN банка и не воспроизводит официальный бланк.

Инструменты QA: pypdf 6.12.2 — BSD-3-Clause; pypdfium2 5.14.0 — Apache-2.0/BSD-3-Clause с отдельными лицензиями PDFium/транзитивных компонентов в пакете. Эти инструменты не нужны runtime генерации. Версии — backend/requirements-test.lock. ГОСТ используется как ориентир оформления, текст стандарта не включён в репозиторий.

## Frontend-компоненты

Дизайн-система включена только в frontend. Версии зафиксированы в `frontend/package-lock.json`; исходные LICENSE/NOTICE сохраняются в npm-пакетах. Шрифты и изображения с внешних CDN не загружаются; используются системные шрифты. PNG из навыка — референсы, не runtime-ресурсы.

| Компонент | Лицензия по метаданным пакета |
|---|---|
| React, React DOM, React Router, TanStack Query | MIT |
| Alfa Core Components, config, stack-context, icons-logotype, icons-glyph | MIT |
| React Hook Form, resolvers, Zod | MIT |
| Vite, Vitest, Prettier, openapi-typescript | MIT |
| TypeScript, Playwright | Apache-2.0 |
| axe-core / @axe-core/playwright (тестирование) | MPL-2.0 |
| Nginx | BSD-2-Clause |

Список включает основные прямые зависимости; транзитивные лицензии не заменяются этой сводкой. Полный npm tree и тексты лицензий доступны в установленном `node_modules`. Это не разрешение на использование бренда банка вне хакатонного прототипа.

## Необязательные модели Савелия

Локальный резерв: [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [Apache-2.0](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/LICENSE). Квантование Ollama `qwen3:4b-instruct-2507-q4_K_M` (Q4_K_M), digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`. Лицензия загружается вместе с моделью; веса и их кэш не входят в репозиторий/Docker. Сам Ollama — [MIT](https://github.com/ollama/ollama/blob/main/LICENSE), установленная на Mac версия 0.40.11.

Приоритетный cloud-кандидат: [NVIDIA Nemotron 3 Super 120B A12B FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8), [NVIDIA Nemotron Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-nemotron-open-model-license/), OpenRouter slug `nvidia/nemotron-3-super-120b-a12b:free`. Условия допускают использование и требуют соблюдения лицензии/уведомлений при распространении; приложение использует API, веса не распространяет. Бесплатный endpoint имеет собственные [условия обработки данных](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free). Проверены каталог и лицензия 25.10.2026; авторизованный cloud-вызов пока не проверен. Передавать только синтетические данные.

Ранее рассматривался Qwen2.5-7B (Apache-2.0); он не установлен в текущем локальном профиле. Настройки и фактически выполненные проверки: [docs/assistant.md](docs/assistant.md). Repowise установлен только в игнорируемой `.deps/repowise-venv` для локального анализа; его зависимости не входят в backend-lock и Docker.
