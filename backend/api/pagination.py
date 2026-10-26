from rest_framework.pagination import PageNumberPagination


class TenItemPagination(PageNumberPagination):
    page_size = 10
    invalid_page_message = "Страница не найдена."
