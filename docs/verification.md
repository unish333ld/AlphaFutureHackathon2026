# Проверка backend

Проверено 22.10.2026 на Python 3.14.2, Django 5.2.18, DRF 3.18.3, drf-spectacular 0.29.0 и отдельном PostgreSQL 18.6. Существующие базы пользователя не использовались. Миграции применены с пустого состояния, seeds повторно выполняются без дублирования.

| Проверка | Результат |
|---|---|
| Django `check` | 0 замечаний |
| `makemigrations --check --dry-run` | Изменений нет, модели соответствуют миграциям |
| `spectacular --validate --fail-on-warn` | Схема проходит валидацию, предупреждений/ошибок генератора нет |
| pytest | 26 passed; сценарии в `backend/tests/test_workflow.py` |
| Ruff lint/format | Все проверки прошли |
| pip check, чтение requirements.lock через pip dry-run | Конфликтов и ошибок формата нет |
| pip-audit по финальному requirements.lock | Известных уязвимостей не найдено; первоначальный DRF 3.16.1 заменён на 3.18.3 |
| HTTP на Gunicorn с DEBUG=false | Swagger, ReDoc, OpenAPI и health — 200; 4 локальных ресурса Swagger — 200 |
| Реальный HTTP-вход через HTML-форму | Сессия создана, редирект в Swagger, GET me и POST калькулятора с CSRF успешны |
| `docker compose config --quiet`, `sh -n backend/entrypoint.sh` | Конфигурация и shell-синтаксис корректны |

Аудит проведён по всем закреплённым Python-пакетам, включая транзитивные зависимости. Это проверка известных записей в базе уязвимостей, а не гарантия отсутствия дефектов. Исправляющий релиз выбран с учётом [официальных release notes DRF](https://www.django-rest-framework.org/community/release-notes/).

В pytest остаются предупреждения drf-spectacular об устаревшем приватном объекте typing `_UnionGenericAlias` в Python 3.14; это предупреждение зависимости о будущем Python 3.17. Проверки и генерация схемы проходят. Предупреждения не подавлялись.

Docker Engine на машине выключен: сборка образа и `docker compose up` здесь не выполнялись. Работа с PostgreSQL, миграции и HTTP проверены локально. ИИ и реальные банковские интеграции не входят в эту версию и не проверялись.

## Проверяемые инварианты из проектных навыков

| Правило | Факт реализации и доказательство |
|---|---|
| H01/H02/H03 | Синтетические seeds, чистые локальные адаптеры, основной путь без ключей/оплаты |
| P01/P02 | Чужие компании/заявки/история/предложения/договоры/выдачи скрыты; tests cross_company, company_member_without_submit_capability, sign_requires_permission |
| P03/P04 | Строгие входные сериализаторы, действия вместо PATCH статуса, версия и транзакционная блокировка; field_injection_and_stale_version |
| P05 | OneToOne, уникальный ключ, блокировка заявки; concurrent_disbursement с одинаковыми и разными ключами в независимых соединениях PostgreSQL |
| P06 | Неизменяемые ревизии/условия, snapshot/hash, сроки; old_offer, signing_deadline, product_snapshot, exact_hash |
| P07 | Decimal, месячные периоды, сохранение суммы основного долга и нулевого остатка; payment_schedule_conserves_principal |
| P08 | check.error хранится без rejected; technical_error_can_retry |
| P09/P10 | Django password hashing, секреты в игнорируемом .env, CSRF входа и изменений; csrf_login_rotation_authenticated_write_and_logout + живой HTTP |
| P16/P19 | История доступна в Admin только для чтения; submitted_revision_and_financial_history_are_immutable; lock, аудит и THIRD_PARTY_NOTICES |

Матрица H/P описывает конкурсные и инженерные требования. Применимость норм L к настоящему банковскому сервису и реальным персональным данным отдельно не исследовалась; юридическое соответствие production-системы не заявляется.
