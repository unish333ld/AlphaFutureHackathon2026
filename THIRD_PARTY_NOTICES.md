# Сторонние компоненты

Прототип создан для хакатонного кейса; это не официальный банковский сервис. Синтетические данные, локальные моки и демонстрационная политика описаны в `docs/architecture.md`. Банковские API, реальные финансовые документы и дизайн-система в текущий backend не включены. ИИ-модель не входит в Docker-образ и запускается отдельно только при включении помощника.

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

Необязательный кандидат для демонстрации Савелия — `Qwen/Qwen2.5-7B-Instruct` с открытыми весами (Apache-2.0), например квантизация `qwen2.5:7b-instruct-q4_0` для Ollama. Перед финальной поставкой нужно закрепить конкретный тег/хеш модели, источник квантизации и воспроизвести запуск на целевой машине. Ни веса, ни сервер Ollama в этот репозиторий не включены. Источники: [карточка модели Qwen](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct), [каталог Ollama](https://ollama.com/library/qwen2.5:7b-instruct-q4_0).

Пример основного внешнего маршрута — открытовесная [Gemma 4 26B A4B IT](https://huggingface.co/google/gemma-4-26B-A4B-it) (Apache-2.0) через бесплатный `google/gemma-4-26b-a4b-it:free` в OpenRouter. Пример облачного резерва — открытовесная [Nemotron 3.5 Lightning 30B A3B](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) (OpenMDW-1.1) через `nvidia/nemotron-3.5-lightning:free`. Веса не входят в проект; тарифы, доступность и правила обработки запросов зависят от endpoint. [Бесплатный endpoint NVIDIA](https://openrouter.ai/nvidia/nemotron-3.5-lightning:free) уведомляет о записи запросов, поэтому ему передаются только синтетические демо-данные. Перед сдачей следует повторно проверить выбранные ID, лицензии и условия endpoint.

Источники: [Django](https://www.djangoproject.com/), [DRF](https://github.com/encode/django-rest-framework), [drf-spectacular](https://github.com/tfranzel/drf-spectacular), [sidecar](https://github.com/tfranzel/drf-spectacular-sidecar), [PostgreSQL](https://www.postgresql.org/), [psycopg](https://www.psycopg.org/), [Gunicorn](https://gunicorn.org/), [WhiteNoise](https://whitenoise.readthedocs.io/), остальные пакеты — соответствующие PyPI-проекты из lock-файла.

Навыки в локальной игнорируемой папке `skills/` используются при разработке и исключены из Docker-контекста; их лицензии остаются в исходных репозиториях. Скоринг, seeds и адаптеры написаны для этого проекта. В runtime не включён код Repowise.
